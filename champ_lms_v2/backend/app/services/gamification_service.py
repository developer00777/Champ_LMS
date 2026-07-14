"""
Gamification service — points, streaks, leaderboard via Redis sorted sets.
"""
from datetime import datetime, timezone, timedelta
import redis.asyncio as aioredis
from beanie.operators import Set, Inc, In
from app.models.user import User
from app.models.gamification import Badge, UserBadge
from app.models.progress import WatchProgress
from app.models.assessment import AssessmentAttempt
from app.models.xp_event import XpEvent
from app.models.quest import Quest
from app.models.enrollment import Enrollment
from app.models.module import Module

POINTS = {
    "complete_episode": 10,
    "complete_module": 50,
    "pass_quiz": 25,
    "perfect_quiz": 15,
    "streak_7day": 100,
    "first_to_complete": 200,
    "quest_complete": 0,  # * variable, set via award_points_amount
}

XP = {
    "complete_episode": 10,
    "complete_module": 50,
    "pass_quiz": 25,
    "perfect_quiz": 15,
    "streak_7day": 100,
    "first_to_complete": 200,
    "module_mastery": 40,
}

# # Badge catalog. Seeded on startup by seed_gamification().
# # criteria.type is matched against the award action that just happened;
# # criteria.count is the threshold checked against the user's REAL progress
# # (see GamificationService._metric_for), not just "the action fired once".
SEED_BADGES = [
    {"name": "First Watch", "description": "Completed your first episode.",
     "criteria": {"type": "complete_episode", "count": 1}},
    {"name": "Getting Hooked", "description": "Completed 10 episodes.",
     "criteria": {"type": "complete_episode", "count": 10}},
    {"name": "Quiz Ace", "description": "Passed 5 quizzes.",
     "criteria": {"type": "pass_quiz", "count": 5}},
    {"name": "5-Day Streak", "description": "Learned 5 days in a row.",
     "criteria": {"type": "streak_days", "count": 5}},
    {"name": "Module Champion", "description": "Completed a full module.",
     "criteria": {"type": "complete_module", "count": 1}},
    {"name": "Mastermind", "description": "Mastered 3 modules (completed + passed quiz).",
     "criteria": {"type": "module_mastery", "count": 3}},
]

SEED_QUESTS = [
    {
        "key": "daily_watch_2",
        "scope": "daily",
        "title": "Watch 2 episodes",
        "criteria": {"type": "watch_episodes", "count": 2},
        "reward_xp": 20,
        "reward_points": 10,
    },
    {
        "key": "daily_pass_quiz",
        "scope": "daily",
        "title": "Pass any quiz",
        "criteria": {"type": "pass_quiz", "count": 1},
        "reward_xp": 25,
        "reward_points": 15,
    },
    {
        "key": "daily_keep_streak",
        "scope": "daily",
        "title": "Keep your streak alive",
        "criteria": {"type": "record_activity", "count": 1},
        "reward_xp": 10,
        "reward_points": 5,
    },
    {
        "key": "weekly_complete_category",
        "scope": "weekly",
        "title": "Complete a module in your domain",
        "criteria": {"type": "complete_module_category", "count": 1},
        "reward_xp": 50,
        "reward_points": 30,
    },
    {
        "key": "weekly_complete_role",
        "scope": "weekly",
        "title": "Master a module for your role",
        "criteria": {"type": "complete_module_role", "count": 1},
        "reward_xp": 60,
        "reward_points": 40,
    },
    {
        "key": "weekly_fresh_zoom",
        "scope": "weekly",
        "title": "Watch a fresh Zoom module",
        "criteria": {"type": "watch_zoom_module", "count": 1},
        "reward_xp": 40,
        "reward_points": 25,
    },
]


async def seed_gamification() -> None:
    """
    Populate the badge catalog and quest catalog. Idempotent: upsert by key/name,
    safe on every startup. Without this the badge engine has nothing to match
    and the quest panel has nothing to show.
    """
    # Badges
    for spec in SEED_BADGES:
        existing = await Badge.find_one(Badge.name == spec["name"])
        if existing:
            # * keep the seeded criteria/description in sync if the catalog changes
            if existing.criteria != spec["criteria"] or existing.description != spec["description"]:
                existing.criteria = spec["criteria"]
                existing.description = spec["description"]
                await existing.save()
            continue
        await Badge(**spec).insert()

    # Quests
    for spec in SEED_QUESTS:
        existing = await Quest.find_one(Quest.key == spec["key"])
        if existing:
            sync_fields = {"title", "criteria", "reward_xp", "reward_points", "active"}
            changed = any(getattr(existing, f) != spec[f] for f in sync_fields)
            if changed:
                for f in sync_fields:
                    setattr(existing, f, spec[f])
                await existing.save()
            continue
        await Quest(**spec).insert()


async def rehydrate_leaderboards(redis: aioredis.Redis) -> None:
    """
    Redis sorted sets are ephemeral; Mongo User.points is the source of truth.
    On boot, replay every user's points into the global + department boards so a
    Redis flush cannot silently wipe the rankings.
    """
    users = await User.find(User.points > 0).to_list()
    for u in users:
        await redis.zadd("leaderboard:global", {u.id: u.points})
        if u.department:
            await redis.zadd(f"leaderboard:dept:{u.department}", {u.id: u.points})


class GamificationService:
    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis

    async def award_points(self, user_id: str, action: str, department: str, multiplier: float = 1.0) -> int:
        pts = int(POINTS.get(action, 0) * multiplier)
        return await self._award_points_amount(user_id, pts, department)

    async def award_points_amount(self, user_id: str, pts: int, department: str) -> int:
        return await self._award_points_amount(user_id, pts, department)

    async def _award_points_amount(self, user_id: str, pts: int, department: str) -> int:
        if pts <= 0:
            return 0
        await self.redis.zincrby("leaderboard:global", pts, user_id)
        if department:
            await self.redis.zincrby(f"leaderboard:dept:{department}", pts, user_id)
        user = await User.get(user_id)
        if user:
            await user.update(Inc({User.points: pts}))
        return pts

    async def award_xp(
        self,
        user_id: str,
        reason: str,
        ref_type: str | None = None,
        ref_id: str | None = None,
    ) -> dict:
        """
        Award XP idempotently using the XpEvent ledger.
        Returns {amount, total_xp, level_up, new_level, new_tier}.
        """
        amount = XP.get(reason, 0)
        return await self._award_xp_amount(user_id, reason, amount, ref_type, ref_id)

    async def award_xp_amount(
        self,
        user_id: str,
        reason: str,
        amount: int,
        ref_type: str | None = None,
        ref_id: str | None = None,
    ) -> dict:
        """Award a custom amount of XP (e.g. quest rewards with variable amounts)."""
        return await self._award_xp_amount(user_id, reason, amount, ref_type, ref_id)

    async def _award_xp_amount(
        self,
        user_id: str,
        reason: str,
        amount: int,
        ref_type: str | None = None,
        ref_id: str | None = None,
    ) -> dict:
        if amount == 0:
            return {"amount": 0, "total_xp": 0, "level_up": False, "new_level": 1, "new_tier": "Rookie"}

        # Idempotency guard: one ledger row per (user, reason, ref)
        existing = await XpEvent.find_one(
            XpEvent.user_id == user_id,
            XpEvent.reason == reason,
            XpEvent.ref_id == (ref_id or ""),
        )
        if existing:
            user = await User.get(user_id)
            return {
                "amount": 0,
                "total_xp": user.xp if user else 0,
                "level_up": False,
                "new_level": user.level if user else 1,
                "new_tier": User.tier_name(user.level) if user else "Rookie",
            }

        await XpEvent(
            user_id=user_id,
            amount=amount,
            reason=reason,
            ref_type=ref_type,
            ref_id=ref_id or "",
        ).insert()

        # Atomic XP increment on User
        user = await User.get(user_id)
        if user:
            await user.update(Inc({User.xp: amount}))
            user_db = await User.get(user_id)
            new_level = User.compute_level(user_db.xp)
            level_up = new_level > user_db.level
            if level_up:
                await user_db.update(Set({User.level: new_level}))
                user_db.level = new_level
            return {
                "amount": amount,
                "total_xp": user_db.xp,
                "level_up": level_up,
                "new_level": user_db.level,
                "new_tier": User.tier_name(user_db.level),
            }

        return {"amount": amount, "total_xp": amount, "level_up": False, "new_level": 1, "new_tier": "Rookie"}

    async def reward(
        self,
        user_id: str,
        action: str,
        department: str,
        ref_type: str | None = None,
        ref_id: str | None = None,
        multiplier: float = 1.0,
    ) -> dict:
        """
        Award both leaderboard points and XP for a single action.
        multiplier is applied to points only (XP is always base progression).
        Returns a merged rewards payload.
        """
        points = await self.award_points(user_id, action, department, multiplier=multiplier)
        xp_info = await self.award_xp(user_id, action, ref_type=ref_type, ref_id=ref_id)
        return {
            "points": points,
            "xp": xp_info["amount"],
            "total_xp": xp_info["total_xp"],
            "level_up": xp_info["level_up"],
            "new_level": xp_info["new_level"],
            "new_tier": xp_info["new_tier"],
        }

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

        # ! streak badges (e.g. 5-Day Streak) only get evaluated here — the watch/
        # ! quiz hooks never pass action="streak_days", so this call is required.
        await self.check_and_award_badges(user_id, "streak_days")

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

    async def _metric_for(self, user_id: str, action: str) -> int:
        """The user's current progress count for a given action type."""
        if action == "complete_episode":
            return await WatchProgress.find(
                WatchProgress.user_id == user_id, WatchProgress.completed == True  # noqa: E712
            ).count()
        if action == "pass_quiz":
            return await AssessmentAttempt.find(
                AssessmentAttempt.user_id == user_id, AssessmentAttempt.passed == True  # noqa: E712
            ).count()
        if action == "streak_days":
            user = await User.get(user_id)
            return user.streak_days if user else 0
        if action == "complete_module":
            return await Enrollment.find(
                Enrollment.user_id == user_id,
                Enrollment.completion_percentage >= 100,
            ).count()
        if action == "module_mastery":
            return await Enrollment.find(
                Enrollment.user_id == user_id,
                Enrollment.completed_at != None,  # noqa: E711
            ).count()
        return 0

    async def check_and_award_badges(self, user_id: str, action: str) -> list[str]:
        """
        Award any badges whose criteria.type == action once the user's real metric
        reaches criteria.count. Returns the names of newly earned badges.
        """
        earned: list[str] = []
        metric = await self._metric_for(user_id, action)

        for badge in await Badge.find_all().to_list():
            criteria = badge.criteria or {}
            if criteria.get("type") != action:
                continue
            if metric < criteria.get("count", 1):
                continue

            # * the UserBadge unique (user_id, badge_id) index is the real idempotency guard
            existing = await UserBadge.find_one(
                UserBadge.user_id == user_id,
                UserBadge.badge_id == badge.id,
            )
            if existing:
                continue

            await UserBadge(user_id=user_id, badge_id=badge.id).insert()
            earned.append(badge.name)

        return earned
