import uuid
from datetime import datetime, timezone
from typing import ClassVar

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class ContentAccessRule(Document):
    """
    A per-person override on one piece of content, set by an admin.

    Audience rules on the content itself (team / department / role) cover the
    common case. This handles the exceptions: letting one person into something
    their team can't see, or keeping one person out of something it can.

    Stored as its own collection rather than a list on the module or the user
    because it is sparse — a handful of exceptions across a growing catalogue —
    and because it carries its own audit fields (who set it, when, and why).

    Covers two kinds of content — modules and test series — in one collection
    rather than two parallel ones. The precedence rules (revoke beats grant,
    required implies access, admins bypass) and the audit fields are identical
    for both, and duplicating them is how the two drift apart.
    """

    # ClassVar, not fields: Pydantic treats bare class attributes as model
    # fields and rejects them without an annotation.
    GRANT: ClassVar[str] = "grant"
    REVOKE: ClassVar[str] = "revoke"
    # Required implies access — you cannot mandate something invisible.
    REQUIRED: ClassVar[str] = "required"

    # What `content_id` points at.
    KIND_MODULE: ClassVar[str] = "module"
    KIND_TEST: ClassVar[str] = "test"
    KINDS: ClassVar[tuple[str, ...]] = (KIND_MODULE, KIND_TEST)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str  # references users.id
    # References modules.id or test_series.id depending on `content_kind`.
    #
    # Still named module_id: renaming it would orphan every rule an admin has
    # already set, since the documents on disk carry that key. The alias below
    # is what the rest of the code reads, so nothing outside this model has to
    # know about the historical name.
    module_id: str
    # Defaults to "module" so rules written before test series were covered
    # keep pointing at modules rather than becoming ambiguous.
    content_kind: str = KIND_MODULE
    # grant    = can see it even if the audience rules say no
    # required = same as grant, plus it is mandatory for this person
    # revoke   = cannot see it even if the audience rules say yes
    access: str
    # Free-text note so the next admin can tell why an exception exists.
    reason: str | None = None
    created_by_admin_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def content_id(self) -> str:
        """The module or test this rule applies to, under a kind-neutral name."""
        return self.module_id

    class Settings:
        name = "content_access_rules"
        indexes = [
            # One rule per user per piece of content; re-assigning updates in
            # place. Module and test ids are both UUIDs from the same space, so
            # the pair stays unique without content_kind in the key — and
            # leaving it out keeps the index compatible with the rules already
            # stored under it.
            IndexModel([("user_id", ASCENDING), ("module_id", ASCENDING)], unique=True),
            IndexModel([("module_id", ASCENDING)]),
            # Drives "every test rule for this person" without scanning module
            # rules, which outnumber them.
            IndexModel([("user_id", ASCENDING), ("content_kind", ASCENDING)]),
        ]
