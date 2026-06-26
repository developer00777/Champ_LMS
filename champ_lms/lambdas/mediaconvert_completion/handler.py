"""
Lambda #2 — Fires when MediaConvert job completes (EventBridge rule).
Updates episode status in the FastAPI backend to 'ready'.
"""
import os
import json
import httpx

API_URL = os.environ["API_INTERNAL_URL"]  # e.g. http://internal-alb/


def handler(event, context):
    detail = event.get("detail", {})
    status = detail.get("status")

    if status not in ("COMPLETE", "ERROR"):
        return

    metadata = detail.get("userMetadata", {})
    episode_id = metadata.get("episode_id")
    if not episode_id:
        print("No episode_id in job metadata, skipping")
        return

    if status == "COMPLETE":
        output_detail = detail.get("outputGroupDetails", [{}])[0]
        output_details = output_detail.get("outputDetails", [{}])
        # HLS manifest is the .m3u8 file
        hls_key = f"hls/{episode_id}/index.m3u8"

        payload = {"status": "ready", "hls_manifest_key": hls_key}
    else:
        payload = {"status": "failed"}

    # Call internal FastAPI to update episode
    with httpx.Client() as client:
        # Use a service token for internal calls
        resp = client.patch(
            f"{API_URL}/admin/episodes/{episode_id}",
            json=payload,
            headers={"Authorization": f"Bearer {os.environ.get('INTERNAL_SERVICE_TOKEN', 'dev-token')}"},
            timeout=10,
        )
        resp.raise_for_status()

    print(f"Episode {episode_id} updated to {payload['status']}")
    return {"statusCode": 200}
