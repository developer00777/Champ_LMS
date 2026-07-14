from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from beanie.operators import In
from datetime import datetime, timezone, timedelta
from app.core.auth import get_current_user
from app.core.redis import get_redis
from app.models.user import User
from app.models.gamification import Badge, UserBadge
from app.models.xp_event import XpEvent
from app.models.quest import Quest, UserQuest
from app.models.progress import WatchProgress
from app.models.assessment import AssessmentAttempt
from app.models.module import Module
from app.models.enrollment import Enrollment
from app.models.episode import Episode
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
        "xp": user.xp,
        "level": user.level,
        "tier": User.tier_name(user.level),
    }


@router.get("/me/level")
async def my_level(user: Annotated[User, Depends(get_current_user)]):
    next_threshold = (user.level + 1) ** 2 * 50
    current_threshold = user.level ** 2 * 50
    return {
        "xp": user.xp,
        "level": user.level,
        "tier": User.tier_name(user.level),
        "next_level_xp": next_threshold,
        "current_level_xp": current_threshold,
        "xp_to_next_level": max(0, next_threshold - user.xp),
    }


@router.get("/me/xp-history")
async def my_xp_history(
    user: Annotated[User, Depends(get_current_user)],
    limit: int = 50,
):
    events = await (
        XpEvent.find(XpEvent.user_id == user.id)
        .sort(-XpEvent.created_at)
        .limit(limit)
        .to_list()
    )
    return [
        {
            "amount": e.amount,
            "reason": e.reason,
            "ref_type": e.ref_type,
            "ref_id": e.ref_id,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


def _period_bounds(scope: str) -> tuple[str, datetime, datetime]:
    """Return (period_key, start, end) for the current daily/weekly period."""
    now = datetime.now(timezone.utc)
    if scope == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return now.strftime("%Y-%m-%d"), start, end
    # weekly: ISO week
    iso_cal = now.isocalendar()
    period_key = f"{iso_cal.year}-W{iso_cal.week:02d}"
    start = now - timedelta(days=now.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return period_key, start, end


async def _compute_quest_progress(user_id: str, quest: Quest) -> tuple[int, int]:
    """Return (progress, target) for a quest against live user data."""
    criteria = quest.criteria or {}
    qtype = criteria.get("type")
    target = criteria.get("count", 1)

    if qtype == "watch_episodes":
        _, start, end = _period_bounds(quest.scope)
        progress = await WatchProgress.find(
            WatchProgress.user_id == user_id,
            WatchProgress.completed == True,  # noqa: E712
            WatchProgress.completed_at >= start,
            WatchProgress.completed_at < end,
        ).count()
        return progress, target

    if qtype == "pass_quiz":
        _, start, end = _period_bounds(quest.scope)
        progress = await AssessmentAttempt.find(
            AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.passed == True,  # noqa: E712
            AssessmentAttempt.attempted_at >= start,
            AssessmentAttempt.attempted_at < end,
        ).count()
        return progress, target

    if qtype == "record_activity":
        _, start, end = _period_bounds(quest.scope)
        user = await User.get(user_id)
        if not user or not user.last_activity_at:
            return 0, target
        if start <= user.last_activity_at < end:
            return 1, target
        return 0, target

    if qtype == "complete_module_category":
        _, start, end = _period_bounds(quest.scope)
        user = await User.get(user_id)
        category = criteria.get("category") or (user.department if user else None)
        if not category:
            return 0, target
        enrollments = await Enrollment.find(
            Enrollment.user_id == user_id,
            Enrollment.completed_at != None,  # noqa: E711
            Enrollment.completed_at >= start,
            Enrollment.completed_at < end,
        ).to_list()
        module_ids = [e.module_id for e in enrollments]
        if not module_ids:
            return 0, target
        modules = {m.id: m for m in await Module.find(In(Module.id, module_ids)).to_list()}
        progress = sum(1 for mid in module_ids if modules.get(mid) and modules[mid].category == category)
        return progress, target

    if qtype == "complete_module_role":
        _, start, end = _period_bounds(quest.scope)
        user = await User.get(user_id)
        user_dept = user.department if user else None
        if not user_dept:
            return 0, target
        enrollments = await Enrollment.find(
            Enrollment.user_id == user_id,
            Enrollment.completed_at != None,  # noqa: E711
            Enrollment.completed_at >= start,
            Enrollment.completed_at < end,
        ).to_list()
        module_ids = [e.module_id for e in enrollments]
        if not module_ids:
            return 0, target
        modules = {m.id: m for m in await Module.find(In(Module.id, module_ids)).to_list()}
        progress = sum(
            1 for mid in module_ids
            if modules.get(mid) and (
                modules[mid].target_department == user_dept
                or (modules[mid].target_roles and user_dept in modules[mid].target_roles)
            )
        )
        return progress, target

    if qtype == "watch_zoom_module":
        _, start, end = _period_bounds(quest.scope)
        completed_watches = await WatchProgress.find(
            WatchProgress.user_id == user_id,
            WatchProgress.completed == True,  # noqa: E712
            WatchProgress.completed_at >= start,
            WatchProgress.completed_at < end,
        ).to_list()
        episode_ids = [w.episode_id for w in completed_watches]
        if not episode_ids:
            return 0, target
        episodes = {e.id: e for e in await Episode.find(In(Episode.id, episode_ids)).to_list()}
        module_ids = {e.module_id for e in episodes.values()}
        if not module_ids:
            return 0, target
        zoom_modules = await Module.find(
            In(Module.id, list(module_ids)),
            Module.source_type == "zoom",
        ).count()
        return min(zoom_modules, target), target

    return 0, target


@router.get("/quests/me")
async def my_quests(
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    """Return the current period's quests with live progress."""
    active_quests = await Quest.find(Quest.active == True).to_list()
    result = []
    now = datetime.now(timezone.utc)
    svc = GamificationService(redis)

    for quest in active_quests:
        period_key, _, _ = _period_bounds(quest.scope)
        progress, target = await _compute_quest_progress(user.id, quest)
        completed = progress >= target

        user_quest = await UserQuest.find_one(
            UserQuest.user_id == user.id,
            UserQuest.quest_id == quest.id,
            UserQuest.period_key == period_key,
        )
        quest_rewarded = False
        if not user_quest:
            user_quest = UserQuest(
                user_id=user.id,
                quest_id=quest.id,
                period_key=period_key,
                progress=progress,
                target=target,
                completed=completed,
                completed_at=now if completed else None,
            )
            await user_quest.insert()
            if completed:
                quest_rewarded = await _grant_quest_reward(svc, user, quest)
        else:
            was_completed = user_quest.completed
            if user_quest.progress != progress or user_quest.completed != completed:
                user_quest.progress = progress
                user_quest.completed = completed
                if completed and not user_quest.completed_at:
                    user_quest.completed_at = now
                await user_quest.save()
            # * Grant reward only on the transition from not-completed to completed
            if completed and not was_completed:
                quest_rewarded = await _grant_quest_reward(svc, user, quest)

        result.append({
            "quest_id": quest.id,
            "key": quest.key,
            "scope": quest.scope,
            "title": quest.title,
            "period_key": period_key,
            "progress": progress,
            "target": target,
            "completed": completed,
            "completed_at": user_quest.completed_at.isoformat() if user_quest.completed_at else None,
            "reward_xp": quest.reward_xp,
            "reward_points": quest.reward_points,
            "just_rewarded": quest_rewarded,
        })

    return result


async def _grant_quest_reward(svc: GamificationService, user: User, quest: Quest) -> bool:
    """Award quest XP and points. Uses a Redis SETNX lock for idempotency."""
    from app.core.redis import get_redis
    redis = await get_redis()
    period_key = _period_bounds(quest.scope)[0]
    lock_key = f"quest:rewarded:{user.id}:{quest.id}:{period_key}"
    acquired = await redis.set(lock_key, "1", nx=True, ex=86400 * 7)
    if not acquired:
        return False
    if quest.reward_xp > 0:
        await svc.award_xp_amount(
            user.id, "quest_complete", quest.reward_xp,
            ref_type="quest", ref_id=f"{quest.id}:{period_key}",
        )
    if quest.reward_points > 0:
        await svc.award_points_amount(user.id, quest.reward_points, user.department or "")
    return True


@router.get("/leaderboard/modules/{module_id}")
async def module_leaderboard(
    module_id: str,
    user: Annotated[User, Depends(get_current_user)],
    department: str | None = None,
    limit: int = 20,
):
    """
    Rank users who completed this module. Optional department filter.
    Useful for department competitions on a specific upskilling track.
    """
    module = await Module.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    filters = [Enrollment.module_id == module_id, Enrollment.completed_at != None]  # noqa: E711
    enrollments = await (
        Enrollment.find(*filters)
        .sort(+Enrollment.completed_at)
        .limit(limit * 3)
        .to_list()
    )

    user_ids = [e.user_id for e in enrollments]
    users = {u.id: u for u in await User.find(In(User.id, user_ids)).to_list()}

    result = []
    rank = 0
    for e in enrollments:
        u = users.get(e.user_id)
        if not u:
            continue
        if department and u.department != department:
            continue
        rank += 1
        if rank > limit:
            break
        result.append({
            "rank": rank,
            "user_id": u.id,
            "full_name": u.full_name,
            "department": u.department,
            "points": u.points,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        })

    return {
        "module_id": module_id,
        "module_title": module.title,
        "department": department,
        "entries": result,
    }


class ShareAchievementBody(BaseModel):
    type: str  # module_mastery | badge
    ref_id: str


@router.post("/share/achievement")
async def share_achievement(
    body: ShareAchievementBody,
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Build a shareable achievement card for the current user.
    Frontend can pass this payload to the Web Share API or render an OG-style card.
    """
    if body.type == "module_mastery":
        enrollment = await Enrollment.find_one(
            Enrollment.user_id == user.id,
            Enrollment.module_id == body.ref_id,
            Enrollment.completed_at != None,  # noqa: E711
        )
        if not enrollment:
            raise HTTPException(status_code=404, detail="Module completion not found")
        module = await Module.get(body.ref_id)
        if not module:
            raise HTTPException(status_code=404, detail="Module not found")
        return {
            "type": "module_mastery",
            "user_name": user.full_name,
            "user_department": user.department,
            "title": f"Mastered: {module.title}",
            "description": module.description or f"{user.full_name or 'A learner'} mastered {module.title} on Champ LMS.",
            "module_id": module.id,
            "module_category": module.category,
            "earned_at": enrollment.completed_at.isoformat() if enrollment.completed_at else None,
            "share_text": f"I mastered '{module.title}' on Champ LMS! 🏆 Level {user.level} · {user.points} pts",
        }

    if body.type == "badge":
        user_badge = await UserBadge.find_one(
            UserBadge.user_id == user.id,
            UserBadge.badge_id == body.ref_id,
        )
        if not user_badge:
            raise HTTPException(status_code=404, detail="Badge not found")
        badge = await Badge.get(body.ref_id)
        if not badge:
            raise HTTPException(status_code=404, detail="Badge not found")
        return {
            "type": "badge",
            "user_name": user.full_name,
            "user_department": user.department,
            "title": f"Earned: {badge.name}",
            "description": badge.description or f"{user.full_name or 'A learner'} earned the {badge.name} badge on Champ LMS.",
            "badge_id": badge.id,
            "earned_at": user_badge.earned_at.isoformat(),
            "share_text": f"I earned the {badge.name} badge on Champ LMS! 🎖️",
        }

    raise HTTPException(status_code=400, detail="Unsupported share type")


@router.get("/activity/recent")
async def recent_activity(
    user: Annotated[User, Depends(get_current_user)],
    department: str | None = None,
    limit: int = 20,
):
    """
    Social activity feed: recent module completions + badge unlocks.
    Filter by department to create a department hall-of-fame.
    """
    enrollments = await (
        Enrollment.find(Enrollment.completed_at != None)  # noqa: E711
        .sort(-Enrollment.completed_at)
        .limit(limit * 2)
        .to_list()
    )
    user_ids = list({e.user_id for e in enrollments})
    users = {u.id: u for u in await User.find(In(User.id, user_ids)).to_list()}

    items = []
    for e in enrollments:
        u = users.get(e.user_id)
        if not u:
            continue
        if department and u.department != department:
            continue
        module = await Module.get(e.module_id)
        items.append({
            "type": "module_completion",
            "user_id": u.id,
            "full_name": u.full_name,
            "department": u.department,
            "module_id": e.module_id,
            "module_title": module.title if module else "Unknown",
            "module_category": module.category if module else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        })

    # Sort merged activity by timestamp and cap
    items.sort(key=lambda x: x["completed_at"], reverse=True)
    return {"entries": items[:limit]}


@router.get("/me/upselling-track")
async def my_upselling_track(
    user: Annotated[User, Depends(get_current_user)],
    category: str | None = None,
):
    """
    Templatized upskilling track for the learner's department/role.
    Returns a structured track the frontend renders from a fixed component registry.
    If no category is provided, the user's department is used.
    """
    track_category = (category or user.department or "general").lower()

    # Match modules by explicit category OR target_department OR target_roles containing user's role/department
    filters = [Module.is_published == True]  # noqa: E712
    or_conditions = [
        Module.category == track_category,
        Module.target_department == track_category,
    ]
    if user.department:
        or_conditions.append(In(Module.target_roles, [user.department]))

    from beanie.operators import Or
    filters.append(Or(*or_conditions))

    modules = await Module.find(*filters).sort(-Module.created_at).to_list()

    # Pull learner progress for these modules
    module_ids = [m.id for m in modules]
    enrollments = {
        e.module_id: e
        for e in await Enrollment.find(
            Enrollment.user_id == user.id,
            In(Enrollment.module_id, module_ids),
        ).to_list()
    }

    total = len(modules)
    completed = sum(1 for m in modules if enrollments.get(m.id) and enrollments[m.id].completion_percentage >= 100)
    mastered = sum(1 for m in modules if enrollments.get(m.id) and enrollments[m.id].completed_at)

    # Department ranking: count mastered modules per department member
    dept_users = await User.find(User.department == user.department).to_list() if user.department else []
    dept_user_ids = [u.id for u in dept_users]
    dept_enrollments = await Enrollment.find(
        In(Enrollment.user_id, dept_user_ids),
        In(Enrollment.module_id, module_ids),
        Enrollment.completed_at != None,  # noqa: E711
    ).to_list()
    mastery_counts: dict[str, int] = {}
    for e in dept_enrollments:
        mastery_counts[e.user_id] = mastery_counts.get(e.user_id, 0) + 1
    sorted_counts = sorted(mastery_counts.values(), reverse=True)
    user_mastery = mastery_counts.get(user.id, 0)
    rank = next((i + 1 for i, c in enumerate(sorted_counts) if c == user_mastery), len(dept_users))

    track_modules = []
    for m in modules:
        e = enrollments.get(m.id)
        progress = e.completion_percentage if e else 0.0
        track_modules.append({
            "module_id": m.id,
            "title": m.title,
            "category": m.category,
            "description": m.description,
            "thumbnail_url": bunny_storage.thumbnail_url(m.thumbnail_bunny_path) if m.thumbnail_bunny_path else None,
            "total_episodes": m.total_episodes,
            "points_weight": m.points_weight,
            "progress": progress,
            "completed": progress >= 100,
            "mastered": bool(e and e.completed_at),
            "status": "mastered" if (e and e.completed_at) else ("completed" if progress >= 100 else ("in_progress" if progress > 0 else "not_started")),
        })

    return {
        "type": "upselling_track",
        "track": track_category,
        "user_department": user.department,
        "total_modules": total,
        "completed_modules": completed,
        "mastered_modules": mastered,
        "mastery_percentage": round((mastered / total) * 100, 2) if total else 0.0,
        "rank_in_department": rank,
        "department_size": len(dept_users),
        "modules": track_modules,
    }
