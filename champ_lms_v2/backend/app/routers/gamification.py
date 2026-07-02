from typing import Annotated
from fastapi import APIRouter, Depends
from beanie.operators import In
from app.core.auth import get_current_user
from app.core.redis import get_redis
from app.models.user import User
from app.models.gamification import Badge, UserBadge
from app.services.gamification_service import GamificationService
from app.services.bunny_storage import bunny_storage
import redis.asyncio as aioredis

router = APIRouter(tags=["gamification"])


@router.get("/leaderboard")
async def leaderboard(
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
    department: str | None = None,
    limit: int = 10,
):
    svc = GamificationService(redis)
    return await svc.get_leaderboard(department=department, limit=limit)


@router.get("/badges/me")
async def my_badges(user: Annotated[User, Depends(get_current_user)]):
    user_badges = await UserBadge.find(UserBadge.user_id == user.id).to_list()
    if not user_badges:
        return []
    badge_ids = [ub.badge_id for ub in user_badges]
    badges = {b.id: b for b in await Badge.find(In(Badge.id, badge_ids)).to_list()}
    return [
        {
            "badge_id": ub.id,
            "name": badges[ub.badge_id].name,
            "description": badges[ub.badge_id].description,
            "icon_url": bunny_storage.cdn_url(badges[ub.badge_id].icon_bunny_path)
            if badges[ub.badge_id].icon_bunny_path else None,
            "earned_at": ub.earned_at.isoformat(),
        }
        for ub in user_badges if ub.badge_id in badges
    ]


@router.get("/streaks/me")
async def my_streak(
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    streak_key = f"streak:{user.id}"
    last_key = f"last_activity:{user.id}"
    streak = int(await redis.get(streak_key) or user.streak_days)
    last_activity = await redis.get(last_key)
    return {
        "streak_days": streak,
        "last_activity_date": last_activity,
        "points": user.points,
    }
