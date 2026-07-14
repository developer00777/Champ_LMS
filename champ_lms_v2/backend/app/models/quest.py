import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Quest(Document):
    """
    Daily/weekly mission template. criteria is a dict the progress engine reads,
    e.g. {"type": "watch_episodes", "count": 2} or {"type": "complete_module_category", "category": "sales"}.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key: str  # unique stable identifier
    scope: str  # daily | weekly
    title: str
    criteria: dict
    reward_xp: int = 0
    reward_points: int = 0
    active: bool = True

    class Settings:
        name = "quests"
        indexes = [
            IndexModel([("key", ASCENDING)], unique=True),
            IndexModel([("scope", ASCENDING), ("active", ASCENDING)]),
        ]


class UserQuest(Document):
    """
    A user's progress toward one Quest for a given period (date or iso-week).
    Unique (user_id, quest_id, period_key) prevents duplicates.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    quest_id: str
    period_key: str  # YYYY-MM-DD for daily, YYYY-Www for weekly
    progress: int = 0
    target: int = 1
    completed: bool = False
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "user_quests"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("quest_id", ASCENDING), ("period_key", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING), ("completed", ASCENDING)]),
        ]
