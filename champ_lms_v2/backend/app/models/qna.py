"""
Questions a learner asks on a course video, and the admin's answer.

Anyone who can open the course sees every question on an episode with its
answer, so one answer serves everyone who wonders the same thing. Admins see
all of them in one inbox (/admin/questions) and answer there or in the player.

at_seconds is in seconds of the whole Bunny video (source time), like the
transcript, so a question stays on its moment when a video is trimmed, split
or joined. The API shows it in clip time. See services/clips.py.
"""
import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING


class EpisodeQuestion(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    module_id: str
    episode_id: str
    user_id: str
    body: str
    at_seconds: float | None = None  # source time; None = about the whole video
    answer: str | None = None
    answered_by: str | None = None  # User.id
    answered_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "episode_questions"
        indexes = [
            IndexModel([("episode_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("answered_at", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("module_id", ASCENDING)]),
        ]
