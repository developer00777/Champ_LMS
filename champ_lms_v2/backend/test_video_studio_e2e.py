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

print("\n== InShot tools: canvas, filter, freeze, fx, stickers ==")
look = {"filter": "vintage", "filter_strength": 60, "warmth": 30, "vignette": 20, "background": "blur",
        "rotate": 90, "flip_h": True, "transition": "zoom"}
bad = c.put(f"/admin/episodes/{ep_id}/studio", json={"start": 0, "end": 150, "edits": {"look": {"rotate": 45}}}, headers=A)
check(bad.status_code == 422, "a rotation other than a quarter turn is refused")
more = {
    "cuts": [{"start": 50, "end": 60}],
    "effects": [
        {"kind": "freeze", "start": 20, "end": 20.5, "hold": 3},
        {"kind": "fx", "start": 30, "end": 34, "style": "glitch"},
    ],
    "overlays": [{"start": 5, "end": 8, "text": "🔥", "style": "sticker", "position": "free", "x": 70, "y": 30, "size": "xl", "anim": "bounce"}],
    "look": look,
}
saved = ok(c.put(f"/admin/episodes/{ep_id}/studio", json={"start": 0, "end": 150, "edits": more}, headers=A), "save inshot")
e = saved["edits"]
check(all(e["look"][k] == v for k, v in look.items()), "filter, canvas and transition are kept")
frz = next(x for x in e["effects"] if x["kind"] == "freeze")
check(frz["hold"] == 3 and "style" not in frz, "a freeze keeps its hold and nothing else")
check(next(x for x in e["effects"] if x["kind"] == "fx")["style"] == "glitch", "a visual effect keeps its style")
st_ov = e["overlays"][0]
check(st_ov["style"] == "sticker" and st_ov["position"] == "free" and st_ov["x"] == 70, "a sticker keeps where it was dragged")

print("\n== music and voice ==")
wav = b"RIFF" + (36).to_bytes(4, "little") + b"WAVEfmt " + bytes(16) + b"data" + bytes(4)
r = c.post(f"/admin/episodes/{ep_id}/studio/audio", files={"file": ("x.txt", b"hello", "text/plain")}, headers=A)
check(r.status_code == 422, "a file that isn't audio is refused")
up = ok(c.post(f"/admin/episodes/{ep_id}/studio/audio", files={"file": ("bed.wav", wav, "audio/wav")},
               data={"kind": "music", "duration": "12.5"}, headers=A), "upload music")
spare = ok(c.post(f"/admin/episodes/{ep_id}/studio/audio", files={"file": ("v.webm", wav, "audio/webm")},
                  data={"kind": "voice"}, headers=A), "upload voice")
check(up["kind"] == "music" and up["duration"] == 12.5, "an upload says what it is and how long")
r = c.put(f"/admin/episodes/{ep_id}/studio", json={"start": 0, "end": 150, "edits": {
    "audio": {"tracks": [{"id": "not-a-file", "start": 0, "duration": 5}]}}}, headers=A)
check(r.status_code == 422, "a track whose file doesn't exist is refused")
track = {"id": up["id"], "kind": "music", "name": "Bed", "start": 2, "duration": 12.5, "volume": 40, "loop": True, "fade_in": True, "fade_out": True}
saved = ok(c.put(f"/admin/episodes/{ep_id}/studio", json={"start": 0, "end": 150, "edits": {
    **more, "audio": {"volume": 60, "tracks": [track]}}}, headers=A), "save with music")
check(saved["edits"]["audio"]["volume"] == 60 and saved["edits"]["audio"]["tracks"][0]["loop"] is True, "the mix is kept")
check(mongo.studio_audio.count_documents({"_id": spare["id"]}) == 0, "an upload no track uses is removed on save")
check(mongo.studio_audio.count_documents({"_id": up["id"]}) == 1, "a track's file is kept")
r = c.get(f"/episodes/{ep_id}/studio-audio/{up['id']}", headers=A)
check(r.status_code == 200 and r.content == wav and r.headers["content-type"].startswith("audio/wav"), "the track's file can be played back")
s2 = ok(c.get(f"/episodes/{part2['id']}/stream", headers=A), "stream part 2 again")
tr2 = s2["edits"]["audio"]["tracks"][0]
check(tr2["start"] == -148.0, "a track that started in part 1 carries on into part 2 (its start is before 0 there)")
r = c.get(f"/episodes/{part2['id']}/studio-audio/{up['id']}", headers=A)
check(r.status_code == 200, "every part of the video plays the same track")
r = c.get(f"/episodes/{ep_id}/studio-audio/{up['id']}")
check(r.status_code == 401, "the audio needs a sign-in")
ok(c.put(f"/admin/episodes/{ep_id}/studio", json={"start": 0, "end": 150, "edits": more}, headers=A), "save without music")
check(mongo.studio_audio.count_documents({"_id": up["id"]}) == 0, "removing the track removes its file")

print(f"\n{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print("  -", f)
sys.exit(1 if FAILED else 0)
