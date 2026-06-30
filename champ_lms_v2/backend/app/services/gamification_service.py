"""
Gamification service — points, streaks, leaderboard via Redis sorted sets.
"""
from datetime import datetime, timezone, timedelta
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.user import User
from app.models.gamification import Badge, UserBadge

POINTS = {
    "complete_episode": 10,
    "complete_module": 50,
    "pass_quiz": 25,
    "streak_7day": 100,
    "first_to_complete": 200,
}

BADGE_CRITERIA = {
    "first_watch": {"type": "complete_episode", "count": 1},
    "streak_5": {"type": "streak_days", "count": 5},
    "module_champion": {"type": "complete_module", "count": 1},
    "quiz_ace": {"type": "pass_quiz", "count": 5},
}


class GamificationService:
    def __init__(self, redis: aioredis.Redis, db: AsyncSession) -> None:
        self.redis = redis
        self.db = db

    async def award_points(self, user_id: str, action: str, department: str) -> int:
        pts = POINTS.get(action, 0)
        if pts == 0:
            return 0

        # Update Redis leaderboards
        await self.redis.zincrby("leaderboard:global", pts, user_id)
        if department:
            await self.redis.zincrby(f"leaderboard:dept:{department}", pts, user_id)

        # Persist to DB
        await self.db.execute(
            update(User).where(User.id == user_id).values(points=User.points + pts)
        )
        await self.db.commit()
        return pts

    async def record_activity(self, user_id: str) -> int:
        """
        Update streak using Redis.
        Returns current streak count.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

        last_key = f"last_activity:{user_id}"
        streak_key = f"streak:{user_id}"

        last_date = await self.redis.get(last_key)
        if last_date == today:
            return int(await self.redis.get(streak_key) or 0)

        if last_date == yesterday:
            streak = await self.redis.incr(streak_key)
        else:
            await self.redis.set(streak_key, 1)
            streak = 1

        await self.redis.set(last_key, today)

        # Persist streak to DB
        await self.db.execute(
            update(User).where(User.id == user_id).values(
                streak_days=streak,
                last_activity_at=datetime.now(timezone.utc),
            )
        )
        await self.db.commit()

        if streak == 7:
            await self.award_points(user_id, "streak_7day", "")

        return streak

    async def get_leaderboard(self, department: str | None = None, limit: int = 10) -> list[dict]:
        key = f"leaderboard:dept:{department}" if department else "leaderboard:global"
        entries = await self.redis.zrevrange(key, 0, limit - 1, withscores=True)
        result = []
        for rank, (user_id, score) in enumerate(entries, 1):
            result_obj = await self.db.execute(select(User).where(User.id == user_id))
            user = result_obj.scalar_one_or_none()
            if user:
                result.append({
                    "rank": rank,
                    "user_id": user_id,
                    "full_name": user.full_name,
                    "department": user.department,
                    "points": int(score),
                    "streak_days": user.streak_days,
                })
        return result

    async def check_and_award_badges(self, user_id: str, action: str) -> list[str]:
        """Check badge criteria and award any newly earned badges. Returns badge names earned."""
        earned = []
        result = await self.db.execute(select(Badge))
        badges = result.scalars().all()

        for badge in badges:
            if not badge.criteria:
                continue
            if badge.criteria.get("type") != action:
                continue

            # Check if already earned
            existing = await self.db.execute(
                select(UserBadge).where(
                    UserBadge.user_id == user_id,
                    UserBadge.badge_id == badge.id,
                )
            )
            if existing.scalar_one_or_none():
                continue

            ub = UserBadge(user_id=user_id, badge_id=badge.id)
            self.db.add(ub)
            earned.append(badge.name)

        if earned:
            await self.db.commit()
        return earned
