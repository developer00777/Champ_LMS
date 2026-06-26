import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.module import Module
from app.models.enrollment import Enrollment
from app.models.progress import WatchProgress
from app.models.episode import Episode
from app.models.recommendation import Recommendation
from app.schemas.feed import FeedRow, FeedCard, FeedResponse


async def build_feed(user_id: uuid.UUID, db: AsyncSession) -> FeedResponse:
    rows = []

    # Continue Watching — in-progress enrollments
    continue_watching = await _get_continue_watching(user_id, db)
    if continue_watching:
        rows.append(FeedRow(row_title="Continue Watching", modules=continue_watching))

    # New Releases — most recently published
    new_releases = await _get_new_releases(db, limit=10)
    if new_releases:
        rows.append(FeedRow(row_title="New Releases", modules=new_releases))

    # Trending — by enrollment count
    trending = await _get_trending(db, limit=10)
    if trending:
        rows.append(FeedRow(row_title="Trending Now", modules=trending))

    # For You — from saved recommendations or fallback to new releases
    for_you = await _get_for_you(user_id, db)
    if for_you:
        rows.append(FeedRow(row_title="Recommended for You", modules=for_you))

    return FeedResponse(rows=rows)


async def _get_continue_watching(user_id: uuid.UUID, db: AsyncSession) -> list[FeedCard]:
    result = await db.execute(
        select(Enrollment)
        .where(Enrollment.user_id == user_id, Enrollment.completed_at.is_(None))
        .order_by(Enrollment.enrolled_at.desc())
        .limit(10)
    )
    enrollments = result.scalars().all()
    cards = []
    for enr in enrollments:
        mod_result = await db.execute(select(Module).where(Module.id == enr.module_id, Module.is_published == True))
        mod = mod_result.scalar_one_or_none()
        if mod:
            cards.append(FeedCard(
                id=mod.id, title=mod.title, thumbnail_url=mod.thumbnail_url,
                category=mod.category, total_episodes=mod.total_episodes,
                completion_percentage=enr.completion_percentage,
            ))
    return cards


async def _get_new_releases(db: AsyncSession, limit: int = 10) -> list[FeedCard]:
    result = await db.execute(
        select(Module)
        .where(Module.is_published == True)
        .order_by(Module.created_at.desc())
        .limit(limit)
    )
    return [
        FeedCard(id=m.id, title=m.title, thumbnail_url=m.thumbnail_url,
                 category=m.category, total_episodes=m.total_episodes, is_new=True)
        for m in result.scalars().all()
    ]


async def _get_trending(db: AsyncSession, limit: int = 10) -> list[FeedCard]:
    result = await db.execute(
        select(Module, func.count(Enrollment.id).label("enroll_count"))
        .join(Enrollment, Enrollment.module_id == Module.id, isouter=True)
        .where(Module.is_published == True)
        .group_by(Module.id)
        .order_by(func.count(Enrollment.id).desc())
        .limit(limit)
    )
    return [
        FeedCard(id=row.Module.id, title=row.Module.title, thumbnail_url=row.Module.thumbnail_url,
                 category=row.Module.category, total_episodes=row.Module.total_episodes)
        for row in result.all()
    ]


async def _get_for_you(user_id: uuid.UUID, db: AsyncSession) -> list[FeedCard]:
    result = await db.execute(
        select(Recommendation).where(Recommendation.user_id == user_id)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        return await _get_new_releases(db, limit=8)

    module_ids = [row["module_ids"] for row in rec.rows[:1]]
    flat_ids = [mid for sublist in module_ids for mid in sublist]
    if not flat_ids:
        return []

    mods_result = await db.execute(
        select(Module).where(Module.id.in_(flat_ids), Module.is_published == True)
    )
    return [
        FeedCard(id=m.id, title=m.title, thumbnail_url=m.thumbnail_url,
                 category=m.category, total_episodes=m.total_episodes)
        for m in mods_result.scalars().all()
    ]
