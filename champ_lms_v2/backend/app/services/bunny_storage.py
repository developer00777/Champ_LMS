"""
Bunny Storage service — replaces S3 for thumbnails and static assets.

Bunny Storage API:
  PUT  https://{host}/{zone}/{path}  — upload file
  GET  https://{host}/{zone}/{path}  — download file
  DELETE https://{host}/{zone}/{path} — delete file

Files served via Bunny CDN Pull Zone with Bunny Optimizer for image processing.
"""
import mimetypes
import httpx
from app.core.config import get_settings


class BunnyStorageService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _thumbs_headers(self, content_type: str = "application/octet-stream") -> dict:
        return {
            "AccessKey": self.settings.bunny_storage_thumbs_password,
            "Content-Type": content_type,
        }

    def _base_url(self, zone: str) -> str:
        return f"https://{self.settings.bunny_storage_host}/{zone}"

    async def upload_thumbnail(self, path: str, data: bytes, filename: str) -> str:
        """
        Upload thumbnail to Bunny Storage (thumbs zone).
        Returns the Bunny path (without zone prefix).
        Path example: 'modules/abc123/thumb.jpg'
        """
        content_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
        zone = self.settings.bunny_storage_thumbs_zone
        url = f"{self._base_url(zone)}/{path}"

        async with httpx.AsyncClient() as client:
            resp = await client.put(
                url,
                content=data,
                headers=self._thumbs_headers(content_type),
                timeout=60,
            )
            resp.raise_for_status()

        return path

    async def delete_thumbnail(self, path: str) -> None:
        zone = self.settings.bunny_storage_thumbs_zone
        url = f"{self._base_url(zone)}/{path}"
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                url,
                headers={"AccessKey": self.settings.bunny_storage_thumbs_password},
                timeout=30,
            )
            resp.raise_for_status()

    def cdn_url(self, path: str, width: int | None = None, height: int | None = None) -> str:
        """
        Build a CDN URL for a stored asset.
        Supports Bunny Optimizer params (?width=&height=&format=webp).
        """
        cdn_host = self.settings.bunny_cdn_hostname
        base = f"https://{cdn_host}/{path}"
        params = []
        if width:
            params.append(f"width={width}")
        if height:
            params.append(f"height={height}")
        # Always request WebP via Bunny Optimizer
        params.append("format=webp")
        if params:
            base += "?" + "&".join(params)
        return base

    def thumbnail_url(self, bunny_path: str, width: int = 480, height: int = 270) -> str:
        """Convenience: CDN URL optimised for 16:9 video card thumbnail."""
        return self.cdn_url(bunny_path, width=width, height=height)

    async def upload_frontend_build(self, file_map: dict[str, tuple[bytes, str]]) -> None:
        """
        Upload a SvelteKit static build to the frontend storage zone.
        file_map: {relative_path: (file_bytes, content_type)}
        """
        zone = self.settings.bunny_storage_frontend_zone
        async with httpx.AsyncClient() as client:
            for rel_path, (data, ct) in file_map.items():
                url = f"{self._base_url(zone)}/{rel_path}"
                resp = await client.put(
                    url,
                    content=data,
                    headers={
                        "AccessKey": self.settings.bunny_storage_frontend_password,
                        "Content-Type": ct,
                    },
                    timeout=60,
                )
                resp.raise_for_status()


bunny_storage = BunnyStorageService()
