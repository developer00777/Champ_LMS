import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.auth import get_current_user_dev as get_current_user
from app.models.user import User
from app.models.assessment import Assessment, AssessmentAttempt
from app.schemas.assessment import AssessmentOut, AttemptCreate, AttemptOut
from app.services.gamification_service import award_points, check_and_award_badges

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.get("/{module_id}", response_model=list[AssessmentOut])
async def get_assessments(
    module_id: uuid.UUID,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Assessment).where(Assessment.module_id == module_id)
    )
    return result.scalars().all()


@router.post("/{assessment_id}/attempt", response_model=AttemptOut)
async def submit_attempt(
    assessment_id: uuid.UUID,
    payload: AttemptCreate,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_result = await db.execute(select(User).where(User.cognito_sub == claims["sub"]))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    assess_result = await db.execute(select(Assessment).where(Assessment.id == assessment_id))
    assessment = assess_result.scalar_one_or_none()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Grade the attempt
    correct = 0
    for q_idx, question in enumerate(assessment.questions):
        submitted = payload.answers.get(str(q_idx))
        if submitted is not None and int(submitted) == question.get("correct_index"):
            correct += 1

    total = len(assessment.questions)
    score = int((correct / total) * 100) if total > 0 else 0
    passed = score >= assessment.pass_threshold

    attempt = AssessmentAttempt(
        user_id=user.id,
        assessment_id=assessment_id,
        score=score,
        passed=passed,
        answers=payload.answers,
    )
    db.add(attempt)
    await db.flush()

    if passed:
        await award_points(user.id, "pass_quiz", db)
        await check_and_award_badges(user.id, "pass_quiz", db)

    return attempt
