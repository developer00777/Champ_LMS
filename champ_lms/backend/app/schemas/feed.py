import uuid
from pydantic import BaseModel


class FeedCard(BaseModel):
    id: uuid.UUID
    title: str
    thumbnail_url: str | None
    category: str | None
    total_episodes: int
    completion_percentage: float = 0.0
    is_new: bool = False


class FeedRow(BaseModel):
    row_title: str
    modules: list[FeedCard]


class FeedResponse(BaseModel):
    rows: list[FeedRow]
