from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.auth import get_current_user
from app.core.redis import get_redis
from app.models.user import User
from app.models.progress import WatchProgress
from app.services.gamification_service import GamificationService
import redis.asyncio as aioredis

router = APIRouter(prefix="/progress", tags=["progress"])


class ProgressUpdate(BaseModel):
    episode_id: str
    watched_seconds: int
    total_seconds: int


@router.post("")
async def upsert_progress(
    body: ProgressUpdate,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    # Cache progress in Redis (key expires in 2 min — flushed by 30s player sync)
    cache_key = f"progress:{user.id}:{body.episode_id}"
    await redis.setex(cache_key, 120, f"{body.watched_seconds}:{body.total_seconds}")

    # Determine completion (≥90% watched)
    completed = body.watched_seconds >= body.total_seconds * 0.9

    wp = await WatchProgress.find_one(
        WatchProgress.user_id == user.id,
        WatchProgress.episode_id == body.episode_id,
    )

    if wp:
        wp.watched_seconds = max(wp.watched_seconds, body.watched_seconds)
        wp.total_seconds = body.total_seconds
        wp.last_watched_at = datetime.now(timezone.utc)
        if completed and not wp.completed:
            wp.completed = True
            wp.completed_at = datetime.now(timezone.utc)
            # Award points on first completion
            gamification = GamificationService(redis)
            await gamification.award_points(user.id, "complete_episode", user.department or "")
            await gamification.record_activity(user.id)
            await gamification.check_and_award_badges(user.id, "complete_episode")
        await wp.save()
    else:
        wp = WatchProgress(
            user_id=user.id,
            episode_id=body.episode_id,
            watched_seconds=body.watched_seconds,
            total_seconds=body.total_seconds,
            completed=completed,
            completed_at=datetime.now(timezone.utc) if completed else None,
        )
        await wp.insert()
        if completed:
            gamification = GamificationService(redis)
            await gamification.award_points(user.id, "complete_episode", user.department or "")
            await gamification.record_activity(user.id)

    return {"completed": completed, "watched_seconds": body.watched_seconds}


@router.get("/me")
async def my_progress(user: Annotated[User, Depends(get_current_user)]):
    progress = await WatchProgress.find(WatchProgress.user_id == user.id).sort(-WatchProgress.last_watched_at).to_list()
    return [
        {
            "episode_id": p.episode_id,
            "watched_seconds": p.watched_seconds,
            "total_seconds": p.total_seconds,
            "completed": p.completed,
            "last_watched_at": p.last_watched_at.isoformat() if p.last_watched_at else None,
        }
        for p in progress
    ]


@router.get("/{episode_id}")
async def episode_progress(
    episode_id: str,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    # Check Redis cache first
    cache_key = f"progress:{user.id}:{episode_id}"
    cached = await redis.get(cache_key)
    if cached:
        watched, total = cached.split(":")
        return {"episode_id": episode_id, "watched_seconds": int(watched), "total_seconds": int(total)}

    wp = await WatchProgress.find_one(
        WatchProgress.user_id == user.id,
        WatchProgress.episode_id == episode_id,
    )
    if not wp:
        return {"episode_id": episode_id, "watched_seconds": 0, "total_seconds": 0}
    return {
        "episode_id": episode_id,
        "watched_seconds": wp.watched_seconds,
        "total_seconds": wp.total_seconds,
        "completed": wp.completed,
    }
