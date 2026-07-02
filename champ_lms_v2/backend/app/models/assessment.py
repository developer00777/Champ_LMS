import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Assessment(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    module_id: str  # references modules.id
    episode_id: str | None = None  # references episodes.id
    title: str | None = None
    # [{question, options[], correct_index, explanation}]
    questions: list
    pass_threshold: int = 70
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "assessments"
        indexes = [
            IndexModel([("module_id", ASCENDING), ("episode_id", ASCENDING)]),
        ]


class AssessmentAttempt(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # references users.id
    assessment_id: str  # references assessments.id
    score: int | None = None
    passed: bool | None = None
    answers: list | None = None
    attempted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "assessment_attempts"
