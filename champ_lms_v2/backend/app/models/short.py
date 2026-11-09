"""
Shorts: short vertical-first videos, watched in a swipeable feed.

A short is a standalone video, not part of a module. Its file lives on Bunny
Stream like every other video (Bunny is video only); its poster is a frame
the admin's browser captured, kept in MongoDB with the other thumbnails
(owner_kind "short").

A short can be any shape. width/height are the file's own pixels; `aspect`
is the nearest named size (9:16, 4:5, 1:1, 16:9) for labels and filters.
`fit` is how the feed shows a picture that isn't the screen's shape:
contain = all of it, on a blurred copy of itself; cover = fill the screen,
cropping around focus_x.
"""
import uuid
from datetime import datetime, timezone

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel

ASPECTS = {"9:16": 9 / 16, "4:5": 4 / 5, "1:1": 1.0, "16:9": 16 / 9}
FITS = ("contain", "cover")
# Longest a short may run, in seconds (YouTube's limit for Shorts).
MAX_SHORT_SECONDS = 180


def nearest_aspect(width: int | None, height: int | None) -> str:
    if not width or not height:
        return "9:16"
    r = width / height
    return min(ASPECTS, key=lambda k: abs(ASPECTS[k] - r))


class Short(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str | None = None
    # A course the short points to ("Watch the full course").
    module_id: str | None = None

    bunny_video_guid: str | None = None
    # pending (no file yet) | processing | ready | failed
    status: str = "pending"
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    aspect: str = "9:16"
    fit: str = "contain"
    focus_x: int = 50
    source_filename: str | None = None
    # resizer = rendered in the admin's browser by the video resizer.
    made_with: str | None = None

    poster_id: str | None = None          # Thumbnail id (Mongo)
    bunny_thumbnail_url: str | None = None  # Bunny's own frame, as a fallback

    is_published: bool = True
    view_count: int = 0
    like_count: int = 0
    created_by: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "shorts"
        indexes = [
            IndexModel([("is_published", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("bunny_video_guid", ASCENDING)]),
        ]


class ShortLike(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    short_id: str
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "short_likes"
        indexes = [IndexModel([("short_id", ASCENDING), ("user_id", ASCENDING)], unique=True)]


class ShortView(Document):
    """One row per learner and short: what the feed uses to show unseen first."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    short_id: str
    user_id: str
    watched_seconds: float = 0
    completed: bool = False
    last_viewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "short_views"
        indexes = [
            IndexModel([("short_id", ASCENDING), ("user_id", ASCENDING)], unique=True),
            IndexModel([("user_id", ASCENDING)]),
        ]
