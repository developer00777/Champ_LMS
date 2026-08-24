"""
Test series router.

Admin flow:  upload a Q&A PDF or Word .docx -> review/edit the parsed draft ->
             publish -> see every learner's score, their answers, and
             AI-generated areas of improvement.
Learner flow: list published tests -> take the interactive questionnaire ->
             get scored instantly, with answers and AI feedback.
"""
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

import redis.asyncio as aioredis
from beanie.operators import In
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.auth import get_current_user, require_admin
from app.core.redis import get_redis
from app.models.test_series import (
    QUESTION_TYPE_MCQ,
    QUESTION_TYPE_WRITTEN,
    QUESTION_TYPES,
    TestAttempt,
    TestQuestion,
    TestSeries,
)
from app.models.user import User
from app.services.ai_service import ai_service, fallback_analysis
from app.services.bunny_storage import bunny_storage
from app.services.gamification_service import GamificationService
from app.services.proctor_service import build_report as build_proctor_report
from app.services.pdf_quiz_parser import (
    SUPPORTED_EXTENSIONS,
    PdfParseError,
    parse_document,
)

router = APIRouter(tags=["test-series"])

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10MB — a question paper is text, not media


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class QuestionIn(BaseModel):
    id: str | None = None
    question: str
    # Defaults keep older clients working: no question_type means mcq, and
    # options may be omitted entirely for a written question.
    question_type: str = QUESTION_TYPE_MCQ
    options: list[str] = Field(default_factory=list)
    correct_index: int | None = None
    explanation: str | None = None
    topic: str | None = None
    marks: int = 1
    expected_answer: str | None = None
    max_words: int | None = None
    time_limit_seconds: int | None = None
    time_limit_source: str | None = None


class TestUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    department: str | None = None
    pass_threshold: int | None = Field(default=None, ge=1, le=100)
    duration_minutes: int | None = None
    max_attempts: int | None = None
    shuffle_questions: bool | None = None
    proctoring_enabled: bool | None = None
    questions: list[QuestionIn] | None = None


class TestCreateIn(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    department: str | None = None
    pass_threshold: int = Field(default=70, ge=1, le=100)
    duration_minutes: int | None = None
    max_attempts: int | None = None
    proctoring_enabled: bool = True
    questions: list[QuestionIn] = Field(default_factory=list)


class AppendQuestionsIn(BaseModel):
    """Add questions to an existing test without resending the ones already there."""
    questions: list[QuestionIn]
    # * where the batch came from, so a test built from several PDFs still shows
    # * its provenance instead of claiming it all came from the first upload
    source_filename: str | None = None
    source_parser: str | None = None


class ProctorEventIn(BaseModel):
    """
    One integrity event as the exam client reports it. Deliberately permissive —
    the proctor service validates the kind against a whitelist and clamps the
    numbers, so a malformed or hostile row is dropped there rather than 422-ing
    a finished exam away.
    """
    kind: str
    at_seconds: int | None = None
    duration_seconds: int | None = None
    question_id: str | None = None
    detail: str | None = None


class SubmitIn(BaseModel):
    # {question_id: selected_option_index}; omit or null for skipped
    answers: dict[str, int | None] = Field(default_factory=dict)
    # {question_id: typed answer} for written questions
    text_answers: dict[str, str] = Field(default_factory=dict)

    # --- proctoring telemetry ----------------------------------------------
    # None means the client sent nothing at all, which the proctor treats as an
    # unmonitored attempt. An empty list means "monitored, nothing happened" —
    # a different thing, so the distinction is preserved rather than defaulted.
    proctor_events: list[ProctorEventIn] | None = None
    # Seconds the learner had the exam open, by the client's own clock. Used to
    # correlate absences against total time; never trusted for scoring.
    elapsed_seconds: int | None = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _admin_view(t: TestSeries) -> dict:
    """Full test including correct answers — admin only."""
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "category": t.category,
        "department": t.department,
        "pass_threshold": t.pass_threshold,
        "duration_minutes": t.duration_minutes,
        "max_attempts": t.max_attempts,
        "shuffle_questions": t.shuffle_questions,
        "proctoring_enabled": t.proctoring_enabled,
        "is_published": t.is_published,
        "is_ready": t.is_ready,
        "unscorable_count": t.unscorable_count,
        "total_marks": t.total_marks,
        "total_questions": len(t.questions),
        "source_filename": t.source_filename,
        "source_parser": t.source_parser,
        "created_at": t.created_at,
        "questions": [
            {
                "id": q.id,
                "question": q.question,
                "question_type": q.question_type,
                "options": q.options,
                "correct_index": q.correct_index,
                "explanation": q.explanation,
                "topic": q.topic,
                "marks": q.marks,
                "expected_answer": q.expected_answer,
                "max_words": q.max_words,
                "time_limit_seconds": q.time_limit_seconds,
                "time_limit_source": q.time_limit_source,
                "scorable": q.scorable,
            }
            for q in t.questions
        ],
    }


def _topic_stats(breakdown: list[dict]) -> dict[str, dict]:
    """Per-topic accuracy, the raw material for weak-area analysis."""
    stats: dict[str, dict] = {}
    for b in breakdown:
        topic = b.get("topic") or "General"
        s = stats.setdefault(topic, {"correct": 0, "total": 0, "accuracy": 0})
        s["total"] += 1
        if b.get("correct"):
            s["correct"] += 1
    for s in stats.values():
        s["accuracy"] = round(s["correct"] / s["total"] * 100) if s["total"] else 0
    return stats


# Sanity bounds for a per-question timer: under 5s is unusable, over an hour
# is indistinguishable from no limit.
MIN_TIME_LIMIT_SECONDS = 5
MAX_TIME_LIMIT_SECONDS = 3600


def _proctor_summary(a: TestAttempt) -> dict | None:
    """
    The verdict without the timeline, for list views.

    None means the attempt was never proctored (made before proctoring existed,
    or on a test with it switched off). Callers must render that as "not
    proctored" rather than as a clean result.
    """
    p = a.proctoring
    if not p:
        return None
    return {
        "risk_level": p.risk_level,
        "risk_score": p.risk_score,
        "summary": p.summary,
        "findings": p.findings,
        "counts": p.counts,
        "away_seconds": p.away_seconds,
        "longest_away_seconds": p.longest_away_seconds,
        "telemetry_missing": p.telemetry_missing,
        "verdict_by": p.verdict_by,
        "event_count": len(p.events),
    }


def _clamp_time_limit(seconds: int | None) -> int | None:
    if seconds is None:
        return None
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None  # 0 / negative means "no limit", not "instant fail"
    return max(MIN_TIME_LIMIT_SECONDS, min(MAX_TIME_LIMIT_SECONDS, value))


def _fallback_time_limit(q: TestQuestion) -> int:
    """
    A sane per-question limit without the AI.

    Used when a suggestion comes back unusable, so the admin still gets a
    complete set rather than a half-filled form. Scales with marks, because a
    5-mark question is not a 1-mark question.
    """
    if q.is_written:
        base = 180  # a short written answer
        return _clamp_time_limit(base + 90 * max(0, q.marks - 1)) or base
    base = 60  # a single-mark multiple-choice question
    return _clamp_time_limit(base + 30 * max(0, q.marks - 1)) or base


def _questions_from_in(items: list[QuestionIn]) -> list[TestQuestion]:
    out: list[TestQuestion] = []
    for q in items:
        qtype = q.question_type if q.question_type in QUESTION_TYPES else QUESTION_TYPE_MCQ
        # A question with no options can only be written, whatever was declared:
        # an MCQ with nothing to choose from is unanswerable.
        options = [o for o in q.options if o.strip()]
        if not options and (q.expected_answer or qtype == QUESTION_TYPE_WRITTEN):
            qtype = QUESTION_TYPE_WRITTEN

        kwargs: dict[str, Any] = {
            "question": q.question,
            "question_type": qtype,
            "options": [] if qtype == QUESTION_TYPE_WRITTEN else options,
            # A written question has no option index to be correct.
            "correct_index": None if qtype == QUESTION_TYPE_WRITTEN else q.correct_index,
            "explanation": q.explanation,
            "topic": q.topic,
            "marks": max(1, q.marks),
            "expected_answer": (q.expected_answer or None) if qtype == QUESTION_TYPE_WRITTEN else None,
            "max_words": q.max_words if qtype == QUESTION_TYPE_WRITTEN else None,
            "time_limit_seconds": _clamp_time_limit(q.time_limit_seconds),
            "time_limit_source": q.time_limit_source,
        }
        if q.id:
            kwargs["id"] = q.id
        out.append(TestQuestion(**kwargs))
    return out


async def _grade_written(q: TestQuestion, answer: str) -> dict | None:
    """
    Grade one written answer with the AI.

    Returns {awarded, correct, feedback, model_answer} or None when grading is
    unavailable (no API key, model error, unusable response). None is a real
    outcome the caller must handle — never a silent zero — because a model
    outage should not look like a wrong answer on the learner's transcript.

    The model's numbers are clamped rather than trusted: it occasionally awards
    more than the question is worth, or returns marks as a string.
    """
    if not ai_service.enabled:
        return None
    try:
        raw = await ai_service.grade_written_answer(
            question=q.question,
            answer=answer,
            marks=q.marks,
            expected_answer=q.expected_answer,
            topic=q.topic,
        )
    except Exception:  # noqa: BLE001 - degrade to "ungraded", never fail the submit
        return None

    try:
        awarded = float(raw.get("marks_awarded") or 0)
    except (TypeError, ValueError):
        awarded = 0.0
    awarded = int(round(max(0.0, min(float(q.marks), awarded))))

    correct = bool(raw.get("correct"))
    # Keep the flag and the marks consistent: a "correct" answer awarded
    # nothing (or vice versa) reads as a bug to whoever sees the transcript.
    if awarded >= q.marks * 0.6 and q.marks > 0:
        correct = True
    if awarded == 0:
        correct = False

    feedback = str(raw.get("feedback") or "").strip() or None
    model_answer = str(raw.get("model_answer") or "").strip() or None
    return {
        "awarded": awarded,
        "correct": correct,
        "feedback": feedback,
        "model_answer": model_answer,
    }


def _normalize_question(text: str) -> str:
    """
    Loose key for duplicate detection across two PDF ingests. Case, punctuation
    and whitespace differ between exports of the same paper, so they're stripped
    before comparing — this only drives a warning, never an automatic deletion.
    """
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


async def _get_test_or_404(test_id: str) -> TestSeries:
    test = await TestSeries.get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test series not found")
    return test


# ==========================================================================
# ADMIN — ingest
# ==========================================================================
@router.post("/admin/test-series/parse-pdf")
async def parse_pdf_upload(
    admin: Annotated[User, Depends(require_admin)],
    file: UploadFile = File(...),
    use_ai: bool = Form(False),
):
    """
    Parse a Q&A document (PDF or Word .docx) into draft questions WITHOUT
    saving anything.
    The admin reviews the result and then POSTs it to /admin/test-series.

    Deterministic parser runs first; `use_ai` (or a pattern parse that found
    nothing) routes to the AI parser for unusual layouts.
    """
    name = (file.filename or "").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext and ext not in SUPPORTED_EXTENSIONS:
        # Only reject on a known-wrong extension. Content-type is unreliable for
        # .docx (browsers send anything from the correct OOXML type to
        # application/octet-stream), so the real format check is the magic-byte
        # sniffing in parse_document().
        if ext == ".doc":
            raise HTTPException(
                status_code=415,
                detail=(
                    "Older Word .doc files can't be read. Save as .docx or export "
                    "to PDF, then upload again."
                ),
            )
        raise HTTPException(
            status_code=415, detail="Upload a PDF or Word (.docx) question paper"
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data) // 1024 // 1024}MB). Limit is 10MB.",
        )

    try:
        questions, text = parse_document(data, filename=file.filename)
    except PdfParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    parser_used = "pattern"
    warnings: list[str] = []

    if use_ai or not questions:
        if not ai_service.enabled:
            if not questions:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Could not detect any questions in this document, and AI "
                        "parsing is unavailable (OPENROUTER_API_KEY not set). Check "
                        "the layout or add questions manually."
                    ),
                )
            warnings.append("AI parsing requested but no API key configured; used pattern parser.")
        else:
            try:
                raw = await ai_service.parse_questions_from_text(text)
                ai_questions = _questions_from_in(
                    [
                        QuestionIn(
                            question=str(r.get("question", "")).strip(),
                            question_type=(
                                QUESTION_TYPE_WRITTEN
                                if str(r.get("question_type") or "").lower() == QUESTION_TYPE_WRITTEN
                                or not (r.get("options") or [])
                                else QUESTION_TYPE_MCQ
                            ),
                            options=[str(o) for o in (r.get("options") or [])],
                            correct_index=r.get("correct_index"),
                            explanation=r.get("explanation"),
                            topic=r.get("topic"),
                            marks=int(r.get("marks") or 1),
                            expected_answer=r.get("expected_answer") or r.get("model_answer"),
                        )
                        for r in raw
                        if str(r.get("question", "")).strip()
                        # An MCQ needs choices; a written question needs none.
                        and (
                            len(r.get("options") or []) >= 2
                            or str(r.get("question_type") or "").lower() == QUESTION_TYPE_WRITTEN
                            or not (r.get("options") or [])
                        )
                    ]
                )
                # * only take the AI result if it actually did better
                if ai_questions and (use_ai or len(ai_questions) > len(questions)):
                    questions, parser_used = ai_questions, "ai"
            except Exception as exc:  # noqa: BLE001 - degrade to pattern result
                if not questions:
                    # 503, not 502: the upload was fine and nothing about it will
                    # fix this — the AI backend is misconfigured or unavailable.
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            f"AI parsing is unavailable ({exc}) and no questions "
                            "could be detected by the pattern parser. Either fix the "
                            "AI configuration, upload a document with numbered questions "
                            "and lettered options, or add the questions manually."
                        ),
                    ) from exc
                warnings.append(f"AI parsing failed ({exc}); used pattern parser instead.")

    if not questions:
        raise HTTPException(
            status_code=422,
            detail=(
                "No questions detected. Expected numbered questions with lettered "
                "options (e.g. '1. ...' then 'A) ...'). Try enabling AI parsing."
            ),
        )

    missing = sum(1 for q in questions if not q.scorable)
    if missing:
        warnings.append(
            f"{missing} of {len(questions)} questions have no correct answer detected — "
            "set them before publishing."
        )

    return {
        "source_filename": file.filename,
        "source_parser": parser_used,
        "extracted_characters": len(text),
        "detected_questions": len(questions),
        "unscorable_count": missing,
        "warnings": warnings,
        "questions": [
            {
                "id": q.id,
                "question": q.question,
                "question_type": q.question_type,
                "options": q.options,
                "correct_index": q.correct_index,
                "explanation": q.explanation,
                "topic": q.topic,
                "marks": q.marks,
                "expected_answer": q.expected_answer,
                "max_words": q.max_words,
                "time_limit_seconds": q.time_limit_seconds,
                "time_limit_source": q.time_limit_source,
                "scorable": q.scorable,
            }
            for q in questions
        ],
    }


# ==========================================================================
# ADMIN — CRUD
# ==========================================================================
@router.post("/admin/test-series", status_code=201)
async def create_test_series(
    body: TestCreateIn,
    admin: Annotated[User, Depends(require_admin)],
    source_filename: str | None = None,
    source_parser: str | None = None,
):
    test = TestSeries(
        title=body.title,
        description=body.description,
        category=body.category,
        department=body.department,
        pass_threshold=body.pass_threshold,
        duration_minutes=body.duration_minutes,
        max_attempts=body.max_attempts,
        proctoring_enabled=body.proctoring_enabled,
        questions=_questions_from_in(body.questions),
        source_filename=source_filename,
        source_parser=source_parser or "manual",
        created_by=admin.id,
    )
    await test.insert()
    return _admin_view(test)


@router.get("/admin/test-series")
async def list_test_series_admin(admin: Annotated[User, Depends(require_admin)]):
    tests = await TestSeries.find_all().sort(-TestSeries.created_at).to_list()
    out = []
    for t in tests:
        attempts = await TestAttempt.find(TestAttempt.test_id == t.id).to_list()
        scores = [a.score for a in attempts]
        out.append({
            "id": t.id,
            "title": t.title,
            "category": t.category,
            "department": t.department,
            "is_published": t.is_published,
            "is_ready": t.is_ready,
            "unscorable_count": t.unscorable_count,
            "total_questions": len(t.questions),
            "pass_threshold": t.pass_threshold,
            "duration_minutes": t.duration_minutes,
            "source_filename": t.source_filename,
            "created_at": t.created_at,
            "attempt_count": len(attempts),
            "average_score": round(sum(scores) / len(scores)) if scores else None,
            "pass_rate": round(sum(1 for a in attempts if a.passed) / len(attempts) * 100)
            if attempts else None,
        })
    return out


@router.get("/admin/test-series/{test_id}")
async def get_test_series_admin(
    test_id: str, admin: Annotated[User, Depends(require_admin)]
):
    return _admin_view(await _get_test_or_404(test_id))


@router.patch("/admin/test-series/{test_id}")
async def update_test_series(
    test_id: str,
    body: TestUpdateIn,
    admin: Annotated[User, Depends(require_admin)],
):
    """Edit metadata and/or replace the question set (the review step)."""
    test = await _get_test_or_404(test_id)
    data = body.model_dump(exclude_unset=True)

    if "questions" in data and body.questions is not None:
        test.questions = _questions_from_in(body.questions)
    for field in (
        "title", "description", "category", "department", "pass_threshold",
        "duration_minutes", "max_attempts", "shuffle_questions",
        "proctoring_enabled",
    ):
        if field in data:
            setattr(test, field, data[field])

    test.updated_at = datetime.now(timezone.utc)
    await test.save()
    return _admin_view(test)


@router.post("/admin/test-series/{test_id}/questions", status_code=201)
async def append_questions(
    test_id: str,
    body: AppendQuestionsIn,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Append a batch of questions to an existing test series — a second PDF, or
    hand-written extras — without touching the questions already there.

    This is deliberately separate from PATCH, which replaces the whole set: an
    admin extending a live test must not have to round-trip every existing
    question (and risk clobbering a concurrent edit) just to add five more.
    """
    test = await _get_test_or_404(test_id)
    incoming = _questions_from_in(body.questions)
    if not incoming:
        raise HTTPException(status_code=422, detail="No questions to add")

    # * ids are regenerated on collision — a re-parsed PDF or a duplicated draft
    # * can arrive carrying ids that already exist, and a duplicate id would make
    # * the two questions indistinguishable in an attempt's answer map
    existing_ids = {q.id for q in test.questions}
    added = 0
    for q in incoming:
        if q.id in existing_ids:
            q.id = str(uuid.uuid4())
        existing_ids.add(q.id)
        test.questions.append(q)
        added += 1

    if body.source_filename:
        # Keep the original provenance and note what got layered on top.
        test.source_filename = (
            f"{test.source_filename} + {body.source_filename}"
            if test.source_filename and body.source_filename not in (test.source_filename or "")
            else body.source_filename
        )
    if body.source_parser and test.source_parser != body.source_parser:
        test.source_parser = "mixed" if test.source_parser else body.source_parser

    # A published test whose new questions aren't scorable would break scoring
    # for the next learner, so pull it back to draft and say so.
    unpublished = False
    if test.is_published and not test.is_ready:
        test.is_published = False
        unpublished = True

    test.updated_at = datetime.now(timezone.utc)
    await test.save()

    attempts = await TestAttempt.find(TestAttempt.test_id == test_id).count()
    return {
        **_admin_view(test),
        "added": added,
        "unpublished_by_this_change": unpublished,
        "existing_attempts": attempts,
        "notice": (
            f"{attempts} learner(s) already took the earlier version — their scores "
            "were graded against the questions that existed then and are unchanged."
        ) if attempts else None,
    }


@router.delete("/admin/test-series/{test_id}/questions/{question_id}")
async def delete_question(
    test_id: str,
    question_id: str,
    admin: Annotated[User, Depends(require_admin)],
):
    """Remove a single question without resending the rest of the set."""
    test = await _get_test_or_404(test_id)
    remaining = [q for q in test.questions if q.id != question_id]
    if len(remaining) == len(test.questions):
        raise HTTPException(status_code=404, detail="Question not found in this test")

    test.questions = remaining
    if test.is_published and not test.is_ready:
        test.is_published = False
    test.updated_at = datetime.now(timezone.utc)
    await test.save()
    return _admin_view(test)


@router.post("/admin/test-series/{test_id}/parse-pdf")
async def parse_pdf_for_existing_test(
    test_id: str,
    admin: Annotated[User, Depends(require_admin)],
    file: UploadFile = File(...),
    use_ai: bool = Form(False),
):
    """
    Parse another question paper against an existing test. Saves nothing — the admin
    reviews the draft and then POSTs it to .../questions to append.

    Flags questions that look like duplicates of ones already in the test so a
    re-uploaded paper doesn't silently double every question.
    """
    test = await _get_test_or_404(test_id)
    parsed = await parse_pdf_upload(admin=admin, file=file, use_ai=use_ai)

    existing = {_normalize_question(q.question) for q in test.questions}
    for q in parsed["questions"]:
        q["duplicate_of_existing"] = _normalize_question(q["question"]) in existing

    dupes = sum(1 for q in parsed["questions"] if q["duplicate_of_existing"])
    if dupes:
        parsed["warnings"].append(
            f"{dupes} question(s) already appear in “{test.title}” — they are "
            "pre-unchecked below so you don't add them twice."
        )
    return {
        **parsed,
        "test_id": test.id,
        "test_title": test.title,
        "existing_questions": len(test.questions),
        "duplicate_count": dupes,
    }


class SuggestTimeLimitsIn(BaseModel):
    # When true, write the suggestions onto the test. When false (default),
    # return them for the admin to review first.
    apply: bool = False
    # Only fill limits that are currently unset, leaving manual values alone.
    only_missing: bool = True


@router.post("/admin/test-series/{test_id}/suggest-time-limits")
async def suggest_time_limits(
    test_id: str,
    body: SuggestTimeLimitsIn,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Ask the AI how long each question should take.

    Returns a suggestion per question; `apply` writes them onto the test.
    Suggestions are marked time_limit_source="ai" so the UI can show them as
    proposals an admin may override.
    """
    test = await _get_test_or_404(test_id)
    if not test.questions:
        raise HTTPException(status_code=422, detail="This test has no questions yet")
    if not ai_service.enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI time suggestions are unavailable (OPENROUTER_API_KEY not set). "
                "Set limits manually instead."
            ),
        )

    targets = [
        (i, q) for i, q in enumerate(test.questions)
        if not (body.only_missing and q.time_limit_seconds is not None)
    ]
    if not targets:
        return {
            "suggestions": [],
            "applied": False,
            "message": "Every question already has a time limit.",
        }

    try:
        raw = await ai_service.suggest_time_limits(
            [
                {
                    "question": q.question,
                    "question_type": q.question_type,
                    "marks": q.marks,
                }
                for _, q in targets
            ]
        )
    except Exception as exc:  # noqa: BLE001 - config/model failure, not a bug here
        raise HTTPException(
            status_code=503, detail=f"Could not get time suggestions: {exc}"
        ) from exc

    # Match by the index the model echoes back, falling back to position, since
    # a model occasionally drops or reorders entries.
    by_index: dict[int, dict] = {}
    for pos, item in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("index", pos))
        except (TypeError, ValueError):
            idx = pos
        by_index.setdefault(idx, item)

    suggestions = []
    applied = 0
    for offset, (real_index, q) in enumerate(targets):
        item = by_index.get(offset) or by_index.get(real_index) or {}
        seconds = _clamp_time_limit(item.get("seconds"))
        if seconds is None:
            seconds = _fallback_time_limit(q)
            why = "default for this question type (no usable AI suggestion)"
        else:
            why = str(item.get("why") or "").strip() or None
        suggestions.append({
            "question_id": q.id,
            "question": q.question[:120],
            "question_type": q.question_type,
            "marks": q.marks,
            "current_seconds": q.time_limit_seconds,
            "suggested_seconds": seconds,
            "why": why,
        })
        if body.apply:
            q.time_limit_seconds = seconds
            q.time_limit_source = "ai"
            applied += 1

    if body.apply and applied:
        test.updated_at = datetime.now(timezone.utc)
        await test.save()

    return {
        "suggestions": suggestions,
        "applied": bool(body.apply and applied),
        "applied_count": applied if body.apply else 0,
    }


@router.patch("/admin/test-series/{test_id}/publish")
async def publish_test_series(
    test_id: str,
    admin: Annotated[User, Depends(require_admin)],
    publish: bool = True,
):
    test = await _get_test_or_404(test_id)
    if publish and not test.is_ready:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Cannot publish: {test.unscorable_count} question(s) have no correct "
                "answer set." if test.questions else "Cannot publish a test with no questions."
            ),
        )
    test.is_published = publish
    await test.save()
    return {"id": test.id, "is_published": test.is_published}


@router.delete("/admin/test-series/{test_id}")
async def delete_test_series(
    test_id: str, admin: Annotated[User, Depends(require_admin)]
):
    test = await _get_test_or_404(test_id)
    await test.delete()
    return {"deleted": test_id}


# ==========================================================================
# ADMIN — results
# ==========================================================================
@router.get("/admin/test-series/{test_id}/results")
async def test_results(
    test_id: str, admin: Annotated[User, Depends(require_admin)]
):
    """Every attempt on this test, with per-question detail and topic accuracy."""
    test = await _get_test_or_404(test_id)
    attempts = await TestAttempt.find(TestAttempt.test_id == test_id).sort(
        -TestAttempt.submitted_at
    ).to_list()

    user_ids = list({a.user_id for a in attempts})
    users = {
        u.id: u for u in await User.find(In(User.id, user_ids)).to_list()
    } if user_ids else {}

    rows = []
    for a in attempts:
        u = users.get(a.user_id)
        rows.append({
            "attempt_id": a.id,
            "user_id": a.user_id,
            "full_name": u.full_name if u else None,
            "employee_code": u.employee_code if u else None,
            "avatar_url": bunny_storage.avatar_url(u.avatar_bunny_path) if u else None,
            "email": u.email if u else None,
            "department": u.department if u else None,
            "score": a.score,
            "marks_earned": a.marks_earned,
            "marks_total": a.marks_total,
            "correct_count": a.correct_count,
            "total_questions": a.total_questions,
            "passed": a.passed,
            "submitted_at": a.submitted_at,
            "breakdown": a.breakdown,
            "topic_stats": _topic_stats(a.breakdown),
            "has_ai_analysis": a.ai_analysis is not None,
            "ai_analysis": a.ai_analysis,
            # * the full event timeline is deliberately not in the list payload —
            # * it is large and only wanted when an admin opens one attempt
            "proctoring": _proctor_summary(a),
        })

    scores = [a.score for a in attempts]
    # * aggregate topic accuracy across everyone — shows what the whole cohort fails
    cohort: dict[str, dict] = {}
    for a in attempts:
        for topic, s in _topic_stats(a.breakdown).items():
            agg = cohort.setdefault(topic, {"correct": 0, "total": 0, "accuracy": 0})
            agg["correct"] += s["correct"]
            agg["total"] += s["total"]
    for s in cohort.values():
        s["accuracy"] = round(s["correct"] / s["total"] * 100) if s["total"] else 0

    return {
        "test_id": test.id,
        "title": test.title,
        "pass_threshold": test.pass_threshold,
        "total_questions": len(test.questions),
        "attempt_count": len(attempts),
        "average_score": round(sum(scores) / len(scores)) if scores else None,
        "pass_rate": round(sum(1 for a in attempts if a.passed) / len(attempts) * 100)
        if attempts else None,
        "cohort_topic_stats": cohort,
        "attempts": rows,
    }


@router.post("/admin/test-series/{test_id}/coach")
async def coach_test_cohort(
    test_id: str,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    AI coaching guidance for the whole cohort: what the group struggled with,
    what to run for everyone, and a ready-to-send message per learner who needs
    attention — so the admin can act on results rather than just read them.
    """
    test = await _get_test_or_404(test_id)
    attempts = await TestAttempt.find(TestAttempt.test_id == test_id).to_list()
    if not attempts:
        raise HTTPException(
            status_code=422, detail="Nobody has taken this test yet."
        )
    if not ai_service.enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI coaching is unavailable (OPENROUTER_API_KEY not set). The "
                "per-question results and topic accuracy are still on this page."
            ),
        )

    user_ids = list({a.user_id for a in attempts})
    users = {u.id: u for u in await User.find(In(User.id, user_ids)).to_list()}

    # Keep only each person's latest attempt: coaching someone on a score they
    # already improved on would be actively misleading.
    latest: dict[str, TestAttempt] = {}
    for a in sorted(attempts, key=lambda x: x.submitted_at):
        latest[a.user_id] = a

    rows = []
    cohort: dict[str, dict] = {}
    for a in latest.values():
        stats = _topic_stats(a.breakdown)
        for topic, st in stats.items():
            agg = cohort.setdefault(topic, {"correct": 0, "total": 0, "accuracy": 0})
            agg["correct"] += st["correct"]
            agg["total"] += st["total"]
        u = users.get(a.user_id)
        rows.append({
            "user_id": a.user_id,
            "full_name": u.full_name if u else None,
            "email": u.email if u else None,
            "score": a.score,
            "passed": a.passed,
            "weak_topics": [
                t for t, st in sorted(stats.items(), key=lambda kv: kv[1]["accuracy"])
                if st["accuracy"] < 100
            ][:3],
        })
    for st in cohort.values():
        st["accuracy"] = round(st["correct"] / st["total"] * 100) if st["total"] else 0

    try:
        guidance = await ai_service.coach_cohort(
            test_title=test.title,
            pass_threshold=test.pass_threshold,
            attempts=rows,
            cohort_topics=cohort,
        )
    except Exception as exc:  # noqa: BLE001 - model/config failure
        raise HTTPException(
            status_code=503, detail=f"Could not generate coaching guidance: {exc}"
        ) from exc

    return {
        "test_id": test.id,
        "test_title": test.title,
        "learners_considered": len(rows),
        "cohort_topics": cohort,
        "guidance": guidance,
    }


@router.post("/admin/test-series/attempts/{attempt_id}/analyze")
async def analyze_attempt_admin(
    attempt_id: str, admin: Annotated[User, Depends(require_admin)]
):
    """Generate (or regenerate) the AI improvement analysis for one attempt."""
    attempt = await TestAttempt.get(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    analysis = await _build_analysis(attempt, force=True)
    return {"attempt_id": attempt.id, "ai_analysis": analysis}


# ==========================================================================
# LEARNER
# ==========================================================================
@router.get("/test-series")
async def list_tests(user: Annotated[User, Depends(get_current_user)]):
    """Published tests visible to this user, with their own attempt history."""
    tests = await TestSeries.find(TestSeries.is_published == True).to_list()  # noqa: E712
    out = []
    for t in tests:
        if t.department and user.department and t.department != user.department:
            continue
        mine = await TestAttempt.find(
            TestAttempt.test_id == t.id, TestAttempt.user_id == user.id
        ).to_list()
        best = max((a.score for a in mine), default=None)
        attempts_left = (
            None if t.max_attempts is None else max(0, t.max_attempts - len(mine))
        )
        out.append({
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "category": t.category,
            "department": t.department,
            "total_questions": len(t.questions),
            "total_marks": t.total_marks,
            "pass_threshold": t.pass_threshold,
            "duration_minutes": t.duration_minutes,
            "max_attempts": t.max_attempts,
            "my_attempts": len(mine),
            "attempts_left": attempts_left,
            "my_best_score": best,
            "passed": any(a.passed for a in mine),
        })
    return out


@router.get("/test-series/{test_id}/take")
async def take_test(
    test_id: str, user: Annotated[User, Depends(get_current_user)]
):
    """The questionnaire, with correct answers stripped out."""
    test = await _get_test_or_404(test_id)
    if not test.is_published:
        raise HTTPException(status_code=403, detail="This test is not published")
    if test.department and user.department and test.department != user.department:
        raise HTTPException(status_code=403, detail="This test is not available to you")

    used = await TestAttempt.find(
        TestAttempt.test_id == test_id, TestAttempt.user_id == user.id
    ).count()
    if test.max_attempts is not None and used >= test.max_attempts:
        raise HTTPException(
            status_code=403,
            detail=f"You have used all {test.max_attempts} attempts for this test.",
        )

    questions = [q for q in test.questions if q.scorable]
    if test.shuffle_questions:
        import random

        questions = random.sample(questions, len(questions))

    return {
        "id": test.id,
        "title": test.title,
        "description": test.description,
        "duration_minutes": test.duration_minutes,
        "pass_threshold": test.pass_threshold,
        "total_marks": sum(q.marks for q in questions),
        "attempt_number": used + 1,
        "max_attempts": test.max_attempts,
        # * when true the client blocks copy/paste/context menu and reports
        # * integrity events with the submission
        "proctoring_enabled": test.proctoring_enabled,
        # * total per-question time, so the client can show an overall budget
        # * when the test has per-question limits but no whole-test duration.
        "total_time_limit_seconds": (
            sum(q.time_limit_seconds for q in questions if q.time_limit_seconds)
            or None
        ),
        "questions": [
            {
                "id": q.id,
                "question": q.question,
                "question_type": q.question_type,
                # Written questions carry no options, and expected_answer is
                # deliberately withheld — it is the answer key.
                "options": [] if q.is_written else q.options,
                "max_words": q.max_words,
                "time_limit_seconds": q.time_limit_seconds,
                "topic": q.topic,
                "marks": q.marks,
            }
            for q in questions
        ],
    }


@router.post("/test-series/{test_id}/submit")
async def submit_test(
    test_id: str,
    body: SubmitIn,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    """Score the submission, persist it, and return the reviewable result."""
    test = await _get_test_or_404(test_id)
    if not test.is_published:
        raise HTTPException(status_code=403, detail="This test is not published")

    used = await TestAttempt.find(
        TestAttempt.test_id == test_id, TestAttempt.user_id == user.id
    ).count()
    if test.max_attempts is not None and used >= test.max_attempts:
        raise HTTPException(
            status_code=403,
            detail=f"You have used all {test.max_attempts} attempts for this test.",
        )

    scorable = [q for q in test.questions if q.scorable]
    if not scorable:
        raise HTTPException(status_code=422, detail="This test has no scorable questions")

    breakdown: list[dict] = []
    marks_earned = 0
    correct_count = 0
    ai_graded = False
    ungraded: list[str] = []

    for q in scorable:
        if q.is_written:
            typed = (body.text_answers.get(q.id) or "").strip()
            row = {
                "question_id": q.id,
                "question": q.question,
                "question_type": QUESTION_TYPE_WRITTEN,
                "options": [],
                "your_index": None,
                "your_answer": typed or None,
                "correct_index": None,
                "correct_answer": q.expected_answer,
                "explanation": q.explanation,
                "topic": q.topic,
                "marks": q.marks,
            }

            if not typed:
                # Nothing written: zero, and no reason to spend a model call.
                row.update({
                    "awarded": 0, "correct": False,
                    "ai_feedback": "You left this answer blank.",
                    "graded_by": "skipped",
                })
            else:
                graded = await _grade_written(q, typed)
                if graded is None:
                    # Grading unavailable. Score 0 but record it so the result
                    # says "not graded" rather than quietly implying a wrong
                    # answer, and an admin can re-grade later.
                    ungraded.append(q.id)
                    row.update({
                        "awarded": 0, "correct": False,
                        "ai_feedback": (
                            "This answer could not be graded automatically. "
                            "An administrator can review it."
                        ),
                        "graded_by": "ungraded",
                    })
                else:
                    ai_graded = True
                    marks_earned += graded["awarded"]
                    if graded["correct"]:
                        correct_count += 1
                    row.update({
                        "awarded": graded["awarded"],
                        "correct": graded["correct"],
                        "ai_feedback": graded["feedback"],
                        "graded_by": "ai",
                    })
                    if graded.get("model_answer") and not row["correct_answer"]:
                        row["correct_answer"] = graded["model_answer"]
            breakdown.append(row)
            continue

        given = body.answers.get(q.id)
        if given is not None and not (0 <= given < len(q.options)):
            given = None  # out-of-range index counts as skipped, never a crash
        is_correct = given is not None and given == q.correct_index
        if is_correct:
            marks_earned += q.marks
            correct_count += 1
        breakdown.append({
            "question_id": q.id,
            "question": q.question,
            "question_type": QUESTION_TYPE_MCQ,
            "options": q.options,
            "your_index": given,
            "your_answer": q.options[given] if given is not None else None,
            "correct_index": q.correct_index,
            "correct_answer": q.options[q.correct_index],
            "correct": is_correct,
            "awarded": q.marks if is_correct else 0,
            "graded_by": "auto",
            "explanation": q.explanation,
            "topic": q.topic,
            "marks": q.marks,
        })

    marks_total = sum(q.marks for q in scorable)
    score = round(marks_earned / marks_total * 100) if marks_total else 0
    passed = score >= test.pass_threshold

    # Integrity review. Runs before the insert so the verdict is stored with the
    # attempt in one write, and is wrapped because a proctoring failure must
    # never cost someone a completed exam.
    proctoring = None
    if test.proctoring_enabled:
        try:
            proctoring = await build_proctor_report(
                raw_events=[e.model_dump() for e in (body.proctor_events or [])],
                questions=scorable,
                text_answers=body.text_answers,
                elapsed_seconds=body.elapsed_seconds,
                client_reported=body.proctor_events is not None,
            )
        except Exception:  # noqa: BLE001 — no verdict is better than a lost submit
            proctoring = None

    started_at = None
    if body.elapsed_seconds and body.elapsed_seconds > 0:
        started_at = datetime.now(timezone.utc) - timedelta(
            seconds=min(body.elapsed_seconds, 24 * 3600)
        )

    attempt = TestAttempt(
        test_id=test.id,
        user_id=user.id,
        answers={q.id: body.answers.get(q.id) for q in scorable if not q.is_written},
        text_answers={
            q.id: (body.text_answers.get(q.id) or "").strip()
            for q in scorable if q.is_written
        },
        ai_graded=ai_graded,
        ungraded_question_ids=ungraded,
        breakdown=breakdown,
        score=score,
        marks_earned=marks_earned,
        marks_total=marks_total,
        correct_count=correct_count,
        total_questions=len(scorable),
        passed=passed,
        proctoring=proctoring,
        started_at=started_at,
    )
    await attempt.insert()

    # Reuse the existing quiz reward actions so tests feed badges/XP/levels.
    rewards = None
    if passed:
        gamification = GamificationService(redis)
        pass_reward = await gamification.reward(
            user.id, "pass_quiz", user.department or "",
            ref_type="test_series", ref_id=test.id,
        )
        badges = await gamification.check_and_award_badges(user.id, "pass_quiz")
        perfect_reward = None
        if score == 100:
            perfect_reward = await gamification.reward(
                user.id, "perfect_quiz", user.department or "",
                ref_type="test_series", ref_id=test.id,
            )
        rewards = {
            "pass": pass_reward,
            "perfect_quiz": perfect_reward,
            "badges_unlocked": badges,
        }

    return {
        "attempt_id": attempt.id,
        "score": score,
        "passed": passed,
        "pass_threshold": test.pass_threshold,
        "marks_earned": marks_earned,
        "marks_total": marks_total,
        "correct_count": correct_count,
        "total_questions": len(scorable),
        "ai_graded": ai_graded,
        "ungraded_count": len(ungraded),
        "breakdown": breakdown,
        "topic_stats": _topic_stats(breakdown),
        "rewards": rewards,
        # The learner is told the attempt was monitored and how many signals
        # were logged, but not the risk verdict — that is for the admin to act
        # on, and showing a score here just teaches people what to evade.
        "proctored": proctoring is not None,
        "proctor_flag_count": len(proctoring.findings) if proctoring else 0,
    }


@router.get("/test-series/attempts/me")
async def my_attempts(user: Annotated[User, Depends(get_current_user)]):
    attempts = await TestAttempt.find(TestAttempt.user_id == user.id).sort(
        -TestAttempt.submitted_at
    ).to_list()
    test_ids = list({a.test_id for a in attempts})
    titles = {
        t.id: t.title
        for t in (await TestSeries.find(In(TestSeries.id, test_ids)).to_list() if test_ids else [])
    }
    return [
        {
            "attempt_id": a.id,
            "test_id": a.test_id,
            "test_title": titles.get(a.test_id, "(deleted test)"),
            "score": a.score,
            "passed": a.passed,
            "correct_count": a.correct_count,
            "total_questions": a.total_questions,
            "submitted_at": a.submitted_at,
        }
        for a in attempts
    ]


@router.get("/test-series/attempts/{attempt_id}")
async def get_attempt(
    attempt_id: str, user: Annotated[User, Depends(get_current_user)]
):
    """Reviewable result. Own attempts only, unless admin."""
    attempt = await TestAttempt.get(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if attempt.user_id != user.id and user.role not in ("admin", "ld_lead"):
        raise HTTPException(status_code=403, detail="Not your attempt")

    test = await TestSeries.get(attempt.test_id)
    is_admin = user.role in ("admin", "ld_lead")

    # The learner is told their attempt was monitored; the risk verdict and the
    # event timeline go to admins only. Handing someone their own score for
    # "how suspicious did that look" is a tuning signal for evading it.
    proctoring: dict | None = None
    if attempt.proctoring:
        if is_admin:
            proctoring = _proctor_summary(attempt)
            proctoring["events"] = [
                e.model_dump() for e in attempt.proctoring.events
            ]
        else:
            proctoring = {"proctored": True}

    return {
        "attempt_id": attempt.id,
        "test_id": attempt.test_id,
        "test_title": test.title if test else "(deleted test)",
        "score": attempt.score,
        "passed": attempt.passed,
        "pass_threshold": test.pass_threshold if test else None,
        "marks_earned": attempt.marks_earned,
        "marks_total": attempt.marks_total,
        "correct_count": attempt.correct_count,
        "total_questions": attempt.total_questions,
        "submitted_at": attempt.submitted_at,
        "breakdown": attempt.breakdown,
        "topic_stats": _topic_stats(attempt.breakdown),
        "ai_analysis": attempt.ai_analysis,
        "proctoring": proctoring,
    }


@router.post("/test-series/attempts/{attempt_id}/analysis")
async def get_attempt_analysis(
    attempt_id: str, user: Annotated[User, Depends(get_current_user)]
):
    """
    AI areas-of-improvement for an attempt. Cached on the attempt after the
    first call so re-opening the result page doesn't re-bill the model.
    """
    attempt = await TestAttempt.get(attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if attempt.user_id != user.id and user.role not in ("admin", "ld_lead"):
        raise HTTPException(status_code=403, detail="Not your attempt")

    analysis = await _build_analysis(attempt)
    return {"attempt_id": attempt.id, "ai_analysis": analysis}


async def _build_analysis(attempt: TestAttempt, force: bool = False) -> dict:
    """
    Produce and cache the improvement analysis. Falls back to a deterministic
    summary if the AI is unconfigured or errors, so this endpoint never 500s on
    a working attempt.
    """
    if attempt.ai_analysis and not force:
        return attempt.ai_analysis

    topic_stats = _topic_stats(attempt.breakdown)
    test = await TestSeries.get(attempt.test_id)
    learner = await User.get(attempt.user_id)

    analysis: dict
    if ai_service.enabled:
        try:
            analysis = await ai_service.analyze_test_performance(
                test_title=test.title if test else "Test",
                learner={
                    "full_name": learner.full_name if learner else None,
                    "role": learner.role if learner else None,
                    "department": learner.department if learner else None,
                },
                score=attempt.score,
                correct_count=attempt.correct_count,
                total_questions=attempt.total_questions,
                passed=attempt.passed,
                breakdown=attempt.breakdown,
                topic_stats=topic_stats,
            )
            analysis["generated_by"] = "ai"
        except Exception:  # noqa: BLE001 - never fail the request over the model
            analysis = fallback_analysis(attempt.score, attempt.passed, topic_stats)
    else:
        analysis = fallback_analysis(attempt.score, attempt.passed, topic_stats)

    attempt.ai_analysis = analysis
    await attempt.save()
    return analysis
