"""
Admin router — module/episode CRUD, video upload to Bunny Stream, analytics.
Replaces S3 presigned upload + MediaConvert trigger from v1.
"""
from typing import Annotated, AsyncIterator
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


class TusUploadRequest(BaseModel):
    file_size: int
    file_name: str
    file_type: str = "video/mp4"


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


@router.post("/episodes/{episode_id}/prepare-upload")
async def prepare_upload(
    episode_id: str,
    body: TusUploadRequest,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Create a TUS upload session for direct browser-to-Bunny upload.
    
    This enables fast, resumable uploads without server bottleneck:
      1. Frontend calls this endpoint with file metadata (size, name, type)
      2. Backend creates TUS session with Bunny (requires API key)
      3. Backend returns 'tus_upload_url' - browser-safe, no auth needed
      4. Frontend uploads chunks via PATCH to tus_upload_url
      5. Bunny webhooks when encoding finishes
    
    The TUS protocol enables:
      - Resumable uploads (if connection drops, resume from last byte)
      - Progress tracking (after each chunk)
      - Direct upload (no bytes through Railway server)
    """
    import logging
    logger = logging.getLogger(__name__)

    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    # Create video object in Bunny Stream library
    logger.info(f"Creating Bunny Stream video object for episode {episode_id}")
    video_obj = await bunny_stream.create_video(ep.title)
    video_guid = video_obj["guid"]
    
    # Create TUS upload session (requires API key, done server-side)
    logger.info(f"Creating TUS session for {body.file_name} ({body.file_size} bytes)")
    try:
        tus_upload_url = await bunny_stream.create_tus_upload_session(
            video_guid=video_guid,
            file_size=body.file_size,
            file_name=body.file_name,
            file_type=body.file_type,
        )
        logger.info(f"TUS session created: {tus_upload_url}")
    except Exception as e:
        logger.error(f"Failed to create TUS session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create upload session: {str(e)}")

    # Update episode record
    ep.bunny_video_id = video_guid
    ep.bunny_video_guid = video_guid
    ep.status = "processing"
    await ep.save()

    return {
        "episode_id": episode_id,
        "bunny_video_guid": video_guid,
        "tus_upload_url": tus_upload_url,
        "file_size": body.file_size,
        "status": "processing",
        "message": "Upload chunks via PATCH to 'tus_upload_url'. No authentication needed for subsequent requests.",
    }


@router.post("/episodes/{episode_id}/upload")
async def upload_episode_video(
    episode_id: str,
    admin: Annotated[User, Depends(require_admin)],
    video: UploadFile = File(...),
):
    """
    Upload a video file for an episode directly to Bunny Stream.
    Uses streaming upload for better performance with large files.
    Bunny auto-transcodes to 360p/720p/1080p HLS on receipt.
    """
    import logging
    logger = logging.getLogger(__name__)

    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    # 1. Create video object in Bunny Stream library
    logger.info(f"Creating Bunny Stream video object for episode {episode_id}")
    video_obj = await bunny_stream.create_video(ep.title)
    video_guid = video_obj["guid"]

    # 2. Stream upload to Bunny Stream (constant memory, chunked)
    logger.info(f"Starting stream upload for {video.filename} ({video.size or 'unknown'} bytes)")

    async def file_chunks(chunk_size: int = 65536) -> AsyncIterator[bytes]:
        """Async generator yielding chunks from UploadFile."""
        while True:
            chunk = await video.read(chunk_size)
            if not chunk:
                break
            yield chunk

    await bunny_stream.upload_video_stream(
        video_guid,
        file_chunks(),
        total_size=video.size,
        chunk_size=65536,
    )

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


class UploadFromUrlBody(BaseModel):
    video_url: str


@router.post("/episodes/{episode_id}/upload-from-url")
async def upload_episode_video_from_url(
    episode_id: str,
    body: UploadFromUrlBody,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Tell Bunny Stream to fetch a video from an external URL directly.
    This is 10x faster than uploading through your server — Bunny pulls
    the video directly from the source URL.

    Example video_url sources:
      - Temporary file hosting: https://file.io/xxxxx
      - Cloud storage presigned URL: https://s3.amazonaws.com/...
      - Another CDN: https://cdn.example.com/video.mp4
      - Zoom recording download URL
    """
    import logging
    logger = logging.getLogger(__name__)

    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    # 1. Create video object in Bunny Stream library
    logger.info(f"Creating Bunny Stream video object for episode {episode_id}")
    video_obj = await bunny_stream.create_video(ep.title)
    video_guid = video_obj["guid"]

    # 2. Tell Bunny Stream to fetch from URL directly
    logger.info(f"Requesting Bunny Stream to fetch from: {body.video_url[:60]}...")
    fetch_result = await bunny_stream.upload_video_from_url(video_guid, body.video_url)

    logger.info(f"Fetch initiated: {fetch_result}")

    # 3. Update episode record — status stays "processing" until webhook fires
    ep.bunny_video_id = video_guid
    ep.bunny_video_guid = video_guid
    ep.status = "processing"
    await ep.save()

    return {
        "episode_id": episode_id,
        "bunny_video_guid": video_guid,
        "status": "processing",
        "fetch_initiated": True,
        "message": "Video fetch initiated — Bunny Stream is pulling the video from the provided URL. Webhook will update status to 'ready' when complete.",
    }


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


@router.get("/episodes/{episode_id}/status")
async def get_episode_status(
    episode_id: str,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Check video processing status from Bunny Stream directly.
    Use this for polling when webhook hasn't arrived yet.
    """
    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")

    # If processing, check Bunny Stream directly
    if ep.status == "processing" and ep.bunny_video_guid:
        try:
            video = await bunny_stream.get_video(ep.bunny_video_guid)
            bunny_status = video.get("status")
            
            # Update our record if Bunny says it's done
            if bunny_status == 4:  # Finished
                ep.status = "ready"
                if video.get("length"):
                    ep.duration_seconds = int(video["length"])
                await ep.save()
            elif bunny_status in (5, 6):  # Error / UploadFailed
                ep.status = "failed"
                await ep.save()
                
            return {
                "episode_id": ep.id,
                "status": ep.status,
                "bunny_status": bunny_status,
                "bunny_video_guid": ep.bunny_video_guid,
                "duration_seconds": ep.duration_seconds,
                "title": ep.title,
            }
        except Exception:
            pass  # Return cached status if Bunny API fails

    return {
        "episode_id": ep.id,
        "status": ep.status,
        "bunny_video_guid": ep.bunny_video_guid,
        "duration_seconds": ep.duration_seconds,
        "title": ep.title,
    }
