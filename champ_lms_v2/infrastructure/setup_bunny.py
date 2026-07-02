#!/usr/bin/env python3
"""
Bunny setup script — run once to configure Bunny Storage + CDN for thumbnails.
Video (Bunny Stream) library is created manually in the Bunny dashboard.

Champ LMS v2 hosts the app itself on Railway (frontend + backend + MongoDB +
Redis), no custom domain. Bunny is used only for video (Stream) and thumbnail
storage/CDN — both of which work fine on Bunny's free b-cdn.net subdomains.

Usage:
    pip install httpx python-dotenv
    python setup_bunny.py

Required env vars (set in .env or environment):
    BUNNY_ACCOUNT_API_KEY
"""
import asyncio
import os
from dotenv import load_dotenv
import httpx

load_dotenv()

BUNNY_API = "https://api.bunny.net"
BUNNY_STREAM_BASE = "https://video.bunnycdn.com"

API_KEY = os.environ["BUNNY_ACCOUNT_API_KEY"]
STREAM_API_KEY = os.environ.get("BUNNY_STREAM_API_KEY", "")

HEADERS = {"AccessKey": API_KEY, "Content-Type": "application/json"}


async def create_storage_zone(client: httpx.AsyncClient, name: str, region: str = "DE") -> dict:
    resp = await client.post(
        f"{BUNNY_API}/storagezone",
        headers=HEADERS,
        json={"Name": name, "Region": region, "ZoneTier": 0},
    )
    if resp.status_code == 201:
        data = resp.json()
        print(f"  ✓ Storage zone '{name}' created — Password: {data.get('Password')}")
        return data
    elif resp.status_code == 400 and ("already exists" in resp.text.lower() or "name_taken" in resp.text.lower()):
        print(f"  ↩ Storage zone '{name}' already exists")
        list_resp = await client.get(f"{BUNNY_API}/storagezone", headers=HEADERS)
        body = list_resp.json()
        zones = body if isinstance(body, list) else body.get("Items", [])
        for z in zones:
            if z["Name"] == name:
                return z
    else:
        print(f"  ✗ Failed to create '{name}': {resp.status_code} {resp.text}")
    return {}


async def create_pull_zone(client: httpx.AsyncClient, name: str, origin_url: str) -> dict:
    """Creates a pull zone with a free *.b-cdn.net hostname — no custom domain needed."""
    resp = await client.post(
        f"{BUNNY_API}/pullzone",
        headers=HEADERS,
        json={
            "Name": name,
            "OriginUrl": origin_url,
            "Type": 0,
            "EnableGeoZoneUS": True,
            "EnableGeoZoneEU": True,
            "EnableGeoZoneASIA": True,
        },
    )
    if resp.status_code in (200, 201):
        data = resp.json()
        hostname = data.get("Hostnames", [{}])[0].get("Value")
        print(f"  ✓ Pull zone '{name}' created — hostname: {hostname}")
        return data
    elif resp.status_code == 400 and ("already exists" in resp.text.lower() or "name_taken" in resp.text.lower()):
        print(f"  ↩ Pull zone '{name}' already exists")
        list_resp = await client.get(f"{BUNNY_API}/pullzone", headers=HEADERS)
        zones = list_resp.json() if isinstance(list_resp.json(), list) else list_resp.json().get("Items", [])
        for z in zones:
            if z["Name"] == name:
                return z
    else:
        print(f"  ✗ Pull zone '{name}': {resp.status_code} {resp.text}")
    return {}


async def add_mobile_block_rule(client: httpx.AsyncClient, pull_zone_id: int) -> None:
    """Optional: block mobile User-Agents at the CDN edge (thumbnails are desktop-only)."""
    mobile_block = {
        "Enabled": True,
        "Description": "Block mobile devices",
        "TriggerMatchingType": 1,  # ANY
        "Triggers": [{
            "Type": 1,  # RequestHeader
            "PatternMatches": ["*Android*", "*iPhone*", "*iPad*", "*Mobile*", "*webOS*"],
            "PatternMatchingType": 0,  # MatchAny
        }],
        "ActionType": 2,  # BlockRequest
        "ActionParameter1": "403",
    }
    resp = await client.post(
        f"{BUNNY_API}/pullzone/{pull_zone_id}/edgerules/addOrUpdate",
        headers=HEADERS,
        json=mobile_block,
    )
    status = "✓" if resp.status_code in (200, 201) else "✗"
    print(f"  {status} Edge rule 'Block mobile devices': {resp.status_code}")


async def verify_stream_library(client: httpx.AsyncClient, library_id: str) -> dict:
    """Verify an existing Bunny Stream library (created manually in the dashboard)."""
    if not STREAM_API_KEY:
        print("  ↩ BUNNY_STREAM_API_KEY not set — skip stream library check")
        return {}
    if not library_id:
        print("  ↩ No BUNNY_STREAM_LIBRARY_ID — skip (create the library manually first)")
        return {}

    headers = {"AccessKey": STREAM_API_KEY, "Content-Type": "application/json"}
    resp = await client.get(
        f"{BUNNY_STREAM_BASE}/library/{library_id}",
        headers=headers,
        timeout=15,
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"  ✓ Stream library verified — videos: {data.get('videoCount', 0)}, collections: {data.get('collectionCount', 0)}")
        return data
    else:
        print(f"  ✗ Stream library check failed: {resp.status_code} {resp.text}")
    return {}


async def main() -> None:
    print("\n=== Champ LMS v2 — Bunny Setup ===\n")

    async with httpx.AsyncClient(timeout=30) as client:

        print("1. Storage zone (thumbnails)")
        thumbs_zone = await create_storage_zone(client, "champ-lms-thumbs")

        print("\n2. CDN Pull zone (thumbnails)")
        pull_zone = {}
        if thumbs_zone.get("Id"):
            origin = f"https://storage.bunnycdn.com/{thumbs_zone['Name']}/"
            pull_zone = await create_pull_zone(client, "champ-lms-cdn", origin)

            if pull_zone.get("Id"):
                print("\n3. Edge Rules")
                await add_mobile_block_rule(client, pull_zone["Id"])

        print("\n4. Bunny Stream library (verify existing)")
        stream_library_id = os.environ.get("BUNNY_STREAM_LIBRARY_ID", "")
        await verify_stream_library(client, stream_library_id)

    print("\n=== Setup complete ===")
    print("\n── Values to copy into backend/.env (or Railway service variables) ──")
    if pull_zone.get("Hostnames"):
        print(f"  BUNNY_CDN_HOSTNAME={pull_zone['Hostnames'][0]['Value']}")
    print(f"  BUNNY_STORAGE_THUMBS_PASSWORD={thumbs_zone.get('Password', '')}")
    print(f"  BUNNY_STREAM_LIBRARY_ID={stream_library_id}")
    print("  BUNNY_STREAM_CDN_HOSTNAME=<from Bunny Stream dashboard, e.g. vz-abc123.b-cdn.net>")
    print(f"  BUNNY_STREAM_WEBHOOK_SECRET={os.environ.get('BUNNY_STREAM_API_KEY', '')}  # = Stream API key")
    print()
    print("── Manual steps remaining ──")
    print("  1. Bunny dashboard → Stream → create a video library (if not already done)")
    print("  2. Stream library → Security → Enable Token Authentication → copy the secret")
    print("  3. Pull Zones → champ-lms-cdn → Optimizer → Enable Image Optimization")
    print("  4. Stream → Webhooks → set URL to <your-railway-domain>/api/webhooks/bunny-stream")


if __name__ == "__main__":
    asyncio.run(main())
