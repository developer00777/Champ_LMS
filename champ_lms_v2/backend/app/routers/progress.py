from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.core.auth import get_current_user
from app.core.redis import get_redis
from beanie.operators import In
from app.models.user import User
from app.models.module import Module
from app.models.episode import Episode
from app.models.progress import WatchProgress
from app.models.enrollment import Enrollment
from app.models.assessment import Assessment, AssessmentAttempt
from app.services.gamification_service import GamificationService
import redis.asyncio as aioredis

router = APIRouter(prefix="/progress", tags=["progress"])


class ProgressUpdate(BaseModel):
    episode_id: str
    watched_seconds: int
    total_seconds: int


async def _update_enrollment(user_id: str, module_id: str) -> dict:
    """
    Recompute episode completion for a user/module and upsert Enrollment.
    Returns {completion_percentage, newly_completed}.
    """
    module = await Module.get(module_id)
    total_episodes = module.total_episodes if module else 0

    episodes = await Episode.find(Episode.module_id == module_id).to_list()
    episode_ids = [ep.id for ep in episodes]

    completed_count = await WatchProgress.find(
        WatchProgress.user_id == user_id,
        In(WatchProgress.episode_id, episode_ids),
        WatchProgress.completed == True,  # noqa: E712
    ).count()

    pct = round((completed_count / total_episodes) * 100, 2) if total_episodes else 0.0

    enrollment = await Enrollment.find_one(
        Enrollment.user_id == user_id,
        Enrollment.module_id == module_id,
    )
    newly_completed = False
    now = datetime.now(timezone.utc)

    if enrollment:
        enrollment.completion_percentage = pct
        if pct >= 100 and not enrollment.completed_at:
            enrollment.completed_at = now
            newly_completed = True
        await enrollment.save()
    else:
        if pct >= 100:
            newly_completed = True
        enrollment = Enrollment(
            user_id=user_id,
            module_id=module_id,
            completion_percentage=pct,
            completed_at=now if pct >= 100 else None,
        )
        await enrollment.insert()

    return {"completion_percentage": pct, "newly_completed": newly_completed}


async def _has_passed_module_quiz(user_id: str, module_id: str) -> bool:
    assessment = await Assessment.find_one(
        Assessment.module_id == module_id,
        Assessment.episode_id == None,  # noqa: E711
    )
    if not assessment:
        return False
    attempt = await AssessmentAttempt.find_one(
        AssessmentAttempt.user_id == user_id,
        AssessmentAttempt.assessment_id == assessment.id,
        AssessmentAttempt.passed == True,  # noqa: E712
    )
    return attempt is not None


@router.post("")
async def upsert_progress(
    body: ProgressUpdate,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    # Cache progress in Redis (key expires in 2 min, flushed by the 30s player sync)
    cache_key = f"progress:{user.id}:{body.episode_id}"
    await redis.setex(cache_key, 120, f"{body.watched_seconds}:{body.total_seconds}")

    # * completion rule: watched >= 90% of total
    completed = body.watched_seconds >= body.total_seconds * 0.9
    now = datetime.now(timezone.utc)

    wp = await WatchProgress.find_one(
        WatchProgress.user_id == user.id,
        WatchProgress.episode_id == body.episode_id,
    )

    newly_completed = False
    if wp:
        wp.watched_seconds = max(wp.watched_seconds, body.watched_seconds)
        wp.total_seconds = body.total_seconds
        wp.last_watched_at = now
        if completed and not wp.completed:
            wp.completed = True
            wp.completed_at = now
            newly_completed = True
        await wp.save()
    else:
        wp = WatchProgress(
            user_id=user.id,
            episode_id=body.episode_id,
            watched_seconds=body.watched_seconds,
            total_seconds=body.total_seconds,
            completed=completed,
            completed_at=now if completed else None,
        )
        await wp.insert()
        newly_completed = completed

    # * one award path for both branches. The old insert branch skipped
    # * check_and_award_badges, so a first-POST completion never earned a badge.
    rewards = None
    if newly_completed:
        gamification = GamificationService(redis)
        episode_reward = await gamification.reward(
            user.id, "complete_episode", user.department or "",
            ref_type="episode", ref_id=body.episode_id,
        )
        streak = await gamification.record_activity(user.id)
        badges = await gamification.check_and_award_badges(user.id, "complete_episode")

        # Wire module completion / mastery
        module_reward = None
        first_reward = None
        mastery_reward = None
        module_badges: list[str] = []
        completion_info: dict | None = None

        episode = await Episode.get(body.episode_id)
        if episode:
            module = await Module.get(episode.module_id)
            module_weight = module.points_weight if module else 1.0
            completion_info = await _update_enrollment(user.id, episode.module_id)
            if completion_info["newly_completed"]:
                module_reward = await gamification.reward(
                    user.id, "complete_module", user.department or "",
                    ref_type="module", ref_id=episode.module_id,
                    multiplier=module_weight,
                )
                module_badges.extend(await gamification.check_and_award_badges(user.id, "complete_module"))

                # First-to-complete race (atomic Redis SETNX)
                first_key = f"module:first:{episode.module_id}"
                was_first = await redis.set(first_key, user.id, nx=True)
                if was_first:
                    first_reward = await gamification.reward(
                        user.id, "first_to_complete", user.department or "",
                        ref_type="module", ref_id=episode.module_id,
                        multiplier=module_weight,
                    )

                # Module mastery = completed + passed module quiz
                if await _has_passed_module_quiz(user.id, episode.module_id):
                    mastery_reward = await gamification.reward(
                        user.id, "module_mastery", user.department or "",
                        ref_type="module", ref_id=episode.module_id,
                        multiplier=module_weight,
                    )
                    module_badges.extend(await gamification.check_and_award_badges(user.id, "module_mastery"))

                    # * Advance any learning paths that contain this module as the current node
                    await _advance_paths_for_module(user.id, episode.module_id)
                    # * Update team challenge progress (collaborative challenges)
                    from app.routers.challenges import update_team_progress
                    await update_team_progress(user.id, episode.module_id)

        rewards = {
            "action": "complete_episode",
            "episode": episode_reward,
            "streak_days": streak,
            "badges_unlocked": badges,
            "completion_percentage_added": completion_info.get("completion_percentage") if completion_info else None,
            "module_completion": module_reward,
            "first_to_complete": first_reward,
            "module_mastery": mastery_reward,
            "module_badges_unlocked": module_badges,
        }

    return {"completed": completed, "watched_seconds": body.watched_seconds, "rewards": rewards}


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


async def _advance_paths_for_module(user_id: str, module_id: str) -> None:
    """When a module is mastered, advance the user in any path where it's the current node."""
    from app.models.learning_path import LearningPath, UserPathProgress
    from datetime import datetime, timezone

    # Find paths where this module_id appears in nodes and the user has progress
    paths = await LearningPath.find_all().to_list()
    for path in paths:
        node_idx = None
        for i, node in enumerate(path.nodes):
            if node.get("module_id") == module_id:
                node_idx = i
                break
        if node_idx is None:
            continue
        progress = await UserPathProgress.find_one(
            UserPathProgress.user_id == user_id,
            UserPathProgress.path_id == path.id,
        )
        if not progress:
            continue
        if progress.current_node != node_idx:
            continue
        if node_idx not in progress.mastered_nodes:
            progress.mastered_nodes.append(node_idx)
        next_node = node_idx + 1
        if next_node < len(path.nodes):
            if next_node not in progress.unlocked_nodes:
                progress.unlocked_nodes.append(next_node)
            progress.current_node = next_node
        else:
            progress.completed_at = datetime.now(timezone.utc)
        await progress.save()
