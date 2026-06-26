import hashlib
import hmac
import json
import boto3
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.auth import get_current_user_dev as get_current_user
from app.core.config import get_settings
from app.models.zoom_session import ZoomSession
from app.schemas.zoom import ZoomSessionCreate, ZoomSessionOut

router = APIRouter(prefix="/zoom", tags=["zoom"])
settings = get_settings()


def _verify_zoom_signature(body: bytes, signature: str, timestamp: str) -> bool:
    message = f"v0:{timestamp}:{body.decode()}"
    expected = "v0=" + hmac.new(
        settings.zoom_webhook_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def zoom_webhook(
    request: Request,
    x_zm_signature: str = Header(None),
    x_zm_request_timestamp: str = Header(None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    # Verify Zoom webhook signature in production
    if settings.zoom_webhook_secret and x_zm_signature:
        if not _verify_zoom_signature(body, x_zm_signature, x_zm_request_timestamp):
            raise HTTPException(status_code=401, detail="Invalid Zoom signature")

    payload = json.loads(body)
    event = payload.get("event")

    if event == "endpoint.url_validation":
        # Zoom URL validation challenge
        token = payload["payload"]["plainToken"]
        encrypted = hmac.new(
            settings.zoom_webhook_secret.encode(), token.encode(), hashlib.sha256
        ).hexdigest()
        return {"plainToken": token, "encryptedToken": encrypted}

    if event == "recording.completed":
        meeting = payload["payload"]["object"]
        session = ZoomSession(
            zoom_meeting_id=str(meeting.get("id")),
            topic=meeting.get("topic"),
            recording_url=meeting.get("recording_files", [{}])[0].get("download_url"),
        )
        db.add(session)
        await db.flush()

        # Push to SQS for async processing
        if settings.sqs_zoom_queue_url:
            sqs = boto3.client("sqs", region_name=settings.aws_region)
            sqs.send_message(
                QueueUrl=settings.sqs_zoom_queue_url,
                MessageBody=json.dumps({"session_id": str(session.id), "payload": meeting}),
            )

    return {"status": "ok"}


@router.post("/sessions", response_model=ZoomSessionOut)
async def create_zoom_session(
    payload: ZoomSessionCreate,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = ZoomSession(**payload.model_dump())
    db.add(session)
    await db.flush()
    return session


@router.get("/sessions", response_model=list[ZoomSessionOut])
async def list_zoom_sessions(
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ZoomSession).order_by(ZoomSession.created_at.desc()).limit(50)
    )
    return result.scalars().all()


@router.post("/build-module/{session_id}")
async def build_module_from_session(
    session_id: str,
    claims: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.ai_service import generate_module_from_zoom
    from app.models.module import Module
    from app.models.episode import Episode

    result = await db.execute(select(ZoomSession).where(ZoomSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Zoom session not found")
    if not session.transcript and not session.summary:
        raise HTTPException(status_code=400, detail="Session has no transcript or summary")

    module_data = await generate_module_from_zoom(
        transcript=session.transcript or "",
        summary=session.summary or "",
    )

    module = Module(
        title=module_data["title"],
        description=module_data["description"],
        category=module_data.get("category"),
        tags=module_data.get("tags"),
        target_roles=module_data.get("target_roles"),
        source_type="zoom",
        zoom_session_id=session.id,
        is_published=False,
    )
    db.add(module)
    await db.flush()

    for i, ep_data in enumerate(module_data.get("episodes", [])):
        episode = Episode(
            module_id=module.id,
            title=ep_data["title"],
            description=ep_data.get("description"),
            sequence_order=i + 1,
            duration_seconds=ep_data.get("duration_estimate_seconds"),
            status="pending_video",
        )
        db.add(episode)

    session.processed = True
    session.module_id = module.id
    await db.flush()

    return {"module_id": str(module.id), "title": module.title, "episodes": len(module_data.get("episodes", []))}
