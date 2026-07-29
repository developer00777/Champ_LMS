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

# Required for provisioning (main()); --ladder-only needs only the Stream key.
API_KEY = os.environ.get("BUNNY_ACCOUNT_API_KEY", "")
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
        # Encoding settings are NOT on the Stream API response — they live on
        # the account API's videolibrary object. Read them from there so the
        # printed ladder reflects reality rather than "(dashboard default)".
        if API_KEY:
            settings_resp = await client.get(
                f"{BUNNY_API}/videolibrary/{library_id}",
                headers=HEADERS,
                timeout=15,
            )
            if settings_resp.status_code == 200:
                s = settings_resp.json()
                rates = " ".join(
                    f"{r}={s.get(f'Bitrate{r}')}k"
                    for r in ("240p", "360p", "480p", "720p", "1080p")
                    if s.get(f"Bitrate{r}")
                )
                print(f"    EnabledResolutions: {s.get('EnabledResolutions') or '(none set)'}")
                print(f"    Bitrates: {rates or '(defaults)'}")
            else:
                print(f"    ↩ Could not read encoding settings: HTTP {settings_resp.status_code}")
        return data
    else:
        print(f"  ✗ Stream library check failed: {resp.status_code} {resp.text}")
    return {}


# ---------------------------------------------------------------------------
# Encoding ladder
# ---------------------------------------------------------------------------

# * Delivery bandwidth is the dominant Bunny cost, and bitrate is the only
# * lever that scales it linearly. Training content is screencast and
# * talking-head — near-static frames — so it encodes far cheaper than the
# * general-purpose defaults assume.
# *
# * Left unset, Bunny applies the dashboard defaults (up to 1080p, and 4K if
# * the library allows it). 2160p/1440p also incur PREMIUM encoding charges
# * ($0.150/min and up) that buy nothing for this content type.
# 240p is kept deliberately. It is the cheapest rung on the ladder and the
# fallback that keeps a lesson watchable on a weak mobile connection — exactly
# the case an LMS must not fail. Dropping it saves nothing (ABR only serves it
# when the client genuinely can't sustain more) and costs accessibility.
LADDER_RESOLUTIONS = "240p,360p,480p,720p"

# Per-rendition bitrates in kbps, roughly half Bunny's general-purpose
# defaults (600/800/1400/2800). Screencast and talking-head footage is
# near-static, so it holds up well below the defaults; 720p at 1500k is
# visually clean for screen capture, where the 5000k v1 MediaConvert setting
# was ~3x more than the content can use.
LADDER_BITRATES = {
    "Bitrate240p": 300,
    "Bitrate360p": 400,
    "Bitrate480p": 800,
    "Bitrate720p": 1500,
    # Explicitly zeroed so a dashboard change can't silently re-enable them.
    "Bitrate1080p": 0,
    "Bitrate1440p": 0,
    "Bitrate2160p": 0,
}


async def configure_stream_ladder(client: httpx.AsyncClient, library_id: str) -> None:
    """Pin the encoding ladder so delivery cost is bounded by configuration.

    Idempotent: re-running with the same values is a no-op on Bunny's side.
    """
    # * Library SETTINGS live on the account API (api.bunny.net/videolibrary),
    # * not the per-library Stream API (video.bunnycdn.com/library) — the
    # * latter only serves GET for a library and answers 405 to a POST.
    # * Different host, different key: this needs BUNNY_ACCOUNT_API_KEY.
    if not API_KEY or not library_id:
        print("  ↩ BUNNY_ACCOUNT_API_KEY or library id missing — skip ladder config")
        return

    headers = {"AccessKey": API_KEY, "Content-Type": "application/json"}
    # * Deliberately does NOT touch KeepOriginalFiles. Discarding originals
    # * saves ~$0.01/GB, but it also makes the ladder a one-way door: without a
    # * source file you cannot re-encode an existing video if these bitrates
    # * later prove too low. For a course library uploaded once and served for
    # * years, that optionality is worth far more than the storage.
    payload = {
        "EnabledResolutions": LADDER_RESOLUTIONS,
        **LADDER_BITRATES,
    }

    resp = await client.post(
        f"{BUNNY_API}/videolibrary/{library_id}",
        headers=headers,
        json=payload,
        timeout=20,
    )
    if resp.status_code in (200, 201, 204):
        print(f"  ✓ Encoding ladder set: {LADDER_RESOLUTIONS} "
              f"(360p={LADDER_BITRATES['Bitrate360p']}k, "
              f"480p={LADDER_BITRATES['Bitrate480p']}k, "
              f"720p={LADDER_BITRATES['Bitrate720p']}k; 1080p+ disabled)")
        print("    NOTE: applies to NEWLY uploaded videos. Existing videos keep "
              "their original renditions unless re-encoded.")
    else:
        print(f"  ✗ Ladder config failed: {resp.status_code} {resp.text[:200]}")
        print("    Set EnabledResolutions manually: Stream → Library → Encoding.")


async def ladder_only() -> None:
    """Apply just the encoding ladder, touching nothing else.

    `main()` is a provisioning script — it creates a storage zone, a pull zone
    and an edge rule. Re-running all of that to adjust a bitrate is both
    unnecessary and risky on a live account, so tuning the ladder has its own
    entry point: `python setup_bunny.py --ladder-only`.
    """
    print("\n=== Champ LMS v2 — Bunny encoding ladder only ===\n")
    library_id = os.environ.get("BUNNY_STREAM_LIBRARY_ID", "")
    if not library_id:
        print("  ✗ BUNNY_STREAM_LIBRARY_ID is not set — nothing to configure.")
        return

    async with httpx.AsyncClient(timeout=30) as client:
        print("Current library state")
        await verify_stream_library(client, library_id)
        print("\nApplying ladder")
        await configure_stream_ladder(client, library_id)
        print("\nRe-reading to confirm")
        await verify_stream_library(client, library_id)


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

        print("\n5. Bunny Stream encoding ladder (delivery-cost control)")
        await configure_stream_ladder(client, stream_library_id)

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
    import sys

    if "--ladder-only" in sys.argv:
        asyncio.run(ladder_only())
    else:
        asyncio.run(main())
