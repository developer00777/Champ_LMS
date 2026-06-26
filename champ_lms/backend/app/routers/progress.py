import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.auth import get_current_user_dev as get_current_user
from app.models.user import User
from app.models.progress import WatchProgress
from app.models.enrollment import Enrollment
from app.models.episode import Episode
from app.schemas.progress import ProgressUpsert, ProgressOut
from app.services.gamification_service import award_points, update_streak, check_and_award_badges

router = APIRouter(prefix="/progress", tags=["progress"])


@router.post("", response_model=ProgressOut)
async def upsert_progress(
    payload: ProgressUpsert,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.cognito_sub == claims["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    prog_result = await db.execute(
        select(WatchProgress).where(
            WatchProgress.user_id == user.id,
            WatchProgress.episode_id == payload.episode_id,
        )
    )
    progress = prog_result.scalar_one_or_none()

    was_completed = progress.completed if progress else False

    if progress:
        progress.watched_seconds = payload.watched_seconds
        progress.total_seconds = payload.total_seconds
        progress.last_watched_at = datetime.now(timezone.utc)
    else:
        progress = WatchProgress(
            user_id=user.id,
            episode_id=payload.episode_id,
            watched_seconds=payload.watched_seconds,
            total_seconds=payload.total_seconds,
        )
        db.add(progress)

    completion_pct = payload.watched_seconds / payload.total_seconds if payload.total_seconds > 0 else 0
    if completion_pct >= 0.9 and not was_completed:
        progress.completed = True
        progress.completed_at = datetime.now(timezone.utc)
        await award_points(user.id, "complete_episode", db)
        await update_streak(user.id, db)
        await check_and_award_badges(user.id, "complete_episode", db)
        await _update_enrollment_progress(user.id, payload.episode_id, db)

    await db.flush()
    return progress


@router.get("/me", response_model=list[ProgressOut])
async def get_my_progress(
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.cognito_sub == claims["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    prog_result = await db.execute(
        select(WatchProgress)
        .where(WatchProgress.user_id == user.id)
        .order_by(WatchProgress.last_watched_at.desc())
    )
    return prog_result.scalars().all()


@router.get("/{episode_id}", response_model=ProgressOut)
async def get_episode_progress(
    episode_id: uuid.UUID,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.cognito_sub == claims["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    prog_result = await db.execute(
        select(WatchProgress).where(
            WatchProgress.user_id == user.id,
            WatchProgress.episode_id == episode_id,
        )
    )
    progress = prog_result.scalar_one_or_none()
    if not progress:
        raise HTTPException(status_code=404, detail="No progress recorded")
    return progress


async def _update_enrollment_progress(user_id: uuid.UUID, episode_id: uuid.UUID, db: AsyncSession):
    ep_result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = ep_result.scalar_one_or_none()
    if not episode:
        return

    enr_result = await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user_id,
            Enrollment.module_id == episode.module_id,
        )
    )
    enrollment = enr_result.scalar_one_or_none()
    if not enrollment:
        enrollment = Enrollment(user_id=user_id, module_id=episode.module_id)
        db.add(enrollment)
        await db.flush()

    completed_result = await db.execute(
        select(WatchProgress).where(
            WatchProgress.user_id == user_id,
            WatchProgress.completed == True,
        )
    )
    completed_episodes = completed_result.scalars().all()
    ep_ids = {str(p.episode_id) for p in completed_episodes}

    ep_count_result = await db.execute(
        select(Episode).where(Episode.module_id == episode.module_id, Episode.status == "ready")
    )
    total = len(ep_count_result.scalars().all())

    if total > 0:
        completed_in_module = sum(1 for p in completed_episodes if str(p.episode_id) in ep_ids)
        enrollment.completion_percentage = (completed_in_module / total) * 100
        if enrollment.completion_percentage >= 100:
            enrollment.completed_at = datetime.now(timezone.utc)
            await award_points(user_id, "complete_module", db)
