import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.db import get_db
from app.core.auth import get_current_user_dev as get_current_user
from app.models.module import Module
from app.models.episode import Episode
from app.models.user import User
from app.models.enrollment import Enrollment
from app.models.progress import WatchProgress
from app.schemas.module import ModuleCreate, ModuleUpdate, ModuleOut
from app.schemas.episode import EpisodeCreate, EpisodeOut, EpisodeUpdate
from app.services.video_service import generate_s3_upload_presign
from app.services.ai_service import generate_quiz_from_transcript

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/modules", response_model=ModuleOut)
async def create_module(
    payload: ModuleCreate,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.cognito_sub == claims["sub"]))
    user = result.scalar_one_or_none()
    module = Module(**payload.model_dump(), created_by=user.id if user else None)
    db.add(module)
    await db.flush()
    return module


@router.patch("/modules/{module_id}", response_model=ModuleOut)
async def update_module(
    module_id: uuid.UUID,
    payload: ModuleUpdate,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Module).where(Module.id == module_id))
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(module, field, value)
    return module


@router.post("/modules/{module_id}/episodes", response_model=EpisodeOut)
async def add_episode(
    module_id: uuid.UUID,
    payload: EpisodeCreate,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Module).where(Module.id == module_id))
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    episode = Episode(module_id=module_id, **payload.model_dump())
    db.add(episode)
    module.total_episodes = (module.total_episodes or 0) + 1
    await db.flush()
    return episode


@router.patch("/episodes/{episode_id}", response_model=EpisodeOut)
async def update_episode(
    episode_id: uuid.UUID,
    payload: EpisodeUpdate,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(episode, field, value)
    return episode


@router.post("/upload/presign")
async def get_upload_presign(
    episode_id: uuid.UUID,
    claims: dict = Depends(get_current_user),
):
    return generate_s3_upload_presign(episode_id)


@router.post("/episodes/{episode_id}/generate-quiz")
async def generate_quiz(
    episode_id: uuid.UUID,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.assessment import Assessment

    result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not episode.transcript:
        raise HTTPException(status_code=400, detail="Episode has no transcript")

    questions = await generate_quiz_from_transcript(episode.title, episode.transcript)
    assessment = Assessment(
        module_id=episode.module_id,
        episode_id=episode_id,
        title=f"Quiz: {episode.title}",
        questions=questions,
    )
    db.add(assessment)
    await db.flush()
    return {"assessment_id": str(assessment.id), "question_count": len(questions)}


@router.get("/analytics")
async def get_analytics(
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    total_modules = (await db.execute(select(func.count(Module.id)).where(Module.is_published == True))).scalar()
    total_completions = (await db.execute(select(func.count(WatchProgress.id)).where(WatchProgress.completed == True))).scalar()
    active_enrollments = (await db.execute(select(func.count(Enrollment.id)).where(Enrollment.completed_at.is_(None)))).scalar()

    return {
        "total_users": total_users,
        "published_modules": total_modules,
        "episode_completions": total_completions,
        "active_enrollments": active_enrollments,
    }
