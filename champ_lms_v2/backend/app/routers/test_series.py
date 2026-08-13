"""
Test series router.

Admin flow:  upload a Q&A PDF -> review/edit the parsed draft -> publish ->
             see every learner's score, their answers, and AI-generated
             areas of improvement.
Learner flow: list published tests -> take the interactive questionnaire ->
             get scored instantly, with answers and AI feedback.
"""
from typing import Annotated, Any

import redis.asyncio as aioredis
from beanie.operators import In
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.auth import get_current_user, require_admin
from app.core.redis import get_redis
from app.models.test_series import TestAttempt, TestQuestion, TestSeries
from app.models.user import User
from app.services.ai_service import ai_service, fallback_analysis
from app.services.gamification_service import GamificationService
from app.services.pdf_quiz_parser import PdfParseError, parse_pdf

router = APIRouter(tags=["test-series"])

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10MB — a question paper is text, not media


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class QuestionIn(BaseModel):
    id: str | None = None
    question: str
    options: list[str]
    correct_index: int | None = None
    explanation: str | None = None
    topic: str | None = None
    marks: int = 1


class TestUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    department: str | None = None
    pass_threshold: int | None = Field(default=None, ge=1, le=100)
    duration_minutes: int | None = None
    max_attempts: int | None = None
    shuffle_questions: bool | None = None
    questions: list[QuestionIn] | None = None


class TestCreateIn(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    department: str | None = None
    pass_threshold: int = Field(default=70, ge=1, le=100)
    duration_minutes: int | None = None
    max_attempts: int | None = None
    questions: list[QuestionIn] = Field(default_factory=list)


class SubmitIn(BaseModel):
    # {question_id: selected_option_index}; omit or null for skipped
    answers: dict[str, int | None]


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
                "options": q.options,
                "correct_index": q.correct_index,
                "explanation": q.explanation,
                "topic": q.topic,
                "marks": q.marks,
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


def _questions_from_in(items: list[QuestionIn]) -> list[TestQuestion]:
    out: list[TestQuestion] = []
    for q in items:
        kwargs: dict[str, Any] = {
            "question": q.question,
            "options": [o for o in q.options if o.strip()],
            "correct_index": q.correct_index,
            "explanation": q.explanation,
            "topic": q.topic,
            "marks": max(1, q.marks),
        }
        if q.id:
            kwargs["id"] = q.id
        out.append(TestQuestion(**kwargs))
    return out


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
    Parse a Q&A PDF into draft questions WITHOUT saving anything.
    The admin reviews the result and then POSTs it to /admin/test-series.

    Deterministic parser runs first; `use_ai` (or a pattern parse that found
    nothing) routes to the AI parser for unusual layouts.
    """
    if file.content_type and "pdf" not in file.content_type.lower():
        raise HTTPException(status_code=415, detail="Upload a PDF file")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF too large ({len(data) // 1024 // 1024}MB). Limit is 10MB.",
        )

    try:
        questions, text = parse_pdf(data)
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
                        "Could not detect any questions in this PDF, and AI parsing "
                        "is unavailable (OPENROUTER_API_KEY not set). Check the PDF "
                        "format or add questions manually."
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
                            options=[str(o) for o in (r.get("options") or [])],
                            correct_index=r.get("correct_index"),
                            explanation=r.get("explanation"),
                            topic=r.get("topic"),
                            marks=int(r.get("marks") or 1),
                        )
                        for r in raw
                        if str(r.get("question", "")).strip()
                        and len(r.get("options") or []) >= 2
                    ]
                )
                # * only take the AI result if it actually did better
                if ai_questions and (use_ai or len(ai_questions) > len(questions)):
                    questions, parser_used = ai_questions, "ai"
            except Exception as exc:  # noqa: BLE001 - degrade to pattern result
                if not questions:
                    raise HTTPException(
                        status_code=502,
                        detail=f"AI parsing failed and no questions were detected: {exc}",
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
                "options": q.options,
                "correct_index": q.correct_index,
                "explanation": q.explanation,
                "topic": q.topic,
                "marks": q.marks,
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
    from datetime import datetime, timezone

    test = await _get_test_or_404(test_id)
    data = body.model_dump(exclude_unset=True)

    if "questions" in data and body.questions is not None:
        test.questions = _questions_from_in(body.questions)
    for field in (
        "title", "description", "category", "department", "pass_threshold",
        "duration_minutes", "max_attempts", "shuffle_questions",
    ):
        if field in data:
            setattr(test, field, data[field])

    test.updated_at = datetime.now(timezone.utc)
    await test.save()
    return _admin_view(test)


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
        "questions": [
            {"id": q.id, "question": q.question, "options": q.options,
             "topic": q.topic, "marks": q.marks}
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

    for q in scorable:
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
            "options": q.options,
            "your_index": given,
            "your_answer": q.options[given] if given is not None else None,
            "correct_index": q.correct_index,
            "correct_answer": q.options[q.correct_index],
            "correct": is_correct,
            "explanation": q.explanation,
            "topic": q.topic,
            "marks": q.marks,
        })

    marks_total = sum(q.marks for q in scorable)
    score = round(marks_earned / marks_total * 100) if marks_total else 0
    passed = score >= test.pass_threshold

    attempt = TestAttempt(
        test_id=test.id,
        user_id=user.id,
        answers={q.id: body.answers.get(q.id) for q in scorable},
        breakdown=breakdown,
        score=score,
        marks_earned=marks_earned,
        marks_total=marks_total,
        correct_count=correct_count,
        total_questions=len(scorable),
        passed=passed,
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
        "breakdown": breakdown,
        "topic_stats": _topic_stats(breakdown),
        "rewards": rewards,
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
