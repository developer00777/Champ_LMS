"""
Approval gate for test series.

A test is only takeable when it is both published (the author says the content
is finished) and approved (an admin says it may be put in front of employees),
and the per-person attempt allowance is the test's cap plus whatever extra
attempts an admin has granted that person.

Both rules live here rather than being re-implemented in each endpoint: the
take and submit paths must agree exactly, or a learner blocked from opening a
paper could still POST a submission for it.
"""
from datetime import datetime, timezone

from app.models.test_series import (
    APPROVAL_APPROVED,
    APPROVAL_PENDING,
    AttemptGrant,
    TestAttempt,
    TestSeries,
)


async def backfill_approvals() -> int:
    """
    Mark every pre-existing published test as approved, once.

    Without this, deploying the approval gate would pull every live test at the
    moment the new code starts — which reads as an outage, not a policy change.
    Approval is a rule for tests published from now on; what was already live
    stays live and is recorded as approved by the system.

    Idempotent: it only touches published tests still sitting at the `pending`
    default and never set an approver, so a test an admin later sends back to
    pending on purpose is not silently re-approved on the next restart.
    """
    stale = await TestSeries.find(
        TestSeries.is_published == True,  # noqa: E712
        TestSeries.approval_status == APPROVAL_PENDING,
        TestSeries.approved_at == None,  # noqa: E711
    ).to_list()

    now = datetime.now(timezone.utc)
    for test in stale:
        test.approval_status = APPROVAL_APPROVED
        test.approved_by = None  # no human approver — grandfathered by the system
        test.approved_at = now
        test.approval_note = (
            "Auto-approved: this test was already published before approval was "
            "required."
        )
        await test.save()
    return len(stale)


async def granted_extra_attempts(test_id: str, user_id: str) -> int:
    """Total extra attempts this person has been granted on this test."""
    grants = await AttemptGrant.find(
        AttemptGrant.test_id == test_id, AttemptGrant.user_id == user_id
    ).to_list()
    return sum(g.extra_attempts for g in grants)


async def attempt_allowance(test: TestSeries, user_id: str) -> int | None:
    """
    How many attempts this person may make on this test in total.

    None means unlimited — the test has no cap, so grants are irrelevant and we
    skip the query entirely.
    """
    if test.max_attempts is None:
        return None
    return test.max_attempts + await granted_extra_attempts(test.id, user_id)


async def attempt_status(test: TestSeries, user_id: str) -> dict:
    """
    One person's attempt position on one test: used, granted, allowed, left.

    Returned whole rather than as separate lookups so the learner list, the
    take endpoint and the admin results page all describe the same numbers.
    """
    used = await TestAttempt.find(
        TestAttempt.test_id == test.id, TestAttempt.user_id == user_id
    ).count()
    granted = (
        0 if test.max_attempts is None
        else await granted_extra_attempts(test.id, user_id)
    )
    allowed = None if test.max_attempts is None else test.max_attempts + granted
    return {
        "used": used,
        "granted_extra": granted,
        "allowed": allowed,
        "left": None if allowed is None else max(0, allowed - used),
        "exhausted": allowed is not None and used >= allowed,
    }
