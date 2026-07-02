"""
Gamification service — points, streaks, leaderboard via Redis sorted sets.
"""
from datetime import datetime, timezone, timedelta
import redis.asyncio as aioredis
from beanie.operators import Set, Inc, In
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
    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis

    async def award_points(self, user_id: str, action: str, department: str) -> int:
        pts = POINTS.get(action, 0)
        if pts == 0:
            return 0

        # Update Redis leaderboards
        await self.redis.zincrby("leaderboard:global", pts, user_id)
        if department:
            await self.redis.zincrby(f"leaderboard:dept:{department}", pts, user_id)

        # Persist to DB — atomic increment, mirrors the old SQL `points = points + pts`
        user = await User.get(user_id)
        if user:
            await user.update(Inc({User.points: pts}))
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
        user = await User.get(user_id)
        if user:
            await user.update(
                Set({User.streak_days: streak, User.last_activity_at: datetime.now(timezone.utc)})
            )

        if streak == 7:
            await self.award_points(user_id, "streak_7day", "")

        return streak

    async def get_leaderboard(self, department: str | None = None, limit: int = 10) -> list[dict]:
        key = f"leaderboard:dept:{department}" if department else "leaderboard:global"
        entries = await self.redis.zrevrange(key, 0, limit - 1, withscores=True)
        if not entries:
            return []

        user_ids = [user_id for user_id, _ in entries]
        users = {u.id: u for u in await User.find(In(User.id, user_ids)).to_list()}

        result = []
        for rank, (user_id, score) in enumerate(entries, 1):
            user = users.get(user_id)
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
        badges = await Badge.find_all().to_list()

        for badge in badges:
            if not badge.criteria:
                continue
            if badge.criteria.get("type") != action:
                continue

            # Check if already earned
            existing = await UserBadge.find_one(
                UserBadge.user_id == user_id,
                UserBadge.badge_id == badge.id,
            )
            if existing:
                continue

            await UserBadge(user_id=user_id, badge_id=badge.id).insert()
            earned.append(badge.name)

        return earned
