#!/usr/bin/env python3
"""
Bunny Stream Diagnostic Script

Tests:
1. API connectivity (create/list videos)
2. Stream URL generation
3. Whether a specific video is playable

Usage:
    python bunny_diagnostic.py --guid YOUR_VIDEO_GUID
    python bunny_diagnostic.py --episode-id YOUR_EPISODE_ID --base-url https://your-app.up.railway.app --token YOUR_JWT
"""

import argparse
import asyncio
import hashlib
import os
import sys

import httpx


BUNNY_STREAM_BASE = "https://video.bunnycdn.com"


def log(msg: str) -> None:
    print(f"[diag] {msg}")


def error(msg: str) -> None:
    print(f"[diag] ❌ ERROR: {msg}")


def ok(msg: str) -> None:
    print(f"[diag] ✅ {msg}")


def warn(msg: str) -> None:
    print(f"[diag] ⚠️  {msg}")


class BunnyDiagnostic:
    def __init__(self, api_key: str, library_id: str, token_secret: str = "", cdn_hostname: str = ""):
        self.api_key = api_key
        self.library_id = library_id
        self.token_secret = token_secret
        self.cdn_hostname = cdn_hostname or f"{library_id}.mediadelivery.net"

    @property
    def _headers(self) -> dict:
        return {"AccessKey": self.api_key, "Content-Type": "application/json"}

    async def test_api_connection(self) -> bool:
        """Test if we can connect to Bunny Stream API."""
        log("Testing Bunny Stream API connection...")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{BUNNY_STREAM_BASE}/library/{self.library_id}/videos",
                    headers=self._headers,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                total_items = data.get("totalItems", 0)
                ok(f"API connection OK — library has {total_items} video(s)")
                return True
        except httpx.HTTPStatusError as e:
            error(f"API returned {e.response.status_code}: {e.response.text}")
            return False
        except Exception as e:
            error(f"API connection failed: {e}")
            return False

    async def get_video_info(self, video_guid: str) -> dict | None:
        """Get video metadata from Bunny Stream."""
        log(f"Fetching video info for {video_guid}...")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{BUNNY_STREAM_BASE}/library/{self.library_id}/videos/{video_guid}",
                    headers=self._headers,
                    timeout=10,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                error(f"Video {video_guid} not found in Bunny Stream library")
            else:
                error(f"API error: {e.response.status_code} — {e.response.text}")
            return None
        except Exception as e:
            error(f"Failed to fetch video: {e}")
            return None

    def generate_stream_url(self, video_guid: str) -> str:
        """Generate token-authenticated HLS URL."""
        if not self.token_secret:
            raise RuntimeError("TOKEN_SECRET not set — cannot generate authenticated URL")
        
        import time
        expires = int(time.time()) + 14400
        path = f"/{video_guid}/playlist.m3u8"
        token_raw = self.token_secret + path + str(expires)
        token = hashlib.sha256(token_raw.encode()).hexdigest()
        return f"https://{self.cdn_hostname}{path}?token={token}&expires={expires}"

    async def test_stream_url(self, video_guid: str) -> bool:
        """Test if the generated stream URL is reachable."""
        log(f"Testing stream URL for {video_guid}...")
        try:
            url = self.generate_stream_url(video_guid)
            log(f"Generated URL: {url[:80]}...")
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=15, follow_redirects=True)
                if resp.status_code == 200:
                    content_type = resp.headers.get("content-type", "")
                    if "mpegurl" in content_type or resp.text.startswith("#EXTM3U"):
                        ok("Stream URL is valid and returns HLS manifest")
                        return True
                    else:
                        warn(f"Stream URL returned 200 but content-type is {content_type}")
                        return False
                else:
                    error(f"Stream URL returned {resp.status_code}: {resp.text[:200]}")
                    return False
        except Exception as e:
            error(f"Stream URL test failed: {e}")
            return False

    async def diagnose_video(self, video_guid: str) -> dict:
        """Run full diagnostic on a video."""
        print(f"\n{'='*60}")
        print(f"DIAGNOSTIC: Video {video_guid}")
        print(f"{'='*60}")

        info = await self.get_video_info(video_guid)
        if not info:
            return {"playable": False, "reason": "Video not found in Bunny Stream"}

        # Print video status
        status = info.get("status")
        status_names = {0: "Created", 1: "Uploaded", 2: "Processing", 3: "Transcoding", 4: "Finished", 5: "Error", 6: "UploadFailed"}
        status_name = status_names.get(status, f"Unknown ({status})")
        log(f"Bunny status: {status_name} (code {status})")
        log(f"Duration: {info.get('length', 'N/A')} seconds")
        log(f"Thumbnail: {info.get('thumbnailFileName', 'N/A')}")

        if status != 4:
            error(f"Video is not ready (status {status} != 4)")
            return {"playable": False, "reason": f"Video not ready: {status_name}"}

        # Test stream URL
        stream_ok = await self.test_stream_url(video_guid)
        
        # Also test embed URL
        embed_url = f"https://iframe.mediadelivery.net/embed/{self.library_id}/{video_guid}"
        log(f"Embed URL: {embed_url}")

        return {
            "playable": stream_ok,
            "info": info,
            "stream_url": self.generate_stream_url(video_guid) if self.token_secret else None,
            "embed_url": embed_url,
        }


async def diagnose_from_app(base_url: str, token: str, episode_id: str) -> None:
    """Test the app's /episodes/{id}/stream endpoint."""
    log(f"Testing app endpoint: {base_url}/episodes/{episode_id}/stream")
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{base_url}/episodes/{episode_id}/stream",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        
        log(f"App returned: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            log(f"stream_url: {data.get('stream_url', 'N/A')[:80]}...")
            log(f"embed_url: {data.get('embed_url', 'N/A')}")
            log(f"expires_in: {data.get('expires_in', 'N/A')}")
            
            # Test if stream_url is reachable
            stream_url = data.get("stream_url")
            if stream_url:
                r = await client.get(stream_url, timeout=15, follow_redirects=True)
                if r.status_code == 200 and ("mpegurl" in r.headers.get("content-type", "") or r.text.startswith("#EXTM3U")):
                    ok("Stream URL from app is VALID and playable!")
                else:
                    error(f"Stream URL from app is NOT playable: {r.status_code}")
                    log(f"Response: {r.text[:200]}")
        elif resp.status_code == 425:
            error("Video is still processing (status 425)")
        elif resp.status_code == 404:
            error("Episode not found (404)")
        else:
            error(f"Unexpected response: {resp.status_code} — {resp.text[:300]}")


async def main():
    parser = argparse.ArgumentParser(description="Bunny Stream Diagnostic")
    parser.add_argument("--api-key", default=os.getenv("BUNNY_STREAM_API_KEY"))
    parser.add_argument("--library-id", default=os.getenv("BUNNY_STREAM_LIBRARY_ID"))
    parser.add_argument("--token-secret", default=os.getenv("BUNNY_STREAM_TOKEN_SECRET"))
    parser.add_argument("--cdn-hostname", default=os.getenv("BUNNY_STREAM_CDN_HOSTNAME", ""))
    parser.add_argument("--guid", help="Bunny Stream video GUID to diagnose")
    parser.add_argument("--episode-id", help="App episode ID to test")
    parser.add_argument("--base-url", default="https://valiant-acceptance-production-d205.up.railway.app")
    parser.add_argument("--token", default=os.getenv("CHAMP_TOKEN"), help="JWT token for app API")
    args = parser.parse_args()

    if not args.api_key or not args.library_id:
        print("ERROR: Set --api-key and --library-id (or env vars BUNNY_STREAM_API_KEY, BUNNY_STREAM_LIBRARY_ID)")
        sys.exit(1)

    diag = BunnyDiagnostic(
        api_key=args.api_key,
        library_id=args.library_id,
        token_secret=args.token_secret,
        cdn_hostname=args.cdn_hostname,
    )

    # Test API connection
    api_ok = await diag.test_api_connection()
    if not api_ok:
        sys.exit(1)

    # Diagnose specific video if provided
    if args.guid:
        result = await diag.diagnose_video(args.guid)
        if result["playable"]:
            ok("\n✅ Video is FULLY PLAYABLE")
        else:
            error(f"\n❌ Video is NOT playable: {result['reason']}")

    # Test app endpoint if provided
    if args.episode_id and args.token:
        await diagnose_from_app(args.base_url, args.token, args.episode_id)


if __name__ == "__main__":
    asyncio.run(main())
