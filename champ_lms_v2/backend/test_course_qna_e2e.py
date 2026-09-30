"""
E2E: Q&A on course videos.

Learners ask on an episode (pinned to a moment), everyone on the course reads
every question and answer, admins answer from their inbox, and questions keep
to their moment when a video is split or joined. Also checks the access gate.

Run inside the API container:  python test_course_qna_e2e.py
"""
import os
import sys
import uuid

import httpx
from pymongo import MongoClient

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:8000")
mongo = MongoClient(os.environ.get("MONGODB_URL", "mongodb://cc-mongo:27017"))[os.environ.get("MONGODB_DB_NAME", "canvas_e2e")]
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
        print(f"FATAL {label}: {r.status_code} {r.text[:400]}")
        sys.exit(1)
    return r.json()


c = httpx.Client(base_url=BASE, timeout=60.0)
A = {"Authorization": "Bearer " + ok(c.post("/auth/token", data={"username": "verify.admin@champtest.com", "password": "adminpass123"}), "admin")["access_token"]}
sfx = uuid.uuid4().hex[:8]
team = f"QnA {sfx}"


def learner(name, t):
    u = ok(c.post("/admin/employees", json={"email": f"{name}.{sfx}@champtest.com", "full_name": name.title(), "department": "Sales", "team": t, "role": "learner"}, headers=A), name)
    return {"Authorization": "Bearer " + ok(c.post("/auth/token", data={"username": f"{name}.{sfx}@champtest.com", "password": u["initial_password"]}), "login")["access_token"]}


L1, L2, OUT = learner("asha", team), learner("ravi", team), learner("outsider", f"Other {sfx}")

course = ok(c.post("/admin/courses", json={"title": f"QnA {sfx}"}, headers=A), "course")
cid, sec = course["id"], course["sections"][0]["id"]
video = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "video", "section_id": sec, "title": "Pricing call"}, headers=A), "video")
eid = video["ref_id"]
guid = f"guid-{uuid.uuid4().hex}"
mongo.episodes.update_one({"_id": eid}, {"$set": {"status": "ready", "duration_seconds": 600, "bunny_video_guid": guid, "bunny_video_id": guid}})
ok(c.patch(f"/admin/courses/{cid}", json={"is_published": True}, headers=A), "publish")
ok(c.patch(f"/admin/content-access/modules/{cid}", json={"audience_teams": [team]}, headers=A), "open")
Q = f"/courses/{cid}/episodes/{eid}/questions"

print("\n== asking ==")
check(c.post(Q, json={"body": "hi", "at_seconds": 5}, headers=OUT).status_code == 404, "someone outside the course can't ask")
check(c.get(Q, headers=OUT).status_code == 404, "or read the Q&A")
check(c.post(Q, json={"body": "   ", "at_seconds": 5}, headers=L1).status_code == 422, "an empty question is refused")
q1 = ok(c.post(Q, json={"body": "Why a 10% discount here?", "at_seconds": 400}, headers=L1), "ask at 6:40")
q2 = ok(c.post(Q, json={"body": "Is there a template for this?"}, headers=L2), "ask about the whole video")
check(q1["at_seconds"] == 400 and q1["mine"] and q1["answer"] is None, "the question is pinned to 6:40 and open")
check(q2["at_seconds"] is None, "a question can be about the whole video")

print("\n== everyone reads ==")
seen = ok(c.get(Q, headers=L2), "ravi reads")
check([q["id"] for q in seen] == [q2["id"], q1["id"]], "newest first, everyone's questions")
check(not next(q for q in seen if q["id"] == q1["id"])["mine"] and next(q for q in seen if q["id"] == q1["id"])["full_name"] == "Asha",
      "others see who asked, and that it isn't theirs")
check(c.delete(f"/courses/{cid}/questions/{q1['id']}", headers=L2).status_code == 403, "you can't delete someone else's question")

print("\n== admin inbox ==")
inbox = ok(c.get("/admin/questions?status=open", headers=A), "inbox")
mine = [q for q in inbox["questions"] if q["course_id"] == cid]
check(len(mine) == 2 and mine[0]["id"] == q1["id"], "open questions, oldest first")
check(mine[0]["course_title"] == f"QnA {sfx}" and mine[0]["episode_title"] == "Pricing call" and mine[0]["team"] == team, "with course, video and team")
check(any(x["id"] == cid for x in inbox["courses"]), "the course is in the filter")
check(c.get("/admin/questions", headers=L1).status_code == 403, "learners can't open the inbox")
check(c.put(f"/admin/questions/{q1['id']}/answer", json={"answer": "x"}, headers=L1).status_code == 403, "learners can't answer")
before = ok(c.get("/admin/questions/count", headers=A), "count")["open"]
ans = ok(c.put(f"/admin/questions/{q1['id']}/answer", json={"answer": "It clears old stock before the quarter ends."}, headers=A), "answer")
check(ans["answer"].startswith("It clears") and ans["answered_by_name"], "answered, with who answered")
check(ok(c.get("/admin/questions/count", headers=A), "count")["open"] == before - 1, "one fewer waiting")
n = mongo.notifications.find_one({"notif_type": "question_answered", "ref_id": cid})
check(n is not None and "Pricing call" in n["body"], "the asker is notified")
ok(c.put(f"/admin/questions/{q1['id']}/answer", json={"answer": "Edited answer."}, headers=A), "edit")
check(mongo.notifications.count_documents({"notif_type": "question_answered", "ref_id": cid}) == 1, "editing the answer doesn't notify again")
seen = ok(c.get(Q, headers=L2), "ravi reads again")
check(next(q for q in seen if q["id"] == q1["id"])["answer"] == "Edited answer.", "everyone on the course sees the answer")
check(all(q["answer"] for q in ok(c.get("/admin/questions?status=answered", headers=A), "answered")["questions"]), "the answered tab has only answered ones")
ok(c.delete(f"/admin/questions/{q1['id']}/answer", headers=A), "reopen")
check(ok(c.get(Q, headers=L1), "reads")[-1]["answer"] is None, "mark unanswered opens it again")
ok(c.put(f"/admin/questions/{q1['id']}/answer", json={"answer": "Final."}, headers=A), "answer again")

print("\n== split and join keep questions on their moment ==")
crs = ok(c.put(f"/admin/courses/{cid}/items/{video['id']}/clip", json={"start": 0, "end": 600, "split_at": [300]}, headers=A), "split at 5:00")
p1, p2 = [i for i in crs["items"] if i["kind"] == "video"]
on2 = ok(c.get(f"/courses/{cid}/episodes/{p2['ref_id']}/questions", headers=L1), "part 2 Q&A")
on1 = ok(c.get(f"/courses/{cid}/episodes/{p1['ref_id']}/questions", headers=L1), "part 1 Q&A")
check([q["id"] for q in on2] == [q1["id"]] and on2[0]["at_seconds"] == 100, "the 6:40 question moves to part 2, at 1:40 of it")
check([q["id"] for q in on1] == [q2["id"]], "the whole-video question stays on part 1")
q3 = ok(c.post(f"/courses/{cid}/episodes/{p2['ref_id']}/questions", json={"body": "And at 0:30 of part 2?", "at_seconds": 30}, headers=L2), "ask on part 2")
check(mongo.episode_questions.find_one({"_id": q3["id"]})["at_seconds"] == 330, "stored at 5:30 of the whole video")
ok(c.post(f"/admin/courses/{cid}/items/{p1['id']}/join-next", headers=A), "join")
back = ok(c.get(f"/courses/{cid}/episodes/{p1['ref_id']}/questions", headers=L1), "joined Q&A")
check(len(back) == 3 and next(q for q in back if q["id"] == q3["id"])["at_seconds"] == 330, "joining brings part 2's questions back at their moment")

print("\n== deleting ==")
ok(c.delete(f"/courses/{cid}/questions/{q2['id']}", headers=L2), "ravi deletes his")
check(mongo.episode_questions.find_one({"_id": q2["id"]}) is None, "your own question can be deleted")
ok(c.delete(f"/admin/questions/{q3['id']}", headers=A), "admin deletes")
check(mongo.episode_questions.find_one({"_id": q3["id"]}) is None, "an admin can delete any question")
ok(c.delete(f"/admin/courses/{cid}/items/{p1['id']}", headers=A), "delete the video")
check(mongo.episode_questions.count_documents({"module_id": cid}) == 0, "deleting the video deletes its questions")

print(f"\n{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print("  -", f)
sys.exit(1 if FAILED else 0)
