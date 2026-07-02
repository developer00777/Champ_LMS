import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Recommendation(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # references users.id
    # [{row_title, module_ids[]}]
    rows: list
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "recommendations"
        indexes = [
            IndexModel([("user_id", ASCENDING)], unique=True),
        ]
