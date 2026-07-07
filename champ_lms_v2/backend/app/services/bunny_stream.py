"""
Bunny Stream service — replaces AWS MediaConvert + CloudFront video CDN.

Bunny Stream handles:
  - Video upload (create video object → upload binary)
  - Auto-transcoding to 360p / 720p / 1080p HLS
  - Token-authenticated HLS playback URLs
  - Webhook on encode completion → POST /webhooks/bunny-stream
"""
import hashlib
import hmac
import time
from typing import AsyncIterator
from urllib.parse import quote
import httpx
from app.core.config import get_settings

BUNNY_STREAM_BASE = "https://video.bunnycdn.com"


def _chunked_reader(file_iterator: AsyncIterator[bytes], chunk_size: int = 8192) -> AsyncIterator[bytes]:
    """Async generator that yields chunks from a file iterator."""
    return file_iterator


class BunnyStreamService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def _headers(self) -> dict:
        return {
            "AccessKey": self.settings.bunny_stream_api_key,
            "Content-Type": "application/json",
        }

    @property
    def _library_id(self) -> str:
        return self.settings.bunny_stream_library_id

    async def create_video(self, title: str, collection_id: str | None = None) -> dict:
        """
        Create a video object in the Bunny Stream library.
        Returns JSON with 'guid' (video ID) and 'uploadUrl'.
        """
        payload: dict = {"title": title}
        if collection_id:
            payload["collectionId"] = collection_id

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BUNNY_STREAM_BASE}/library/{self._library_id}/videos",
                headers=self._headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def upload_video_bytes(self, video_guid: str, data: bytes) -> None:
        """
        Upload raw video bytes to a Bunny Stream video object.
        After this call, Bunny automatically starts transcoding.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{BUNNY_STREAM_BASE}/library/{self._library_id}/videos/{video_guid}",
                headers={
                    "AccessKey": self.settings.bunny_stream_api_key,
                    "Content-Type": "application/octet-stream",
                },
                content=data,
                timeout=600,  # large uploads need long timeout
            )
            resp.raise_for_status()

    async def upload_video_stream(
        self,
        video_guid: str,
        file_iterator: AsyncIterator[bytes],
        total_size: int | None = None,
        chunk_size: int = 65536,
    ) -> None:
        """
        Stream upload video chunks to Bunny Stream — much faster for large files
        and uses constant memory instead of loading the entire file.

        Args:
            video_guid: Bunny Stream video GUID
            file_iterator: Async iterator yielding byte chunks
            total_size: Total file size in bytes (for Content-Length header)
            chunk_size: Size of each chunk to read
        """
        import logging
        logger = logging.getLogger(__name__)

        headers = {
            "AccessKey": self.settings.bunny_stream_api_key,
            "Content-Type": "application/octet-stream",
        }
        if total_size:
            headers["Content-Length"] = str(total_size)

        url = f"{BUNNY_STREAM_BASE}/library/{self._library_id}/videos/{video_guid}"

        async def stream_chunks() -> AsyncIterator[bytes]:
            bytes_uploaded = 0
            async for chunk in file_iterator:
                bytes_uploaded += len(chunk)
                if bytes_uploaded % (1024 * 1024) < chunk_size:  # Log every ~1MB
                    logger.info(f"Uploading {video_guid}: {bytes_uploaded / 1024 / 1024:.1f} MB...")
                yield chunk
            logger.info(f"Upload complete: {bytes_uploaded / 1024 / 1024:.1f} MB")

        async with httpx.AsyncClient() as client:
            resp = await client.put(
                url,
                headers=headers,
                content=stream_chunks(),
                timeout=600,
            )
            resp.raise_for_status()

    async def upload_video_from_url(self, video_guid: str, url: str) -> dict:
        """
        Tell Bunny Stream to fetch a video from an external URL (e.g. Zoom recording URL).
        Bunny pulls it directly — no bytes routed through our server.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BUNNY_STREAM_BASE}/library/{self._library_id}/videos/{video_guid}/fetch",
                headers=self._headers,
                json={"url": url},
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json()

    async def get_video(self, video_guid: str) -> dict:
        """Get video metadata including status, duration, thumbnailFileName."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BUNNY_STREAM_BASE}/library/{self._library_id}/videos/{video_guid}",
                headers=self._headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_video(self, video_guid: str) -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{BUNNY_STREAM_BASE}/library/{self._library_id}/videos/{video_guid}",
                headers=self._headers,
                timeout=30,
            )
            resp.raise_for_status()

    async def list_collections(self) -> list[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BUNNY_STREAM_BASE}/library/{self._library_id}/collections",
                headers=self._headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("items", [])

    async def create_collection(self, name: str) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BUNNY_STREAM_BASE}/library/{self._library_id}/collections",
                headers=self._headers,
                json={"name": name},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()

    def get_hls_url(self, video_guid: str) -> str:
        """
        Return the plain (no token) HLS manifest URL.
        Only use this if token auth is disabled on the library.
        """
        cdn_host = self.settings.bunny_stream_cdn_hostname
        return f"https://{cdn_host}/{video_guid}/playlist.m3u8"

    def get_token_auth_url(self, video_guid: str, expires_in_seconds: int = 14400) -> str:
        """
        Generate a Bunny Stream token-authenticated HLS URL.
        Token auth must be enabled on the Stream library in Bunny dashboard.

        Formula (from Bunny docs):
          token = SHA256(token_secret + video_path + expires)
          URL   = https://{cdn_host}/{video_guid}/playlist.m3u8
                    ?token={token}&expires={expires}
        """
        secret = self.settings.bunny_stream_token_secret
        cdn_host = self.settings.bunny_stream_cdn_hostname
        expires = int(time.time()) + expires_in_seconds
        path = f"/{video_guid}/playlist.m3u8"

        token_raw = secret + path + str(expires)
        token = hashlib.sha256(token_raw.encode()).hexdigest()

        return f"https://{cdn_host}{path}?token={token}&expires={expires}"

    def get_embed_url(self, video_guid: str) -> str:
        """Bunny Stream built-in embed player URL (iframe-embeddable)."""
        return f"https://iframe.mediadelivery.net/embed/{self._library_id}/{video_guid}"

    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        """
        Verify Bunny Stream webhook authenticity.

        Bunny Stream does NOT send a configurable HMAC secret — it sends the
        library's API key in the header 'AccessKey'. We compare that against
        the known API key instead of doing HMAC.

        If BUNNY_STREAM_WEBHOOK_SECRET is set (to the library API key), we
        compare it directly. If empty, we skip verification (dev/local mode).
        """
        secret = self.settings.bunny_stream_webhook_secret
        if not secret:
            return True  # dev mode — skip verification
        return hmac.compare_digest(secret, signature_header)


bunny_stream = BunnyStreamService()
