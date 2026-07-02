import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Badge(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str | None = None
    # Bunny Storage path, served via CDN
    icon_bunny_path: str | None = None
    # {"type": "complete_module", "count": 1} etc.
    criteria: dict | None = None

    class Settings:
        name = "badges"


class UserBadge(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # references users.id
    badge_id: str  # references badges.id
    earned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "user_badges"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("badge_id", ASCENDING)], unique=True),
        ]
