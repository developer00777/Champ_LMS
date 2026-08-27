"""
E2E: extra attempts (retakes) granted from the Content access screen.

The claim under test is end-to-end, not just API-shaped: an admin grants a
retake from the same place they grant access, and the learner's own test list
immediately offers the test again.
"""
import sys
import uuid

import httpx

BASE = "http://127.0.0.1:8099"
ADMIN = {"username": "verify.admin@champtest.com", "password": "adminpass123"}

PASSED, FAILED = 0, []


def check(cond, label):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok    {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL  {label}")


def ok(r, label):
    if r.status_code >= 400:
        print(f"FATAL {label}: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    return r.json()


c = httpx.Client(base_url=BASE, timeout=60.0)
tok = ok(c.post("/auth/token", data=ADMIN), "admin login")["access_token"]
A = {"Authorization": f"Bearer {tok}"}
sfx = uuid.uuid4().hex[:8]


def mk_employee(name, dept="Sales", team="Alpha"):
    body = {"email": f"{name}.{sfx}@champtest.com", "full_name": name.title(),
            "department": dept, "team": team, "role": "learner"}
    u = ok(c.post("/admin/employees", json=body, headers=A), f"create {name}")
    t = ok(c.post("/auth/token", data={"username": body["email"], "password": u["initial_password"]}),
           f"login {name}")["access_token"]
    return u, {"Authorization": f"Bearer {t}"}


learner, L = mk_employee("retaker")
other, O = mk_employee("bystander")

# A test capped at ONE attempt, so exhaustion is one submit away.
t = ok(c.post("/admin/test-series", json={
    "title": f"Retake Test {sfx}",
    "max_attempts": 1,
    "questions": [{"question": "2+2?", "options": ["3", "4"], "correct_index": 1, "marks": 1}],
}, headers=A), "create test")
TID = t["id"]
ok(c.patch(f"/admin/test-series/{TID}/publish?publish=true", headers=A), "publish")


def my_row(hdrs):
    return next((x for x in ok(c.get("/test-series", headers=hdrs), "list") if x["id"] == TID), None)


def submit_once(hdrs):
    paper = ok(c.get(f"/test-series/{TID}/take", headers=hdrs), "take")
    qid = paper["questions"][0]["id"]
    return c.post(f"/test-series/{TID}/submit", json={"answers": {qid: 0}, "text_answers": {}}, headers=hdrs)


print("\n1. Learner starts with the test's nominal cap")
row = my_row(L)
check(row["attempts_allowed"] == 1, "allowance is the test cap")
check(row["extra_attempts_granted"] == 0, "no grants yet")
check(row["attempts_left"] == 1, "one attempt left")

print("\n2. Learner spends their only attempt")
check(submit_once(L).status_code == 200, "first attempt scores")
row = my_row(L)
check(row["attempts_left"] == 0, "no attempts left")
check(c.get(f"/test-series/{TID}/take", headers=L).status_code == 403, "cannot re-open the paper")
check(submit_once.__name__ and c.post(f"/test-series/{TID}/submit",
      json={"answers": {}, "text_answers": {}}, headers=L).status_code == 403,
      "cannot submit again")

print("\n3. The Content access people view shows the spent allowance")
ppl = ok(c.get(f"/admin/content-access/tests/{TID}/people", headers=A), "people")
check(ppl["max_attempts"] == 1, "people view reports the cap")
me = next(p for p in ppl["people"] if p["user_id"] == learner["id"])
check(me["attempts"]["used"] == 1, "shows 1 used")
check(me["attempts"]["exhausted"] is True, "flagged exhausted")
check(me["attempts"]["granted_extra"] == 0, "no grants yet")

print("\n4. Admin grants a retake FROM the Content access screen")
g = ok(c.post(f"/admin/content-access/tests/{TID}/grants",
              json={"user_id": learner["id"], "extra_attempts": 1, "reason": "browser crashed"},
              headers=A), "grant retake")
check(g["attempts"]["allowed"] == 2, "allowance rises to 2")
check(g["attempts"]["left"] == 1, "one attempt back")
check(g["attempts"]["exhausted"] is False, "no longer exhausted")
GRANT_ID = g["grant_id"]

print("\n5. The learner immediately sees the test open again")
row = my_row(L)
check(row["attempts_left"] == 1, "learner list offers an attempt again")
check(row["attempts_allowed"] == 2, "learner sees the raised ceiling")
check(row["extra_attempts_granted"] == 1, "learner sees it was granted")
paper = ok(c.get(f"/test-series/{TID}/take", headers=L), "re-open")
check(paper["attempts_allowed"] == 2, "paper header shows 'of 2', not the nominal cap")
check(paper["attempt_number"] == 2, "and calls it attempt 2")
check(submit_once(L).status_code == 200, "the retake actually scores")

print("\n6. The grant is auditable and additive")
grants = ok(c.get(f"/admin/content-access/tests/{TID}/grants", headers=A), "list grants")
check(len(grants) == 1, "one grant on the ledger")
check(grants[0]["reason"] == "browser crashed", "reason recorded")
check(grants[0]["granted_by_name"] is not None, "grantor recorded")
ok(c.post(f"/admin/content-access/tests/{TID}/grants",
          json={"user_id": learner["id"], "extra_attempts": 1}, headers=A), "second grant")
grants = ok(c.get(f"/admin/content-access/tests/{TID}/grants", headers=A), "list grants")
check(len(grants) == 2, "granting twice appends rather than overwrites")
check(my_row(L)["attempts_allowed"] == 3, "allowance is now 3")

print("\n7. Revoking a grant lowers the ceiling, without touching sat attempts")
ok(c.delete(f"/admin/content-access/tests/{TID}/grants/{GRANT_ID}", headers=A), "revoke")
row = my_row(L)
check(row["attempts_allowed"] == 2, "ceiling drops back to 2")
check(row["my_attempts"] == 2, "the two sat attempts remain on record")
check(row["my_best_score"] is not None, "and their score is intact")

print("\n8. A grant is scoped to one person and one test")
check(my_row(O) is None or my_row(O)["extra_attempts_granted"] == 0,
      "the bystander got nothing")
other_row = my_row(O)
check(other_row["attempts_left"] == 1, "bystander still on the nominal cap")

print("\n9. Guard rails")
check(c.post(f"/admin/content-access/tests/{TID}/grants",
             json={"user_id": learner["id"], "extra_attempts": 999}, headers=A).status_code == 422,
      "absurd grant sizes rejected")
check(c.post(f"/admin/content-access/tests/{TID}/grants",
             json={"user_id": learner["id"], "extra_attempts": 1}, headers=L).status_code in (401, 403),
      "a learner cannot grant themselves a retake")
check(c.post(f"/admin/content-access/tests/{TID}/grants",
             json={"user_id": str(uuid.uuid4()), "extra_attempts": 1}, headers=A).status_code == 404,
      "unknown employee 404s")
check(c.delete(f"/admin/content-access/tests/{TID}/grants/{uuid.uuid4()}", headers=A).status_code == 404,
      "unknown grant 404s")

# An uncapped test has nothing to extend.
unc = ok(c.post("/admin/test-series", json={
    "title": f"Uncapped {sfx}",
    "questions": [{"question": "1+1?", "options": ["1", "2"], "correct_index": 1, "marks": 1}],
}, headers=A), "create uncapped")
check(c.post(f"/admin/content-access/tests/{unc['id']}/grants",
             json={"user_id": learner["id"], "extra_attempts": 1}, headers=A).status_code == 422,
      "granting on an uncapped test is refused, not stored as a no-op")
unc_ppl = ok(c.get(f"/admin/content-access/tests/{unc['id']}/people", headers=A), "uncapped people")
check(unc_ppl["max_attempts"] is None, "uncapped test reports no cap, so the UI hides the control")

print("\n10. Access and retakes are independent levers")
ok(c.put(f"/admin/content-access/tests/{TID}/people",
         json={"user_id": learner["id"], "access": "revoke"}, headers=A), "revoke access")
check(c.get(f"/test-series/{TID}/take", headers=L).status_code == 403,
      "a revoked learner cannot sit it even holding granted attempts")
ok(c.delete(f"/admin/content-access/tests/{TID}/people/{learner['id']}", headers=A), "clear")
# Access is restored, but this learner has spent their whole (grant-raised)
# allowance by now — so the block that remains is the attempt cap, not access.
ppl = ok(c.get(f"/admin/content-access/tests/{TID}/people", headers=A), "people")
me = next(p for p in ppl["people"] if p["user_id"] == learner["id"])
check(me["can_access"] is True and me["rule"] is None, "access restored once the revoke is cleared")
check(me["attempts"]["exhausted"] is True, "still capped: the two levers are independent")
# One more retake and they are back in, proving access was genuinely restored.
ok(c.post(f"/admin/content-access/tests/{TID}/grants",
          json={"user_id": learner["id"], "extra_attempts": 1}, headers=A), "final grant")
check(c.get(f"/test-series/{TID}/take", headers=L).status_code == 200,
      "restored access + a fresh retake lets them sit it again")

print(f"\n{'=' * 60}")
print(f"{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print(f"  FAILED: {f}")
sys.exit(1 if FAILED else 0)
