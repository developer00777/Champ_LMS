"""
E2E: trimming and splitting course videos.

Trim and split never touch Bunny: an episode plays [clip_start, clip_end] of
its video, and splitting makes more episodes sharing the same video. Checks
lengths, clip-time transcripts, part titles, a quiz between parts, per-part
transcript edits, join (undo), the Bunny webhook reaching every part, and that
deleting one part keeps the video for the others.

Run inside the API container:  python test_course_clips_e2e.py
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
team = f"Clips {sfx}"
u = ok(c.post("/admin/employees", json={"email": f"clips.{sfx}@champtest.com", "full_name": "Clip Learner", "department": "Sales", "team": team, "role": "learner"}, headers=A), "learner")
L = {"Authorization": "Bearer " + ok(c.post("/auth/token", data={"username": f"clips.{sfx}@champtest.com", "password": u["initial_password"]}), "login")["access_token"]}

course = ok(c.post("/admin/courses", json={"title": f"Clips {sfx}"}, headers=A), "course")
cid, sec = course["id"], course["sections"][0]["id"]
video = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "video", "section_id": sec, "title": "Kickoff call"}, headers=A), "video")
guid = f"guid-{uuid.uuid4().hex}"
mongo.episodes.update_one({"_id": video["ref_id"]}, {"$set": {"status": "processing", "bunny_video_guid": guid, "bunny_video_id": guid}})
item = lambda crs, iid: next(i for i in crs["items"] if i["id"] == iid)
videos = lambda crs: [i for i in crs["items"] if i["kind"] == "video"]

print("\n== before the video is ready ==")
r = c.put(f"/admin/courses/{cid}/items/{video['id']}/clip", json={"start": 0, "end": 100}, headers=A)
check(r.status_code == 409, "a video still processing can't be trimmed")
mongo.episodes.update_one({"_id": video["ref_id"]}, {"$set": {"status": "ready", "duration_seconds": 600}})

# A transcript of the whole 10-minute video: a line every 100 s.
lines = [{"start": t, "end": t + 8, "text": f"line at {t}"} for t in range(0, 600, 100)]
ok(c.put(f"/admin/episodes/{video['ref_id']}/transcript", json={"segments": lines, "source": "auto"}, headers=A), "transcript")
quiz = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "quiz", "section_id": sec}, headers=A), "quiz after video")
check(quiz["source_episode_ids"] == [video["ref_id"]], "a quiz written from the video")

print("\n== trim ==")
for bad, why in (({"start": 100, "end": 105}, "a part under 10 s"), ({"start": 0, "end": 600, "split_at": [700]}, "a split outside the part")):
    check(c.put(f"/admin/courses/{cid}/items/{video['id']}/clip", json=bad, headers=A).status_code == 422, f"refuses {why}")
crs = ok(c.put(f"/admin/courses/{cid}/items/{video['id']}/clip", json={"start": 60, "end": 540}, headers=A), "trim")
v = item(crs, video["id"])
check(v["duration_seconds"] == 480 and v["clip_start"] == 60 and v["clip_end"] == 540 and v["source_duration_seconds"] == 600,
      "trimmed to 1:00-9:00: 8 minutes long, source still 10")
check([s["start"] for s in v["transcript_segments"]] == [40, 140, 240, 340, 440], "transcript shows only the kept part, timed from its start")
ep = mongo.episodes.find_one({"_id": video["ref_id"]})
check("line at 0" not in ep["transcript"] and "line at 500" in ep["transcript"], "quiz and notes read only the kept part")
check(len(ep["transcript_segments"]) == 6, "the whole video's transcript is kept, so the trim can be widened again")

print("\n== split ==")
crs = ok(c.put(f"/admin/courses/{cid}/items/{video['id']}/clip", json={"start": 60, "end": 540, "split_at": [250]}, headers=A), "split")
vs = videos(crs)
p1, p2 = vs[0], vs[1]
check(len(vs) == 2 and [i["kind"] for i in crs["items"]] == ["video", "video", "quiz"], "the new part sits right after the first")
check(p1["id"] == video["id"] and p1["duration_seconds"] == 190 and p2["duration_seconds"] == 290, "parts of 3:10 and 4:50")
check(p1["title"] == "Kickoff call (part 1)" and p2["title"] == "Kickoff call (part 2)", "parts are titled in order")
check(p1["part"] == [1, 2] and p2["part"] == [2, 2] and p2["episode_number"] == 2, "each knows it is part n of 2")
check([s["start"] for s in p2["transcript_segments"]] == [50, 150, 250], "part 2 shows its own lines from 0:00")
qz = mongo.assessments.find_one({"_id": quiz["ref_id"]})
check(qz["source_episode_ids"] == [p1["ref_id"], p2["ref_id"]], "the quiz on the whole video now covers both parts")

print("\n== join undoes a split ==")
crs = ok(c.post(f"/admin/courses/{cid}/items/{p1['id']}/join-next", headers=A), "join")
vs = videos(crs)
check(len(vs) == 1 and vs[0]["duration_seconds"] == 480 and vs[0]["title"] == "Kickoff call", "back to one 8-minute episode, suffix gone")
check(mongo.episodes.find_one({"_id": p2["ref_id"]}) is None and mongo.episodes.find_one({"_id": p1["ref_id"]})["bunny_video_guid"] == guid,
      "the joined part's episode is gone, the video is kept")
check(mongo.assessments.find_one({"_id": quiz["ref_id"]})["source_episode_ids"] == [p1["ref_id"]], "the quiz points at the joined episode")

print("\n== a quiz between the parts ==")
crs = ok(c.put(f"/admin/courses/{cid}/items/{video['id']}/clip", json={"start": 60, "end": 540, "split_at": [250]}, headers=A), "split again")
p1, p2 = videos(crs)
mid = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "quiz", "section_id": sec, "index": 1}, headers=A), "quiz between")
crs = ok(c.get(f"/admin/courses/{cid}", headers=A), "reload")
check([i["id"] for i in crs["items"]][:3] == [p1["id"], mid["id"], p2["id"]], "part 1, a quiz, then part 2")
check(mid["source_episode_ids"] == [p1["ref_id"]], "a quiz between the parts is written from part 1")
check(c.post(f"/admin/courses/{cid}/items/{p1['id']}/join-next", headers=A).status_code == 409, "parts with something between them don't join")

print("\n== per-part transcript edits ==")
ok(c.put(f"/admin/episodes/{p2['ref_id']}/transcript", json={"segments": [{"start": 0, "end": 5, "text": "edited opening"}], "source": "manual"}, headers=A), "edit part 2")
e2 = mongo.episodes.find_one({"_id": p2["ref_id"]})
check([s["text"] for s in e2["transcript_segments"]] == ["line at 0", "line at 100", "line at 200", "edited opening"],
      "the edit replaces part 2's lines only, at 4:10 of the video")
fresh = [{"start": t, "end": t + 8, "text": f"new {t}"} for t in range(0, 600, 100)]
ok(c.put(f"/admin/episodes/{p1['ref_id']}/transcript", json={"segments": fresh, "source": "auto"}, headers=A), "new automatic run")
e1, e2 = mongo.episodes.find_one({"_id": p1["ref_id"]}), mongo.episodes.find_one({"_id": p2["ref_id"]})
check(e1["transcript"].startswith("new 100") and "edited opening" in e2["transcript"], "an automatic run reaches the other parts but not a hand-edited one")

print("\n== Bunny's webhook ==")
mongo.episodes.update_many({"bunny_video_guid": guid}, {"$set": {"status": "processing"}})
ok(c.post("/webhooks/bunny-stream", json={"VideoGuid": guid, "Status": 4, "Length": 600}), "webhook")
parts = list(mongo.episodes.find({"bunny_video_guid": guid}))
check(len(parts) == 2 and all(p["status"] == "ready" for p in parts), "every part becomes ready")
check(sorted(p["duration_seconds"] for p in parts) == [190, 290], "each keeps its own length, not the video's")

print("\n== learner ==")
ok(c.patch(f"/admin/courses/{cid}", json={"is_published": True}, headers=A), "publish")
ok(c.patch(f"/admin/content-access/modules/{cid}", json={"audience_teams": [team]}, headers=A), "open")
lc = ok(c.get(f"/courses/{cid}", headers=L), "learner course")
lp1, lp2 = [i for i in lc["items"] if i["kind"] == "video"]
check(lp2["clip_start"] == 250 and lp2["clip_end"] == 540 and lp2["duration_seconds"] == 290, "the player gets part 2's range")
check(lc["runtime_seconds"] == 480, "course runtime counts the parts, not the video twice")
tr = ok(c.get(f"/courses/{cid}/episodes/{p2['ref_id']}/transcript", headers=L), "learner transcript")
check(tr["segments"][0] == {"start": 0.0, "end": 5.0, "text": "edited opening"}, "the learner's transcript is part 2's, from 0:00")
st = c.get(f"/episodes/{p2['ref_id']}/stream", headers=L)
if st.status_code == 200:
    check(st.json()["course_id"] == cid and st.json()["clip_start"] == 250, "the classic player hands course episodes to the course player")
r = ok(c.post("/progress", json={"episode_id": p2["ref_id"], "watched_seconds": 0, "total_seconds": 290}, headers=L), "start part 2")
r = ok(c.post("/progress", json={"episode_id": p2["ref_id"], "watched_seconds": 270, "total_seconds": 290}, headers=L), "watch part 2")
check(r["completed"], "watching part 2 through completes it")

print("\n== deleting one part keeps the video ==")
crs = ok(c.delete(f"/admin/courses/{cid}/items/{p2['id']}", headers=A), "delete part 2")
check(mongo.episodes.find_one({"_id": p2["ref_id"]}) is None, "part 2 is gone")
check(mongo.episodes.find_one({"_id": p1["ref_id"]})["bunny_video_guid"] == guid, "part 1 still plays the video")
check(videos(crs)[0]["title"] == "Kickoff call", "the last part loses its suffix")

print(f"\n{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print("  -", f)
sys.exit(1 if FAILED else 0)
