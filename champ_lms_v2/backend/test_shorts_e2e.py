"""
E2E: shorts.

Creating, validating, editing and deleting a short; learners see only
published, ready shorts, a shared one first and unseen before seen; likes
toggle and views count each person once. Bunny is never called: the short's
video is marked ready in Mongo directly.

Run inside the app container:  python test_shorts_e2e.py
(signs in as ADMIN_EMAIL / ADMIN_PASSWORD from the environment or .env)
"""
import os
import sys
import uuid

import httpx
from pymongo import MongoClient

from app.core.config import get_settings

settings = get_settings()
BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:8000")
mongo = MongoClient(settings.mongodb_url)[settings.mongodb_db_name]
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
A = {"Authorization": "Bearer " + ok(c.post("/auth/token", data={"username": settings.admin_email, "password": settings.admin_password}), "admin login")["access_token"]}
sfx = uuid.uuid4().hex[:8]

# A learner to watch with.
email = f"shorts.learner.{sfx}@champtest.com"
emp = ok(c.post("/admin/employees", json={"email": email, "full_name": "Shorts Learner", "role": "learner"}, headers=A), "learner")
L = {"Authorization": "Bearer " + ok(c.post("/auth/token", data={"username": email, "password": emp["initial_password"]}), "learner login")["access_token"]}

print("\n== validation ==")
r = c.post("/admin/shorts", json={"title": "Too long", "duration_seconds": 400, "width": 1080, "height": 1920}, headers=A)
check(r.status_code == 422, "a short over 3 minutes is refused")
r = c.post("/admin/shorts", json={"title": "Bad fit", "fit": "stretch"}, headers=A)
check(r.status_code == 422, "an unknown fit is refused")
r = c.post("/admin/shorts", json={"title": "x"}, headers=L)
check(r.status_code == 403, "learners can't create shorts")

print("\n== create ==")
vert = ok(c.post("/admin/shorts", json={"title": f"Vertical {sfx}", "duration_seconds": 42, "width": 1080, "height": 1920}, headers=A), "vertical")
land = ok(c.post("/admin/shorts", json={"title": f"Landscape {sfx}", "duration_seconds": 30, "width": 1920, "height": 1080, "fit": "cover"}, headers=A), "landscape")
sq = ok(c.post("/admin/shorts", json={"title": f"Square {sfx}", "duration_seconds": 20, "width": 720, "height": 720, "made_with": "resizer"}, headers=A), "square")
port = ok(c.post("/admin/shorts", json={"title": f"Portrait {sfx}", "duration_seconds": 15, "width": 1080, "height": 1350, "is_published": False}, headers=A), "portrait")
check(vert["aspect"] == "9:16" and land["aspect"] == "16:9" and sq["aspect"] == "1:1" and port["aspect"] == "4:5", "each size is named by its nearest shape")
check(vert["status"] == "pending" and not vert["has_video"], "a new short waits for its video")
check(sq["made_with"] == "resizer", "made with the resizer is kept")

print("\n== feed ==")
feed = ok(c.get("/shorts", headers=L), "feed")
check(not any(s["id"] in (vert["id"], land["id"]) for s in feed), "shorts without a ready video stay out of the feed")
ids = [vert["id"], land["id"], sq["id"], port["id"]]
for i, sid in enumerate(ids):
    mongo.shorts.update_one({"_id": sid}, {"$set": {"status": "ready", "bunny_video_guid": f"guid-{sfx}-{i}"}})
feed = [s["id"] for s in ok(c.get("/shorts", headers=L), "feed")]
check(vert["id"] in feed and land["id"] in feed and sq["id"] in feed, "ready, published shorts are in the feed")
check(port["id"] not in feed, "a hidden short is not")
check(feed.index(sq["id"]) < feed.index(vert["id"]), "newest first")
r = c.get(f"/shorts/{port['id']}", headers=L)
check(r.status_code == 404, "a learner can't open a hidden short by link")
check(c.get(f"/shorts/{port['id']}", headers=A).status_code == 200, "an admin can, to check it")

started = [s["id"] for s in ok(c.get(f"/shorts?start={vert['id']}", headers=L), "feed from a link")]
check(started[0] == vert["id"], "a shared short opens first")

print("\n== views and likes ==")
v = ok(c.post(f"/shorts/{land['id']}/view", json={"watched_seconds": 5}, headers=L), "view")
v = ok(c.post(f"/shorts/{land['id']}/view", json={"watched_seconds": 30, "completed": True}, headers=L), "view again")
check(v["view_count"] == 1, "one person counts as one viewer, however often they watch")
row = mongo.short_views.find_one({"short_id": land["id"]})
check(row and row["completed"] and row["watched_seconds"] == 30, "the furthest watch and completion are kept")
feed = [s["id"] for s in ok(c.get("/shorts", headers=L), "feed")]
check(feed[-1] == land["id"], "a seen short moves behind unseen ones")
check(feed.index(vert["id"]) < feed.index(land["id"]), "unseen first, even when older")

lk = ok(c.post(f"/shorts/{vert['id']}/like", headers=L), "like")
check(lk == {"liked": True, "like_count": 1}, "like")
one = ok(c.get(f"/shorts/{vert['id']}", headers=L), "one")
check(one["liked"] and one["like_count"] == 1, "the short knows you liked it")
lk = ok(c.post(f"/shorts/{vert['id']}/like", headers=L), "unlike")
check(lk == {"liked": False, "like_count": 0}, "liking again takes it back")

print("\n== edit ==")
mod = ok(c.post("/admin/modules", json={"title": f"Linked course {sfx}"}, headers=A), "module")
ok(c.patch(f"/admin/modules/{mod['id']}/publish?publish=true", headers=A), "publish module")
ed = ok(c.patch(f"/admin/shorts/{vert['id']}", json={"title": f"Renamed {sfx}", "module_id": mod["id"], "description": "  Hi  "}, headers=A), "edit")
check(ed["title"] == f"Renamed {sfx}" and ed["module_title"] == f"Linked course {sfx}" and ed["description"] == "Hi", "title, description and course link change")
one = ok(c.get(f"/shorts/{vert['id']}", headers=L), "one")
check(one["course"] and one["course"]["id"] == mod["id"], "learners see the linked course")
check(c.patch(f"/admin/shorts/{vert['id']}", json={"module_id": "nope"}, headers=A).status_code == 422, "linking a course that doesn't exist is refused")
ed = ok(c.patch(f"/admin/shorts/{vert['id']}", json={"module_id": None}, headers=A), "unlink")
check(ed["module_id"] is None, "the course link can be removed")

print("\n== delete ==")
check(c.delete(f"/admin/shorts/{port['id']}", headers=A).status_code == 428, "delete needs ?confirm=<id>")
# No Bunny video behind these test shorts: drop the guid so nothing remote is touched.
mongo.shorts.update_many({"_id": {"$in": ids}}, {"$set": {"bunny_video_guid": None}})
for sid in ids:
    d = ok(c.delete(f"/admin/shorts/{sid}?confirm={sid}", headers=A), "delete")
check(d["video"] == "nothing_to_delete", "a short without a video deletes cleanly")
check(mongo.shorts.count_documents({"_id": {"$in": ids}}) == 0, "the shorts are gone")
check(mongo.short_likes.count_documents({"short_id": {"$in": ids}}) == 0 and mongo.short_views.count_documents({"short_id": {"$in": ids}}) == 0, "with their likes and views")

# Tidy up the course and learner made for this run.
mongo.modules.delete_one({"_id": mod["id"]})
mongo.users.delete_one({"email": email})

print(f"\n{PASSED} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
