"""
E2E: test series are targetable from Content access, and the gate is real.

Covers the two halves of the change:
  * an admin can set a test's audience and per-person rules from the same
    Content access surface as modules, and
  * a learner outside that audience cannot list, open OR submit the test.

Run against a live container:  python test_test_access_e2e.py
"""
import sys
import uuid

import httpx

BASE = "http://127.0.0.1:8099"
ADMIN = {"username": "verify.admin@champtest.com", "password": "adminpass123"}

PASSED = 0
FAILED = []


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

# --- admin login ---------------------------------------------------------
tok = ok(c.post("/auth/token", data=ADMIN), "admin login")["access_token"]
A = {"Authorization": f"Bearer {tok}"}

sfx = uuid.uuid4().hex[:8]

# --- two learners in different departments/teams --------------------------
def mk_employee(name, dept, team):
    body = {
        "email": f"{name}.{sfx}@champtest.com",
        "full_name": name.title(),
        "department": dept,
        "team": team,
        "role": "learner",
    }
    u = ok(c.post("/admin/employees", json=body, headers=A), f"create {name}")
    t = ok(
        c.post("/auth/token", data={"username": body["email"], "password": u["initial_password"]}),
        f"login {name}",
    )["access_token"]
    return u, {"Authorization": f"Bearer {t}"}


sales_u, SALES = mk_employee("insider", "Sales", "Alpha")
eng_u, ENG = mk_employee("outsider", "Engineering", "Beta")

# --- admin creates and publishes a test ----------------------------------
test = ok(
    c.post(
        "/admin/test-series",
        json={
            "title": f"Access Gate Test {sfx}",
            "description": "audience e2e",
            "questions": [
                {"question": "2+2?", "options": ["3", "4"], "correct_index": 1, "marks": 1},
                {"question": "Sky?", "options": ["blue", "green"], "correct_index": 0, "marks": 1},
            ],
        },
        headers=A,
    ),
    "create test",
)
TID = test["id"]
ok(c.patch(f"/admin/test-series/{TID}/publish?publish=true", headers=A), "publish test")

print("\n1. Test appears in the Content access catalogue")
cat = ok(c.get("/admin/content-access/modules", headers=A), "catalogue")
check("tests" in cat, "catalogue exposes a `tests` list")
row = next((t for t in cat.get("tests", []) if t["id"] == TID), None)
check(row is not None, "the uploaded test is in the catalogue")
check(row and row["kind"] == "test", "row is tagged kind=test")
check(row and row["is_restricted"] is False, "new test starts open to everyone")
check(row and row["total_questions"] == 2, "row carries the question count")

print("\n2. Open test is visible to every learner")
check(any(t["id"] == TID for t in ok(c.get("/test-series", headers=SALES), "list")), "sales sees it")
check(any(t["id"] == TID for t in ok(c.get("/test-series", headers=ENG), "list")), "eng sees it")

print("\n3. Admin restricts the test to the Sales department")
r = ok(
    c.patch(
        f"/admin/content-access/tests/{TID}",
        json={"audience_departments": ["Sales"]},
        headers=A,
    ),
    "set audience",
)
check(r["is_restricted"] is True, "test now reports restricted")
check(r["audience_departments"] == ["Sales"], "audience persisted")

print("\n4. The gate is enforced on list, take AND submit")
check(any(t["id"] == TID for t in ok(c.get("/test-series", headers=SALES), "list")), "insider still lists it")
check(not any(t["id"] == TID for t in ok(c.get("/test-series", headers=ENG), "list")), "outsider no longer lists it")
check(c.get(f"/test-series/{TID}/take", headers=SALES).status_code == 200, "insider can open it")
check(c.get(f"/test-series/{TID}/take", headers=ENG).status_code == 403, "outsider cannot open it")
# The hole worth closing: hiding the row is not enough if /submit stays open.
sub = c.post(f"/test-series/{TID}/submit", json={"answers": {}, "text_answers": {}}, headers=ENG)
check(sub.status_code == 403, "outsider cannot submit directly (403, not a scored attempt)")

print("\n5. Per-person GRANT lets one outsider in")
ok(
    c.put(
        f"/admin/content-access/tests/{TID}/people",
        json={"user_id": eng_u["id"], "access": "grant", "reason": "covering for sales"},
        headers=A,
    ),
    "grant",
)
check(any(t["id"] == TID for t in ok(c.get("/test-series", headers=ENG), "list")), "granted outsider lists it")
check(c.get(f"/test-series/{TID}/take", headers=ENG).status_code == 200, "granted outsider can open it")

print("\n6. Per-person REVOKE beats the audience")
ok(
    c.put(
        f"/admin/content-access/tests/{TID}/people",
        json={"user_id": sales_u["id"], "access": "revoke", "reason": "on leave"},
        headers=A,
    ),
    "revoke",
)
check(not any(t["id"] == TID for t in ok(c.get("/test-series", headers=SALES), "list")), "revoked insider loses the row")
check(c.get(f"/test-series/{TID}/take", headers=SALES).status_code == 403, "revoked insider cannot open it")
check(
    c.post(f"/test-series/{TID}/submit", json={"answers": {}, "text_answers": {}}, headers=SALES).status_code == 403,
    "revoked insider cannot submit",
)

print("\n7. REQUIRED implies access and is surfaced to the learner")
ok(
    c.put(
        f"/admin/content-access/tests/{TID}/people",
        json={"user_id": sales_u["id"], "access": "required", "reason": "mandatory"},
        headers=A,
    ),
    "require",
)
mine = ok(c.get("/test-series", headers=SALES), "list")
mine_row = next((t for t in mine if t["id"] == TID), None)
check(mine_row is not None, "required overrides the earlier revoke (re-assign updates in place)")
check(mine_row and mine_row["required"] is True, "learner list flags it as required")
check(c.get(f"/test-series/{TID}/take", headers=SALES).status_code == 200, "required learner can open it")

print("\n8. The people view explains each decision")
people = ok(c.get(f"/admin/content-access/tests/{TID}/people", headers=A), "people")
by_id = {p["user_id"]: p for p in people["people"]}
check(by_id[sales_u["id"]]["rule"] == "required", "insider shows rule=required")
check(by_id[sales_u["id"]]["required"] is True, "insider flagged required")
check(by_id[eng_u["id"]]["rule"] == "grant", "outsider shows rule=grant")
check(by_id[eng_u["id"]]["why"] == "rule: grant", "why names the rule")
check(people["can_access_count"] >= 2, "count reflects both people")

print("\n9. Clearing a rule falls back to the audience")
ok(c.delete(f"/admin/content-access/tests/{TID}/people/{eng_u['id']}", headers=A), "clear")
check(c.get(f"/test-series/{TID}/take", headers=ENG).status_code == 403, "outsider blocked again once the grant is cleared")

print("\n10. Module rules and test rules do not leak into each other")
emp = ok(c.get(f"/admin/content-access/employees/{sales_u['id']}", headers=A), "overview")
check("tests" in emp, "employee overview lists tests")
trow = next((t for t in emp["tests"] if t["test_id"] == TID), None)
check(trow is not None and trow["rule"] == "required", "test rule shows on the employee overview")
check(all(m.get("rule") is None for m in emp["modules"]), "the test rule did not appear as a module rule")

print("\n11. Legacy `department` on a test still gates, as one audience")
legacy = ok(
    c.post(
        "/admin/test-series",
        json={
            "title": f"Legacy Dept Test {sfx}",
            "department": "Sales",
            "questions": [{"question": "1+1?", "options": ["1", "2"], "correct_index": 1, "marks": 1}],
        },
        headers=A,
    ),
    "create legacy test",
)
LID = legacy["id"]
ok(c.patch(f"/admin/test-series/{LID}/publish?publish=true", headers=A), "publish legacy")
check(any(t["id"] == LID for t in ok(c.get("/test-series", headers=SALES), "list")), "sales sees legacy-dept test")
check(not any(t["id"] == LID for t in ok(c.get("/test-series", headers=ENG), "list")), "eng does not")
check(c.get(f"/test-series/{LID}/take", headers=ENG).status_code == 403, "eng blocked from legacy-dept test")
lrow = next(t for t in ok(c.get("/admin/content-access/modules", headers=A), "cat")["tests"] if t["id"] == LID)
check(lrow["is_restricted"] is True, "legacy department counts as a restriction in the admin view")

print("\n12. Learners cannot administer access themselves")
check(
    c.patch(f"/admin/content-access/tests/{TID}", json={"audience_departments": []}, headers=ENG).status_code in (401, 403),
    "learner cannot change a test audience",
)
check(
    c.put(
        f"/admin/content-access/tests/{TID}/people",
        json={"user_id": eng_u["id"], "access": "grant"},
        headers=ENG,
    ).status_code in (401, 403),
    "learner cannot grant themselves access",
)

print("\n13. Unknown ids 404 as the right kind")
check(c.get(f"/admin/content-access/tests/{uuid.uuid4()}/people", headers=A).status_code == 404, "missing test 404s")
check(
    c.patch(f"/admin/content-access/tests/{TID}", json={"target_roles": ["wizard"]}, headers=A).status_code == 422,
    "unknown role rejected",
)

print("\n14. An insider can still actually sit and score the test")
ok(c.delete(f"/admin/content-access/tests/{TID}/people/{sales_u['id']}", headers=A), "clear required")
paper = ok(c.get(f"/test-series/{TID}/take", headers=SALES), "take")
answers = {q["id"]: 1 if q["question"].startswith("2+2") else 0 for q in paper["questions"]}
res = ok(
    c.post(f"/test-series/{TID}/submit", json={"answers": answers, "text_answers": {}}, headers=SALES),
    "submit",
)
check(res["score"] == 100, f"insider scores normally through the gate (got {res['score']}%)")

print(f"\n{'=' * 60}")
print(f"{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print(f"  FAILED: {f}")
sys.exit(1 if FAILED else 0)
