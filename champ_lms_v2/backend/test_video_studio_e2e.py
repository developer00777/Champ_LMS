"""
E2E: the video studio's edits.

Effects (zoom, speed, mute, blur), caption style, text overlay options and
the progress bar are validated and normalised on save, kept on every part of
a split video, and reach the player in clip time. A speed-up counts towards
how long a part plays, so a part sped up below the minimum is refused.

Run inside the API container:  python test_video_studio_e2e.py
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

course = ok(c.post("/admin/courses", json={"title": f"Studio {sfx}"}, headers=A), "course")
cid, sec = course["id"], course["sections"][0]["id"]
video = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "video", "section_id": sec, "title": "Demo"}, headers=A), "video")
ep_id = video["ref_id"]
guid = f"guid-{uuid.uuid4().hex}"
mongo.episodes.update_one({"_id": ep_id}, {"$set": {
    "status": "ready", "bunny_video_guid": guid, "bunny_video_id": guid,
    "duration_seconds": 300, "source_duration_seconds": 300,
    "transcript_segments": [{"start": i * 10.0, "end": i * 10.0 + 8, "text": f"line {i}"} for i in range(30)],
}})

edits = {
    "cuts": [{"start": 50, "end": 60}],
    "effects": [
        {"kind": "zoom", "start": 10, "end": 14, "scale": 1.6, "x": 30, "y": 40},
        {"kind": "speed", "start": 100, "end": 160, "rate": 2},
        {"kind": "speed", "start": 150, "end": 170, "rate": 4},   # overlaps: starts where the first stops
        {"kind": "mute", "start": 20, "end": 25},
        {"kind": "blur", "start": 200, "end": 230, "x": 5, "y": 6, "w": 30, "h": 20, "mode": "black"},
        {"kind": "zoom", "start": 5, "end": 5.2, "scale": 2},     # too short: dropped
    ],
    "overlays": [{"start": 0, "end": 4, "text": "Hello", "style": "callout", "position": "top", "size": "l", "anim": "type", "color": "#123abc"}],
    "captions": {"preset": "pop", "font": "display", "color": "#ffffff", "highlight": "#7ef0a8", "uppercase": True},
    "brand": {"progress_bar": True, "progress_color": "#ffd23f"},
}

print("\n== validation ==")
bad = c.put(f"/admin/episodes/{ep_id}/studio", json={"start": 0, "end": 300, "edits": {"effects": [{"kind": "speed", "start": 0, "end": 10, "rate": 9}]}}, headers=A)
check(bad.status_code == 422, "a speed past 4x is refused")
bad = c.put(f"/admin/episodes/{ep_id}/studio", json={"start": 0, "end": 300, "edits": {"captions": {"color": "red"}}}, headers=A)
check(bad.status_code == 422, "a caption colour that isn't #rrggbb is refused")
bad = c.put(f"/admin/episodes/{ep_id}/studio", json={"start": 0, "end": 30, "edits": {"effects": [{"kind": "speed", "start": 0, "end": 30, "rate": 4}]}}, headers=A)
check(bad.status_code == 422, "a part sped up below the minimum length is refused")

print("\n== save ==")
saved = ok(c.put(f"/admin/episodes/{ep_id}/studio", json={"start": 0, "end": 300, "split_at": [150], "edits": edits}, headers=A), "save")
e = saved["edits"]
kinds = [(x["kind"], x["start"], x["end"]) for x in e["effects"]]
check(("zoom", 5.0, 5.2) not in kinds, "an effect under half a second is dropped")
check(("speed", 160.0, 170.0) in kinds, "an overlapping speed starts where the earlier one stops")
check([x["start"] for x in e["effects"]] == sorted(x["start"] for x in e["effects"]), "effects are in time order")
blur = next(x for x in e["effects"] if x["kind"] == "blur")
check(blur["mode"] == "black" and blur["w"] == 30 and "rate" not in blur, "a blur keeps its box and nothing else")
check(e["captions"]["font"] == "display" and e["captions"]["uppercase"] is True, "caption font and capitals are kept")
check(e["brand"]["progress_bar"] is True and e["brand"]["progress_color"] == "#ffd23f", "the progress bar is kept")
check(e["overlays"][0]["anim"] == "type" and e["overlays"][0]["color"] == "#123abc", "overlay entrance and colour are kept")
check(saved["part"] == [1, 2], "the split made two parts")

print("\n== every part, in clip time ==")
part2 = next(p for p in saved["parts"] if not p["is_this"])
check(mongo.episodes.find_one({"_id": part2["id"]})["edits"] == mongo.episodes.find_one({"_id": ep_id})["edits"], "both parts carry the same edits")
s1 = ok(c.get(f"/episodes/{ep_id}/stream", headers=A), "stream part 1")
s2 = ok(c.get(f"/episodes/{part2['id']}/stream", headers=A), "stream part 2")
k1 = {x["kind"] for x in s1["edits"]["effects"]}
check(k1 == {"zoom", "speed", "mute"}, f"part 1 gets the effects inside it ({sorted(k1)})")
sp2 = [x for x in s2["edits"]["effects"] if x["kind"] == "speed"]
check(sp2 and sp2[0]["start"] == 0.0 and sp2[0]["end"] == 10.0, "part 2's speed-ups are in its own time")
bl2 = next(x for x in s2["edits"]["effects"] if x["kind"] == "blur")
check(bl2["start"] == 50.0 and bl2["end"] == 80.0, "part 2's blur is moved into its own time")
check(s2["edits"]["brand"]["progress_bar"] is True, "styling reaches every part")

print("\n== AI tasks are known ==")
for task in ("zooms", "details"):
    r = c.post(f"/admin/episodes/{ep_id}/studio/ai", json={"task": task}, headers=A)
    check(r.status_code != 422, f"the {task} task is accepted ({r.status_code})")

print(f"\n{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print("  -", f)
sys.exit(1 if FAILED else 0)
