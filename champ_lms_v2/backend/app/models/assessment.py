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

    # --- Canvas checkpoint quizzes -----------------------------------------
    # "checkpoint" marks a quiz placed on a course canvas. None on the older
    # per-module and per-episode quizzes; the lookups for those filter on
    # kind == None so a checkpoint is never mistaken for a module quiz.
    kind: str | None = None
    # Episodes the questions were written from.
    source_episode_ids: list[str] = Field(default_factory=list)
    question_count: int = 5
    difficulty: str = "medium"  # easy | medium | hard
    # When true, the canvas item after this quiz stays locked until it is passed.
    must_pass: bool = False
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
