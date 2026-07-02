import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Enrollment(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # references users.id
    module_id: str  # references modules.id
    enrolled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    completion_percentage: float = 0.0

    class Settings:
        name = "enrollments"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("module_id", ASCENDING)], unique=True),
        ]
