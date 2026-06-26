import uuid
from datetime import datetime
from pydantic import BaseModel


class BadgeOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    icon_url: str | None
    earned_at: datetime

    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    full_name: str | None
    department: str | None
    points: int
    streak_days: int
