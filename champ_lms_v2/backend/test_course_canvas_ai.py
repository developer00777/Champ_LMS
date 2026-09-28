"""
The canvas' AI paths, with only the network call to OpenRouter faked.

AIService._chat is replaced by a stub that returns canned model output, so the
real prompt building, JSON extraction, validation and persistence all run.
Checks: audio clips become timed lines shifted by their offset; malformed quiz
questions from the model are dropped; notes are drafted after an automatic
transcript but never over admin-written notes; section notes and AI test
papers are built from the course's transcripts.

Run inside the API container:  python test_course_canvas_ai.py
"""
import json
import sys
import uuid

from fastapi.testclient import TestClient

from app.main import app
from app.services.ai_service import ai_service

PASSED, FAILED = 0, []
calls: list[dict] = []


def check(cond, label):
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok    {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL  {label}")


async def fake_chat(prompt, max_tokens=4096, audio=None, model=None):
    calls.append({"prompt": prompt, "audio": audio, "model": model})
    if audio:
        return '```json\n[{"start": 0, "end": 3.5, "text": "Hello team."}, {"start": 3.5, "end": 8, "text": "Today: discovery."}, {"start": 1, "text": ""}]\n```'
    if "checkpoint quiz" in prompt:
        return json.dumps([
            {"question": "What makes discovery work?", "options": ["Talking", "Asking about the cost of doing nothing", "Pricing", "Demos"], "correct_index": 1, "explanation": "Said at 0:40.", "episode": 2},
            {"question": "Broken: two options, bad index", "options": ["a", "b"], "correct_index": 5, "episode": 1},
            {"question": "Who signs?", "options": ["Economic buyer", "Champion", "User", "Legal"], "correct_index": 0, "episode": 1},
        ])
    if "study notes" in prompt:
        return "## Key points\n- Ask about the cost of doing nothing\n## Try this\n- Use it on one call"
    if "one-page reading" in prompt:
        return "## Discovery\n- Start with the cost of doing nothing"
    return "[]"


ai_service._chat = fake_chat
ai_service.settings.openrouter_api_key = "test-key"  # makes ai_service.enabled true

with TestClient(app) as c:
    tok = c.post("/auth/token", data={"username": "verify.admin@champtest.com", "password": "adminpass123"}).json()["access_token"]
    A = {"Authorization": f"Bearer {tok}"}
    course = c.post("/admin/courses", json={"title": f"AI course {uuid.uuid4().hex[:6]}"}, headers=A).json()
    cid, sec = course["id"], course["sections"][0]["id"]
    v1 = c.post(f"/admin/courses/{cid}/items", json={"kind": "video", "section_id": sec, "title": "Intro"}, headers=A).json()
    v2 = c.post(f"/admin/courses/{cid}/items", json={"kind": "video", "section_id": sec, "title": "Discovery"}, headers=A).json()

    print("\n== transcription ==")
    r = c.post(f"/admin/episodes/{v1['ref_id']}/transcribe-chunk",
               files={"audio": ("c.wav", b"RIFF....WAVEfmt fake", "audio/wav")},
               data={"offset_seconds": "120"}, headers=A)
    segs = r.json().get("segments", [])
    check(r.status_code == 200 and len(segs) == 2, "clip becomes two lines, empty line dropped")
    check(segs and segs[0]["start"] == 120 and segs[1]["end"] == 128, "times shifted by the clip offset")
    check(calls[-1]["audio"] and calls[-1]["audio"][1] == "wav", "audio sent to the model as wav")
    check(calls[-1]["model"] == ai_service.settings.openrouter_transcribe_model == "google/gemini-3.1-flash-lite",
          "transcripts use the transcript model, not the default chat model")
    r = c.post(f"/admin/episodes/{v1['ref_id']}/transcribe-chunk",
               files={"audio": ("c.wav", b"RIFF....WAVEfmt fake", "audio/wav")},
               data={"offset_seconds": "240", "clip_seconds": "6"}, headers=A)
    clamped = r.json()["segments"]
    check(max(x["end"] for x in clamped) == 246 and all(240 <= x["start"] <= 246 for x in clamped),
          "a timestamp past the end of the clip is held inside it")
    big = c.post(f"/admin/episodes/{v1['ref_id']}/transcribe-chunk",
                 files={"audio": ("c.wav", b"0" * (12 * 1024 * 1024 + 1), "audio/wav")}, headers=A)
    check(big.status_code == 413, "oversized clip refused")

    print("\n== notes follow an automatic transcript ==")
    for v, text in ((v1, "Hello team."), (v2, "Ask about the cost of doing nothing.")):
        c.put(f"/admin/episodes/{v['ref_id']}/transcript",
              json={"segments": [{"start": 0, "end": 4, "text": text}], "source": "auto"}, headers=A)
    admin = c.get(f"/admin/courses/{cid}", headers=A).json()
    ep2 = [i for i in admin["items"] if i["ref_id"] == v2["ref_id"]][0]
    check(ep2["notes_source"] == "ai" and ep2["notes"].startswith("## Key points"), "notes drafted after the transcript")
    c.put(f"/admin/episodes/{v1['ref_id']}/notes", json={"notes": "Mine"}, headers=A)
    c.put(f"/admin/episodes/{v1['ref_id']}/transcript",
          json={"segments": [{"start": 0, "end": 4, "text": "Hello again."}], "source": "auto"}, headers=A)
    admin = c.get(f"/admin/courses/{cid}", headers=A).json()
    ep1 = [i for i in admin["items"] if i["ref_id"] == v1["ref_id"]][0]
    check(ep1["notes"] == "Mine" and ep1["notes_source"] == "manual", "admin-written notes are never redrafted")
    r = c.post(f"/admin/episodes/{v1['ref_id']}/notes/generate", headers=A).json()
    check(r["notes_source"] == "ai", "explicit redraft replaces them on request")

    print("\n== checkpoint quiz ==")
    qz = c.post(f"/admin/courses/{cid}/items", json={"kind": "quiz", "section_id": sec}, headers=A).json()
    r = c.post(f"/admin/assessments/{qz['ref_id']}/generate", headers=A).json()
    qs = r["questions"]
    check(len(qs) == 2, "malformed question from the model dropped")
    check(qs[0]["source_episode_id"] == v2["ref_id"] and qs[1]["source_episode_id"] == v1["ref_id"], "questions mapped to their episodes")
    prompt = [x for x in calls if "checkpoint quiz" in x["prompt"]][-1]["prompt"]
    check("Episode 1: Intro" in prompt and "Episode 2: Discovery" in prompt, "both transcripts in the prompt, in order")

    print("\n== notes page and test ==")
    nt = c.post(f"/admin/courses/{cid}/items", json={"kind": "notes", "section_id": sec}, headers=A).json()
    r = c.post(f"/admin/notes/{nt['ref_id']}/draft", headers=A).json()
    check(r["source"] == "ai" and r["body"].startswith("## Discovery"), "section notes drafted")
    ts = c.post(f"/admin/courses/{cid}/items", json={"kind": "test", "section_id": sec}, headers=A).json()
    r = c.post(f"/admin/courses/{cid}/tests/{ts['ref_id']}/generate", json={"count": 10}, headers=A).json()
    check(r["question_count"] == 2 and r["is_ready"] and r["source_parser"] == "ai", "AI test paper is ready to publish")

print("\n== out of credit for audio ==")
# The real _chat against a faked HTTP 402, as OpenRouter sends when the
# account balance is under the $0.50 it requires for audio.
import asyncio  # noqa: E402

from app.services import ai_service as ai_module  # noqa: E402
from app.services.ai_service import AIService, AIServiceError  # noqa: E402


class _Resp:
    status_code = 402
    text = '{"error":{"message":"This request requires at least $0.50 in balance for audio"}}'

    def json(self):
        return {"error": {"message": "This request requires at least $0.50 in balance for audio"}}


class _Client:
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, *a, **k): return _Resp()


_real_client = ai_module.httpx.AsyncClient
ai_module.httpx.AsyncClient = _Client
try:
    asyncio.run(AIService().transcribe_audio("AAAA", 0))
    check(False, "a 402 on audio raises")
except AIServiceError as e:
    check("$0.50" in str(e) and "credits" in str(e), "a 402 on audio explains the audio balance minimum")
finally:
    ai_module.httpx.AsyncClient = _real_client

print(f"\n{PASSED} passed, {len(FAILED)} failed")
for f in FAILED:
    print("  -", f)
sys.exit(1 if FAILED else 0)
