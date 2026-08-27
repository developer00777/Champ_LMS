"""
E2E test for the test-series approval gate and per-person extra attempts.

Covers the two rules this suite exists to protect:

  1. Approval gate — a test nobody approved must not be publishable, must not
     appear in any learner's list, and must be refused by both /take and
     /submit. Editing the questions of an approved test withdraws the approval.
  2. Extra attempts — an admin can lift one person's ceiling on one test
     without touching anybody else's, and revoking the grant puts it back.

Prerequisites:
- Backend running on BASE with MongoDB + Redis reachable
- ADMIN_EMAIL / ADMIN_PASSWORD set to the values below (or exported to match)

Run:
    python test_approval_attempts_e2e.py
"""
import asyncio
import os
import sys
import uuid

import httpx

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:8000")
ADMIN = {
    "email": os.environ.get("E2E_ADMIN_EMAIL", "approval.admin@champ-e2e.example.com"),
    "password": os.environ.get("E2E_ADMIN_PASSWORD", "adminpass123"),
}

# Unique per run so repeated runs don't collide on the unique email index.
RUN = uuid.uuid4().hex[:8]
LEARNER = {
    "email": f"approval.learner.{RUN}@champ-e2e.example.com",
    "full_name": "Approval Learner",
    "password": "learner123",
    "department": "sales",
}
OTHER = {
    "email": f"approval.other.{RUN}@champ-e2e.example.com",
    "full_name": "Other Learner",
    "password": "learner123",
    "department": "sales",
}

QUESTIONS = [
    {
        "question": "Which pricing tier includes onboarding support?",
        "question_type": "mcq",
        "options": ["Starter", "Growth", "Enterprise", "Trial"],
        "correct_index": 2,
        "topic": "Pricing",
        "marks": 1,
    },
    {
        "question": "What is the standard renewal notice period?",
        "question_type": "mcq",
        "options": ["7 days", "30 days", "60 days", "90 days"],
        "correct_index": 1,
        "topic": "Contracts",
        "marks": 1,
    },
]

_passed = 0
_failed = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}")
    else:
        _failed += 1
        print(f"  FAIL  {label}" + (f" -- {detail}" if detail else ""))


def ok(resp: httpx.Response, label: str) -> dict:
    """Assert a 2xx and return the body; any error here aborts the run."""
    if resp.status_code >= 400:
        print(f"  ABORT {label}: {resp.status_code} {resp.text[:300]}")
        sys.exit(1)
    return resp.json() if resp.content else {}


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def login(client: httpx.AsyncClient, email: str, password: str) -> str:
    resp = await client.post(
        "/auth/token", data={"username": email, "password": password}
    )
    return ok(resp, f"login {email}")["access_token"]


async def provision(client: httpx.AsyncClient, admin_h: dict, person: dict) -> str:
    """Create an employee (public sign-up is disabled) and return their token."""
    ok(
        await client.post(
            "/admin/employees",
            headers=admin_h,
            json={
                "email": person["email"],
                "full_name": person["full_name"],
                "department": person["department"],
                "role": "learner",
                "initial_password": person["password"],
            },
        ),
        f"provision {person['email']}",
    )
    return await login(client, person["email"], person["password"])


async def answers_for(client: httpx.AsyncClient, token: str, test_id: str) -> dict:
    """Fetch the paper and answer every question correctly."""
    paper = ok(
        await client.get(f"/test-series/{test_id}/take", headers=auth(token)),
        "take paper",
    )
    return {
        "answers": {q["id"]: 2 if "onboarding" in q["question"] else 1
                    for q in paper["questions"]},
        "text_answers": {},
    }


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=60) as client:
        print("=" * 64)
        print("Champ LMS v2 — approval gate + extra attempts E2E")
        print("=" * 64)

        admin_token = await login(client, ADMIN["email"], ADMIN["password"])
        admin_h = auth(admin_token)

        learner_token = await provision(client, admin_h, LEARNER)
        other_token = await provision(client, admin_h, OTHER)
        learner_h, other_h = auth(learner_token), auth(other_token)

        # ------------------------------------------------------------------
        print("\n[1] A new test starts unapproved")
        # ------------------------------------------------------------------
        test = ok(
            await client.post(
                "/admin/test-series",
                headers=admin_h,
                json={
                    "title": f"Approval Gate Test {RUN}",
                    "description": "E2E fixture",
                    "department": "sales",
                    "pass_threshold": 50,
                    "max_attempts": 1,
                    "questions": QUESTIONS,
                },
            ),
            "create test",
        )
        tid = test["id"]
        check(test["approval_status"] == "pending", "new test is pending approval",
              str(test["approval_status"]))
        check(test["is_live"] is False, "new test is not live")

        # ------------------------------------------------------------------
        print("\n[2] Publishing without approval is refused")
        # ------------------------------------------------------------------
        r = await client.patch(
            f"/admin/test-series/{tid}/publish?publish=true", headers=admin_h
        )
        check(r.status_code == 403, "publish refused before approval", f"got {r.status_code}")
        check("approval" in r.text.lower(), "refusal explains approval is needed", r.text[:120])

        # ------------------------------------------------------------------
        print("\n[3] An unapproved test is invisible and untakeable")
        # ------------------------------------------------------------------
        listed = ok(await client.get("/test-series", headers=learner_h), "learner list")
        check(all(t["id"] != tid for t in listed), "unapproved test absent from learner list")

        r = await client.get(f"/test-series/{tid}/take", headers=learner_h)
        check(r.status_code == 403, "take refused for unapproved test", f"got {r.status_code}")

        # The real gate: submitting directly, without ever opening the paper.
        r = await client.post(
            f"/test-series/{tid}/submit", headers=learner_h,
            json={"answers": {}, "text_answers": {}},
        )
        check(r.status_code == 403, "direct submit refused for unapproved test",
              f"got {r.status_code}")

        # ------------------------------------------------------------------
        print("\n[4] Approval queue, then approve + publish")
        # ------------------------------------------------------------------
        ok(await client.post(f"/admin/test-series/{tid}/submit-for-approval",
                             headers=admin_h), "submit for approval")
        queue = ok(await client.get("/admin/test-series-pending-approval",
                                    headers=admin_h), "approval queue")
        row = next((q for q in queue if q["id"] == tid), None)
        check(row is not None, "test appears in the approval queue")
        check(bool(row and row["awaiting_review"]), "queue marks it awaiting review")

        approved = ok(
            await client.post(f"/admin/test-series/{tid}/approve", headers=admin_h,
                              json={"note": "Reviewed, content is accurate."}),
            "approve",
        )
        check(approved["approval_status"] == "approved", "status is approved")
        check(approved["approved_by"] is not None, "approver is recorded")
        check(approved["is_live"] is False, "approved-but-unpublished is still not live")

        pub = ok(await client.patch(f"/admin/test-series/{tid}/publish?publish=true",
                                    headers=admin_h), "publish after approval")
        check(pub["is_live"] is True, "approved + published == live")

        listed = ok(await client.get("/test-series", headers=learner_h), "learner list")
        mine = next((t for t in listed if t["id"] == tid), None)
        check(mine is not None, "live test now visible to the learner")

        # ------------------------------------------------------------------
        print("\n[5] Editing questions withdraws the approval")
        # ------------------------------------------------------------------
        edited = ok(
            await client.post(
                f"/admin/test-series/{tid}/questions", headers=admin_h,
                json={"questions": [{
                    "question": "Which region owns EMEA renewals?",
                    "question_type": "mcq",
                    "options": ["APAC", "EMEA", "NA", "LATAM"],
                    "correct_index": 1,
                    "topic": "Contracts",
                    "marks": 1,
                }]},
            ),
            "append question",
        )
        check(edited["approval_revoked_by_this_change"] is True,
              "adding a question revokes approval")
        check(edited["approval_status"] == "pending", "edited test is pending again")

        r = await client.get(f"/test-series/{tid}/take", headers=learner_h)
        check(r.status_code == 403, "edited test is untakeable until re-approved",
              f"got {r.status_code}")

        # Re-approve so the attempt tests below have a live test to work with.
        ok(await client.post(f"/admin/test-series/{tid}/approve", headers=admin_h,
                             json={"note": "Re-reviewed after edit."}), "re-approve")

        # ------------------------------------------------------------------
        print("\n[6] Attempt cap is enforced")
        # ------------------------------------------------------------------
        body = await answers_for(client, learner_token, tid)
        first = ok(await client.post(f"/test-series/{tid}/submit", headers=learner_h,
                                     json=body), "first attempt")
        check("score" in first, "first attempt scored")

        r = await client.get(f"/test-series/{tid}/take", headers=learner_h)
        check(r.status_code == 403, "second attempt blocked at the cap",
              f"got {r.status_code}")

        r = await client.post(f"/test-series/{tid}/submit", headers=learner_h, json=body)
        check(r.status_code == 403, "second submit blocked at the cap",
              f"got {r.status_code}")

        # ------------------------------------------------------------------
        print("\n[7] Admin grants one extra attempt to one person")
        # ------------------------------------------------------------------
        me = ok(await client.get("/auth/me", headers=learner_h), "learner profile")
        learner_id = me["id"]

        grant = ok(
            await client.post(f"/admin/test-series/{tid}/grants", headers=admin_h,
                              json={"user_id": learner_id, "extra_attempts": 1,
                                    "reason": "Browser crashed mid-exam"}),
            "grant attempt",
        )
        check(grant["allowed"] == 2, "allowance raised to 2", str(grant.get("allowed")))
        check(grant["left"] == 1, "one attempt left after the grant", str(grant.get("left")))

        paper = ok(await client.get(f"/test-series/{tid}/take", headers=learner_h),
                   "take after grant")
        check(paper["attempts_allowed"] == 2, "paper reports the granted ceiling")
        check(paper["extra_attempts_granted"] == 1, "paper reports the grant")

        second = ok(await client.post(f"/test-series/{tid}/submit", headers=learner_h,
                                      json=await answers_for(client, learner_token, tid)),
                    "granted attempt submits")
        check("score" in second, "granted attempt scored")

        r = await client.post(f"/test-series/{tid}/submit", headers=learner_h, json=body)
        check(r.status_code == 403, "blocked again once the grant is spent",
              f"got {r.status_code}")
        check("granted" in r.text.lower(), "message mentions the granted attempts",
              r.text[:140])

        # ------------------------------------------------------------------
        print("\n[8] The grant is scoped to one person")
        # ------------------------------------------------------------------
        listed = ok(await client.get("/test-series", headers=other_h), "other learner list")
        theirs = next((t for t in listed if t["id"] == tid), None)
        check(theirs is not None, "test visible to the other learner")
        check(theirs and theirs["attempts_allowed"] == 1,
              "other learner still capped at 1", str(theirs and theirs["attempts_allowed"]))
        check(theirs and theirs["extra_attempts_granted"] == 0,
              "other learner has no grant")

        # ------------------------------------------------------------------
        print("\n[9] Grants are audited and revocable")
        # ------------------------------------------------------------------
        grants = ok(await client.get(f"/admin/test-series/{tid}/grants", headers=admin_h),
                    "list grants")
        check(len(grants) == 1, "one grant on the ledger", str(len(grants)))
        check(grants[0]["reason"] == "Browser crashed mid-exam", "reason retained")
        check(grants[0]["granted_by_name"] is not None, "grantor name resolved")

        results = ok(await client.get(f"/admin/test-series/{tid}/results", headers=admin_h),
                     "results")
        row = next((a for a in results["attempts"] if a["user_id"] == learner_id), None)
        check(row is not None, "learner appears in results")
        check(row and row["attempts_used"] == 2, "results show 2 attempts used",
              str(row and row["attempts_used"]))
        check(row and row["extra_attempts_granted"] == 1, "results show the grant")
        check(row and row["attempts_exhausted"] is True, "results show exhausted")

        revoked = ok(
            await client.delete(
                f"/admin/test-series/{tid}/grants/{grants[0]['grant_id']}",
                headers=admin_h),
            "revoke grant",
        )
        check(revoked["allowed"] == 1, "allowance back to 1 after revoke",
              str(revoked.get("allowed")))

        # ------------------------------------------------------------------
        print("\n[10] Rejection unpublishes and blocks")
        # ------------------------------------------------------------------
        r = await client.post(f"/admin/test-series/{tid}/reject", headers=admin_h,
                              json={"note": ""})
        check(r.status_code == 422, "rejection requires a reason", f"got {r.status_code}")

        rejected = ok(
            await client.post(f"/admin/test-series/{tid}/reject", headers=admin_h,
                              json={"note": "Question 3 is out of scope."}),
            "reject",
        )
        check(rejected["approval_status"] == "rejected", "status is rejected")
        check(rejected["is_published"] is False, "rejection unpublishes the test")
        check(rejected["approval_note"] == "Question 3 is out of scope.",
              "rejection reason retained")

        listed = ok(await client.get("/test-series", headers=other_h), "list after reject")
        check(all(t["id"] != tid for t in listed), "rejected test vanishes from the list")

        r = await client.patch(f"/admin/test-series/{tid}/publish?publish=true",
                               headers=admin_h)
        check(r.status_code == 403, "rejected test cannot be republished",
              f"got {r.status_code}")

        # ------------------------------------------------------------------
        print("\n[11] Cleanup")
        # ------------------------------------------------------------------
        ok(await client.delete(f"/admin/test-series/{tid}", headers=admin_h), "delete test")
        for uid in (learner_id, ok(await client.get("/auth/me", headers=other_h), "me2")["id"]):
            await client.delete(f"/admin/employees/{uid}", headers=admin_h)
        print("  done")

        print("\n" + "=" * 64)
        print(f"  {_passed} passed, {_failed} failed")
        print("=" * 64)
        sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
