import uuid
from datetime import datetime, timezone
from typing import ClassVar

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class ContentAccessRule(Document):
    """
    A per-person override on one module, set by an admin.

    Audience rules on the module itself (team / department / role) cover the
    common case. This handles the exceptions: letting one person into something
    their team can't see, or keeping one person out of something it can.

    Stored as its own collection rather than a list on the module or the user
    because it is sparse — a handful of exceptions across a growing catalogue —
    and because it carries its own audit fields (who set it, when, and why).
    """

    # ClassVar, not fields: Pydantic treats bare class attributes as model
    # fields and rejects them without an annotation.
    GRANT: ClassVar[str] = "grant"
    REVOKE: ClassVar[str] = "revoke"
    # Required implies access — you cannot mandate something invisible.
    REQUIRED: ClassVar[str] = "required"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # references users.id
    module_id: str  # references modules.id
    # grant    = can see it even if the audience rules say no
    # required = same as grant, plus it is mandatory for this person
    # revoke   = cannot see it even if the audience rules say yes
    access: str
    # Free-text note so the next admin can tell why an exception exists.
    reason: str | None = None
    created_by_admin_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "content_access_rules"
        indexes = [
            # One rule per user per module; re-assigning updates in place.
            IndexModel([("user_id", ASCENDING), ("module_id", ASCENDING)], unique=True),
            IndexModel([("module_id", ASCENDING)]),
        ]
