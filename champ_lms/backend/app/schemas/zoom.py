import uuid
from datetime import datetime
from pydantic import BaseModel


class ZoomSessionCreate(BaseModel):
    zoom_meeting_id: str | None = None
    topic: str
    summary: str
    transcript: str
    recording_url: str | None = None


class ZoomSessionOut(BaseModel):
    id: uuid.UUID
    zoom_meeting_id: str | None
    topic: str | None
    summary: str | None
    processed: bool
    module_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
