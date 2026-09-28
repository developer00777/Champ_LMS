import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING


class Episode(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    module_id: str  # references modules.id — cascade delete handled in app code
    title: str
    description: str | None = None
    duration_seconds: int | None = None
    sequence_order: int

    # Bunny Stream video ID (returned when video is created in library)
    bunny_video_id: str | None = None
    # Bunny Stream GUID (same as bunny_video_id but stored explicitly for clarity)
    bunny_video_guid: str | None = None

    # status: processing | ready | failed | pending
    status: str = "processing"

    # Transcript + AI outputs
    transcript: str | None = None
    ai_summary: str | None = None
    # Timed transcript lines [{start, end, text}] in seconds. Drives the
    # learner's synced transcript; `transcript` above stays the plain-text join
    # so the quiz generator and Zoom pipeline keep reading what they always did.
    transcript_segments: list[dict] | None = None
    # auto = written by the AI from the audio; manual = typed or edited by an
    # admin. Regenerating never silently replaces a manual transcript.
    transcript_source: str | None = None
    # processing | ready | failed | None (nothing attempted yet)
    transcript_status: str | None = None
    # Notes shown under the video, in the canvas' light markup ("## " headings,
    # "- " bullets). ai = drafted from the transcript; manual = admin-written.
    notes: str | None = None
    notes_source: str | None = None
    # Name of the file the admin uploaded. Lets the canvas match a file picked
    # again later (to transcribe a video uploaded before transcripts worked)
    # to its episode.
    source_filename: str | None = None

    # Bunny Storage path for episode thumbnail (manually uploaded)
    thumbnail_bunny_path: str | None = None
    # Bunny Stream auto-generated thumbnail URL (set when transcoding finishes)
    thumbnail_url: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "episodes"
        indexes = [
            IndexModel([("module_id", ASCENDING), ("sequence_order", ASCENDING)]),
            IndexModel([("bunny_video_guid", ASCENDING)]),
        ]
