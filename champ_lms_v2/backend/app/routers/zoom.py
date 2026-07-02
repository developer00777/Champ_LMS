"""
Zoom integration router.
Webhook → background task → Claude AI → Module creation → Bunny Stream upload.
Replaces SQS + Lambda from v1 with a simple asyncio background task.
"""
import asyncio
import hmac
import hashlib
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from app.core.auth import get_current_user, require_admin
from app.core.config import get_settings
from app.models.user import User
from app.models.zoom_session import ZoomSession
from app.models.module import Module
from app.models.episode import Episode
from app.services.ai_service import ai_service
from app.services.bunny_stream import bunny_stream
from app.services.zoom_service import zoom_service

router = APIRouter(prefix="/zoom", tags=["zoom"])
settings = get_settings()


class AddSessionBody(BaseModel):
    zoom_meeting_id: str | None = None
    topic: str
    summary: str
    transcript: str
    recording_download_url: str | None = None


@router.post("/webhook", status_code=200)
async def zoom_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Receives Zoom webhook (recording.completed).
    Returns 200 immediately; processing happens in background task.
    Replaces SQS + Lambda decoupling from v1.
    """
    body = await request.body()
    signature = request.headers.get("x-zm-signature", "")
    timestamp = request.headers.get("x-zm-request-timestamp", "")

    if not zoom_service.verify_webhook(body, signature, timestamp):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")
    if event != "recording.completed":
        return {"ignored": True}

    meeting = payload.get("payload", {}).get("object", {})
    zoom_meeting_id = str(meeting.get("id", ""))
    topic = meeting.get("topic", "")
    recording_files = meeting.get("recording_files", [])

    recording_url = next(
        (f.get("download_url") for f in recording_files if f.get("file_type") == "MP4"),
        None,
    )

    # Persist session record
    session = ZoomSession(
        zoom_meeting_id=zoom_meeting_id,
        topic=topic,
        recording_download_url=recording_url,
    )
    await session.insert()

    background_tasks.add_task(_process_zoom_session, session.id)
    return {"status": "queued", "session_id": session.id}


async def _process_zoom_session(session_id: str) -> None:
    """
    Background task: fetch transcript from Zoom, run AI pipeline,
    create module + episodes, upload recording to Bunny Stream.
    """
    session = await ZoomSession.get(session_id)
    if not session:
        return

    try:
        # 1. Fetch transcript from Zoom (if available)
        transcript = session.transcript or ""
        summary = session.summary or session.topic or ""

        if session.zoom_meeting_id and not transcript:
            try:
                recordings = await zoom_service.get_recording(session.zoom_meeting_id)
                # Zoom transcript is a separate file in recording_files
                transcript_url = next(
                    (f["download_url"] for f in recordings.get("recording_files", [])
                     if f.get("file_type") == "TRANSCRIPT"),
                    None,
                )
                if transcript_url:
                    raw = await zoom_service.download_recording_bytes(transcript_url)
                    transcript = raw.decode("utf-8", errors="ignore")
            except Exception:
                pass

        if not transcript:
            return

        # 2. Claude AI → module structure
        module_data = await ai_service.build_module_from_zoom(transcript, summary)

        # 3. Create Module record
        module = Module(
            title=module_data["title"],
            description=module_data.get("description"),
            category=module_data.get("category"),
            tags=module_data.get("tags"),
            target_roles=module_data.get("target_roles"),
            source_type="zoom",
            zoom_session_id=session_id,
            total_episodes=len(module_data.get("episodes", [])),
        )
        await module.insert()

        # 4. Create Episode records
        for i, ep_data in enumerate(module_data.get("episodes", []), 1):
            ep = Episode(
                module_id=module.id,
                title=ep_data["title"],
                description=ep_data.get("description"),
                sequence_order=i,
                duration_seconds=ep_data.get("duration_estimate_seconds"),
                transcript=transcript,
                ai_summary="\n".join(ep_data.get("key_points", [])),
                status="pending",
            )
            await ep.insert()

        # 5. Upload recording to Bunny Stream (if URL available)
        if session.recording_download_url:
            video_obj = await bunny_stream.create_video(f"{module.title} — Full Recording")
            video_guid = video_obj["guid"]
            # Instruct Bunny to fetch the video directly from Zoom URL
            await bunny_stream.upload_video_from_url(video_guid, session.recording_download_url)
            session.bunny_video_id = video_guid

        session.module_id = module.id
        session.processed = True
        await session.save()

    except Exception as exc:
        # Log but don't crash — session stays unprocessed for retry
        import structlog
        log = structlog.get_logger()
        log.error("zoom_processing_failed", session_id=session_id, error=str(exc))


@router.post("/sessions")
async def add_manual_session(
    body: AddSessionBody,
    admin: Annotated[User, Depends(require_admin)],
    background_tasks: BackgroundTasks,
):
    """Manually add a Zoom session (paste transcript + summary from Zoom AI)."""
    session = ZoomSession(
        zoom_meeting_id=body.zoom_meeting_id,
        topic=body.topic,
        summary=body.summary,
        transcript=body.transcript,
        recording_download_url=body.recording_download_url,
    )
    await session.insert()
    background_tasks.add_task(_process_zoom_session, session.id)
    return {"session_id": session.id, "status": "processing"}


@router.post("/sessions/{session_id}/build-module")
async def build_module_from_session(
    session_id: str,
    admin: Annotated[User, Depends(require_admin)],
    background_tasks: BackgroundTasks,
):
    """Manually trigger AI module build for an existing session."""
    session = await ZoomSession.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    background_tasks.add_task(_process_zoom_session, session_id)
    return {"status": "building", "session_id": session_id}


@router.get("/sessions")
async def list_sessions(admin: Annotated[User, Depends(require_admin)]):
    sessions = await ZoomSession.find_all().sort(-ZoomSession.created_at).to_list()
    return [
        {
            "id": s.id,
            "zoom_meeting_id": s.zoom_meeting_id,
            "topic": s.topic,
            "processed": s.processed,
            "module_id": s.module_id,
            "bunny_video_id": s.bunny_video_id,
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]
