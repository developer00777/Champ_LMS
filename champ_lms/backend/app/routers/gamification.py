from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.auth import get_current_user_dev as get_current_user
from app.core.redis import get_redis
from app.models.user import User
from app.models.gamification import UserBadge, Badge
from app.schemas.gamification import BadgeOut, LeaderboardEntry
from app.services.gamification_service import get_leaderboard

router = APIRouter(tags=["gamification"])


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(
    department: str | None = Query(None),
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entries = await get_leaderboard(department=department)
    result = []
    for rank, entry in enumerate(entries, 1):
        user_result = await db.execute(select(User).where(User.id == entry["user_id"]))
        user = user_result.scalar_one_or_none()
        result.append(LeaderboardEntry(
            rank=rank,
            user_id=entry["user_id"],
            full_name=user.full_name if user else None,
            department=user.department if user else None,
            points=entry["points"],
            streak_days=user.streak_days if user else 0,
        ))
    return result


@router.get("/badges/me", response_model=list[BadgeOut])
async def my_badges(
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.cognito_sub == claims["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        return []

    ub_result = await db.execute(
        select(UserBadge).where(UserBadge.user_id == user.id)
    )
    user_badges = ub_result.scalars().all()

    badges = []
    for ub in user_badges:
        badge_result = await db.execute(select(Badge).where(Badge.id == ub.badge_id))
        badge = badge_result.scalar_one_or_none()
        if badge:
            badges.append(BadgeOut(
                id=badge.id,
                name=badge.name,
                description=badge.description,
                icon_url=badge.icon_url,
                earned_at=ub.earned_at,
            ))
    return badges


@router.get("/streaks/me")
async def my_streak(
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.cognito_sub == claims["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        return {"streak_days": 0, "points": 0}

    redis = get_redis()
    streak = int(await redis.get(f"streak:{user.id}") or user.streak_days)
    return {"streak_days": streak, "points": user.points, "last_activity_at": user.last_activity_at}
