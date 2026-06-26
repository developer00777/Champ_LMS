import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from app.core.db import get_db
from app.core.auth import get_current_user_dev as get_current_user
from app.models.module import Module
from app.models.episode import Episode
from app.models.user import User
from app.schemas.module import ModuleOut
from app.schemas.feed import FeedResponse
from app.services.video_service import generate_cloudfront_signed_url
from app.services.recommendation_service import build_feed

router = APIRouter(tags=["content"])


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.cognito_sub == claims["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await build_feed(user.id, db)


@router.get("/modules", response_model=list[ModuleOut])
async def list_modules(
    category: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 20,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Module).where(Module.is_published == True)
    if category:
        q = q.where(Module.category == category)
    if search:
        q = q.where(or_(
            Module.title.ilike(f"%{search}%"),
            Module.description.ilike(f"%{search}%"),
        ))
    q = q.order_by(Module.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/modules/{module_id}", response_model=ModuleOut)
async def get_module(
    module_id: uuid.UUID,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Module).where(Module.id == module_id, Module.is_published == True)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    return module


@router.get("/episodes/{episode_id}/stream")
async def get_stream_url(
    episode_id: uuid.UUID,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    if episode.status != "ready":
        raise HTTPException(status_code=409, detail="Episode is still processing")
    if not episode.hls_manifest_key:
        raise HTTPException(status_code=409, detail="HLS manifest not available")

    signed_url = generate_cloudfront_signed_url(episode.hls_manifest_key)
    return {"stream_url": signed_url, "episode_id": str(episode_id)}


@router.get("/search", response_model=list[ModuleOut])
async def search(
    q: str = Query(..., min_length=2),
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Module).where(
            Module.is_published == True,
            or_(
                Module.title.ilike(f"%{q}%"),
                Module.description.ilike(f"%{q}%"),
            )
        ).limit(20)
    )
    return result.scalars().all()
