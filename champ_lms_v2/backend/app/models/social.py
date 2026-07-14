import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class SocialPost(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    team_id: str | None = None
    post_type: str = "win"  # win | shoutout | help | milestone
    body: str
    ref_type: str | None = None  # module | badge | challenge | path
    ref_id: str | None = None
    likes: list[str] = Field(default_factory=list)  # user_ids who liked
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "social_posts"
        indexes = [
            IndexModel([("created_at", ASCENDING)]),
            IndexModel([("user_id", ASCENDING)]),
            IndexModel([("team_id", ASCENDING)]),
            IndexModel([("post_type", ASCENDING)]),
        ]


class Notification(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    notif_type: str  # badge_earned | level_up | quest_complete | team_update | shoutout | challenge_won
    title: str
    body: str | None = None
    ref_type: str | None = None
    ref_id: str | None = None
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "notifications"
        indexes = [
            IndexModel([("user_id", ASCENDING), ("read", ASCENDING), ("created_at", ASCENDING)]),
        ]
