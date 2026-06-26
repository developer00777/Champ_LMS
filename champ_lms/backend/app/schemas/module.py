import uuid
from datetime import datetime
from pydantic import BaseModel
from app.schemas.episode import EpisodeOut


class ModuleOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    category: str | None
    tags: list[str] | None
    target_roles: list[str] | None
    source_type: str
    thumbnail_url: str | None
    is_published: bool
    total_episodes: int
    created_at: datetime
    episodes: list[EpisodeOut] = []

    model_config = {"from_attributes": True}


class ModuleCreate(BaseModel):
    title: str
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    target_roles: list[str] | None = None
    source_type: str = "manual"


class ModuleUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    target_roles: list[str] | None = None
    thumbnail_url: str | None = None
    is_published: bool | None = None
