"""
Bunny Storage service — replaces S3 for thumbnails and static assets.

Bunny Storage API:
  PUT  https://{host}/{zone}/{path}  — upload file
  GET  https://{host}/{zone}/{path}  — download file
  DELETE https://{host}/{zone}/{path} — delete file

Files are served through the Bunny CDN pull zone as plain, already-correct
objects.

* COST NOTE — Bunny Optimizer is deliberately NOT used.
* Optimizer bills per request served with transform params (?width=&format=…),
* and these URLs appear in nav bars, leaderboards, kudos feeds and every
* module card, so it was charging on effectively every page view — it reached
* $8.10/mo against <$0.01 for CDN + Storage combined.
* The transforms it performed are one-time, deterministic and cheap to do
* ourselves: `optimize_image()` resizes and re-encodes to WebP once, at upload
* time, so what lands in Storage is already the exact byte payload the browser
* should receive. Serving it needs no query params at all, which means plain
* CDN egress (fractions of a cent) and a far better edge cache hit rate.
* Do not reintroduce width/height/format/quality params on these URLs.
"""
import io
import mimetypes
import httpx
from PIL import Image, ImageOps
from app.core.config import get_settings

# Target dimensions, applied at upload time. Each is a bounding box: the image
# is fitted inside it preserving aspect ratio, never upscaled.
AVATAR_BOX = (200, 200)      # nav, leaderboard rows, kudos feed
THUMBNAIL_BOX = (480, 270)   # 16:9 module/episode cards
WEBP_QUALITY = 82            # visually lossless for photos at these sizes


def optimize_image(
    data: bytes,
    box: tuple[int, int],
    quality: int = WEBP_QUALITY,
) -> tuple[bytes, str]:
    """
    Resize and re-encode an uploaded image once, at upload time.

    Returns (encoded_bytes, file_extension). Replaces what Bunny Optimizer
    used to do per-request — see the COST NOTE at the top of this module.

    Animated GIFs are passed through untouched: flattening one to a still WebP
    here would silently destroy the upload, and they are rare enough that the
    saved bytes aren't worth that.
    """
    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").lower()
        # `n_frames` is what actually forces Pillow to read frame count;
        # `is_animated` alone is unset on a freshly-opened image.
        if getattr(img, "n_frames", 1) > 1:
            return data, f".{fmt or 'gif'}"

        # EXIF orientation must be applied before resizing, otherwise a phone
        # photo lands rotated with no metadata left to correct it.
        img = ImageOps.exif_transpose(img)
        # WebP has no CMYK/palette encoder; RGBA is kept so PNG cut-outs stay
        # transparent.
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "A" in img.mode else "RGB")

        img.thumbnail(box, Image.Resampling.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="WEBP", quality=quality, method=6)
        return out.getvalue(), ".webp"
    except Exception:  # noqa: BLE001
        # A file Pillow can't decode is still a file the admin chose to upload.
        # Store it as-is rather than failing the request; it just won't be
        # shrunk.
        return data, ""


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

    async def upload_optimized(
        self,
        path_prefix: str,
        data: bytes,
        box: tuple[int, int],
    ) -> str:
        """
        Resize/re-encode then upload, returning the final Bunny path.

        `path_prefix` carries no extension — this picks it, since the encode
        decides the format (usually `.webp`).
        """
        encoded, ext = optimize_image(data, box)
        path = f"{path_prefix}{ext}"
        return await self.upload_thumbnail(path, encoded, path.rsplit("/", 1)[-1])

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

    def avatar_url(self, path: str | None) -> str | None:
        """CDN URL for a profile picture, or None when none is set."""
        if not path:
            return None
        return self.cdn_url(path)

    def cdn_url(self, path: str, width: int | None = None, height: int | None = None) -> str:
        """
        Build a plain CDN URL for a stored asset.

        `width`/`height` are accepted and ignored, kept only so existing
        callers don't break. Sizing happens at upload time instead — emitting
        them here would re-enable per-request Optimizer billing (see the module
        COST NOTE).
        """
        cdn_host = self.settings.bunny_cdn_hostname
        return f"https://{cdn_host}/{path}"

    def thumbnail_url(self, bunny_path: str, width: int = 480, height: int = 270) -> str:
        """CDN URL for a video card thumbnail (already 16:9-sized in storage)."""
        return self.cdn_url(bunny_path)


bunny_storage = BunnyStorageService()
