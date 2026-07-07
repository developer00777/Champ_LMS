"""
Content / Browse router — home feed and stream URL generation via Bunny Stream.
"""
import logging
import re
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from beanie.operators import In, Or, RegEx
from pydantic import BaseModel
from app.core.auth import get_current_user
from app.core.redis import get_redis
from app.models.user import User
from app.models.module import Module
from app.models.episode import Episode
from app.models.progress import WatchProgress
from app.models.recommendation import Recommendation
from app.services.bunny_stream import bunny_stream
from app.services.bunny_storage import bunny_storage
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["content"])


def _ci_regex(q: str) -> str:
    """Case-insensitive substring match, escaped — mirrors the old ILIKE %q% pattern."""
    return re.escape(q)


class EpisodeOut(BaseModel):
    id: str
    title: str
    description: str | None
    duration_seconds: int | None
    sequence_order: int
    status: str
    thumbnail_url: str | None

    class Config:
        from_attributes = True


class ModuleOut(BaseModel):
    id: str
    title: str
    description: str | None
    category: str | None
    tags: list[str] | None
    thumbnail_url: str | None
    total_episodes: int
    is_published: bool

    class Config:
        from_attributes = True


class FeedRow(BaseModel):
    row_title: str
    modules: list[ModuleOut]


def _thumbnail_url(bunny_path: str | None) -> str | None:
    if not bunny_path:
        return None
    return bunny_storage.thumbnail_url(bunny_path, 480, 270)


@router.get("/feed", response_model=list[FeedRow])
async def get_feed(
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    """Personalized home feed rows. Uses cached recommendations if fresh."""
    rec = await Recommendation.find_one(Recommendation.user_id == user.id)

    # Fallback: build basic rows if no recommendations yet
    all_modules = await Module.find(Module.is_published == True).sort(-Module.created_at).limit(40).to_list()

    rows: list[FeedRow] = []

    # Continue Watching — find episodes in progress
    in_progress = await (
        WatchProgress.find(WatchProgress.user_id == user.id, WatchProgress.completed == False)
        .sort(-WatchProgress.last_watched_at)
        .limit(8)
        .to_list()
    )

    if in_progress:
        ep_ids = [p.episode_id for p in in_progress]
        episodes = await Episode.find(In(Episode.id, ep_ids)).to_list()
        module_ids = list({e.module_id for e in episodes})
        mods = await Module.find(In(Module.id, module_ids)).to_list()
        if mods:
            rows.append(FeedRow(
                row_title="Continue Watching",
                modules=[
                    ModuleOut(
                        id=m.id,
                        title=m.title,
                        description=m.description,
                        category=m.category,
                        tags=m.tags,
                        thumbnail_url=_thumbnail_url(m.thumbnail_bunny_path),
                        total_episodes=m.total_episodes,
                        is_published=m.is_published,
                    )
                    for m in mods
                ],
            ))

    # Use saved recommendation rows if available
    if rec and rec.rows:
        for row_data in rec.rows:
            module_ids = row_data.get("module_ids", [])
            mods = await Module.find(In(Module.id, module_ids)).to_list()
            if mods:
                rows.append(FeedRow(
                    row_title=row_data["row_title"],
                    modules=[
                        ModuleOut(
                            id=m.id,
                            title=m.title,
                            description=m.description,
                            category=m.category,
                            tags=m.tags,
                            thumbnail_url=_thumbnail_url(m.thumbnail_bunny_path),
                            total_episodes=m.total_episodes,
                            is_published=m.is_published,
                        )
                        for m in mods
                    ],
                ))
    else:
        # Default rows by category
        categories = list({m.category for m in all_modules if m.category})
        for cat in categories[:3]:
            cat_mods = [m for m in all_modules if m.category == cat][:8]
            rows.append(FeedRow(
                row_title=f"Trending in {cat.title()}",
                modules=[
                    ModuleOut(
                        id=m.id,
                        title=m.title,
                        description=m.description,
                        category=m.category,
                        tags=m.tags,
                        thumbnail_url=_thumbnail_url(m.thumbnail_bunny_path),
                        total_episodes=m.total_episodes,
                        is_published=m.is_published,
                    )
                    for m in cat_mods
                ],
            ))

        # New Releases
        rows.append(FeedRow(
            row_title="New Releases",
            modules=[
                ModuleOut(
                    id=m.id,
                    title=m.title,
                    description=m.description,
                    category=m.category,
                    tags=m.tags,
                    thumbnail_url=_thumbnail_url(m.thumbnail_bunny_path),
                    total_episodes=m.total_episodes,
                    is_published=m.is_published,
                )
                for m in all_modules[:8]
            ],
        ))

    return rows


@router.get("/modules", response_model=list[ModuleOut])
async def list_modules(
    user: Annotated[User, Depends(get_current_user)],
    category: str | None = None,
    q: str | None = None,
):
    filters = [Module.is_published == True]
    if category:
        filters.append(Module.category == category)
    if q:
        pattern = _ci_regex(q)
        filters.append(Or(RegEx(Module.title, pattern, "i"), RegEx(Module.description, pattern, "i")))
    modules = await Module.find(*filters).sort(-Module.created_at).to_list()
    return [
        ModuleOut(
            id=m.id,
            title=m.title,
            description=m.description,
            category=m.category,
            tags=m.tags,
            thumbnail_url=_thumbnail_url(m.thumbnail_bunny_path),
            total_episodes=m.total_episodes,
            is_published=m.is_published,
        )
        for m in modules
    ]


@router.get("/modules/{module_id}", response_model=dict)
async def get_module(
    module_id: str,
    user: Annotated[User, Depends(get_current_user)],
):
    module = await Module.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    episodes = await Episode.find(Episode.module_id == module_id).sort(+Episode.sequence_order).to_list()

    return {
        "id": module.id,
        "title": module.title,
        "description": module.description,
        "category": module.category,
        "tags": module.tags,
        "thumbnail_url": _thumbnail_url(module.thumbnail_bunny_path),
        "total_episodes": module.total_episodes,
        "is_published": module.is_published,
        "episodes": [
            {
                "id": ep.id,
                "title": ep.title,
                "description": ep.description,
                "duration_seconds": ep.duration_seconds,
                "sequence_order": ep.sequence_order,
                "status": ep.status,
                "thumbnail_url": _thumbnail_url(ep.thumbnail_bunny_path),
            }
            for ep in episodes
        ],
    }


@router.get("/episodes/{episode_id}/stream")
async def get_stream_url(
    episode_id: str,
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Returns a Bunny Stream token-authenticated HLS URL for the episode.
    Replaces CloudFront signed URL generation from v1.
    """
    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    if ep.status != "ready" and ep.bunny_video_guid:
        # Webhook delivery isn't guaranteed (misconfigured URL, dropped
        # request, etc). Fall back to asking Bunny directly so an episode
        # doesn't get stuck in "processing" forever if the webhook never
        # arrives.
        video = await bunny_stream.get_video(ep.bunny_video_guid)
        bunny_status = video.get("status")
        if bunny_status == 4:  # Finished
            ep.status = "ready"
            if video.get("length"):
                ep.duration_seconds = int(video["length"])
            await ep.save()
        elif bunny_status in (5, 6):  # Error / UploadFailed
            ep.status = "failed"
            await ep.save()

    if ep.status != "ready":
        raise HTTPException(status_code=425, detail="Video is still processing")
    if not ep.bunny_video_guid:
        raise HTTPException(status_code=503, detail="Video not available")

    # Generate stream URL with fallback options
    try:
        stream_url = bunny_stream.get_token_auth_url(ep.bunny_video_guid, expires_in_seconds=14400)
    except RuntimeError as e:
        logger.warning(f"Token auth URL failed for {ep.bunny_video_guid}: {e}")
        # Fallback to plain HLS URL (only works if token auth is disabled in Bunny dashboard)
        stream_url = bunny_stream.get_hls_url(ep.bunny_video_guid)
        logger.info(f"Falling back to plain HLS URL: {stream_url}")

    embed_url = bunny_stream.get_embed_url(ep.bunny_video_guid)

    return {
        "stream_url": stream_url,    # HLS manifest — use with Video.js / HLS.js
        "embed_url": embed_url,       # Bunny iframe player fallback
        "expires_in": 14400,
        "episode_status": ep.status,
        "bunny_video_guid": ep.bunny_video_guid,
    }


@router.get("/search")
async def search(
    q: str,
    user: Annotated[User, Depends(get_current_user)],
):
    pattern = _ci_regex(q)
    title_or_desc = lambda title_field, desc_field: Or(
        RegEx(title_field, pattern, "i"), RegEx(desc_field, pattern, "i")
    )
    modules = await (
        Module.find(Module.is_published == True, title_or_desc(Module.title, Module.description))
        .limit(20)
        .to_list()
    )
    episodes = await (
        Episode.find(title_or_desc(Episode.title, Episode.description), Episode.status == "ready")
        .limit(20)
        .to_list()
    )
    return {
        "modules": [
            {"id": m.id, "title": m.title, "category": m.category,
             "thumbnail_url": _thumbnail_url(m.thumbnail_bunny_path)}
            for m in modules
        ],
        "episodes": [
            {"id": e.id, "title": e.title, "module_id": e.module_id}
            for e in episodes
        ],
    }
