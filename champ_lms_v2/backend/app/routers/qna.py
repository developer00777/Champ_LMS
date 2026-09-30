"""
Q&A on course videos.

Learner flow: while watching, press Q&A on the player -> ask, pinned to the
              moment in the video -> see everyone's questions on the episode,
              and the admin's answers under them.
Admin flow:   /admin/questions lists every question, open ones first -> answer
              (or edit an answer) there or in the course player. The asker is
              told through a notification.

Times go out in clip time (from the start of the episode's part) and are
stored in source time (seconds of the whole Bunny video); see models/qna.py.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from beanie.operators import In
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import get_current_user, require_admin
from app.models.episode import Episode
from app.models.module import ITEM_VIDEO, Module
from app.models.qna import EpisodeQuestion
from app.models.social import Notification
from app.models.user import User
from app.routers.courses import _require_course, _utc
from app.services import content_access
from app.services.clips import clip_bounds

router = APIRouter(tags=["qna"])

MAX_QUESTION_CHARS = 2000
MAX_ANSWER_CHARS = 5000


class QuestionIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    # Clip time, from the start of the episode. None = about the whole video.
    at_seconds: float | None = Field(default=None, ge=0)


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)


def _name(u: User | None) -> str:
    return (u.full_name or u.email) if u else "Former employee"


async def _users(ids: set[str]) -> dict[str, User]:
    ids.discard(None)  # type: ignore[arg-type]
    return {u.id: u for u in await User.find(In(User.id, list(ids))).to_list()} if ids else {}


def _clip_time(q: EpisodeQuestion, ep: Episode | None) -> float | None:
    if q.at_seconds is None:
        return None
    start = clip_bounds(ep)[0] if ep else 0.0
    return round(max(0.0, q.at_seconds - start), 1)


def _view(q: EpisodeQuestion, ep: Episode | None, users: dict[str, User], me: User) -> dict:
    asker = users.get(q.user_id)
    return {
        "id": q.id,
        "episode_id": q.episode_id,
        "body": q.body,
        "at_seconds": _clip_time(q, ep),
        "full_name": _name(asker),
        "mine": q.user_id == me.id,
        # Staff questions read as the team's, not a colleague's.
        "asked_by_staff": bool(asker and asker.is_staff),
        "answer": q.answer,
        "answered_by_name": _name(users.get(q.answered_by)) if q.answer else None,
        "answered_at": _utc(q.answered_at),
        "created_at": _utc(q.created_at),
    }


async def _course_episode(course_id: str, episode_id: str, user: User) -> tuple[Module, Episode]:
    module = await _require_course(course_id, user)
    if not any(it.kind == ITEM_VIDEO and it.ref_id == episode_id for it in module.items):
        raise HTTPException(status_code=404, detail="Episode not found")
    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    return module, ep


# ==========================================================================
# In the course player
# ==========================================================================
@router.get("/courses/{course_id}/episodes/{episode_id}/questions")
async def list_questions(
    course_id: str, episode_id: str, user: Annotated[User, Depends(get_current_user)],
):
    """Everyone's questions on this episode, newest first, with any answers."""
    _, ep = await _course_episode(course_id, episode_id, user)
    qs = await EpisodeQuestion.find(EpisodeQuestion.episode_id == ep.id).sort(-EpisodeQuestion.created_at).to_list()
    users = await _users({q.user_id for q in qs} | {q.answered_by for q in qs if q.answered_by})
    return [_view(q, ep, users, user) for q in qs]


@router.post("/courses/{course_id}/episodes/{episode_id}/questions", status_code=201)
async def ask_question(
    course_id: str, episode_id: str, body: QuestionIn,
    user: Annotated[User, Depends(get_current_user)],
):
    module, ep = await _course_episode(course_id, episode_id, user)
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Write your question first.")
    at = None
    if body.at_seconds is not None:
        start, end = clip_bounds(ep)
        at = start + body.at_seconds
        if end is not None:
            at = min(at, end)
    q = EpisodeQuestion(module_id=module.id, episode_id=ep.id, user_id=user.id, body=text, at_seconds=at)
    await q.insert()
    return _view(q, ep, {user.id: user}, user)


@router.delete("/courses/{course_id}/questions/{question_id}")
async def delete_own_question(
    course_id: str, question_id: str, user: Annotated[User, Depends(get_current_user)],
):
    """A learner takes back their own question; an admin may remove any."""
    await _require_course(course_id, user)
    q = await EpisodeQuestion.get(question_id)
    if not q or q.module_id != course_id:
        raise HTTPException(status_code=404, detail="Question not found")
    if q.user_id != user.id and not content_access.is_admin(user):
        raise HTTPException(status_code=403, detail="You can only delete your own questions.")
    await q.delete()
    return {"deleted": question_id}


# ==========================================================================
# Admin inbox
# ==========================================================================
@router.get("/admin/questions/count")
async def open_question_count(admin: Annotated[User, Depends(require_admin)]):
    return {"open": await EpisodeQuestion.find(EpisodeQuestion.answer == None).count()}  # noqa: E711


@router.get("/admin/questions")
async def admin_questions(
    admin: Annotated[User, Depends(require_admin)],
    status: str = Query("open", pattern="^(open|answered|all)$"),
    course_id: str | None = None,
    limit: int = Query(200, ge=1, le=500),
):
    """Questions across every course. Open ones oldest first, so none wait forever."""
    filters: dict = {}
    if status == "open":
        filters["answer"] = None
    elif status == "answered":
        filters["answer"] = {"$ne": None}
    if course_id:
        filters["module_id"] = course_id
    order = +EpisodeQuestion.created_at if status == "open" else -EpisodeQuestion.created_at
    qs = await EpisodeQuestion.find(filters).sort(order).limit(limit).to_list()

    eps = {e.id: e for e in await Episode.find(In(Episode.id, list({q.episode_id for q in qs}))).to_list()} if qs else {}
    mods = {m.id: m for m in await Module.find(In(Module.id, list({q.module_id for q in qs}))).to_list()} if qs else {}
    users = await _users({q.user_id for q in qs} | {q.answered_by for q in qs if q.answered_by})
    rows = []
    for q in qs:
        ep, mod, asker = eps.get(q.episode_id), mods.get(q.module_id), users.get(q.user_id)
        rows.append({
            **_view(q, ep, users, admin),
            "team": asker.team if asker else None,
            "course_id": q.module_id,
            "course_title": mod.title if mod else "Deleted course",
            "episode_title": ep.title if ep else "Deleted video",
        })

    # Every course that has questions, for the filter.
    course_ids = await EpisodeQuestion.distinct("module_id")
    courses = [
        {"id": m.id, "title": m.title}
        for m in await Module.find(In(Module.id, course_ids)).sort(+Module.title).to_list()
    ] if course_ids else []
    return {
        "questions": rows,
        "open": await EpisodeQuestion.find(EpisodeQuestion.answer == None).count(),  # noqa: E711
        "courses": courses,
    }


@router.put("/admin/questions/{question_id}/answer")
async def answer_question(
    question_id: str, body: AnswerIn, admin: Annotated[User, Depends(require_admin)],
):
    """Answer a question, or edit the answer. The asker is notified the first time."""
    q = await EpisodeQuestion.get(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    text = body.answer.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Write an answer first.")
    first = q.answer is None
    q.answer = text
    q.answered_by = admin.id
    q.answered_at = datetime.now(timezone.utc)
    await q.save()

    ep = await Episode.get(q.episode_id)
    if first and q.user_id != admin.id:
        await Notification(
            user_id=q.user_id,
            notif_type="question_answered",
            title="Your question was answered",
            body=f"On “{ep.title if ep else 'a video'}”: {text[:140]}",
            ref_type="course",
            ref_id=q.module_id,
        ).insert()
    users = await _users({q.user_id, admin.id})
    return _view(q, ep, users, admin)


@router.delete("/admin/questions/{question_id}/answer")
async def clear_answer(question_id: str, admin: Annotated[User, Depends(require_admin)]):
    """Take an answer back, so the question is open again."""
    q = await EpisodeQuestion.get(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    q.answer = q.answered_by = q.answered_at = None
    await q.save()
    ep = await Episode.get(q.episode_id)
    return _view(q, ep, await _users({q.user_id}), admin)


@router.delete("/admin/questions/{question_id}")
async def admin_delete_question(question_id: str, admin: Annotated[User, Depends(require_admin)]):
    q = await EpisodeQuestion.get(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    await q.delete()
    return {"deleted": question_id}
