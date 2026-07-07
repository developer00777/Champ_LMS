#!/usr/bin/env python3
"""
Champ LMS End-to-End Video Test

Logs in as admin (or any user), browses published modules, finds the first
ready episode, requests a Bunny Stream HLS URL, verifies the manifest is
reachable, and downloads the video stream to a local file.

Usage:
    python e2e_video_test.py
    python e2e_video_test.py --base-url https://your-app.up.railway.app --email admin@example.com --password secret

Requirements:
    pip install requests
"""

import argparse
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests


def log(msg: str) -> None:
    print(f"[e2e] {msg}")


def login(session: requests.Session, base_url: str, email: str, password: str) -> str:
    """OAuth2 password flow."""
    url = f"{base_url}/auth/token"
    data = {"username": email, "password": password}
    log(f"POST {url} (login)")
    resp = session.post(url, data=data, timeout=30)
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("No access_token in login response")
    log("Login OK — token received")
    return token


def get_feed(session: requests.Session, base_url: str) -> list[dict]:
    url = f"{base_url}/feed"
    log(f"GET {url}")
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def list_modules(session: requests.Session, base_url: str) -> list[dict]:
    url = f"{base_url}/modules"
    log(f"GET {url}")
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_module_detail(session: requests.Session, base_url: str, module_id: str) -> dict:
    url = f"{base_url}/modules/{module_id}"
    log(f"GET {url}")
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_stream_url(session: requests.Session, base_url: str, episode_id: str) -> dict:
    url = f"{base_url}/episodes/{episode_id}/stream"
    log(f"GET {url}")
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def resolve_url(base: str, rel: str) -> str:
    """Resolve a relative URL against a base URL."""
    return urllib.parse.urljoin(base, rel)


def download_hls(manifest_url: str, out_path: Path, max_segments: int | None = None) -> None:
    """
    Naïve HLS downloader — handles master playlists and media playlists.
    Concatenates MPEG-TS segments into a single file.
    If you have ffmpeg installed you can instead run:
        ffmpeg -i "{manifest_url}" -c copy output.mp4
    """
    log(f"Downloading HLS stream → {out_path}")
    session = requests.Session()

    # 1. Fetch top-level manifest
    r = session.get(manifest_url, timeout=30)
    r.raise_for_status()
    manifest_text = r.text.strip()

    lines = [line.strip() for line in manifest_text.splitlines() if line.strip()]

    # If it's a master playlist, pick the first variant
    if any(line.startswith("#EXT-X-STREAM-INF") for line in lines):
        variant_url = None
        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
                variant_url = resolve_url(manifest_url, lines[i + 1])
                break
        if not variant_url:
            raise RuntimeError("Master playlist found but no variant URL")
        log(f"Resolved variant playlist: {variant_url}")
        r = session.get(variant_url, timeout=30)
        r.raise_for_status()
        manifest_text = r.text.strip()
        media_base = variant_url
    else:
        media_base = manifest_url

    # 2. Parse media playlist for segments
    segment_urls = []
    for line in manifest_text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            segment_urls.append(resolve_url(media_base, line))

    if not segment_urls:
        raise RuntimeError("No segments found in HLS media playlist")

    log(f"Found {len(segment_urls)} segment(s)")
    if max_segments:
        segment_urls = segment_urls[:max_segments]
        log(f"Limiting download to first {max_segments} segment(s)")

    # 3. Download & concatenate
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        for idx, seg_url in enumerate(segment_urls, 1):
            log(f"Downloading segment {idx}/{len(segment_urls)} ...")
            seg_resp = session.get(seg_url, timeout=60)
            seg_resp.raise_for_status()
            f.write(seg_resp.content)
            time.sleep(0.1)  # be polite

    log(f"Saved {out_path.stat().st_size} bytes to {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Champ LMS E2E Video Test")
    parser.add_argument("--base-url", default=os.getenv("CHAMP_BASE_URL", "https://valiant-acceptance-production-d205.up.railway.app"))
    parser.add_argument("--email", default=os.getenv("CHAMP_EMAIL", "deep@championsmail.com"))
    parser.add_argument("--password", default=os.getenv("CHAMP_PASSWORD", ""))
    parser.add_argument("--output", default="./e2e_download.ts", help="Output file path")
    parser.add_argument("--max-segments", type=int, default=None, help="Limit segments for quick test")
    args = parser.parse_args()

    if not args.password:
        log("ERROR: No password provided. Use --password or set CHAMP_PASSWORD")
        return 1

    base_url = args.base_url.rstrip("/")
    out_path = Path(args.output)

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    # ── 1. LOGIN ──────────────────────────────────────────────────────────────
    try:
        token = login(session, base_url, args.email, args.password)
    except requests.HTTPError as e:
        log(f"Login failed: {e.response.status_code} — {e.response.text}")
        return 1
    session.headers.update({"Authorization": f"Bearer {token}"})

    # ── 2. DISCOVER CONTENT ───────────────────────────────────────────────────
    # Try feed first; fallback to flat module list
    modules = []
    try:
        feed = get_feed(session, base_url)
        for row in feed:
            modules.extend(row.get("modules", []))
    except requests.HTTPError:
        log("Feed failed, falling back to /modules list")
        modules = list_modules(session, base_url)

    if not modules:
        log("No published modules found")
        return 1

    log(f"Discovered {len(modules)} module(s)")

    # ── 3. FIND FIRST READY EPISODE ───────────────────────────────────────────
    target_episode = None
    target_module = None
    for mod in modules:
        detail = get_module_detail(session, base_url, mod["id"])
        for ep in detail.get("episodes", []):
            if ep.get("status") == "ready":
                target_episode = ep
                target_module = detail
                break
        if target_episode:
            break

    if not target_episode:
        log("No ready episodes found in any module")
        return 1

    log(f"Selected episode: '{target_episode['title']}' (id={target_episode['id']}) "
        f"in module '{target_module['title']}'")

    # ── 4. GET STREAM URL ─────────────────────────────────────────────────────
    try:
        stream_info = get_stream_url(session, base_url, target_episode["id"])
    except requests.HTTPError as e:
        if e.response.status_code == 425:
            log("Episode stream returned 425 — video is still processing")
        else:
            log(f"Stream URL request failed: {e.response.status_code} — {e.response.text}")
        return 1

    stream_url = stream_info.get("stream_url")
    embed_url = stream_info.get("embed_url")
    log(f"stream_url : {stream_url}")
    log(f"embed_url  : {embed_url}")

    # ── 5. VERIFY MANIFEST REACHABLE ──────────────────────────────────────────
    head = session.head(stream_url, timeout=30, allow_redirects=True)
    log(f"Manifest HEAD status: {head.status_code}")
    if head.status_code not in (200, 405):  # 405 = HEAD not allowed (sometimes on CDNs)
        get_check = session.get(stream_url, timeout=30, stream=True)
        log(f"Manifest GET status: {get_check.status_code}")
        if get_check.status_code != 200:
            log("ERROR: Manifest is not reachable")
            return 1
        get_check.close()

    # ── 6. DOWNLOAD VIDEO ─────────────────────────────────────────────────────
    try:
        download_hls(stream_url, out_path, max_segments=args.max_segments)
    except Exception as e:
        log(f"Download failed: {e}")
        return 1

    log("✅ E2E test passed — login → discover → stream URL → download all OK")
    log(f"   Output: {out_path.resolve()}")
    if args.max_segments:
        log("   (Partial download because --max-segments was set)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
