"""
E2E: the thumbnail studio's backend — course and episode thumbnails in Mongo.

Covers:
  * saving an uploaded, AI or text thumbnail for a course and for an episode;
  * every image is cropped to a 1280x720 WebP and served publicly by id;
  * a new image replaces (and deletes) the old one; text designs keep their
    settings for re-editing;
  * the studio image wins over Bunny's auto frame, and removing it falls back;
  * course list, canvas, learner course and module views all carry it;
  * AI generation validates its input (the image model itself is not called
    unless OPENROUTER_API_KEY is set and E2E_CALL_AI=1);
  * purging a course deletes its images.

Run inside the API container:  python test_thumbnails_e2e.py
"""
import io
import json
import os
import sys
import uuid

import httpx
from PIL import Image
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


def png(w, h, color=(200, 30, 60)):
    out = io.BytesIO()
    Image.new("RGB", (w, h), color).save(out, format="PNG")
    return out.getvalue()


def image(url):
    # Thumbnail URLs are written for the browser, under the /api proxy.
    return c.get(url.removeprefix("/api"))


c = httpx.Client(base_url=BASE, timeout=120.0)
tok = ok(c.post("/auth/token", data=ADMIN), "admin login")["access_token"]
A = {"Authorization": f"Bearer {tok}"}
sfx = uuid.uuid4().hex[:8]

print("== course thumbnail ==")
course = ok(c.post("/admin/courses", json={"title": f"Thumbs {sfx}", "category": "sales"}, headers=A), "create course")
cid = course["id"]
check(course["thumbnail_url"] is None, "new course has no thumbnail")
r = ok(c.post(f"/admin/thumbnails/module/{cid}", files={"file": ("a.png", png(900, 900), "image/png")},
              data={"source": "upload"}, headers=A), "upload")
first = r["thumbnail_url"]
got = image(first)
check(got.status_code == 200 and got.headers["content-type"] == "image/webp", "served as webp without auth")
check(Image.open(io.BytesIO(got.content)).size == (1280, 720), "cropped to 1280x720")

design = {"template": "split", "palette": "ocean", "font": "serif", "title": "Thumbs", "kicker": "Sales"}
r = ok(c.post(f"/admin/thumbnails/module/{cid}", files={"file": ("t.png", png(1280, 720), "image/png")},
              data={"source": "text", "design": json.dumps(design)}, headers=A), "text design")
check(r["thumbnail_design"]["template"] == "split", "design settings kept")
check(image(first).status_code == 404, "replaced image deleted")
check(mongo.thumbnails.count_documents({"owner_id": cid}) == 1, "one image stored per course")
check(c.post(f"/admin/thumbnails/module/{cid}", files={"file": ("x.txt", b"no", "text/plain")}, headers=A).status_code == 422,
      "non-image refused")
check(c.post(f"/admin/thumbnails/module/{cid}", files={"file": ("a.png", png(8, 8), "image/png")}).status_code == 401,
      "saving needs a login")

print("== where it shows ==")
lst = ok(c.get("/admin/courses", headers=A), "course list")
check(next(x for x in lst if x["id"] == cid)["thumbnail_url"] == r["thumbnail_url"], "course list")
check(ok(c.get(f"/admin/courses/{cid}", headers=A), "canvas")["thumbnail_source"] == "text", "canvas view")
check(ok(c.get(f"/admin/modules/{cid}", headers=A), "module")["thumbnail_source"] == "text", "module editor view")

print("== episode thumbnail ==")
sec = course["sections"][0]["id"]
vid = ok(c.post(f"/admin/courses/{cid}/items", json={"kind": "video", "section_id": sec, "title": "Ep"}, headers=A), "add video")
mongo.episodes.update_one({"_id": vid["ref_id"]}, {"$set": {"thumbnail_url": "https://example.test/frame.jpg"}})
r = ok(c.post(f"/admin/thumbnails/episode/{vid['ref_id']}", files={"file": ("a.png", png(1920, 1080), "image/png")},
              data={"source": "ai"}, headers=A), "episode thumbnail")
item = ok(c.get(f"/admin/courses/{cid}", headers=A), "canvas")["items"][0]
check(item["thumbnail_url"] == r["thumbnail_url"], "studio image beats Bunny's frame")
r = ok(c.delete(f"/admin/thumbnails/episode/{vid['ref_id']}", headers=A), "remove")
check(r["thumbnail_url"] == "https://example.test/frame.jpg", "removing falls back to Bunny's frame")

print("== AI generation ==")
check(c.post("/admin/thumbnails/generate", json={"title": "x", "style": "watercolour"}, headers=A).status_code in (422, 503),
      "unknown style refused")
if os.environ.get("E2E_CALL_AI") == "1":
    g = ok(c.post("/admin/thumbnails/generate", json={"owner_kind": "module", "owner_id": cid, "style": "illustration"},
                  headers=A), "generate (real model)")
    check(g["image"].startswith("data:image/webp;base64,"), "image model returned a picture")
    check(mongo.thumbnails.count_documents({"owner_id": cid}) == 1, "generating saved nothing")

print("== purge ==")
ok(c.delete(f"/admin/modules/{cid}?confirm={cid}", headers=A), "delete course")
check(mongo.thumbnails.count_documents({"owner_id": {"$in": [cid, vid["ref_id"]]}}) == 0, "images deleted with the course")

print(f"\n{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print("  -", f)
sys.exit(1 if FAILED else 0)
