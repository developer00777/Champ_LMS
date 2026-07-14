import uuid
from datetime import datetime, timezone
from typing import Any
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class PathNode:
    """Embedded node in a LearningPath. Not a separate collection."""
    sequence: int
    module_id: str
    node_type: str = "video"  # video | quiz | milestone | summit
    unlock_rule: str = "previous"  # previous | all_previous_mastered | manual
    is_summit: bool = False
    title: str | None = None


class LearningPath(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key: str  # unique stable identifier
    title: str
    description: str | None = None
    department: str | None = None  # sales | leadership | onboarding | product | engineering | ops
    path_type: str = "upskilling"  # onboarding | upskilling
    variant: str = "ridge"  # trail (onboarding) | ridge (upskilling)
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    total_modules: int = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "learning_paths"
        indexes = [
            IndexModel([("key", ASCENDING)], unique=True),
            IndexModel([("department", ASCENDING), ("path_type", ASCENDING)]),
        ]


class UserPathProgress(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    path_id: str
    current_node: int = 0  # index into nodes array
    unlocked_nodes: list[int] = Field(default_factory=lambda: [0])  # node indices unlocked
    mastered_nodes: list[int] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    class Settings:
        name = "user_path_progress"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("path_id", ASCENDING)], unique=True),
        ]
