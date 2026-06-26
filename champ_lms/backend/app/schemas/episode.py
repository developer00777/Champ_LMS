import uuid
from datetime import datetime
from pydantic import BaseModel


class EpisodeOut(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    title: str
    description: str | None
    duration_seconds: int | None
    sequence_order: int
    thumbnail_key: str | None
    status: str
    ai_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EpisodeCreate(BaseModel):
    title: str
    description: str | None = None
    duration_seconds: int | None = None
    sequence_order: int


class EpisodeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    hls_manifest_key: str | None = None
    transcript: str | None = None
    ai_summary: str | None = None
    duration_seconds: int | None = None
