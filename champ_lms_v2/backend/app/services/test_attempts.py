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

    Returned whole rather than as separate lookups so every caller describes
    the same numbers.
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


def exhausted_message(status: dict) -> str:
    """
    Explain a spent allowance, naming the granted attempts when there were any.

    Someone who was given an extra attempt and used it should be told their
    total was 3, not the test's nominal 2 — otherwise the message contradicts
    what they were told when the grant was made.
    """
    allowed = status["allowed"]
    if status["granted_extra"]:
        return (
            f"You have used all {allowed} attempts for this test "
            f"(including {status['granted_extra']} granted by an admin)."
        )
    return f"You have used all {allowed} attempts for this test."
