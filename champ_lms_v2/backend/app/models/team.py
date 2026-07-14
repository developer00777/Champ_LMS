import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Team(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    department: str | None = None
    member_ids: list[str] = Field(default_factory=list)
    captain_id: str | None = None
    challenge_id: str | None = None  # the challenge this team is entered in
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "teams"
        indexes = [
            IndexModel([("challenge_id", ASCENDING)]),
            IndexModel([("department", ASCENDING)]),
        ]


class TeamChallenge(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key: str  # unique stable identifier
    title: str
    description: str | None = None
    challenge_type: str = "dept_race"  # onboarding_sprint | compliance_quest | dept_race
    department: str | None = None  # None = cross-department
    team_size: int = 4
    start_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_at: datetime | None = None
    criteria: dict = Field(default_factory=dict)  # {"type": "team_complete_modules", "count": 5}
    reward_xp: int = 100
    reward_points: int = 50
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "team_challenges"
        indexes = [
            IndexModel([("key", ASCENDING)], unique=True),
            IndexModel([("active", ASCENDING), ("department", ASCENDING)]),
        ]


class TeamProgress(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    challenge_id: str
    team_id: str
    progress: int = 0
    target: int = 1
    completed: bool = False
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "team_progress"
        indexes = [
            IndexModel([("challenge_id", ASCENDING), ("team_id", ASCENDING)], unique=True),
        ]
