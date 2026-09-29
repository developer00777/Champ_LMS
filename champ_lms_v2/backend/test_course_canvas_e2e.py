"""
E2E: the course canvas, closed-by-default access, and per-attempt test approval.

Covers:
  * building a course on the canvas: sections, videos, checkpoint quizzes,
    tests, notes pages, reordering, deleting;
  * canvas courses start closed: nobody sees them until an admin adds people,
    while classic modules with an empty audience stay open to everyone;
  * watch access and test access are separate decisions;
  * test requests: learner asks -> admin approves N attempts -> learner sits
    them through the existing /take and /submit -> asks again;
  * checkpoint quizzes never masquerade as the old module quiz;
  * the must-pass gate locks later items.

Bunny is not called: videos are marked as encoded directly in Mongo.

Run inside the API container:  python test_course_canvas_e2e.py
"""
import os
import sys
import uuid

import httpx
from pymongo import MongoClient

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:8000")
ADMIN = {"username": "verify.admin@champtest.com", "password": "adminpass123"}
mongo = MongoClient(os.environ.get("MONGODB_URL", "mongodb://cc-mongo:27017"))[
    os.environ.get("MONGODB_DB_NAME", "canvas_e2e")
]

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
        print(f"FATAL {label}: {r.status_code} {r.text[:400]}")
        sys.exit(1)
    return r.json()


c = httpx.Client(base_url=BASE, timeout=60.0)
tok = ok(c.post("/auth/token", data=ADMIN), "admin login")["access_token"]
A = {"Authorization": f"Bearer {tok}"}
sfx = uuid.uuid4().hex[:8]
TEAM_X, TEAM_Y = f"Canvas North {sfx}", f"Canvas South {sfx}"


def mk_employee(name, dept, team):
    body = {"email": f"{name}.{sfx}@champtest.com", "full_name": name.title(),
            "department": dept, "team": team, "role": "learner"}
    u = ok(c.post("/admin/employees", json=body, headers=A), f"create {name}")
    t = ok(c.post("/auth/token", data={"username": body["email"], "password": u["initial_password"]}),
           f"login {name}")["access_token"]
    return u["id"], {"Authorization": f"Bearer {t}"}


ann_id, ANN = mk_employee("ann", "Sales", TEAM_X)
bob_id, BOB = mk_employee("bob", "Sales", TEAM_Y)


def mark_encoded(episode_id, seconds=300):
    mongo.episodes.update_one(
        {"_id": episode_id},
        {"$set": {"status": "ready", "bunny_video_guid": f"guid-{episode_id}",
                  "bunny_video_id": f"guid-{episode_id}", "duration_seconds": seconds}},
    )


def course_item(course, kind, n=0):
    return [i for i in course["items"] if i["kind"] == kind][n]


print("\n== create a course ==")
course = ok(c.post("/admin/courses", json={"title": f"Canvas course {sfx}", "category": "Sales"}, headers=A), "create course")
cid = course["id"]
sec1 = course["sections"][0]["id"]
check(course["access_mode"] == "closed", "new course is closed")
check(course["format"] == "empty" and len(course["sections"]) == 1, "starts empty with one section")
check(course["can_watch_count"] == 0, "nobody can watch a new course")

print("\n== videos ==")
v1 = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "video", "section_id": sec1, "title": "Why deals stall"}, headers=A), "add video 1")
v2 = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "video", "section_id": sec1, "title": "Buying committee"}, headers=A), "add video 2")
check(v1["episode_number"] == 1 and v2["episode_number"] == 2, "episodes numbered in canvas order")
check(v2["status"] == "pending", "new video waits for its upload")
mark_encoded(v1["ref_id"], 400)
mark_encoded(v2["ref_id"], 500)
course = ok(c.get(f"/admin/courses/{cid}", headers=A), "reload course")
check(course["format"] == "series", "videos only -> series")

print("\n== transcripts and notes ==")
seg = [{"start": 0, "end": 4, "text": "Deals stall when nobody owns the next step."},
       {"start": 4, "end": 9, "text": "Leave every call with a dated next step."}]
r = ok(c.put(f"/admin/episodes/{v1['ref_id']}/transcript", json={"segments": seg, "source": "manual"}, headers=A), "save manual transcript")
check(r["transcript_status"] == "ready" and r["transcript_source"] == "manual", "manual transcript saved")
r = c.put(f"/admin/episodes/{v1['ref_id']}/transcript", json={"segments": seg[:1], "source": "auto"}, headers=A)
check(r.status_code == 409, "automatic run cannot overwrite a hand-edited transcript")
r = ok(c.put(f"/admin/episodes/{v2['ref_id']}/transcript", json={"segments": seg, "source": "auto"}, headers=A), "save auto transcript")
check(r["transcript_source"] == "auto", "auto transcript saved")
r = c.post(f"/admin/episodes/{v1['ref_id']}/transcribe-chunk", files={"audio": ("a.wav", b"RIFF0000", "audio/wav")}, data={"offset_seconds": "0"}, headers=A)
check(r.status_code == 503, "transcribing without an AI key explains itself")
ok(c.patch(f"/admin/episodes/{v2['ref_id']}/transcript-status", json={"status": "processing"}, headers=A), "mark processing")
ok(c.put(f"/admin/episodes/{v1['ref_id']}/notes", json={"notes": "## Key points\n- Own the next step"}, headers=A), "save notes")
ep1 = mongo.episodes.find_one({"_id": v1["ref_id"]})
check(ep1["transcript"].startswith("Deals stall") and ep1["notes_source"] == "manual", "plain transcript and notes stored")

print("\n== checkpoint quiz ==")
qz = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "quiz", "section_id": sec1}, headers=A), "add quiz")
check(qz["source_episode_ids"] == [v1["ref_id"], v2["ref_id"]], "quiz defaults to the videos above it")
r = c.post(f"/admin/assessments/{qz['ref_id']}/generate", headers=A)
check(r.status_code == 503, "AI quiz without a key explains itself")
bad = c.patch(f"/admin/assessments/{qz['ref_id']}", json={"questions": [{"question": "Q", "options": ["only one"], "correct_index": 0}]}, headers=A)
check(bad.status_code == 422, "a question with one option is refused")
questions = [
    {"question": "What stalls deals?", "options": ["Price", "Nobody owns the next step", "Legal", "Demos"], "correct_index": 1, "source_episode_id": v1["ref_id"]},
    {"question": "Leave every call with?", "options": ["A deck", "A dated next step"], "correct_index": 1},
]
qv = ok(c.patch(f"/admin/assessments/{qz['ref_id']}", json={"questions": questions, "pass_threshold": 100, "must_pass": True}, headers=A), "save quiz questions")
check(len(qv["questions"]) == 2 and qv["must_pass"], "quiz questions and gate saved")
course = ok(c.get(f"/admin/courses/{cid}", headers=A), "reload")
check(course["format"] == "course", "adding a quiz turns the series into a course")

print("\n== notes page ==")
sec2 = str(uuid.uuid4())
course = ok(c.put(f"/admin/courses/{cid}/structure", json={
    "sections": [{"id": sec1, "title": "Foundations"}, {"id": sec2, "title": "Certification"}],
    "order": [{"id": i["id"], "section_id": sec1} for i in course["items"]],
}, headers=A), "add a second section")
check([s["title"] for s in course["sections"]] == ["Foundations", "Certification"], "sections saved")
nt = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "notes", "section_id": sec1, "title": "Worksheet"}, headers=A), "add notes")
ok(c.patch(f"/admin/notes/{nt['ref_id']}", json={"body": "## Roles\n- Economic buyer"}, headers=A), "write notes")
r = c.post(f"/admin/notes/{nt['ref_id']}/attachment", files={"file": ("x.txt", b"hello", "text/plain")}, headers=A)
check(r.status_code == 422, "non-PDF attachment refused")
pdf = b"%PDF-1.4\n% tiny test pdf\n%%EOF"
r = ok(c.post(f"/admin/notes/{nt['ref_id']}/attachment", files={"file": ("worksheet.pdf", pdf, "application/pdf")}, headers=A), "attach pdf")
check(r["attachment_name"] == "worksheet.pdf" and r["attachment_size"] == len(pdf), "pdf stored in Mongo")
check(mongo.note_attachments.count_documents({"note_id": nt["ref_id"]}) == 1, "one attachment row")

print("\n== test ==")
ts = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "test", "section_id": sec2, "title": "Certification"}, headers=A), "add test")
tid = ts["ref_id"]
check(not ts["is_published"] and ts["question_count"] == 0, "test starts unpublished and empty")
ok(c.patch(f"/admin/courses/{cid}/tests/{tid}", json={"attempts_per_approval": 2, "unlock_rule": "all_videos", "proctoring_enabled": False}, headers=A), "test settings")
pub = ok(c.patch(f"/admin/courses/{cid}", json={"is_published": True}, headers=A), "publish course")
check(pub["is_published"] and any("Certification" in w for w in pub["warnings"]), "publishing warns about an empty test")
ok(c.post(f"/admin/test-series/{tid}/questions", json={"questions": [
    {"question": "Who signs the budget?", "options": ["Economic buyer", "Champion"], "correct_index": 0},
    {"question": "When meet legal?", "options": ["Before contract", "After"], "correct_index": 0},
]}, headers=A), "add test questions")
pub = ok(c.patch(f"/admin/courses/{cid}", json={"is_published": True}, headers=A), "publish again")
check(course_item(pub, "test")["is_published"] and not pub["warnings"], "a ready test is published with its course")

print("\n== closed by default ==")
check(c.get(f"/courses/{cid}", headers=ANN).status_code == 404, "ann cannot open a closed course")
check(all(m["id"] != cid for m in ok(c.get("/modules", headers=ANN), "ann modules")), "closed course not listed")
classic = ok(c.post("/admin/modules", json={"title": f"Classic {sfx}"}, headers=A), "classic module")
ok(c.patch(f"/admin/modules/{classic['id']}/publish", headers=A), "publish classic")
check(any(m["id"] == classic["id"] for m in ok(c.get("/modules", headers=BOB), "bob modules")), "classic module with no audience is still open")

ok(c.patch(f"/admin/content-access/modules/{cid}", json={"audience_teams": [TEAM_X]}, headers=A), "open course to team X")
lc = ok(c.get(f"/courses/{cid}", headers=ANN), "ann opens course")
check(c.get(f"/courses/{cid}", headers=BOB).status_code == 404, "bob, outside the team, still cannot")
check(lc["format"] == "course", "learner sees a full course")
kinds = [i["kind"] for i in lc["items"]]
check(kinds == ["video", "video", "quiz", "notes", "test"], f"learner item order {kinds}")
check(ok(c.get(f"/admin/courses/{cid}", headers=A), "admin")["can_watch_count"] == 1, "watch count counts ann only")
lt = course_item(lc, "test")
check(lt["state"] == "not_allowed", "watch access alone does not open the test")
check(c.post(f"/courses/{cid}/tests/{tid}/request", headers=ANN).status_code == 403, "request refused without test access")

print("\n== legacy quiz lookup ==")
check(c.get(f"/assessments/{cid}", headers=ANN).status_code == 404, "checkpoint quiz is not served as the module quiz")

print("\n== must-pass gate ==")
check(course_item(lc, "notes")["locked"] and lt["locked"], "items after an unpassed must-pass quiz are locked")
check(not course_item(lc, "video")["locked"], "items before it are not")
quiz = ok(c.get(f"/courses/{cid}/quizzes/{qz['ref_id']}", headers=ANN), "ann loads quiz")
check("correct_index" not in quiz["questions"][0], "quiz answers are not sent to the learner")
check(c.get(f"/courses/{cid}/quizzes/{qz['ref_id']}", headers=BOB).status_code == 404, "bob cannot load the quiz")
check(c.post(f"/assessments/{qz['ref_id']}/attempt", json={"answers": [1, 1]}, headers=BOB).status_code == 404, "bob cannot score against it")
fail = ok(c.post(f"/assessments/{qz['ref_id']}/attempt", json={"answers": [0, 1]}, headers=ANN), "ann fails quiz")
check(not fail["passed"], "wrong answer fails a 100% quiz")
passed = ok(c.post(f"/assessments/{qz['ref_id']}/attempt", json={"answers": [1, 1]}, headers=ANN), "ann passes quiz")
check(passed["passed"], "retake needs no approval and passes")
lc = ok(c.get(f"/courses/{cid}", headers=ANN), "reload")
check(not course_item(lc, "notes")["locked"] and course_item(lc, "quiz")["passed"], "passing unlocks the rest")

print("\n== notes for learners ==")
r = c.get(f"/courses/{cid}/notes/{nt['ref_id']}/attachment", headers=ANN)
check(r.status_code == 200 and r.content == pdf and r.headers["content-type"].startswith("application/pdf"), "ann downloads the pdf")
check(c.get(f"/courses/{cid}/notes/{nt['ref_id']}/attachment", headers=BOB).status_code == 404, "bob cannot")
tr = ok(c.get(f"/courses/{cid}/episodes/{v1['ref_id']}/transcript", headers=ANN), "ann transcript")
check(len(tr["segments"]) == 2 and tr["segments"][1]["start"] == 4, "timed transcript served")

print("\n== test requests ==")
ok(c.patch(f"/admin/content-access/tests/{tid}", json={"audience_teams": [TEAM_X]}, headers=A), "open test to team X")
lt = course_item(ok(c.get(f"/courses/{cid}", headers=ANN), "reload"), "test")
check(lt["state"] == "none" and not lt["unlocked"], "test open to ask, but locked until videos are watched")
check(c.post(f"/courses/{cid}/tests/{tid}/request", headers=ANN).status_code == 409, "request refused before watching everything")
r = c.get(f"/test-series/{tid}/take", headers=ANN)
check(r.status_code == 403 and "approval" in r.text, "cannot take before approval")
print("\n== skipping ahead in course videos ==")
# v2 is 500 s long. One report claiming the end is held to about five minutes
# past the furthest point reached; a second skip of under five minutes is fine.
def progress(ep, pos, total, who=ANN):
    return ok(c.post("/progress", json={"episode_id": ep, "watched_seconds": pos, "total_seconds": total}, headers=who), f"progress {pos}")

r = progress(v2["ref_id"], 0, 500)
check(r["watched_seconds"] == 0 and not r["skip_limited"], "starting to watch is recorded as sent")
r = progress(v2["ref_id"], 490, 500)
check(r["skip_limited"] and 300 <= r["watched_seconds"] <= 320 and not r["completed"],
      f"a jump to the end is held to about 5 minutes ({r['watched_seconds']} s)")
r = progress(v2["ref_id"], 480, 500)
check(not r["skip_limited"] and r["completed"], "a further skip of under 5 minutes is allowed and finishes the episode")
progress(v2["ref_id"], 10, 500)  # rewind to rewatch
r = progress(v2["ref_id"], 499, 500)
check(not r["skip_limited"] and r["watched_seconds"] == 499, "a finished episode can be skipped through freely")
r = progress(v1["ref_id"], 0, 0)
check(not r["completed"], "a report with no length yet is not a finished video")
r = progress(v1["ref_id"], 390, 400, who=A)
check(not r["skip_limited"] and r["completed"], "admins previewing are not held back")
classic_mod = ok(c.post("/admin/modules", json={"title": f"Classic skip {sfx}"}, headers=A), "classic module")
classic_ep = ok(c.post(f"/admin/modules/{classic_mod['id']}/episodes", json={"title": "Classic episode"}, headers=A), "classic episode")
r = progress(classic_ep["id"], 2900, 3000)
check(not r["skip_limited"] and r["completed"], "classic modules keep free seeking")


def mark_watched(user_id, ep_id):
    """Everything below needs the episodes finished; write that directly."""
    mongo.watch_progress.update_one(
        {"user_id": user_id, "episode_id": ep_id},
        {"$set": {"watched_seconds": 1000, "total_seconds": 1000, "completed": True},
         "$setOnInsert": {"_id": str(uuid.uuid4())}},
        upsert=True,
    )


for v in (v1, v2):
    mark_watched(ann_id, v["ref_id"])
req = ok(c.post(f"/courses/{cid}/tests/{tid}/request", headers=ANN), "ann requests test")
again = ok(c.post(f"/courses/{cid}/tests/{tid}/request", headers=ANN), "ann asks again")
check(again["id"] == req["id"], "asking twice returns the same pending request")
check(course_item(ok(c.get(f"/courses/{cid}", headers=ANN), "reload"), "test")["state"] == "pending", "ann sees pending")

pend = ok(c.get("/admin/test-requests", headers=A), "pending list")
mine = [p for p in pend if p["id"] == req["id"]]
check(len(mine) == 1 and mine[0]["course_progress"] == 100 and mine[0]["attempts_per_approval"] == 2, "admin sees the request with progress and suggested attempts")
check(c.get("/admin/test-requests", headers=ANN).status_code == 403, "learners cannot list requests")
check(c.post(f"/admin/test-requests/{req['id']}/approve", json={"attempts": 2}, headers=ANN).status_code == 403, "learners cannot approve themselves")
ap = ok(c.post(f"/admin/test-requests/{req['id']}/approve", json={"attempts": 2, "note": "Good luck"}, headers=A), "approve 2")
check(ap["status"] == "approved" and ap["attempts_granted"] == 2, "approved with 2 attempts")
check(c.post(f"/admin/test-requests/{req['id']}/approve", json={"attempts": 1}, headers=A).status_code == 409, "a decided request cannot be decided again")
lt = course_item(ok(c.get(f"/courses/{cid}", headers=ANN), "reload"), "test")
check(lt["state"] == "approved" and lt["attempts_left"] == 2 and lt["note"] == "Good luck", "ann sees 2 approved attempts and the note")

paper = ok(c.get(f"/test-series/{tid}/take", headers=ANN), "take 1")
check(paper["attempts_allowed"] == 2, "paper shows the approved ceiling")
qids = [q["id"] for q in paper["questions"]]
ok(c.post(f"/test-series/{tid}/submit", json={"answers": {qids[0]: 1, qids[1]: 1}}, headers=ANN), "submit 1")
check(c.post(f"/courses/{cid}/tests/{tid}/request", headers=ANN).status_code == 409, "cannot ask while an attempt is left")
listed = [t for t in ok(c.get("/test-series", headers=ANN), "ann tests") if t["id"] == tid]
check(listed and listed[0]["course_id"] == cid and listed[0]["attempts_left"] == 1, "tests list links the course and counts down")
ok(c.post(f"/test-series/{tid}/submit", json={"answers": {qids[0]: 0, qids[1]: 0}}, headers=ANN), "submit 2")
lt = course_item(ok(c.get(f"/courses/{cid}", headers=ANN), "reload"), "test")
check(lt["state"] == "used" and lt["attempts_left"] == 0 and lt["passed"], "both attempts used, best one passed")
check(c.get(f"/test-series/{tid}/take", headers=ANN).status_code == 403, "no third attempt without asking")
req2 = ok(c.post(f"/courses/{cid}/tests/{tid}/request", headers=ANN), "ask again")
dn = ok(c.post(f"/admin/test-requests/{req2['id']}/deny", json={"reason": "You passed already"}, headers=A), "deny")
check(dn["status"] == "denied", "denied")
lt = course_item(ok(c.get(f"/courses/{cid}", headers=ANN), "reload"), "test")
check(lt["state"] == "denied" and lt["reason"] == "You passed already", "ann sees the reason")
decided = ok(c.get("/admin/test-requests?status=decided", headers=A), "decided list")
check({req["id"], req2["id"]} <= {d["id"] for d in decided}, "both show as decided")

print("\n== watch access also gates the exam ==")
req3 = ok(c.post(f"/courses/{cid}/tests/{tid}/request", headers=ANN), "ask a third time")
ok(c.post(f"/admin/test-requests/{req3['id']}/approve", json={"attempts": 1}, headers=A), "approve 1")
ok(c.patch(f"/admin/content-access/modules/{cid}", json={"audience_teams": []}, headers=A), "close course again")
check(c.get(f"/test-series/{tid}/take", headers=ANN).status_code == 403, "closing the course stops the exam")
check(all(t["id"] != tid for t in ok(c.get("/test-series", headers=ANN), "list")), "and hides it from the tests list")
ok(c.put(f"/admin/content-access/modules/{cid}/people", json={"user_id": ann_id, "access": "grant"}, headers=A), "grant ann personally")
check(c.get(f"/test-series/{tid}/take", headers=ANN).status_code == 200, "a personal grant reopens it")

print("\n== reorder ==")
course = ok(c.get(f"/admin/courses/{cid}", headers=A), "admin")
ids = {i["kind"] + str(n): i["id"] for n, i in enumerate(course["items"])}
order = [i for i in course["items"]]
order[0], order[1] = order[1], order[0]  # swap the videos
course = ok(c.put(f"/admin/courses/{cid}/structure", json={
    "sections": course["sections"], "order": [{"id": i["id"], "section_id": i["section_id"]} for i in order],
}, headers=A), "swap videos")
check(course_item(course, "video")["ref_id"] == v2["ref_id"] and course_item(course, "video")["episode_number"] == 1, "swapped video is now episode 1")
check(mongo.episodes.find_one({"_id": v2["ref_id"]})["sequence_order"] == 1, "sequence_order follows the canvas")
stale = c.put(f"/admin/courses/{cid}/structure", json={
    "sections": course["sections"], "order": [{"id": i["id"], "section_id": i["section_id"]} for i in order[:-1]],
}, headers=A)
check(stale.status_code == 409, "an order missing an item is refused")
moved = ok(c.put(f"/admin/courses/{cid}/structure", json={
    "sections": course["sections"],
    "order": [{"id": i["id"], "section_id": sec2 if i["kind"] == "notes" else i["section_id"]} for i in course["items"]],
}, headers=A), "move notes to section 2")
check(course_item(moved, "notes")["section_id"] == sec2, "notes moved between sections")

print("\n== delete ==")
moved = ok(c.delete(f"/admin/courses/{cid}/items/{course_item(moved, 'notes')['id']}", headers=A), "delete notes")
check(mongo.note_attachments.count_documents({"note_id": nt["ref_id"]}) == 0, "notes pdf deleted with the page")
moved = ok(c.delete(f"/admin/courses/{cid}/items/{course_item(moved, 'test')['id']}", headers=A), "delete test")
check(mongo.test_attempts.count_documents({"test_id": tid}) == 0 and mongo.test_requests.count_documents({"test_id": tid}) == 0, "test attempts and requests deleted")
moved = ok(c.delete(f"/admin/courses/{cid}/items/{course_item(moved, 'video')['id']}", headers=A), "delete a video")
q_after = mongo.assessments.find_one({"_id": qz["ref_id"]})
check(v2["ref_id"] not in q_after["source_episode_ids"], "deleted video leaves the quiz's sources")
check([i["kind"] for i in moved["items"]] == ["video", "quiz"], "two items left")
moved = ok(c.delete(f"/admin/courses/{cid}/items/{course_item(moved, 'quiz')['id']}", headers=A), "delete quiz")
check(moved["format"] == "series", "back to a series once only videos remain")
check(c.get(f"/admin/courses/{classic['id']}", headers=A).status_code == 404, "classic modules are not served as canvas courses")

print(f"\n{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print("  -", f)
sys.exit(1 if FAILED else 0)
