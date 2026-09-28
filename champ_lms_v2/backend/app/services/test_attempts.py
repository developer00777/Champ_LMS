"""
How many attempts one person gets on one test.

The allowance is the test's own cap plus whatever extra attempts an admin has
granted that individual — the person whose browser died mid-exam, or who was
sat in the wrong room. Grants are an append-only ledger (AttemptGrant) rather
than a counter, so "who let them retake it, when, and why" is answerable later,
two admins granting at once can't lose each other's update, and revoking is
deleting one row.

Lives here rather than inline in the router because the learner list, the take
endpoint and the submit endpoint must all agree on the same numbers. A learner
told "1 attempt left" by the list and then refused by /submit is worse than
either answer on its own.
"""
from __future__ import annotations

from app.models.test_series import AttemptGrant, TestAttempt, TestSeries


def base_attempts(test: TestSeries) -> int | None:
    """
    The allowance before any grant: the test's cap, or None for unlimited.

    A test that needs approval starts every person at zero. Approving a
    request writes an AttemptGrant, so their allowance is exactly the
    attempts they were approved for, and max_attempts plays no part.
    """
    if test.requires_approval:
        return 0
    return test.max_attempts


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
    base = base_attempts(test)
    if base is None:
        return None
    return base + await granted_extra_attempts(test.id, user_id)


async def attempt_status(test: TestSeries, user_id: str) -> dict:
    """
    One person's attempt position on one test: used, granted, allowed, left.

    Returned whole rather than as separate lookups so every caller describes
    the same numbers.
    """
    used = await TestAttempt.find(
        TestAttempt.test_id == test.id, TestAttempt.user_id == user_id
    ).count()
    base = base_attempts(test)
    granted = 0 if base is None else await granted_extra_attempts(test.id, user_id)
    allowed = None if base is None else base + granted
    return {
        "used": used,
        "granted_extra": granted,
        "allowed": allowed,
        "left": None if allowed is None else max(0, allowed - used),
        "exhausted": allowed is not None and used >= allowed,
        "requires_approval": test.requires_approval,
    }


def exhausted_message(status: dict) -> str:
    """
    Explain a spent allowance, naming the granted attempts when there were any.

    Someone who was given an extra attempt and used it should be told their
    total was 3, not the test's nominal 2 — otherwise the message contradicts
    what they were told when the grant was made.
    """
    allowed = status["allowed"]
    if status.get("requires_approval"):
        if not allowed:
            return "This test needs your admin's approval. Send a request from the course."
        return (
            f"You have used the {allowed} attempt{'s' if allowed != 1 else ''} "
            "your admin approved. Ask for another from the course."
        )
    if status["granted_extra"]:
        return (
            f"You have used all {allowed} attempts for this test "
            f"(including {status['granted_extra']} granted by an admin)."
        )
    return f"You have used all {allowed} attempts for this test."
