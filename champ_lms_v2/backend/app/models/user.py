import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class User(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    full_name: str | None = None
    hashed_password: str
    # role: learner | admin | ld_lead
    role: str = "learner"
    department: str | None = None
    # Bunny Storage path for avatar, served via CDN
    avatar_bunny_path: str | None = None
    points: int = 0
    streak_days: int = 0
    last_activity_at: datetime | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "users"
        indexes = [
            IndexModel([("email", ASCENDING)], unique=True),
        ]
