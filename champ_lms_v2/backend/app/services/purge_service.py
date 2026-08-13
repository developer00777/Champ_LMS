"""
Permanent deletion of video content — Bunny Stream, Bunny Storage, and every
Mongo/Redis row that references it.

This is irreversible: Bunny has no undelete. Everything here is therefore
built around two rules:

1. **Preview before destroy.** plan_*() reports exactly what would be removed
   without touching anything, so the admin confirms against real numbers.
2. **Remote first, then local.** The Bunny objects are the only part we cannot
   recreate, so they go first. If a remote call fails we abort with the DB
   intact rather than leaving a row pointing at a video that may or may not
   exist. Bunny 404s count as success — already gone is the desired state.

XP is deliberately preserved. XpEvent rows stay as tombstones and User.points /
User.xp are untouched, so deleting content never retroactively drops someone's
level or leaderboard rank. Those rows also keep the (user_id, reason, ref_id)
idempotency guard intact, so a re-uploaded episode can't be farmed for repeat XP.
"""
from __future__ import annotations

import logging

import httpx
from beanie.operators import In

from app.models.assessment import Assessment, AssessmentAttempt
from app.models.enrollment import Enrollment
from app.models.episode import Episode
from app.models.module import Module
from app.models.progress import WatchProgress
from app.models.zoom_session import ZoomSession
from app.services.bunny_storage import bunny_storage
from app.services.bunny_stream import bunny_stream

logger = logging.getLogger(__name__)


class PurgeError(Exception):
    """A remote asset could not be deleted; the database was left untouched."""


def _is_already_gone(exc: Exception) -> bool:
    """Treat 'not found' as success — the goal state is 'no longer exists'."""
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (404, 410)


async def _delete_remote_assets(episodes: list[Episode]) -> list[dict]:
    """
    Delete Bunny Stream videos and Bunny Storage thumbnails for these episodes.

    Raises PurgeError on the first hard failure so the caller can abort before
    touching the database. Returns a per-asset log for the response.
    """
    results: list[dict] = []

    for ep in episodes:
        guid = ep.bunny_video_guid or ep.bunny_video_id
        if guid:
            # A Zoom "Full Recording" video is a separate Bunny asset tracked on
            # ZoomSession, not on any Episode. Guard anyway: if some episode ever
            # shares that GUID, deleting it here would break the ZoomSession.
            shared = await ZoomSession.find_one(ZoomSession.bunny_video_id == guid)
            if shared:
                results.append({
                    "episode_id": ep.id, "asset": "stream", "guid": guid,
                    "status": "skipped",
                    "detail": f"GUID also referenced by ZoomSession {shared.id}",
                })
            else:
                try:
                    await bunny_stream.delete_video(guid)
                    results.append({"episode_id": ep.id, "asset": "stream",
                                    "guid": guid, "status": "deleted"})
                except Exception as exc:  # noqa: BLE001
                    if _is_already_gone(exc):
                        results.append({"episode_id": ep.id, "asset": "stream",
                                        "guid": guid, "status": "already_absent"})
                    else:
                        logger.exception("Bunny Stream delete failed for %s", guid)
                        raise PurgeError(
                            f"Could not delete video {guid} from Bunny Stream: {exc}. "
                            "Nothing was removed from the database — retry, or check "
                            "BUNNY_STREAM_API_KEY and the library ID."
                        ) from exc
        else:
            results.append({"episode_id": ep.id, "asset": "stream",
                            "guid": None, "status": "nothing_to_delete"})

        if ep.thumbnail_bunny_path:
            try:
                await bunny_storage.delete_thumbnail(ep.thumbnail_bunny_path)
                results.append({"episode_id": ep.id, "asset": "thumbnail",
                                "path": ep.thumbnail_bunny_path, "status": "deleted"})
            except Exception as exc:  # noqa: BLE001
                # A leftover thumbnail is cosmetic and cheap; never block the
                # video deletion (the expensive, sensitive part) over one.
                status = "already_absent" if _is_already_gone(exc) else "failed"
                if status == "failed":
                    logger.warning("Thumbnail delete failed for %s: %s",
                                   ep.thumbnail_bunny_path, exc)
                results.append({"episode_id": ep.id, "asset": "thumbnail",
                                "path": ep.thumbnail_bunny_path, "status": status})

    return results


async def _related_counts(episode_ids: list[str]) -> dict:
    """Count the rows that a purge of these episodes would remove."""
    if not episode_ids:
        return {"watch_progress": 0, "assessments": 0, "assessment_attempts": 0}

    assessments = await Assessment.find(In(Assessment.episode_id, episode_ids)).to_list()
    assessment_ids = [a.id for a in assessments]
    attempts = (
        await AssessmentAttempt.find(In(AssessmentAttempt.assessment_id, assessment_ids)).count()
        if assessment_ids else 0
    )
    return {
        "watch_progress": await WatchProgress.find(
            In(WatchProgress.episode_id, episode_ids)
        ).count(),
        "assessments": len(assessments),
        "assessment_attempts": attempts,
    }


async def _purge_db_rows(episodes: list[Episode], redis=None) -> dict:
    """
    Remove the episodes and every row that points at them.

    XpEvent is intentionally left alone — see the module docstring.
    """
    episode_ids = [ep.id for ep in episodes]
    if not episode_ids:
        return {"episodes": 0, "watch_progress": 0, "assessments": 0,
                "assessment_attempts": 0, "redis_keys": 0}

    # Cached per-episode progress would otherwise serve data for a dead episode.
    redis_keys = 0
    if redis is not None:
        for ep_id in episode_ids:
            try:
                async for key in redis.scan_iter(match=f"progress:*:{ep_id}"):
                    await redis.delete(key)
                    redis_keys += 1
            except Exception:  # noqa: BLE001 - a stale cache key is not fatal
                logger.warning("Could not clear Redis progress keys for %s", ep_id)

    assessments = await Assessment.find(In(Assessment.episode_id, episode_ids)).to_list()
    assessment_ids = [a.id for a in assessments]
    attempts_deleted = 0
    if assessment_ids:
        res = await AssessmentAttempt.find(
            In(AssessmentAttempt.assessment_id, assessment_ids)
        ).delete()
        attempts_deleted = getattr(res, "deleted_count", 0) or 0
        await Assessment.find(In(Assessment.episode_id, episode_ids)).delete()

    wp_res = await WatchProgress.find(In(WatchProgress.episode_id, episode_ids)).delete()
    wp_deleted = getattr(wp_res, "deleted_count", 0) or 0

    ep_res = await Episode.find(In(Episode.id, episode_ids)).delete()
    ep_deleted = getattr(ep_res, "deleted_count", 0) or 0

    return {
        "episodes": ep_deleted,
        "watch_progress": wp_deleted,
        "assessments": len(assessment_ids),
        "assessment_attempts": attempts_deleted,
        "redis_keys": redis_keys,
    }


async def _recompute_enrollments(module_id: str) -> int:
    """
    Recompute completion for everyone enrolled in this module.

    Without this, percentages computed against the old episode count persist
    until the next episode completion — and can read above 100%.
    """
    module = await Module.get(module_id)
    total = module.total_episodes if module else 0
    episode_ids = [ep.id for ep in await Episode.find(Episode.module_id == module_id).to_list()]

    updated = 0
    for enr in await Enrollment.find(Enrollment.module_id == module_id).to_list():
        if total and episode_ids:
            done = await WatchProgress.find(
                WatchProgress.user_id == enr.user_id,
                In(WatchProgress.episode_id, episode_ids),
                WatchProgress.completed == True,  # noqa: E712
            ).count()
            pct = round(min(done / total, 1.0) * 100, 2)
        else:
            pct = 0.0
        if enr.completion_percentage != pct:
            enr.completion_percentage = pct
            await enr.save()
            updated += 1
    return updated


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
async def plan_episode_purge(episode: Episode) -> dict:
    """Dry run: what deleting this one episode would destroy."""
    counts = await _related_counts([episode.id])
    guid = episode.bunny_video_guid or episode.bunny_video_id
    module = await Module.get(episode.module_id)
    return {
        "scope": "episode",
        "episode_id": episode.id,
        "title": episode.title,
        "module_id": episode.module_id,
        "module_title": module.title if module else None,
        "bunny_video_guid": guid,
        "has_remote_video": bool(guid),
        "thumbnail_bunny_path": episode.thumbnail_bunny_path,
        "episodes": 1,
        **counts,
        "xp_events_preserved": True,
    }


async def plan_module_purge(module: Module) -> dict:
    """Dry run: what deleting this module and all its episodes would destroy."""
    episodes = await Episode.find(Episode.module_id == module.id).to_list()
    counts = await _related_counts([ep.id for ep in episodes])
    return {
        "scope": "module",
        "module_id": module.id,
        "module_title": module.title,
        "is_published": module.is_published,
        "episodes": len(episodes),
        "remote_videos": sum(
            1 for ep in episodes if (ep.bunny_video_guid or ep.bunny_video_id)
        ),
        "episode_titles": [ep.title for ep in episodes][:50],
        "enrollments": await Enrollment.find(Enrollment.module_id == module.id).count(),
        **counts,
        "xp_events_preserved": True,
    }


async def purge_episode(episode: Episode, redis=None) -> dict:
    """
    Permanently delete one episode: Bunny video, thumbnail, and all local rows.
    Decrements the module's episode counter and repairs affected enrollments.
    """
    module_id = episode.module_id
    remote = await _delete_remote_assets([episode])  # raises PurgeError -> DB untouched
    deleted = await _purge_db_rows([episode], redis=redis)

    if deleted["episodes"]:
        module = await Module.get(module_id)
        if module:
            # Recount instead of decrementing: the counter is only ever
            # incremented on add, so a plain -1 would preserve any existing
            # drift (and could go negative). Recounting is self-healing.
            live = await Episode.find(Episode.module_id == module_id).count()
            if module.total_episodes != live:
                module.total_episodes = live
                await module.save()

    enrollments_updated = await _recompute_enrollments(module_id)
    return {
        "scope": "episode",
        "episode_id": episode.id,
        "remote": remote,
        "deleted": deleted,
        "enrollments_recomputed": enrollments_updated,
        "xp_events_preserved": True,
    }


async def purge_module(module: Module, redis=None) -> dict:
    """
    Permanently delete a module: every episode's Bunny video and thumbnail,
    every local row, the enrollments, and the module itself.
    """
    episodes = await Episode.find(Episode.module_id == module.id).to_list()
    remote = await _delete_remote_assets(episodes)  # raises PurgeError -> DB untouched
    deleted = await _purge_db_rows(episodes, redis=redis)

    # Module-level assessments (episode_id is None) are only reachable here.
    mod_assessments = await Assessment.find(
        Assessment.module_id == module.id, Assessment.episode_id == None  # noqa: E711
    ).to_list()
    if mod_assessments:
        ids = [a.id for a in mod_assessments]
        res = await AssessmentAttempt.find(In(AssessmentAttempt.assessment_id, ids)).delete()
        deleted["assessment_attempts"] += getattr(res, "deleted_count", 0) or 0
        await Assessment.find(In(Assessment.id, ids)).delete()
        deleted["assessments"] += len(ids)

    enr_res = await Enrollment.find(Enrollment.module_id == module.id).delete()
    deleted["enrollments"] = getattr(enr_res, "deleted_count", 0) or 0

    # Release the permanent first-to-complete lock so a future module reusing
    # this id (or a re-import) isn't silently denied the bonus.
    if redis is not None:
        try:
            await redis.delete(f"module:first:{module.id}")
        except Exception:  # noqa: BLE001
            logger.warning("Could not clear first-complete lock for %s", module.id)

    # Detach any Zoom session so it stops pointing at a module that's gone.
    for zs in await ZoomSession.find(ZoomSession.module_id == module.id).to_list():
        zs.module_id = None
        await zs.save()

    await module.delete()
    return {
        "scope": "module",
        "module_id": module.id,
        "remote": remote,
        "deleted": deleted,
        "xp_events_preserved": True,
    }
