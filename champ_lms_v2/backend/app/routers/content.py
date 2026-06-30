"""
Content / Browse router — home feed and stream URL generation via Bunny Stream.
"""
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from pydantic import BaseModel
from app.core.db import get_db
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

router = APIRouter(tags=["content"])


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
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    """Personalized home feed rows. Uses cached recommendations if fresh."""
    rec_result = await db.execute(
        select(Recommendation).where(Recommendation.user_id == user.id)
    )
    rec = rec_result.scalar_one_or_none()

    # Fallback: build basic rows if no recommendations yet
    all_modules_result = await db.execute(
        select(Module).where(Module.is_published == True).order_by(Module.created_at.desc()).limit(40)
    )
    all_modules = all_modules_result.scalars().all()

    rows: list[FeedRow] = []

    # Continue Watching — find episodes in progress
    progress_result = await db.execute(
        select(WatchProgress)
        .where(WatchProgress.user_id == user.id, WatchProgress.completed == False)
        .order_by(WatchProgress.last_watched_at.desc())
        .limit(8)
    )
    in_progress = progress_result.scalars().all()

    if in_progress:
        ep_ids = [p.episode_id for p in in_progress]
        ep_result = await db.execute(select(Episode).where(Episode.id.in_(ep_ids)))
        episodes = ep_result.scalars().all()
        module_ids = list({e.module_id for e in episodes})
        mods_result = await db.execute(select(Module).where(Module.id.in_(module_ids)))
        mods = mods_result.scalars().all()
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
            mods_result = await db.execute(select(Module).where(Module.id.in_(module_ids)))
            mods = mods_result.scalars().all()
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
    db: Annotated[AsyncSession, Depends(get_db)],
    category: str | None = None,
    q: str | None = None,
):
    query = select(Module).where(Module.is_published == True)
    if category:
        query = query.where(Module.category == category)
    if q:
        query = query.where(
            or_(Module.title.ilike(f"%{q}%"), Module.description.ilike(f"%{q}%"))
        )
    result = await db.execute(query.order_by(Module.created_at.desc()))
    modules = result.scalars().all()
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
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Module).where(Module.id == module_id))
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    ep_result = await db.execute(
        select(Episode).where(Episode.module_id == module_id).order_by(Episode.sequence_order)
    )
    episodes = ep_result.scalars().all()

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
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    Returns a Bunny Stream token-authenticated HLS URL for the episode.
    Replaces CloudFront signed URL generation from v1.
    """
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    ep = result.scalar_one_or_none()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    if ep.status != "ready":
        raise HTTPException(status_code=425, detail="Video is still processing")
    if not ep.bunny_video_guid:
        raise HTTPException(status_code=503, detail="Video not available")

    stream_url = bunny_stream.get_token_auth_url(ep.bunny_video_guid, expires_in_seconds=14400)
    embed_url = bunny_stream.get_embed_url(ep.bunny_video_guid)

    return {
        "stream_url": stream_url,    # HLS manifest — use with Video.js / HLS.js
        "embed_url": embed_url,       # Bunny iframe player fallback
        "expires_in": 14400,
    }


@router.get("/search")
async def search(
    q: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    mod_result = await db.execute(
        select(Module).where(
            Module.is_published == True,
            or_(Module.title.ilike(f"%{q}%"), Module.description.ilike(f"%{q}%")),
        ).limit(20)
    )
    ep_result = await db.execute(
        select(Episode).where(
            or_(Episode.title.ilike(f"%{q}%"), Episode.description.ilike(f"%{q}%")),
            Episode.status == "ready",
        ).limit(20)
    )
    return {
        "modules": [
            {"id": m.id, "title": m.title, "category": m.category,
             "thumbnail_url": _thumbnail_url(m.thumbnail_bunny_path)}
            for m in mod_result.scalars().all()
        ],
        "episodes": [
            {"id": e.id, "title": e.title, "module_id": e.module_id}
            for e in ep_result.scalars().all()
        ],
    }
