import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class WatchProgress(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # references users.id — cascade delete handled in app code
    episode_id: str  # references episodes.id — cascade delete handled in app code
    watched_seconds: int = 0
    total_seconds: int | None = None
    completed: bool = False
    completed_at: datetime | None = None
    last_watched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "watch_progress"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("episode_id", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING), ("completed", ASCENDING), ("last_watched_at", ASCENDING)]),
        ]
