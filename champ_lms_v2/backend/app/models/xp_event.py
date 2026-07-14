import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class XpEvent(Document):
    """
    Immutable XP ledger. Every XP award is one row.
    Unique (user_id, reason, ref_id) prevents double-awards on retries.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # references users.id
    amount: int
    reason: str   # e.g. complete_episode, complete_module, pass_quiz, module_mastery
    ref_type: str | None = None  # episode, module, assessment, quest
    ref_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "xp_events"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("reason", ASCENDING), ("ref_id", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING), ("created_at", ASCENDING)]),
        ]
