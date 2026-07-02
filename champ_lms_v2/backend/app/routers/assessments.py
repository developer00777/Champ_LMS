from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.core.auth import get_current_user
from app.core.redis import get_redis
from app.models.user import User
from app.models.assessment import Assessment, AssessmentAttempt
from app.services.gamification_service import GamificationService
import redis.asyncio as aioredis

router = APIRouter(prefix="/assessments", tags=["assessments"])


class AttemptBody(BaseModel):
    answers: list[int]  # list of selected option indices


@router.get("/{module_id}")
async def get_assessment(
    module_id: str,
    user: Annotated[User, Depends(get_current_user)],
):
    assessment = await Assessment.find_one(
        Assessment.module_id == module_id,
        Assessment.episode_id == None,
    )
    if not assessment:
        raise HTTPException(status_code=404, detail="No assessment for this module")
    # Don't reveal correct answers to client
    questions_sanitized = [
        {"question": q["question"], "options": q["options"]}
        for q in assessment.questions
    ]
    return {"id": assessment.id, "title": assessment.title, "questions": questions_sanitized}


@router.post("/{assessment_id}/attempt")
async def submit_attempt(
    assessment_id: str,
    body: AttemptBody,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    assessment = await Assessment.get(assessment_id)
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    questions = assessment.questions
    if len(body.answers) != len(questions):
        raise HTTPException(status_code=422, detail="Answer count mismatch")

    correct = sum(
        1 for i, ans in enumerate(body.answers)
        if ans == questions[i].get("correct_index")
    )
    score = int(correct / len(questions) * 100)
    passed = score >= assessment.pass_threshold

    attempt = AssessmentAttempt(
        user_id=user.id,
        assessment_id=assessment_id,
        score=score,
        passed=passed,
        answers=body.answers,
    )
    await attempt.insert()

    if passed:
        gamification = GamificationService(redis)
        await gamification.award_points(user.id, "pass_quiz", user.department or "")
        await gamification.check_and_award_badges(user.id, "pass_quiz")

    feedback = [
        {
            "question": q["question"],
            "your_answer": q["options"][body.answers[i]] if body.answers[i] < len(q["options"]) else None,
            "correct_answer": q["options"][q["correct_index"]],
            "explanation": q.get("explanation"),
            "correct": body.answers[i] == q.get("correct_index"),
        }
        for i, q in enumerate(questions)
    ]

    return {"score": score, "passed": passed, "pass_threshold": assessment.pass_threshold, "feedback": feedback}
