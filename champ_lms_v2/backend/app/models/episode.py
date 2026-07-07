import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Episode(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    module_id: str  # references modules.id — cascade delete handled in app code
    title: str
    description: str | None = None
    duration_seconds: int | None = None
    sequence_order: int

    # Bunny Stream video ID (returned when video is created in library)
    bunny_video_id: str | None = None
    # Bunny Stream GUID (same as bunny_video_id but stored explicitly for clarity)
    bunny_video_guid: str | None = None

    # status: processing | ready | failed | pending
    status: str = "processing"

    # Transcript + AI outputs
    transcript: str | None = None
    ai_summary: str | None = None

    # Bunny Storage path for episode thumbnail (manually uploaded)
    thumbnail_bunny_path: str | None = None
    # Bunny Stream auto-generated thumbnail URL (set when transcoding finishes)
    thumbnail_url: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "episodes"
        indexes = [
            IndexModel([("module_id", ASCENDING), ("sequence_order", ASCENDING)]),
            IndexModel([("bunny_video_guid", ASCENDING)]),
        ]
