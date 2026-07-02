import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Module(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    target_roles: list[str] | None = None
    created_by: str | None = None  # references users.id
    source_type: str = "manual"  # manual|zoom|upload
    zoom_session_id: str | None = None  # references zoom_sessions.id
    # Bunny Storage path for thumbnail, served via CDN with Optimizer
    thumbnail_bunny_path: str | None = None
    is_published: bool = False
    total_episodes: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "modules"
        indexes = [
            IndexModel([("is_published", ASCENDING), ("created_at", ASCENDING)]),
            IndexModel([("category", ASCENDING)]),
        ]
