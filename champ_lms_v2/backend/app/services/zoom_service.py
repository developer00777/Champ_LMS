"""
Zoom service — OAuth token management and recording download.
Replaces nothing (same as v1); recording is now uploaded to Bunny Stream
instead of S3.
"""
import base64
import httpx
from app.core.config import get_settings

ZOOM_API_BASE = "https://api.zoom.us/v2"
ZOOM_OAUTH_URL = "https://zoom.us/oauth/token"


class ZoomService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._access_token: str | None = None

    async def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        credentials = base64.b64encode(
            f"{self.settings.zoom_client_id}:{self.settings.zoom_client_secret}".encode()
        ).decode()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                ZOOM_OAUTH_URL,
                params={
                    "grant_type": "account_credentials",
                    "account_id": self.settings.zoom_account_id,
                },
                headers={"Authorization": f"Basic {credentials}"},
            )
            resp.raise_for_status()
            self._access_token = resp.json()["access_token"]
            return self._access_token

    async def get_recording(self, meeting_id: str) -> dict:
        token = await self._get_access_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{ZOOM_API_BASE}/meetings/{meeting_id}/recordings",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def download_recording_bytes(self, download_url: str) -> bytes:
        """Download a Zoom recording as bytes for upload to Bunny Stream."""
        token = await self._get_access_token()
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                download_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=300,
            )
            resp.raise_for_status()
            return resp.content

    def verify_webhook(self, payload: bytes, signature: str, timestamp: str) -> bool:
        import hmac
        import hashlib
        message = f"v0:{timestamp}:{payload.decode()}"
        expected = "v0=" + hmac.new(
            self.settings.zoom_webhook_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


zoom_service = ZoomService()
