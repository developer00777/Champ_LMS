"""
A learner asking to sit a test that needs approval.

Approving writes an AttemptGrant, so the allowance the take and submit
endpoints already enforce is simply the sum of approved attempts. This
document is the request and its decision; the grant is the permission. Keeping
them apart means the existing retake ledger stays the one place attempts are
counted.
"""
import uuid
from datetime import datetime, timezone
from typing import ClassVar
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING


class TestRequest(Document):
    PENDING: ClassVar[str] = "pending"
    APPROVED: ClassVar[str] = "approved"
    DENIED: ClassVar[str] = "denied"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    test_id: str
    module_id: str | None = None
    user_id: str
    status: str = "pending"
    # Filled on approval.
    attempts_granted: int | None = None
    grant_id: str | None = None  # AttemptGrant.id
    note: str | None = None  # the admin's note to the learner on approval
    reason: str | None = None  # the admin's reason on denial
    decided_by: str | None = None
    decided_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "test_requests"
        indexes = [
            IndexModel([("status", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("test_id", ASCENDING), ("user_id", ASCENDING)]),
        ]
