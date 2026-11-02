"""
Music and voice-overs added in the video studio.

Kept in MongoDB, like notes PDFs: Bunny is used for video only, and the
studio never re-encodes the video, so the player mixes these in as it plays.
One document per file, capped well under Mongo's 16MB document limit. A file
belongs to a Bunny video (every part split from it shares the same edits),
and files no saved edit uses any more are removed when the studio saves.
"""
import uuid
from datetime import datetime, timezone

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

MAX_STUDIO_AUDIO_BYTES = 12 * 1024 * 1024


class StudioAudio(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    video_guid: str
    # music: an uploaded track; voice: a voice-over recorded in the studio.
    kind: str = "music"
    filename: str
    content_type: str
    # Seconds, as the browser measured it; the player needs it to loop and fade.
    duration: float | None = None
    data: bytes
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "studio_audio"
        indexes = [IndexModel([("video_guid", ASCENDING)])]
