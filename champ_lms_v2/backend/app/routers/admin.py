"""
Admin router — module/episode CRUD, video upload to Bunny Stream, analytics.
Replaces S3 presigned upload + MediaConvert trigger from v1.
"""
from typing import Annotated
import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from beanie.operators import Inc
from pydantic import BaseModel
from app.core.auth import require_admin
from app.models.user import User
from app.models.module import Module
from app.models.episode import Episode
from app.models.progress import WatchProgress
from app.models.enrollment import Enrollment
from app.services.bunny_stream import bunny_stream
from app.services.bunny_storage import bunny_storage
from app.services.ai_service import ai_service

router = APIRouter(prefix="/admin", tags=["admin"])


class CreateModuleBody(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    target_roles: list[str] | None = None


class CreateEpisodeBody(BaseModel):
    title: str
    description: str | None = None
    sequence_order: int


@router.post("/modules", status_code=201)
async def create_module(
    body: CreateModuleBody,
    admin: Annotated[User, Depends(require_admin)],
):
    module = Module(
        title=body.title,
        description=body.description,
        category=body.category,
        tags=body.tags,
        target_roles=body.target_roles,
        created_by=admin.id,
    )
    await module.insert()
    return {"id": module.id, "title": module.title}


@router.patch("/modules/{module_id}/publish")
async def publish_module(
    module_id: str,
    admin: Annotated[User, Depends(require_admin)],
):
    module = await Module.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    module.is_published = True
    await module.save()
    return {"published": True}


@router.post("/modules/{module_id}/episodes", status_code=201)
async def add_episode(
    module_id: str,
    body: CreateEpisodeBody,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Create episode record. Video upload is a separate step via /admin/episodes/{id}/upload.
    """
    module = await Module.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    ep = Episode(
        module_id=module_id,
        title=body.title,
        description=body.description,
        sequence_order=body.sequence_order,
        status="pending",
    )
    await ep.insert()
    await module.update(Inc({Module.total_episodes: 1}))
    return {"id": ep.id, "title": ep.title}


@router.post("/episodes/{episode_id}/upload")
async def upload_episode_video(
    episode_id: str,
    admin: Annotated[User, Depends(require_admin)],
    video: UploadFile = File(...),
):
    """
    Upload a video file for an episode directly to Bunny Stream.
    Bunny auto-transcodes to 360p/720p/1080p HLS on receipt.
    No MediaConvert, no S3 raw bucket needed.
    """
    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    # 1. Create video object in Bunny Stream library
    video_obj = await bunny_stream.create_video(ep.title)
    video_guid = video_obj["guid"]

    # 2. Upload bytes to Bunny Stream
    data = await video.read()
    await bunny_stream.upload_video_bytes(video_guid, data)

    # 3. Update episode record — status stays "processing" until webhook fires
    ep.bunny_video_id = video_guid
    ep.bunny_video_guid = video_guid
    ep.status = "processing"
    await ep.save()

    return {
        "episode_id": episode_id,
        "bunny_video_guid": video_guid,
        "status": "processing",
        "message": "Video uploaded to Bunny Stream — transcoding in progress. Webhook will update status to 'ready'.",
    }


@router.post("/episodes/{episode_id}/thumbnail")
async def upload_episode_thumbnail(
    episode_id: str,
    admin: Annotated[User, Depends(require_admin)],
    image: UploadFile = File(...),
):
    """Upload thumbnail to Bunny Storage. Served via CDN with Optimizer (auto-WebP)."""
    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    filename = image.filename or "thumb.jpg"
    data = await image.read()
    path = f"episodes/{episode_id}/{filename}"
    await bunny_storage.upload_thumbnail(path, data, filename)

    ep.thumbnail_bunny_path = path
    await ep.save()

    return {
        "thumbnail_url": bunny_storage.thumbnail_url(path),
        "cdn_url_full": bunny_storage.cdn_url(path),
    }


@router.post("/episodes/{episode_id}/generate-quiz")
async def generate_quiz(
    episode_id: str,
    admin: Annotated[User, Depends(require_admin)],
):
    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not ep.transcript:
        raise HTTPException(status_code=422, detail="Episode has no transcript")

    questions = await ai_service.generate_quiz(ep.transcript)
    return {"questions": questions}


@router.get("/analytics")
async def analytics(admin: Annotated[User, Depends(require_admin)]):
    total_users = await User.find_all().count()
    total_modules = await Module.find(Module.is_published == True).count()
    completions = await WatchProgress.find(WatchProgress.completed == True).count()
    enrollments = await Enrollment.find_all().count()

    return {
        "total_users": total_users,
        "published_modules": total_modules,
        "episode_completions": completions,
        "total_enrollments": enrollments,
    }
