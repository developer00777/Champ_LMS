import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field


class ZoomSession(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    zoom_meeting_id: str | None = None
    topic: str | None = None
    summary: str | None = None
    transcript: str | None = None
    recording_download_url: str | None = None
    # Bunny Stream video ID after download + upload to Bunny
    bunny_video_id: str | None = None
    processed: bool = False
    module_id: str | None = None  # references modules.id
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "zoom_sessions"
