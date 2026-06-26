"""
Lambda #3 — Zoom SQS processor.
Trigger: SQS champ-lms-zoom-processing queue.
Downloads transcript from Zoom → runs Claude AI pipeline → creates module.
"""
import os
import json
import httpx

API_URL = os.environ["API_INTERNAL_URL"]
INTERNAL_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "dev-token")
ZOOM_ACCOUNT_ID = os.environ.get("ZOOM_ACCOUNT_ID", "")
ZOOM_CLIENT_ID = os.environ.get("ZOOM_CLIENT_ID", "")
ZOOM_CLIENT_SECRET = os.environ.get("ZOOM_CLIENT_SECRET", "")


def get_zoom_token() -> str:
    import base64
    creds = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()
    with httpx.Client() as client:
        res = client.post(
            "https://zoom.us/oauth/token",
            params={"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID},
            headers={"Authorization": f"Basic {creds}"},
        )
        res.raise_for_status()
        return res.json()["access_token"]


def handler(event, context):
    for record in event["Records"]:
        body = json.loads(record["body"])
        session_id = body.get("session_id")
        meeting_payload = body.get("payload", {})

        if not session_id:
            continue

        # Trigger the AI module builder via FastAPI
        with httpx.Client(timeout=300) as client:
            resp = client.post(
                f"{API_URL}/zoom/build-module/{session_id}",
                headers={"Authorization": f"Bearer {INTERNAL_TOKEN}"},
            )
            if resp.status_code == 200:
                result = resp.json()
                print(f"Module created: {result['title']} ({result['episodes']} episodes)")
            else:
                print(f"Failed to build module for session {session_id}: {resp.text}")
                raise Exception(f"API returned {resp.status_code}")

    return {"statusCode": 200}
