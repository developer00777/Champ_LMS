import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.user import User
from app.models.gamification import Badge, UserBadge
from app.core.redis import get_redis

POINTS = {
    "complete_episode": 10,
    "complete_module": 50,
    "pass_quiz": 25,
    "streak_7": 100,
    "first_complete": 200,
}

BADGE_CRITERIA = {
    "first_watch": {"type": "complete_episode", "count": 1},
    "streak_5": {"type": "streak_days", "count": 5},
    "module_champion": {"type": "complete_module", "count": 1},
    "quiz_ace": {"type": "pass_quiz", "count": 1},
}


async def award_points(user_id: uuid.UUID, action: str, db: AsyncSession) -> int:
    points = POINTS.get(action, 0)
    if not points:
        return 0

    await db.execute(
        update(User).where(User.id == user_id).values(points=User.points + points)
    )

    redis = get_redis()
    await redis.zincrby("leaderboard:global", points, str(user_id))

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user and user.department:
        await redis.zincrby(f"leaderboard:dept:{user.department}", points, str(user_id))

    return points


async def update_streak(user_id: uuid.UUID, db: AsyncSession):
    redis = get_redis()
    streak_key = f"streak:{user_id}"
    last_activity_key = f"streak_last:{user_id}"

    now = datetime.now(timezone.utc)
    last_raw = await redis.get(last_activity_key)

    if last_raw:
        last_dt = datetime.fromisoformat(last_raw)
        diff_days = (now.date() - last_dt.date()).days
        if diff_days == 1:
            await redis.incr(streak_key)
        elif diff_days > 1:
            await redis.set(streak_key, 1)
        # diff_days == 0: same day, no change
    else:
        await redis.set(streak_key, 1)

    await redis.set(last_activity_key, now.isoformat())

    streak = int(await redis.get(streak_key) or 1)
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(streak_days=streak, last_activity_at=now)
    )

    if streak == 7:
        await award_points(user_id, "streak_7", db)

    return streak


async def check_and_award_badges(user_id: uuid.UUID, action: str, db: AsyncSession):
    result = await db.execute(select(Badge))
    badges = result.scalars().all()

    for badge in badges:
        criteria = badge.criteria or {}
        if criteria.get("type") == action:
            existing = await db.execute(
                select(UserBadge).where(
                    UserBadge.user_id == user_id,
                    UserBadge.badge_id == badge.id,
                )
            )
            if not existing.scalar_one_or_none():
                db.add(UserBadge(user_id=user_id, badge_id=badge.id))


async def get_leaderboard(department: str | None = None, limit: int = 10) -> list[dict]:
    redis = get_redis()
    key = f"leaderboard:dept:{department}" if department else "leaderboard:global"
    entries = await redis.zrevrange(key, 0, limit - 1, withscores=True)
    return [{"user_id": uid, "points": int(score)} for uid, score in entries]
