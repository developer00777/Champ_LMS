import uuid
from datetime import datetime
from pydantic import BaseModel


class ProgressUpsert(BaseModel):
    episode_id: uuid.UUID
    watched_seconds: int
    total_seconds: int


class ProgressOut(BaseModel):
    episode_id: uuid.UUID
    watched_seconds: int
    total_seconds: int | None
    completed: bool
    last_watched_at: datetime

    model_config = {"from_attributes": True}
