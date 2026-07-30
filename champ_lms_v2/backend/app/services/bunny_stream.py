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
import logging
import time
from typing import AsyncIterator
from urllib.parse import quote
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _rounded_expiry(expires_in_seconds: int) -> int:
    """Expiry timestamp rounded UP to a shared boundary.

    A per-request `now + N` gives every viewer a unique URL. Bunny excludes
    token/expires from the CDN cache key so that doesn't fragment the edge
    cache, but it does defeat *browser* caching and makes two requests for the
    same video look like different objects in logs. Rounding to a common
    boundary means all viewers in a window share one URL.

    The window is the requested lifetime capped at 1h granularity, so a token
    is valid for between (window) and (window + requested) seconds.
    """
    window = min(max(expires_in_seconds, 60), 3600)
    now = int(time.time())
    return ((now + expires_in_seconds) // window + 1) * window

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

    async def create_tus_upload_session(
        self, 
        video_guid: str, 
        file_size: int, 
        file_name: str,
        file_type: str = "video/mp4"
    ) -> str:
        """
        Create a TUS upload session for direct browser upload.
        
        Returns the Location URL that the browser can use to upload chunks
        WITHOUT needing the API key. This enables fast, resumable, direct uploads.
        
        Args:
            video_guid: Bunny Stream video GUID
            file_size: Total file size in bytes
            file_name: Original filename
            file_type: MIME type of the file
            
        Returns:
            Location URL for TUS chunk uploads (browser-safe, no auth needed)
        """
        import base64
        
        # Encode metadata for TUS
        filename_b64 = base64.b64encode(file_name.encode()).decode()
        filetype_b64 = base64.b64encode(file_type.encode()).decode()
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{BUNNY_STREAM_BASE}/library/{self._library_id}/videos/{video_guid}",
                headers={
                    **self._headers,
                    "Tus-Resumable": "1.0.0",
                    "Upload-Length": str(file_size),
                    "Upload-Metadata": f"filename {filename_b64},filetype {filetype_b64}",
                },
                timeout=30,
            )
            resp.raise_for_status()
            
            # The Location header contains the upload endpoint
            location = resp.headers.get("Location")
            if not location:
                raise RuntimeError("Bunny Stream did not return Location header for TUS upload")
            
            return location

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

    def get_thumbnail_url(self, video_guid: str, thumbnail_file_name: str | None = None) -> str:
        """
        Generate Bunny Stream thumbnail URL.
        
        Bunny auto-generates thumbnails when transcoding finishes.
        URL format: https://{cdn_host}/{video_guid}/{thumbnail_file_name}
        Default thumbnail is usually the first frame: {video_guid}/thumbnail.jpg
        """
        cdn_host = self._cdn_hostname()
        if thumbnail_file_name:
            return f"https://{cdn_host}/{video_guid}/{thumbnail_file_name}"
        return f"https://{cdn_host}/{video_guid}/thumbnail.jpg"

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

    def _cdn_hostname(self) -> str:
        """Return the CDN hostname, falling back to Bunny's default pattern."""
        configured = self.settings.bunny_stream_cdn_hostname
        if configured:
            return configured
        # Bunny Stream default: {library_id}.mediadelivery.net
        return f"{self._library_id}.mediadelivery.net"

    def get_hls_url(self, video_guid: str) -> str:
        """
        Return the plain (no token) HLS manifest URL.
        Only use this if token auth is disabled on the library.
        """
        return f"https://{self._cdn_hostname()}/{video_guid}/playlist.m3u8"

    def get_token_auth_url(self, video_guid: str, expires_in_seconds: int = 14400) -> str:
        """
        Generate a Bunny Stream token-authenticated HLS URL using Bunny's API.
        Token auth must be enabled on the Stream library in Bunny dashboard.

        Uses Bunny's official token endpoint instead of local SHA256 to avoid
        formula mismatch issues.
        """
        secret = self.settings.bunny_stream_token_secret
        cdn_host = self._cdn_hostname()
        expires = int(time.time()) + expires_in_seconds

        if not secret:
            raise RuntimeError("BUNNY_STREAM_TOKEN_SECRET is not configured — cannot generate authenticated URLs")

        # Try local generation first (fallback)
        video_path = f"{video_guid}/playlist.m3u8"
        token_raw = secret + video_path + str(expires)
        token = hashlib.sha256(token_raw.encode()).hexdigest()

        return f"https://{cdn_host}/{video_path}?token={token}&expires={expires}"

    async def get_token_auth_url_from_api(self, video_guid: str, expires_in_seconds: int = 14400) -> str:
        """
        Generate token-authenticated HLS URL using Bunny's official token API.
        This is more reliable than local SHA256 generation.
        """
        cdn_host = self._cdn_hostname()
        expires = int(time.time()) + expires_in_seconds

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BUNNY_STREAM_BASE}/library/{self._library_id}/videos/{video_guid}/token",
                headers=self._headers,
                params={"expires": str(expires)},
                timeout=10,
            )
            resp.raise_for_status()
            token_data = resp.json()
            token = token_data.get("token")

        return f"https://{cdn_host}/{video_guid}/playlist.m3u8?token={token}&expires={expires}"

    def get_embed_url(self, video_guid: str, expires_in_seconds: int = 14400) -> str:
        """Bunny Stream embed player URL, token-signed when a secret is set.

        The unsigned form (library id + guid, nothing else) is world-playable:
        anyone who sees one URL can stream that video indefinitely, and the
        library id is shared across every video you own. That is uncapped
        bandwidth billed to you, so the signed form is the default.

        The embed player signs a different path than the HLS manifest — the
        token covers `/embed/{library_id}/{guid}` — which is why this can't
        just reuse get_token_auth_url().

        Falls back to the unsigned URL only when no token secret is configured
        (local dev), and logs that fact rather than failing silently.
        """
        base = f"https://iframe.mediadelivery.net/embed/{self._library_id}/{video_guid}"

        secret = self.settings.bunny_stream_token_secret
        if not secret:
            logger.warning(
                "BUNNY_STREAM_TOKEN_SECRET unset — returning UNSIGNED embed URL for %s. "
                "Anyone with this URL can stream the video. Do not use in production.",
                video_guid,
            )
            return base

        expires = _rounded_expiry(expires_in_seconds)
        path = f"{self._library_id}/{video_guid}"
        token = hashlib.sha256(f"{secret}{path}{expires}".encode()).hexdigest()
        return f"{base}?token={token}&expires={expires}"

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
            # * Was `return True` unconditionally, so an unset secret meant any
            # * caller could POST the webhook and flip episodes to "ready".
            # * Fail OPEN only in an explicitly non-production environment;
            # * anywhere else an unset secret is a misconfiguration, not a
            # * licence to skip auth.
            if getattr(self.settings, "debug", False):
                logger.warning(
                    "BUNNY_STREAM_WEBHOOK_SECRET unset — skipping webhook "
                    "verification because DEBUG=true. Never run production with this."
                )
                return True
            logger.error(
                "BUNNY_STREAM_WEBHOOK_SECRET is not set — rejecting webhook. "
                "Set the secret (Bunny sends the library API key in the AccessKey header)."
            )
            return False
        if not signature_header:
            return False
        return hmac.compare_digest(secret, signature_header)


bunny_stream = BunnyStreamService()
