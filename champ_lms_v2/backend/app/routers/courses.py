"""
Course canvas router.

A canvas course is a Module with layout "canvas": an ordered list of items
(videos, AI checkpoint quizzes, tests, notes pages) grouped into sections. Each
item points at a document in its own collection; the Module holds only the
running order. See models/module.py.

Admin flow:   build the course on one canvas -> choose who can watch and who
              can ask for its tests -> approve each test request with a number
              of attempts.
Learner flow: open the course (a series player when it is only videos, the full
              course player otherwise) -> watch, read, take checkpoint quizzes
              -> ask to sit the test -> sit it through the existing exam flow.

Bunny is used for video only. Transcripts are written by the AI from audio the
admin's browser extracts during upload, and notes PDFs are stored in MongoDB.
"""
from __future__ import annotations

import base64
import logging
import re
from datetime import datetime, timezone
from typing import Annotated

import redis.asyncio as aioredis
from beanie.operators import In
from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile,
)
from pydantic import BaseModel, Field

from app.core.auth import get_current_user, require_admin
from app.core.redis import get_redis
from app.models.assessment import Assessment, AssessmentAttempt
from app.models.content_access import ContentAccessRule
from app.models.episode import Episode
from app.models.module import (
    ACCESS_CLOSED, ITEM_KINDS, ITEM_NOTES, ITEM_QUIZ, ITEM_TEST, ITEM_VIDEO,
    LAYOUT_CANVAS, CourseItem, CourseSection, Module,
)
from app.models.note import MAX_ATTACHMENT_BYTES, CourseNote, NoteAttachment
from app.models.progress import WatchProgress
from app.models.test_request import TestRequest
from app.models.test_series import AttemptGrant, TestAttempt, TestQuestion, TestSeries
from app.models.user import User
from app.services import content_access
from app.services.ai_service import AIServiceError, ai_service
from app.services.bunny_storage import bunny_storage
from app.services.clips import (
    MIN_CLIP_SECONDS, clip_bounds, is_clipped, merge_clip_segments,
    refresh_transcript_text, segments_in_clip, source_length,
)
from app.services.purge_service import (
    PurgeError, purge_course_test, purge_episode, purge_note,
)
from app.services.test_attempts import attempt_status

logger = logging.getLogger(__name__)

router = APIRouter(tags=["courses"])

# Audio clips arrive from the browser as 16 kHz mono WAV, about 32 KB a second.
# Two minutes is under 4 MB; the cap leaves room without inviting whole files.
MAX_AUDIO_CHUNK_BYTES = 12 * 1024 * 1024
MAX_QUIZ_QUESTIONS = 20


# ==========================================================================
# Schemas
# ==========================================================================
class CourseCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    category: str | None = None


class CourseUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = None
    is_published: bool | None = None


class SectionIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=200)


class OrderIn(BaseModel):
    id: str
    section_id: str


class StructureIn(BaseModel):
    """The whole running order. Every existing item must appear exactly once."""
    sections: list[SectionIn]
    order: list[OrderIn]


class ItemCreateIn(BaseModel):
    kind: str
    section_id: str
    # Position within the section; omit to append.
    index: int | None = None
    title: str | None = Field(default=None, max_length=200)
    # Quizzes only: which episodes to write from. Omit to use the videos just
    # above the quiz in its section.
    source_episode_ids: list[str] | None = None
    # Videos only: the name of the file being uploaded.
    source_filename: str | None = Field(default=None, max_length=300)


class SegmentIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=2000)


class TranscriptIn(BaseModel):
    segments: list[SegmentIn]
    source: str = "manual"  # auto | manual
    # "source": times count from the start of the whole video (an automatic
    # run over the uploaded file). "clip": from the start of this episode's
    # part (an admin's edit). Defaults to source for auto, clip for manual.
    timebase: str | None = None


class ClipIn(BaseModel):
    """Where a video's kept part starts and ends, and where to split it, in source seconds."""
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    split_at: list[float] = Field(default_factory=list, max_length=20)


class TranscriptStatusIn(BaseModel):
    status: str  # processing | failed


class NotesIn(BaseModel):
    notes: str = Field(max_length=20000)


class QuizQuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    options: list[str]
    correct_index: int
    explanation: str | None = None
    source_episode_id: str | None = None


class QuizUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    source_episode_ids: list[str] | None = None
    question_count: int | None = Field(default=None, ge=1, le=MAX_QUIZ_QUESTIONS)
    difficulty: str | None = None
    pass_threshold: int | None = Field(default=None, ge=1, le=100)
    must_pass: bool | None = None
    questions: list[QuizQuestionIn] | None = None


class CourseTestUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    pass_threshold: int | None = Field(default=None, ge=1, le=100)
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    proctoring_enabled: bool | None = None
    shuffle_questions: bool | None = None
    attempts_per_approval: int | None = Field(default=None, ge=1, le=10)
    unlock_rule: str | None = None


class GenerateTestIn(BaseModel):
    count: int = Field(default=15, ge=3, le=50)


class NoteUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=50000)


class ApproveIn(BaseModel):
    attempts: int = Field(default=1, ge=1, le=10)
    note: str | None = Field(default=None, max_length=500)


class DenyIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# ==========================================================================
# Loading and shaping
# ==========================================================================
class _Refs:
    """Every backing document a course's items point at, loaded in 4 queries."""

    def __init__(self) -> None:
        self.episodes: dict[str, Episode] = {}
        self.quizzes: dict[str, Assessment] = {}
        self.tests: dict[str, TestSeries] = {}
        self.notes: dict[str, CourseNote] = {}

    def doc(self, item: CourseItem):
        return {
            ITEM_VIDEO: self.episodes, ITEM_QUIZ: self.quizzes,
            ITEM_TEST: self.tests, ITEM_NOTES: self.notes,
        }[item.kind].get(item.ref_id)


async def _load_refs(module: Module) -> _Refs:
    refs = _Refs()
    ids: dict[str, list[str]] = {k: [] for k in ITEM_KINDS}
    for it in module.items:
        ids.setdefault(it.kind, []).append(it.ref_id)
    if ids[ITEM_VIDEO]:
        refs.episodes = {e.id: e for e in await Episode.find(In(Episode.id, ids[ITEM_VIDEO])).to_list()}
    if ids[ITEM_QUIZ]:
        refs.quizzes = {a.id: a for a in await Assessment.find(In(Assessment.id, ids[ITEM_QUIZ])).to_list()}
    if ids[ITEM_TEST]:
        refs.tests = {t.id: t for t in await TestSeries.find(In(TestSeries.id, ids[ITEM_TEST])).to_list()}
    if ids[ITEM_NOTES]:
        refs.notes = {n.id: n for n in await CourseNote.find(In(CourseNote.id, ids[ITEM_NOTES])).to_list()}
    return refs


def _live_items(module: Module, refs: _Refs) -> list[CourseItem]:
    """
    Items whose backing document still exists.

    An episode can be deleted from the older content manager without the
    canvas knowing, so a dangling item is skipped rather than breaking the
    whole course.
    """
    return [it for it in module.items if refs.doc(it) is not None]


def _course_format(kinds: list[str]) -> str:
    """series when the course is only videos; course once anything else is added."""
    if not kinds:
        return "empty"
    return "series" if all(k == ITEM_VIDEO for k in kinds) else "course"


def _episode_numbers(items: list[CourseItem]) -> dict[str, int]:
    """Episode id -> its number among the course's videos, in running order."""
    out: dict[str, int] = {}
    for it in items:
        if it.kind == ITEM_VIDEO:
            out[it.ref_id] = len(out) + 1
    return out


def _thumb(ep: Episode) -> str | None:
    if ep.thumbnail_url:
        return ep.thumbnail_url
    if ep.thumbnail_bunny_path:
        return bunny_storage.thumbnail_url(ep.thumbnail_bunny_path)
    return None


def _utc(dt: datetime | None) -> datetime | None:
    """
    Mongo hands datetimes back without a timezone. They are UTC; say so, or a
    browser reads "10:00" as local time and a request made a minute ago in
    India shows as five and a half hours old.
    """
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _join_segments(segments: list[dict]) -> str:
    return " ".join(s["text"] for s in segments if s.get("text")).strip()


async def _get_course_or_404(course_id: str) -> Module:
    module = await Module.get(course_id)
    if not module or module.layout != LAYOUT_CANVAS:
        raise HTTPException(status_code=404, detail="Course not found")
    return module


def _find_item(module: Module, item_id: str) -> CourseItem:
    for it in module.items:
        if it.id == item_id:
            return it
    raise HTTPException(status_code=404, detail="That item is not on this course")


async def _course_for_ref(kind: str, ref_id: str) -> Module | None:
    """The canvas course an episode, quiz, test or note sits on, if any."""
    return await Module.find_one({"items": {"$elemMatch": {"kind": kind, "ref_id": ref_id}}})


async def _renumber_episodes(module: Module, refs: _Refs | None = None) -> None:
    """
    Keep Episode.sequence_order matching the canvas order.

    The classic player, the feed and progress all still read sequence_order,
    so it follows the canvas rather than drifting from it.
    """
    refs = refs or await _load_refs(module)
    position = 0
    for it in module.items:
        if it.kind != ITEM_VIDEO:
            continue
        ep = refs.episodes.get(it.ref_id)
        if not ep:
            continue
        position += 1
        if ep.sequence_order != position:
            ep.sequence_order = position
            await ep.save()
    if module.total_episodes != position:
        module.total_episodes = position
        await module.save()


async def _people_count(content) -> int:
    """How many active, non-staff people can open this module or test now."""
    kind = "test" if isinstance(content, TestSeries) else "module"
    users = await User.find(User.is_active == True).to_list()  # noqa: E712
    rules = await ContentAccessRule.find(
        ContentAccessRule.module_id == content.id,
        ContentAccessRule.content_kind == kind,
    ).to_list()
    by_user = {r.user_id: r.access for r in rules}
    return sum(
        1 for u in users
        if not u.is_staff and content_access.can_access(
            content, u, {content.id: by_user[u.id]} if u.id in by_user else {}
        )
    )


def _clean_questions(raw: list, source_ids: list[str]) -> list[dict]:
    """
    Keep only well-formed questions from the model's answer.

    The model is told the shape, but a question with three options or an
    out-of-range answer must never reach a learner as if it were scorable.
    """
    out = []
    for q in raw if isinstance(raw, list) else []:
        if not isinstance(q, dict):
            continue
        text = str(q.get("question") or "").strip()
        options = [str(o).strip() for o in (q.get("options") or []) if str(o).strip()]
        try:
            ci = int(q.get("correct_index"))
        except (TypeError, ValueError):
            continue
        if not text or len(options) < 2 or not (0 <= ci < len(options)):
            continue
        try:
            ep_no = int(q.get("episode") or 0)
        except (TypeError, ValueError):
            ep_no = 0
        out.append({
            "question": text,
            "options": options,
            "correct_index": ci,
            "explanation": (str(q.get("explanation") or "").strip() or None),
            "source_episode_id": source_ids[ep_no - 1] if 1 <= ep_no <= len(source_ids) else None,
        })
    return out


# --------------------------------------------------------------------------
# Admin views
# --------------------------------------------------------------------------
def _part_numbers(items: list[CourseItem], refs: _Refs) -> dict[str, tuple[int, int]]:
    """
    Episode id -> (part, of) for videos split into several episodes.

    Parts are the episodes on the course playing the same Bunny video, counted
    in canvas order. A video that was never split has no entry.
    """
    by_video: dict[str, list[str]] = {}
    for it in items:
        if it.kind != ITEM_VIDEO:
            continue
        ep = refs.episodes.get(it.ref_id)
        if ep and ep.bunny_video_guid:
            by_video.setdefault(ep.bunny_video_guid, []).append(ep.id)
    return {
        ep_id: (n, len(ids))
        for ids in by_video.values() if len(ids) > 1
        for n, ep_id in enumerate(ids, start=1)
    }


async def _admin_item(
    it: CourseItem, refs: _Refs, numbers: dict[str, int],
    parts: dict[str, tuple[int, int]] | None = None,
) -> dict:
    doc = refs.doc(it)
    base = {"id": it.id, "kind": it.kind, "ref_id": it.ref_id, "section_id": it.section_id}
    if it.kind == ITEM_VIDEO:
        ep: Episode = doc
        return {
            **base,
            "title": ep.title,
            "description": ep.description,
            "episode_number": numbers.get(ep.id),
            "status": ep.status,
            "duration_seconds": ep.duration_seconds,
            "thumbnail_url": _thumb(ep),
            "has_remote_video": bool(ep.bunny_video_guid or ep.bunny_video_id),
            "source_filename": ep.source_filename,
            # Trim and split, in seconds of the whole Bunny video.
            "clip_start": ep.clip_start,
            "clip_end": ep.clip_end,
            "source_duration_seconds": source_length(ep),
            "part": list((parts or {}).get(ep.id, ())) or None,
            "transcript_status": ep.transcript_status or ("ready" if ep.transcript_segments else None),
            "transcript_source": ep.transcript_source,
            # Clip time: what the admin edits is this part only, from 0.
            "transcript_segments": segments_in_clip(ep),
            "notes": ep.notes,
            "notes_source": ep.notes_source,
        }
    if it.kind == ITEM_QUIZ:
        q: Assessment = doc
        return {
            **base,
            "title": q.title or "Checkpoint quiz",
            "source_episode_ids": q.source_episode_ids,
            "question_count": q.question_count,
            "difficulty": q.difficulty,
            "pass_threshold": q.pass_threshold,
            "must_pass": q.must_pass,
            "questions": q.questions or [],
        }
    if it.kind == ITEM_TEST:
        t: TestSeries = doc
        pending = await TestRequest.find(
            TestRequest.test_id == t.id, TestRequest.status == TestRequest.PENDING
        ).count()
        return {
            **base,
            "title": t.title,
            "description": t.description,
            "question_count": len(t.questions),
            "unscorable_count": t.unscorable_count,
            "is_ready": t.is_ready,
            "is_published": t.is_published,
            "pass_threshold": t.pass_threshold,
            "duration_minutes": t.duration_minutes,
            "proctoring_enabled": t.proctoring_enabled,
            "shuffle_questions": t.shuffle_questions,
            "attempts_per_approval": t.attempts_per_approval,
            "unlock_rule": t.unlock_rule,
            "source_filename": t.source_filename,
            "source_parser": t.source_parser,
            "pending_requests": pending,
        }
    n: CourseNote = doc
    return {
        **base,
        "title": n.title,
        "body": n.body,
        "source": n.source,
        "attachment_name": n.attachment_name,
        "attachment_size": n.attachment_size,
    }


async def _admin_course(module: Module) -> dict:
    refs = await _load_refs(module)
    items = _live_items(module, refs)
    numbers = _episode_numbers(items)
    parts = _part_numbers(items, refs)
    return {
        "id": module.id,
        "title": module.title,
        "description": module.description,
        "category": module.category,
        "is_published": module.is_published,
        "access_mode": module.access_mode,
        "format": _course_format([i.kind for i in items]),
        "sections": [s.model_dump() for s in module.sections],
        "items": [await _admin_item(i, refs, numbers, parts) for i in items],
        "can_watch_count": await _people_count(module),
        "created_at": _utc(module.created_at),
    }


# ==========================================================================
# ADMIN — courses
# ==========================================================================
@router.get("/admin/courses")
async def list_courses(admin: Annotated[User, Depends(require_admin)]):
    """Every canvas course, newest first, with what an admin needs to pick one."""
    modules = await Module.find(Module.layout == LAYOUT_CANVAS).sort(-Module.created_at).to_list()
    out = []
    for m in modules:
        refs = await _load_refs(m)
        items = _live_items(m, refs)
        kinds = [i.kind for i in items]
        runtime = sum(
            (refs.episodes[i.ref_id].duration_seconds or 0)
            for i in items if i.kind == ITEM_VIDEO
        )
        test_ids = [i.ref_id for i in items if i.kind == ITEM_TEST]
        pending = await TestRequest.find(
            In(TestRequest.test_id, test_ids), TestRequest.status == TestRequest.PENDING
        ).count() if test_ids else 0
        first_video = next((refs.episodes[i.ref_id] for i in items if i.kind == ITEM_VIDEO), None)
        out.append({
            "id": m.id,
            "title": m.title,
            "category": m.category,
            "is_published": m.is_published,
            "format": _course_format(kinds),
            "counts": {k: kinds.count(k) for k in ITEM_KINDS},
            "runtime_seconds": runtime,
            "can_watch_count": await _people_count(m),
            "pending_requests": pending,
            "thumbnail_url": _thumb(first_video) if first_video else None,
            "created_at": _utc(m.created_at),
        })
    return out


@router.post("/admin/courses", status_code=201)
async def create_course(body: CourseCreateIn, admin: Annotated[User, Depends(require_admin)]):
    """A new, empty, closed course with one section."""
    module = Module(
        title=body.title.strip(),
        description=body.description,
        category=body.category,
        created_by=admin.id,
        layout=LAYOUT_CANVAS,
        access_mode=ACCESS_CLOSED,
        sections=[CourseSection(title="Section 1")],
        items=[],
    )
    await module.insert()
    return await _admin_course(module)


@router.get("/admin/courses/{course_id}")
async def get_course_admin(course_id: str, admin: Annotated[User, Depends(require_admin)]):
    return await _admin_course(await _get_course_or_404(course_id))


@router.patch("/admin/courses/{course_id}")
async def update_course(
    course_id: str, body: CourseUpdateIn, admin: Annotated[User, Depends(require_admin)],
):
    """
    Edit course details, or publish/unpublish.

    Publishing also publishes every test on the course that is ready. A test
    with unanswered questions stays unpublished and is named in `warnings`, so
    the admin knows it is not yet sittable instead of assuming it is.
    """
    module = await _get_course_or_404(course_id)
    data = body.model_dump(exclude_unset=True)
    warnings: list[str] = []
    for field in ("title", "description", "category"):
        if field in data:
            setattr(module, field, data[field].strip() if isinstance(data[field], str) else data[field])
    if data.get("is_published") is not None:
        module.is_published = data["is_published"]
        if module.is_published:
            refs = await _load_refs(module)
            for t in refs.tests.values():
                if t.is_ready and not t.is_published:
                    t.is_published = True
                    await t.save()
                elif not t.is_ready:
                    warnings.append(
                        f"“{t.title}” is not published yet: "
                        + ("it has no questions." if not t.questions
                           else f"{t.unscorable_count} question(s) have no correct answer.")
                    )
    await module.save()
    return {**await _admin_course(module), "warnings": warnings}


@router.put("/admin/courses/{course_id}/structure")
async def set_structure(
    course_id: str, body: StructureIn, admin: Annotated[User, Depends(require_admin)],
):
    """
    Save sections and the running order in one go: reorder, move between
    sections, add, rename or drop sections.

    Items are never created or deleted here, so the order must list every
    existing item exactly once; a stale client cannot silently drop one.
    """
    module = await _get_course_or_404(course_id)
    section_ids = [s.id for s in body.sections]
    if not section_ids:
        raise HTTPException(status_code=422, detail="A course needs at least one section")
    if len(set(section_ids)) != len(section_ids):
        raise HTTPException(status_code=422, detail="Two sections share an id")

    by_id = {it.id: it for it in module.items}
    ordered_ids = [o.id for o in body.order]
    if len(set(ordered_ids)) != len(ordered_ids) or set(ordered_ids) != set(by_id):
        raise HTTPException(
            status_code=409,
            detail="The course changed since you loaded it. Reload and try again.",
        )
    new_items = []
    for o in body.order:
        if o.section_id not in section_ids:
            raise HTTPException(status_code=422, detail="An item points at a section that is not in the list")
        it = by_id[o.id]
        it.section_id = o.section_id
        new_items.append(it)

    module.sections = [CourseSection(id=s.id, title=s.title.strip()) for s in body.sections]
    module.items = new_items
    await module.save()
    await _renumber_episodes(module)
    return await _admin_course(module)


def _insert_index(module: Module, section_id: str, index: int | None) -> int:
    """Where in the flat item list the new item goes, given a section position."""
    positions = [i for i, it in enumerate(module.items) if it.section_id == section_id]
    if not positions:
        # Empty section: after the last item of any earlier section.
        order = [s.id for s in module.sections]
        before = set(order[: order.index(section_id)])
        last = [i for i, it in enumerate(module.items) if it.section_id in before]
        return (last[-1] + 1) if last else 0
    if index is None or index >= len(positions):
        return positions[-1] + 1
    return positions[max(0, index)]


@router.post("/admin/courses/{course_id}/items", status_code=201)
async def add_item(
    course_id: str, body: ItemCreateIn, admin: Annotated[User, Depends(require_admin)],
):
    """
    Put a new video, quiz, test or notes page on the canvas.

    A video item is created empty; the browser then uploads the file through
    the existing /admin/episodes/{id}/prepare-upload flow.
    """
    module = await _get_course_or_404(course_id)
    if body.kind not in ITEM_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of: {', '.join(ITEM_KINDS)}")
    if body.section_id not in {s.id for s in module.sections}:
        raise HTTPException(status_code=422, detail="That section is not on this course")

    at = _insert_index(module, body.section_id, body.index)
    title = (body.title or "").strip()

    if body.kind == ITEM_VIDEO:
        doc = Episode(
            module_id=module.id,
            title=title or "Untitled episode",
            sequence_order=0,
            status="pending",
            source_filename=body.source_filename,
        )
        await doc.insert()
    elif body.kind == ITEM_QUIZ:
        if body.source_episode_ids is not None:
            sources = [i for i in body.source_episode_ids
                       if any(it.kind == ITEM_VIDEO and it.ref_id == i for it in module.items)]
        else:
            # The videos just above the quiz in its section, back to the
            # previous quiz: what "a quiz on what you just watched" means.
            sources = []
            for it in reversed(module.items[:at]):
                if it.section_id != body.section_id or it.kind == ITEM_QUIZ:
                    break
                if it.kind == ITEM_VIDEO:
                    sources.insert(0, it.ref_id)
        section = next(s for s in module.sections if s.id == body.section_id)
        doc = Assessment(
            module_id=module.id,
            kind="checkpoint",
            title=title or f"Checkpoint: {section.title}",
            questions=[],
            source_episode_ids=sources,
            question_count=min(MAX_QUIZ_QUESTIONS, max(3, 2 * len(sources)) if sources else 5),
        )
        await doc.insert()
    elif body.kind == ITEM_TEST:
        doc = TestSeries(
            title=title or "Course test",
            category=module.category,
            module_id=module.id,
            access_mode=ACCESS_CLOSED,
            requires_approval=True,
            proctoring_enabled=True,
            duration_minutes=30,
            source_parser="manual",
            created_by=admin.id,
        )
        await doc.insert()
    else:
        doc = CourseNote(module_id=module.id, title=title or "Notes")
        await doc.insert()

    item = CourseItem(kind=body.kind, ref_id=doc.id, section_id=body.section_id)
    module.items.insert(at, item)
    await module.save()
    if body.kind == ITEM_VIDEO:
        await _renumber_episodes(module)
    refs = await _load_refs(module)
    return await _admin_item(item, refs, _episode_numbers(_live_items(module, refs)))


@router.delete("/admin/courses/{course_id}/items/{item_id}")
async def delete_item(
    course_id: str,
    item_id: str,
    admin: Annotated[User, Depends(require_admin)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    """
    Remove an item and permanently delete what it holds: the video on Bunny,
    a quiz and its attempts, a test with its attempts and requests, or a notes
    page and its PDF.
    """
    module = await _get_course_or_404(course_id)
    item = _find_item(module, item_id)

    if item.kind == ITEM_VIDEO:
        ep = await Episode.get(item.ref_id)
        if ep:
            try:
                await purge_episode(ep, redis=redis)
            except PurgeError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
        # A quiz written from this episode no longer counts it as a source.
        for q in await Assessment.find(
            Assessment.module_id == module.id, Assessment.kind == "checkpoint"
        ).to_list():
            if item.ref_id in q.source_episode_ids:
                q.source_episode_ids = [s for s in q.source_episode_ids if s != item.ref_id]
                await q.save()
    elif item.kind == ITEM_QUIZ:
        q = await Assessment.get(item.ref_id)
        if q:
            await AssessmentAttempt.find(AssessmentAttempt.assessment_id == q.id).delete()
            await q.delete()
    elif item.kind == ITEM_TEST:
        t = await TestSeries.get(item.ref_id)
        if t:
            await purge_course_test(t)
    else:
        n = await CourseNote.get(item.ref_id)
        if n:
            await purge_note(n)

    module = await _get_course_or_404(course_id)  # purge_episode may have saved it
    module.items = [it for it in module.items if it.id != item_id]
    await module.save()
    await _renumber_episodes(module)
    if item.kind == ITEM_VIDEO:
        await _retitle_parts(module)  # the parts left of a split video renumber
    return await _admin_course(await _get_course_or_404(course_id))


# ==========================================================================
# ADMIN — trim and split
# ==========================================================================
_PART_TITLE = re.compile(r"^(.*?)\s*\(part \d+\)$")


def _set_range(ep: Episode, start: float, end: float, length: float) -> None:
    """Point an episode at [start, end] of its video and keep what follows from it in step."""
    ep.clip_start = start if start > 0 else None
    ep.clip_end = end if end < length else None
    ep.duration_seconds = int(round(end - start))
    refresh_transcript_text(ep)


async def _retitle_parts(module: Module) -> None:
    """
    Keep "(part n)" titles in canvas order.

    Only titles that still read "<name> (part n)" are renumbered, so a part an
    admin renamed keeps its name. A video that is whole again loses the suffix.
    """
    refs = await _load_refs(module)
    groups: dict[str, list[Episode]] = {}
    for it in module.items:
        ep = refs.episodes.get(it.ref_id) if it.kind == ITEM_VIDEO else None
        if ep and ep.bunny_video_guid:
            groups.setdefault(ep.bunny_video_guid, []).append(ep)
    for eps in groups.values():
        for n, ep in enumerate(eps, start=1):
            m = _PART_TITLE.match(ep.title)
            if not m:
                continue
            title = m.group(1) if len(eps) == 1 else f"{m.group(1)} (part {n})"
            if title != ep.title:
                ep.title = title
                await ep.save()


async def _get_course_video(module: Module, item_id: str) -> tuple[CourseItem, Episode]:
    item = _find_item(module, item_id)
    if item.kind != ITEM_VIDEO:
        raise HTTPException(status_code=422, detail="Only videos can be trimmed or split")
    return item, await _get_episode_or_404(item.ref_id)


@router.put("/admin/courses/{course_id}/items/{item_id}/clip")
async def set_clip(
    course_id: str,
    item_id: str,
    body: ClipIn,
    background: BackgroundTasks,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Trim a video, and optionally split it into several episodes.

    `start` and `end` are where the part to keep begins and ends, in seconds of
    the whole Bunny video; `split_at` are points inside that range where it is
    cut into more episodes, so a quiz or test can sit between them. The first
    part stays this episode, so its progress and place on the canvas carry
    over; each further part becomes a new episode right after it, playing the
    same Bunny video. Nothing on Bunny changes, so all of it can be moved or
    undone later (see join-next).
    """
    module = await _get_course_or_404(course_id)
    item, ep = await _get_course_video(module, item_id)
    length = source_length(ep)
    if ep.status != "ready" or not length or not ep.bunny_video_guid:
        raise HTTPException(
            status_code=409,
            detail="The video can be trimmed or split once it has finished processing.",
        )
    start, end = round(body.start, 2), round(min(body.end, length), 2)
    cuts = sorted({round(t, 2) for t in body.split_at})
    if any(not (start < t < end) for t in cuts):
        raise HTTPException(status_code=422, detail="Split points must fall inside the part you keep.")
    points = [start, *cuts, end]
    if any(b - a < MIN_CLIP_SECONDS for a, b in zip(points, points[1:])):
        raise HTTPException(
            status_code=422, detail=f"Each part needs to be at least {MIN_CLIP_SECONDS} seconds long.",
        )
    ranges = list(zip(points, points[1:]))

    ep.source_duration_seconds = int(length)
    _set_range(ep, *ranges[0], length)
    base = (_PART_TITLE.match(ep.title) or re.match(r"^(.*)$", ep.title)).group(1)
    if len(ranges) > 1 and not _PART_TITLE.match(ep.title):
        ep.title = f"{base} (part 1)"
    await ep.save()

    at = module.items.index(item) + 1
    new_parts: list[Episode] = []
    for n, (a, b) in enumerate(ranges[1:], start=2):
        part = Episode(
            module_id=module.id,
            title=f"{base} (part {n})",
            description=ep.description,
            sequence_order=0,
            status=ep.status,
            bunny_video_guid=ep.bunny_video_guid,
            bunny_video_id=ep.bunny_video_id,
            thumbnail_url=ep.thumbnail_url,
            source_filename=ep.source_filename,
            source_duration_seconds=ep.source_duration_seconds,
            # The whole video's transcript; each part shows only its own lines.
            transcript_segments=list(ep.transcript_segments or []) or None,
            transcript_source=ep.transcript_source,
            transcript_status=ep.transcript_status,
        )
        _set_range(part, a, b, length)
        await part.insert()
        module.items.insert(at, CourseItem(kind=ITEM_VIDEO, ref_id=part.id, section_id=item.section_id))
        at += 1
        new_parts.append(part)
    await module.save()

    # A quiz written from the whole video now covers all of its parts.
    if new_parts:
        for q in await Assessment.find(
            Assessment.module_id == module.id, Assessment.kind == "checkpoint"
        ).to_list():
            if ep.id in q.source_episode_ids:
                i = q.source_episode_ids.index(ep.id) + 1
                q.source_episode_ids[i:i] = [p.id for p in new_parts]
                await q.save()

    await _renumber_episodes(module)
    await _retitle_parts(module)
    # Each part's notes follow its own stretch of the transcript.
    for target in [ep, *new_parts]:
        if target.transcript and target.notes_source != "manual":
            background.add_task(_draft_episode_notes, target.id)
    return await _admin_course(await _get_course_or_404(course_id))


@router.post("/admin/courses/{course_id}/items/{item_id}/join-next")
async def join_next(
    course_id: str,
    item_id: str,
    background: BackgroundTasks,
    admin: Annotated[User, Depends(require_admin)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    """
    Undo a split: join this part with the part right after it.

    Only neighbouring parts of the same video join. The later part's episode is
    removed (with its progress); the Bunny video stays, since this part still
    plays it. Lines an admin edited in the later part's transcript are kept.
    """
    module = await _get_course_or_404(course_id)
    item, ep = await _get_course_video(module, item_id)
    idx = module.items.index(item)
    nxt = module.items[idx + 1] if idx + 1 < len(module.items) else None
    other = await Episode.get(nxt.ref_id) if nxt and nxt.kind == ITEM_VIDEO else None
    length = source_length(ep)
    if (
        not other or not ep.bunny_video_guid or other.bunny_video_guid != ep.bunny_video_guid
        or not length or abs((clip_bounds(ep)[1] or length) - clip_bounds(other)[0]) > 0.5
    ):
        raise HTTPException(
            status_code=409, detail="Only a part and the part right after it, from the same video, can be joined.",
        )

    b_start, b_end = clip_bounds(other)
    b_end = b_end if b_end is not None else length
    ep.transcript_segments = sorted(
        [s for s in (ep.transcript_segments or []) if s["start"] < b_start or s["start"] >= b_end]
        + [s for s in (other.transcript_segments or []) if b_start <= s["start"] < b_end],
        key=lambda s: s["start"],
    ) or None
    if other.transcript_source == "manual":
        ep.transcript_source = "manual"
    _set_range(ep, clip_bounds(ep)[0], b_end, length)
    await ep.save()

    for q in await Assessment.find(
        Assessment.module_id == module.id, Assessment.kind == "checkpoint"
    ).to_list():
        if other.id in q.source_episode_ids:
            q.source_episode_ids = list(dict.fromkeys(
                ep.id if s == other.id else s for s in q.source_episode_ids
            ))
            await q.save()

    try:
        # Keeps the Bunny video: this part still plays it (see purge_service).
        await purge_episode(other, redis=redis)
    except PurgeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    module = await _get_course_or_404(course_id)
    module.items = [it for it in module.items if it.id != nxt.id]
    await module.save()
    await _renumber_episodes(module)
    await _retitle_parts(module)
    if ep.transcript and ep.notes_source != "manual":
        background.add_task(_draft_episode_notes, ep.id)
    return await _admin_course(await _get_course_or_404(course_id))


# ==========================================================================
# ADMIN — transcripts and episode notes
# ==========================================================================
async def _get_episode_or_404(episode_id: str) -> Episode:
    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    return ep


async def _draft_episode_notes(episode_id: str) -> None:
    """Background: draft notes from a fresh transcript, unless an admin wrote them."""
    ep = await Episode.get(episode_id)
    if not ep or not ep.transcript or ep.notes_source == "manual" or not ai_service.enabled:
        return
    try:
        ep.notes = await ai_service.episode_notes(ep.title, ep.transcript)
        ep.notes_source = "ai"
        await ep.save()
    except AIServiceError as exc:
        logger.warning("Could not draft notes for episode %s: %s", episode_id, exc)


@router.post("/admin/episodes/{episode_id}/transcribe-chunk")
async def transcribe_chunk(
    episode_id: str,
    admin: Annotated[User, Depends(require_admin)],
    audio: UploadFile = File(...),
    offset_seconds: float = Form(0.0),
    clip_seconds: float | None = Form(None),
):
    """
    Timed transcript lines for one short audio clip of an episode.

    The admin's browser extracts the audio while the video uploads to Bunny and
    sends it here clip by clip. Nothing is saved: the browser collects every
    clip's lines and saves the whole transcript with PUT .../transcript, so a
    half-finished run never leaves a partial transcript behind.
    """
    await _get_episode_or_404(episode_id)
    if not ai_service.enabled:
        raise HTTPException(
            status_code=503,
            detail="Automatic transcripts need OPENROUTER_API_KEY. Add the transcript by hand instead.",
        )
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=422, detail="The audio clip is empty")
    if len(data) > MAX_AUDIO_CHUNK_BYTES:
        raise HTTPException(status_code=413, detail="Audio clip too large; send shorter clips")
    try:
        segments = await ai_service.transcribe_audio(
            base64.b64encode(data).decode("ascii"),
            max(0.0, offset_seconds),
            clip_seconds if clip_seconds and clip_seconds > 0 else None,
        )
    except AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"segments": segments}


@router.patch("/admin/episodes/{episode_id}/transcript-status")
async def set_transcript_status(
    episode_id: str, body: TranscriptStatusIn, admin: Annotated[User, Depends(require_admin)],
):
    """Mark a transcript as being written (or failed) so the canvas can show it."""
    if body.status not in ("processing", "failed"):
        raise HTTPException(status_code=422, detail="status must be processing or failed")
    ep = await _get_episode_or_404(episode_id)
    ep.transcript_status = body.status
    await ep.save()
    return {"id": ep.id, "transcript_status": ep.transcript_status}


@router.put("/admin/episodes/{episode_id}/transcript")
async def save_transcript(
    episode_id: str,
    body: TranscriptIn,
    background: BackgroundTasks,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Save the whole timed transcript.

    `source` "auto" is the browser finishing an automatic run; "manual" is an
    admin's edit or an uploaded caption file. An automatic run never replaces a
    transcript an admin already edited: it is refused with 409 so their work is
    not lost to a re-upload. Notes are redrafted from the new transcript unless
    an admin wrote them.
    """
    if body.source not in ("auto", "manual"):
        raise HTTPException(status_code=422, detail="source must be auto or manual")
    timebase = body.timebase or ("source" if body.source == "auto" else "clip")
    if timebase not in ("source", "clip"):
        raise HTTPException(status_code=422, detail="timebase must be source or clip")
    ep = await _get_episode_or_404(episode_id)
    if body.source == "auto" and ep.transcript_source == "manual":
        raise HTTPException(
            status_code=409,
            detail="This transcript was edited by hand, so the automatic one was not saved over it.",
        )
    segments = sorted(
        (
            {"start": round(s.start, 2), "end": round(max(s.end, s.start), 2), "text": s.text.strip()}
            for s in body.segments if s.text.strip()
        ),
        key=lambda s: s["start"],
    )

    # A transcript of the whole video also belongs to every other part split
    # from it, unless an admin has edited that part's transcript by hand.
    targets = [ep]
    if timebase == "source" and ep.bunny_video_guid:
        targets += [
            other for other in await Episode.find(
                Episode.bunny_video_guid == ep.bunny_video_guid, Episode.id != ep.id
            ).to_list()
            if other.transcript_source != "manual"
        ]
    for target in targets:
        target.transcript_segments = (
            segments if timebase == "source" else merge_clip_segments(target, segments)
        )
        refresh_transcript_text(target)
        target.transcript_source = body.source
        target.transcript_status = "ready"
        await target.save()
        if target.transcript and target.notes_source != "manual":
            background.add_task(_draft_episode_notes, target.id)
    return {
        "id": ep.id,
        "transcript_status": ep.transcript_status,
        "transcript_source": ep.transcript_source,
        "transcript_segments": segments_in_clip(ep),
        "parts_updated": len(targets),
        "notes_will_update": bool(ep.transcript and ep.notes_source != "manual" and ai_service.enabled),
    }


@router.post("/admin/episodes/{episode_id}/notes/generate")
async def generate_episode_notes(episode_id: str, admin: Annotated[User, Depends(require_admin)]):
    """Redraft this episode's notes from its transcript, replacing what is there."""
    ep = await _get_episode_or_404(episode_id)
    if not ep.transcript:
        raise HTTPException(status_code=422, detail="This episode has no transcript yet")
    if not ai_service.enabled:
        raise HTTPException(status_code=503, detail="AI notes need OPENROUTER_API_KEY")
    try:
        ep.notes = await ai_service.episode_notes(ep.title, ep.transcript)
    except AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    ep.notes_source = "ai"
    await ep.save()
    return {"id": ep.id, "notes": ep.notes, "notes_source": ep.notes_source}


@router.put("/admin/episodes/{episode_id}/notes")
async def save_episode_notes(
    episode_id: str, body: NotesIn, admin: Annotated[User, Depends(require_admin)],
):
    ep = await _get_episode_or_404(episode_id)
    ep.notes = body.notes
    ep.notes_source = "manual"
    await ep.save()
    return {"id": ep.id, "notes": ep.notes, "notes_source": ep.notes_source}


# ==========================================================================
# ADMIN — checkpoint quizzes
# ==========================================================================
async def _get_quiz_or_404(quiz_id: str) -> Assessment:
    q = await Assessment.get(quiz_id)
    if not q or q.kind != "checkpoint":
        raise HTTPException(status_code=404, detail="Quiz not found")
    return q


@router.patch("/admin/assessments/{quiz_id}")
async def update_quiz(
    quiz_id: str, body: QuizUpdateIn, admin: Annotated[User, Depends(require_admin)],
):
    q = await _get_quiz_or_404(quiz_id)
    data = body.model_dump(exclude_unset=True)
    if "difficulty" in data and data["difficulty"] not in ("easy", "medium", "hard"):
        raise HTTPException(status_code=422, detail="difficulty must be easy, medium or hard")
    if "source_episode_ids" in data:
        module = await Module.get(q.module_id)
        allowed = {it.ref_id for it in (module.items if module else []) if it.kind == ITEM_VIDEO}
        data["source_episode_ids"] = [i for i in data["source_episode_ids"] if i in allowed]
    if "questions" in data:
        cleaned = []
        for i, qq in enumerate(body.questions or [], start=1):
            opts = [o.strip() for o in qq.options if o.strip()]
            if len(opts) < 2 or not (0 <= qq.correct_index < len(opts)):
                raise HTTPException(
                    status_code=422,
                    detail=f"Question {i} needs at least two options and a correct answer.",
                )
            cleaned.append({
                "question": qq.question.strip(),
                "options": opts,
                "correct_index": qq.correct_index,
                "explanation": (qq.explanation or "").strip() or None,
                "source_episode_id": qq.source_episode_id,
            })
        data["questions"] = cleaned
    for field, value in data.items():
        setattr(q, field, value)
    await q.save()
    return {"id": q.id, **{k: getattr(q, k) for k in (
        "title", "source_episode_ids", "question_count", "difficulty",
        "pass_threshold", "must_pass", "questions",
    )}}


@router.post("/admin/assessments/{quiz_id}/generate")
async def generate_quiz_questions(quiz_id: str, admin: Annotated[User, Depends(require_admin)]):
    """
    (Re)write the quiz's questions from its source episodes' transcripts.

    Replaces the current questions. Episodes without a transcript yet are left
    out and named, rather than failing the whole run.
    """
    q = await _get_quiz_or_404(quiz_id)
    if not ai_service.enabled:
        raise HTTPException(status_code=503, detail="AI quizzes need OPENROUTER_API_KEY")
    module = await Module.get(q.module_id)
    order = [it.ref_id for it in (module.items if module else []) if it.kind == ITEM_VIDEO]
    eps = {e.id: e for e in await Episode.find(In(Episode.id, q.source_episode_ids)).to_list()}
    chosen = [eps[i] for i in order if i in eps]
    usable = [e for e in chosen if e.transcript]
    skipped = [e.title for e in chosen if not e.transcript]
    if not usable:
        raise HTTPException(
            status_code=422,
            detail="None of the chosen episodes has a transcript yet. Wait for it, or add one by hand.",
        )
    try:
        raw = await ai_service.generate_checkpoint_quiz(
            [(e.title, e.transcript) for e in usable], q.question_count, q.difficulty
        )
    except AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="The AI answer could not be read. Try again.") from exc
    questions = _clean_questions(raw, [e.id for e in usable])[: q.question_count]
    if not questions:
        raise HTTPException(status_code=502, detail="The AI returned no usable questions. Try again.")
    q.questions = questions
    await q.save()
    return {"id": q.id, "questions": q.questions, "skipped_episodes": skipped}


# ==========================================================================
# ADMIN — tests on a course
# ==========================================================================
async def _get_course_test(course_id: str, test_id: str) -> tuple[Module, TestSeries]:
    module = await _get_course_or_404(course_id)
    if not any(it.kind == ITEM_TEST and it.ref_id == test_id for it in module.items):
        raise HTTPException(status_code=404, detail="That test is not on this course")
    test = await TestSeries.get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test not found")
    return module, test


@router.patch("/admin/courses/{course_id}/tests/{test_id}")
async def update_course_test(
    course_id: str, test_id: str, body: CourseTestUpdateIn,
    admin: Annotated[User, Depends(require_admin)],
):
    """Test settings from the canvas. Questions are edited with the test-series endpoints."""
    module, test = await _get_course_test(course_id, test_id)
    data = body.model_dump(exclude_unset=True)
    if "unlock_rule" in data and data["unlock_rule"] not in ("all_videos", "any"):
        raise HTTPException(status_code=422, detail="unlock_rule must be all_videos or any")
    for field, value in data.items():
        setattr(test, field, value)
    test.updated_at = datetime.now(timezone.utc)
    await test.save()
    refs = await _load_refs(module)
    item = next(it for it in module.items if it.ref_id == test.id)
    return await _admin_item(item, refs, {})


@router.post("/admin/courses/{course_id}/tests/{test_id}/generate")
async def generate_course_test(
    course_id: str, test_id: str, body: GenerateTestIn,
    admin: Annotated[User, Depends(require_admin)],
):
    """Write the test paper with AI from every transcribed episode on the course."""
    module, test = await _get_course_test(course_id, test_id)
    if not ai_service.enabled:
        raise HTTPException(status_code=503, detail="AI tests need OPENROUTER_API_KEY")
    refs = await _load_refs(module)
    eps = [refs.episodes[it.ref_id] for it in module.items
           if it.kind == ITEM_VIDEO and it.ref_id in refs.episodes]
    usable = [e for e in eps if e.transcript]
    if not usable:
        raise HTTPException(status_code=422, detail="No episode on this course has a transcript yet.")
    try:
        raw = await ai_service.generate_checkpoint_quiz(
            [(e.title, e.transcript) for e in usable], body.count, "medium"
        )
    except AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="The AI answer could not be read. Try again.") from exc
    titles = {e.id: e.title for e in usable}
    cleaned = _clean_questions(raw, [e.id for e in usable])
    if not cleaned:
        raise HTTPException(status_code=502, detail="The AI returned no usable questions. Try again.")
    test.questions = [
        TestQuestion(
            question=c["question"], options=c["options"], correct_index=c["correct_index"],
            explanation=c["explanation"], topic=titles.get(c["source_episode_id"] or ""),
        )
        for c in cleaned
    ]
    test.source_parser = "ai"
    test.source_filename = None
    test.updated_at = datetime.now(timezone.utc)
    await test.save()
    item = next(it for it in module.items if it.ref_id == test.id)
    return await _admin_item(item, await _load_refs(module), {})


# ==========================================================================
# ADMIN — notes pages
# ==========================================================================
async def _get_note_or_404(note_id: str) -> CourseNote:
    n = await CourseNote.get(note_id)
    if not n:
        raise HTTPException(status_code=404, detail="Notes page not found")
    return n


def _note_view(n: CourseNote) -> dict:
    return {
        "id": n.id, "title": n.title, "body": n.body, "source": n.source,
        "attachment_name": n.attachment_name, "attachment_size": n.attachment_size,
    }


@router.patch("/admin/notes/{note_id}")
async def update_note(note_id: str, body: NoteUpdateIn, admin: Annotated[User, Depends(require_admin)]):
    n = await _get_note_or_404(note_id)
    if body.title is not None:
        n.title = body.title.strip()
    if body.body is not None and body.body != n.body:
        n.body = body.body
        n.source = "manual"
    n.updated_at = datetime.now(timezone.utc)
    await n.save()
    return _note_view(n)


@router.post("/admin/notes/{note_id}/draft")
async def draft_note(note_id: str, admin: Annotated[User, Depends(require_admin)]):
    """Draft the page with AI from the videos in the same section."""
    n = await _get_note_or_404(note_id)
    if not ai_service.enabled:
        raise HTTPException(status_code=503, detail="AI drafting needs OPENROUTER_API_KEY")
    module = await Module.get(n.module_id)
    item = next((it for it in (module.items if module else []) if it.ref_id == n.id), None)
    if not module or not item:
        raise HTTPException(status_code=404, detail="Notes page is not on a course")
    section = next((s for s in module.sections if s.id == item.section_id), None)
    ep_ids = [it.ref_id for it in module.items if it.kind == ITEM_VIDEO and it.section_id == item.section_id]
    eps = {e.id: e for e in await Episode.find(In(Episode.id, ep_ids)).to_list()} if ep_ids else {}
    material = [(eps[i].title, eps[i].notes or eps[i].transcript or "") for i in ep_ids if i in eps]
    material = [(t, b) for t, b in material if b]
    if not material:
        raise HTTPException(
            status_code=422,
            detail="This section has no videos with a transcript or notes to draft from yet.",
        )
    try:
        n.body = await ai_service.section_notes(section.title if section else module.title, material)
    except AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    n.source = "ai"
    n.updated_at = datetime.now(timezone.utc)
    await n.save()
    return _note_view(n)


@router.post("/admin/notes/{note_id}/attachment")
async def upload_note_attachment(
    note_id: str, admin: Annotated[User, Depends(require_admin)], file: UploadFile = File(...),
):
    """Attach a PDF to a notes page, replacing any earlier one. Stored in MongoDB."""
    n = await _get_note_or_404(note_id)
    name = (file.filename or "attachment.pdf").strip()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="The file is empty")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="PDFs can be up to 10 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(status_code=422, detail="Only PDF files can be attached")
    await NoteAttachment.find(NoteAttachment.note_id == n.id).delete()
    att = NoteAttachment(note_id=n.id, filename=name, data=data)
    await att.insert()
    n.attachment_id, n.attachment_name, n.attachment_size = att.id, name, len(data)
    await n.save()
    return _note_view(n)


@router.delete("/admin/notes/{note_id}/attachment")
async def delete_note_attachment(note_id: str, admin: Annotated[User, Depends(require_admin)]):
    n = await _get_note_or_404(note_id)
    await NoteAttachment.find(NoteAttachment.note_id == n.id).delete()
    n.attachment_id = n.attachment_name = n.attachment_size = None
    await n.save()
    return _note_view(n)


# ==========================================================================
# ADMIN — test requests
# ==========================================================================
async def _course_progress(user_id: str, module: Module | None) -> int:
    """Percent of the course's ready videos this person has finished."""
    if not module:
        return 0
    ids = [it.ref_id for it in module.items if it.kind == ITEM_VIDEO]
    if not ids:
        return 100
    ready = [e.id for e in await Episode.find(In(Episode.id, ids), Episode.status == "ready").to_list()]
    if not ready:
        return 100
    done = await WatchProgress.find(
        WatchProgress.user_id == user_id, In(WatchProgress.episode_id, ready),
        WatchProgress.completed == True,  # noqa: E712
    ).count()
    return round(done / len(ready) * 100)


async def _request_view(r: TestRequest, cache: dict) -> dict:
    async def get(model, key):
        k = (model.__name__, key)
        if k not in cache:
            cache[k] = await model.get(key) if key else None
        return cache[k]

    user = await get(User, r.user_id)
    test = await get(TestSeries, r.test_id)
    module = await get(Module, r.module_id)
    used = await TestAttempt.find(TestAttempt.test_id == r.test_id, TestAttempt.user_id == r.user_id).count()
    return {
        "id": r.id,
        "status": r.status,
        "user_id": r.user_id,
        "full_name": (user.full_name or user.email) if user else "Former employee",
        "team": user.team if user else None,
        "department": user.department if user else None,
        "test_id": r.test_id,
        "test_title": test.title if test else "Deleted test",
        "question_count": len(test.questions) if test else 0,
        "duration_minutes": test.duration_minutes if test else None,
        "pass_threshold": test.pass_threshold if test else None,
        "proctoring_enabled": test.proctoring_enabled if test else False,
        "attempts_per_approval": test.attempts_per_approval if test else 1,
        "course_id": r.module_id,
        "course_title": module.title if module else None,
        "course_progress": await _course_progress(r.user_id, module),
        "previous_attempts": used,
        "attempts_granted": r.attempts_granted,
        "note": r.note,
        "reason": r.reason,
        "created_at": _utc(r.created_at),
        "decided_at": _utc(r.decided_at),
    }


@router.get("/admin/test-requests")
async def list_test_requests(
    admin: Annotated[User, Depends(require_admin)],
    status: str = "pending",
    limit: int = 100,
):
    """
    Pending requests (status=pending) or decided ones (status=decided).

    The admin shell polls the pending list to raise the approval pop-up, so it
    is kept to one query plus lookups for the handful of rows returned.
    """
    if status == "pending":
        q = TestRequest.find(TestRequest.status == TestRequest.PENDING).sort(+TestRequest.created_at)
    elif status == "decided":
        q = TestRequest.find(TestRequest.status != TestRequest.PENDING).sort(-TestRequest.decided_at)
    else:
        raise HTTPException(status_code=422, detail="status must be pending or decided")
    rows = await q.limit(max(1, min(limit, 500))).to_list()
    cache: dict = {}
    return [await _request_view(r, cache) for r in rows]


async def _get_pending_request(request_id: str) -> TestRequest:
    r = await TestRequest.get(request_id)
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")
    if r.status != TestRequest.PENDING:
        raise HTTPException(status_code=409, detail=f"This request was already {r.status}.")
    return r


@router.post("/admin/test-requests/{request_id}/approve")
async def approve_request(
    request_id: str, body: ApproveIn, admin: Annotated[User, Depends(require_admin)],
):
    """
    Let the person sit the test `attempts` times.

    Writes an AttemptGrant, which is what /take and /submit already count, so
    approval needs no extra check anywhere else.
    """
    r = await _get_pending_request(request_id)
    test = await TestSeries.get(r.test_id)
    if not test:
        raise HTTPException(status_code=404, detail="The test no longer exists")
    grant = AttemptGrant(
        test_id=test.id,
        user_id=r.user_id,
        extra_attempts=body.attempts,
        reason=f"Approved test request {r.id}",
        granted_by=admin.id,
    )
    await grant.insert()
    r.status = TestRequest.APPROVED
    r.attempts_granted = body.attempts
    r.grant_id = grant.id
    r.note = (body.note or "").strip() or None
    r.decided_by = admin.id
    r.decided_at = datetime.now(timezone.utc)
    await r.save()
    return await _request_view(r, {})


@router.post("/admin/test-requests/{request_id}/deny")
async def deny_request(
    request_id: str, body: DenyIn, admin: Annotated[User, Depends(require_admin)],
):
    r = await _get_pending_request(request_id)
    r.status = TestRequest.DENIED
    r.reason = (body.reason or "").strip() or None
    r.decided_by = admin.id
    r.decided_at = datetime.now(timezone.utc)
    await r.save()
    return await _request_view(r, {})


# ==========================================================================
# LEARNER
# ==========================================================================
async def _require_course(course_id: str, user: User) -> Module:
    """The course, if this person may open it. 404 otherwise, never 403."""
    module = await Module.get(course_id)
    if not module or module.layout != LAYOUT_CANVAS:
        raise HTTPException(status_code=404, detail="Course not found")
    if not content_access.is_admin(user):
        if not module.is_published or not await content_access.can_access_module_id(module.id, user):
            raise HTTPException(status_code=404, detail="Course not found")
    return module


async def _test_state(test: TestSeries, user: User, module: Module, videos_done: bool) -> dict:
    """Where one person stands on one course test: may they ask, and what happened."""
    status = await attempt_status(test, user.id)
    latest = await TestRequest.find(
        TestRequest.test_id == test.id, TestRequest.user_id == user.id
    ).sort(-TestRequest.created_at).first_or_none()
    attempts = await TestAttempt.find(
        TestAttempt.test_id == test.id, TestAttempt.user_id == user.id
    ).sort(-TestAttempt.submitted_at).to_list()
    can_request = await content_access.can_access_test(test, user)
    unlocked = test.unlock_rule == "any" or videos_done

    if not can_request:
        state = "not_allowed"
    elif (status["left"] or 0) > 0:
        state = "approved"
    elif latest and latest.status == TestRequest.PENDING:
        state = "pending"
    elif latest and latest.status == TestRequest.DENIED:
        state = "denied"
    elif attempts:
        state = "used"
    else:
        state = "none"
    return {
        "state": state,
        "unlocked": unlocked,
        "attempts_left": status["left"] or 0,
        "attempts_used": status["used"],
        "attempts_allowed": status["allowed"] or 0,
        "passed": any(a.passed for a in attempts),
        "best_score": max((a.score for a in attempts), default=None),
        "last_score": attempts[0].score if attempts else None,
        "last_attempt_id": attempts[0].id if attempts else None,
        "request_id": latest.id if latest else None,
        "requested_at": _utc(latest.created_at) if latest else None,
        "note": latest.note if latest and latest.status == TestRequest.APPROVED else None,
        "reason": latest.reason if latest and latest.status == TestRequest.DENIED else None,
    }


@router.get("/courses/{course_id}")
async def get_course(course_id: str, user: Annotated[User, Depends(get_current_user)]):
    """
    The course for the player: sections, items and this person's place in it.

    Videos still processing, quizzes with no questions and unpublished tests
    are left out, so a learner only ever sees items they can use.
    """
    module = await _require_course(course_id, user)
    refs = await _load_refs(module)

    visible: list[CourseItem] = []
    for it in _live_items(module, refs):
        doc = refs.doc(it)
        if it.kind == ITEM_VIDEO and (doc.status != "ready" or not (doc.bunny_video_guid or doc.bunny_video_id)):
            continue
        if it.kind == ITEM_QUIZ and not doc.questions:
            continue
        if it.kind == ITEM_TEST and not doc.is_published:
            continue
        visible.append(it)

    numbers = _episode_numbers(visible)
    ep_ids = [it.ref_id for it in visible if it.kind == ITEM_VIDEO]
    progress = {
        p.episode_id: p for p in await WatchProgress.find(
            WatchProgress.user_id == user.id, In(WatchProgress.episode_id, ep_ids)
        ).to_list()
    } if ep_ids else {}
    videos_done = all(progress.get(i) and progress[i].completed for i in ep_ids)

    quiz_ids = [it.ref_id for it in visible if it.kind == ITEM_QUIZ]
    quiz_attempts: dict[str, list[AssessmentAttempt]] = {}
    if quiz_ids:
        for a in await AssessmentAttempt.find(
            AssessmentAttempt.user_id == user.id, In(AssessmentAttempt.assessment_id, quiz_ids)
        ).to_list():
            quiz_attempts.setdefault(a.assessment_id, []).append(a)

    out_items = []
    locked = False
    for it in visible:
        doc = refs.doc(it)
        row: dict = {"id": it.id, "kind": it.kind, "ref_id": it.ref_id,
                     "section_id": it.section_id, "locked": locked}
        if it.kind == ITEM_VIDEO:
            p = progress.get(doc.id)
            row.update({
                "title": doc.title,
                "description": doc.description,
                "episode_number": numbers[doc.id],
                "duration_seconds": doc.duration_seconds,
                "thumbnail_url": _thumb(doc),
                "has_transcript": bool(segments_in_clip(doc)),
                # The part of the Bunny video to play, in its seconds. The
                # player keeps to it and counts time from clip_start.
                "clip_start": clip_bounds(doc)[0] if is_clipped(doc) else None,
                "clip_end": clip_bounds(doc)[1] if is_clipped(doc) else None,
                "notes": doc.notes,
                "notes_source": doc.notes_source,
                "watched_seconds": p.watched_seconds if p else 0,
                "completed": bool(p and p.completed),
            })
            row["done"] = row["completed"]
        elif it.kind == ITEM_QUIZ:
            mine = quiz_attempts.get(doc.id, [])
            passed = any(a.passed for a in mine)
            row.update({
                "title": doc.title or "Checkpoint quiz",
                "question_count": len(doc.questions),
                "pass_threshold": doc.pass_threshold,
                "must_pass": doc.must_pass,
                "source_episode_numbers": sorted(numbers[e] for e in doc.source_episode_ids if e in numbers),
                "best_score": max((a.score or 0 for a in mine), default=None),
                "attempts": len(mine),
                "passed": passed,
                "done": passed,
            })
            if doc.must_pass and not passed:
                locked = True  # everything after this waits for a pass
        elif it.kind == ITEM_NOTES:
            row.update({
                "title": doc.title, "body": doc.body, "source": doc.source,
                "attachment_name": doc.attachment_name, "attachment_size": doc.attachment_size,
                "done": False,
            })
        else:
            state = await _test_state(doc, user, module, videos_done)
            row.update({
                "title": doc.title,
                "description": doc.description,
                "question_count": len([q for q in doc.questions if q.scorable]),
                "duration_minutes": doc.duration_minutes,
                "pass_threshold": doc.pass_threshold,
                "proctoring_enabled": doc.proctoring_enabled,
                "unlock_rule": doc.unlock_rule,
                **state,
                "done": state["passed"],
            })
        out_items.append(row)

    used_sections = {i["section_id"] for i in out_items}
    return {
        "id": module.id,
        "title": module.title,
        "description": module.description,
        "category": module.category,
        "format": _course_format([i["kind"] for i in out_items]),
        "sections": [s.model_dump() for s in module.sections if s.id in used_sections],
        "items": out_items,
        "runtime_seconds": sum(i.get("duration_seconds") or 0 for i in out_items if i["kind"] == ITEM_VIDEO),
    }


@router.get("/courses/{course_id}/episodes/{episode_id}/transcript")
async def get_episode_transcript(
    course_id: str, episode_id: str, user: Annotated[User, Depends(get_current_user)],
):
    module = await _require_course(course_id, user)
    if not any(it.kind == ITEM_VIDEO and it.ref_id == episode_id for it in module.items):
        raise HTTPException(status_code=404, detail="Episode not found")
    ep = await _get_episode_or_404(episode_id)
    return {
        "episode_id": ep.id,
        "source": ep.transcript_source,
        # This part only, timed from its own start.
        "segments": segments_in_clip(ep),
    }


@router.get("/courses/{course_id}/quizzes/{quiz_id}")
async def get_course_quiz(
    course_id: str, quiz_id: str, user: Annotated[User, Depends(get_current_user)],
):
    """The quiz without its answers. Submitted through /assessments/{id}/attempt."""
    module = await _require_course(course_id, user)
    if not any(it.kind == ITEM_QUIZ and it.ref_id == quiz_id for it in module.items):
        raise HTTPException(status_code=404, detail="Quiz not found")
    q = await _get_quiz_or_404(quiz_id)
    return {
        "id": q.id,
        "title": q.title,
        "pass_threshold": q.pass_threshold,
        "questions": [{"question": x["question"], "options": x["options"]} for x in q.questions],
    }


@router.get("/courses/{course_id}/notes/{note_id}/attachment")
async def get_note_attachment(
    course_id: str, note_id: str, user: Annotated[User, Depends(get_current_user)],
):
    module = await _require_course(course_id, user)
    if not any(it.kind == ITEM_NOTES and it.ref_id == note_id for it in module.items):
        raise HTTPException(status_code=404, detail="Attachment not found")
    att = await NoteAttachment.find_one(NoteAttachment.note_id == note_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    safe = att.filename.replace('"', "").replace("\n", " ")
    return Response(
        content=att.data,
        media_type=att.content_type,
        headers={"Content-Disposition": f'inline; filename="{safe}"'},
    )


@router.post("/courses/{course_id}/tests/{test_id}/request", status_code=201)
async def request_test(
    course_id: str, test_id: str, user: Annotated[User, Depends(get_current_user)],
):
    """
    Ask to sit a course test. The admin gets a pop-up and decides the attempts.

    Refused while approved attempts are still unused (they are used first), and
    until every episode is watched when the test is set to open that way.
    Asking twice while a request is pending returns the pending one.
    """
    module = await _require_course(course_id, user)
    if not any(it.kind == ITEM_TEST and it.ref_id == test_id for it in module.items):
        raise HTTPException(status_code=404, detail="Test not found")
    test = await TestSeries.get(test_id)
    if not test or not test.is_published or not test.requires_approval:
        raise HTTPException(status_code=404, detail="Test not found")
    if not await content_access.can_access_test(test, user):
        raise HTTPException(status_code=403, detail="Your admin hasn't opened this test to you")

    status = await attempt_status(test, user.id)
    if (status["left"] or 0) > 0:
        raise HTTPException(status_code=409, detail="You still have approved attempts. Start the test.")

    pending = await TestRequest.find_one(
        TestRequest.test_id == test.id, TestRequest.user_id == user.id,
        TestRequest.status == TestRequest.PENDING,
    )
    if pending:
        return {"id": pending.id, "status": pending.status, "created_at": _utc(pending.created_at)}

    if test.unlock_rule == "all_videos" and await _course_progress(user.id, module) < 100:
        raise HTTPException(status_code=409, detail="Watch every episode first. This test opens after that.")

    r = TestRequest(test_id=test.id, module_id=module.id, user_id=user.id)
    await r.insert()
    return {"id": r.id, "status": r.status, "created_at": r.created_at}
