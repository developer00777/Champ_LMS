"""
Notes pages on a course canvas, and the PDFs attached to them.

Attachments live in MongoDB rather than Bunny: Bunny is used for video only.
A notes PDF is small and read rarely, so one document per file (capped well
under Mongo's 16MB document limit) is simpler than adding another store.
"""
import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING

MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


class CourseNote(Document):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    module_id: str
    title: str
    # Light markup: "## " headings, "- " bullets, blank line between paragraphs.
    body: str = ""
    # manual = written by an admin; ai = drafted from the section's videos.
    source: str = "manual"
    attachment_id: str | None = None  # NoteAttachment.id
    attachment_name: str | None = None
    attachment_size: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "course_notes"
        indexes = [IndexModel([("module_id", ASCENDING)])]


class NoteAttachment(Document):
    """The bytes of one attached PDF, kept apart so listing notes stays light."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    note_id: str
    filename: str
    content_type: str = "application/pdf"
    data: bytes
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "note_attachments"
        indexes = [IndexModel([("note_id", ASCENDING)])]
