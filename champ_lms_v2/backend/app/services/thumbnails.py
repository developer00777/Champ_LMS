"""
Course and episode thumbnails: which image to show, and storing new ones.

Three generations of thumbnail can exist on a row, and the newest kind wins:

  1. thumbnail_id        — made in the thumbnail studio, stored in MongoDB
  2. thumbnail_bunny_path — uploaded by an admin to Bunny Storage (legacy)
  3. thumbnail_url        — the frame Bunny Stream picked (episodes only)

Anything an admin chose beats a frame Bunny picked on its own.
"""
from __future__ import annotations

import io
import logging

from beanie.operators import In
from PIL import Image, ImageOps

from app.models.episode import Episode
from app.models.module import Module
from app.models.thumbnail import OWNER_EPISODE, OWNER_MODULE, Thumbnail
from app.services.bunny_storage import bunny_storage

logger = logging.getLogger(__name__)

# 16:9, large enough for the home page hero banner, small enough as WebP
# (about 50-200 KB) to keep in Mongo and send to every card.
THUMB_SIZE = (1280, 720)
WEBP_QUALITY = 84
MAX_INPUT_BYTES = 12 * 1024 * 1024

# The frontend reaches the API under /api in every deployment (the SvelteKit
# server and the Vite dev server both proxy it; VITE_API_URL is /api). The URL
# goes straight into <img src> and CSS, which cannot send a bearer token, so
# the image route is public and relies on unguessable ids.
PUBLIC_PREFIX = "/api/thumbnails"


class ThumbnailError(ValueError):
    """The image could not be used, with a message safe to show an admin."""


def encode_thumbnail(data: bytes) -> bytes:
    """
    Fit any image to a 1280x720 WebP, cropping from the centre.

    Cards, the hero banner and the course header are all 16:9, so cropping
    once here means every place shows the same framing the studio previewed.
    """
    if not data:
        raise ThumbnailError("The image is empty")
    if len(data) > MAX_INPUT_BYTES:
        raise ThumbnailError("Images can be up to 12 MB")
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            # Flatten transparency onto the app's near-black background
            # instead of letting WebP keep an alpha channel cards don't expect.
            rgba = img.convert("RGBA")
            bg = Image.new("RGB", rgba.size, (10, 10, 15))
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        img = ImageOps.fit(img, THUMB_SIZE, Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        out = io.BytesIO()
        img.save(out, format="WEBP", quality=WEBP_QUALITY, method=6)
        return out.getvalue()
    except ThumbnailError:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow raises many kinds
        raise ThumbnailError("That file isn't an image we can read. Try a PNG, JPEG or WebP.") from exc


def public_url(thumbnail_id: str) -> str:
    return f"{PUBLIC_PREFIX}/{thumbnail_id}"


def module_thumbnail_url(m: Module | None) -> str | None:
    if not m:
        return None
    if m.thumbnail_id:
        return public_url(m.thumbnail_id)
    if m.thumbnail_bunny_path:
        return bunny_storage.thumbnail_url(m.thumbnail_bunny_path)
    return None


def episode_thumbnail_url(ep: Episode | None) -> str | None:
    if not ep:
        return None
    if ep.thumbnail_id:
        return public_url(ep.thumbnail_id)
    if ep.thumbnail_bunny_path:
        return bunny_storage.thumbnail_url(ep.thumbnail_bunny_path)
    return ep.thumbnail_url


def thumbnail_has_text(owner: Module | Episode | None) -> bool:
    """True when the image shown is a text design, which carries the title itself."""
    return bool(owner and owner.thumbnail_id and owner.thumbnail_source == "text")


def thumbnail_view(owner: Module | Episode) -> dict:
    """The thumbnail fields the studio needs to show and reopen a design."""
    url = module_thumbnail_url(owner) if isinstance(owner, Module) else episode_thumbnail_url(owner)
    return {
        "thumbnail_url": url,
        "thumbnail_source": owner.thumbnail_source if owner.thumbnail_id else None,
        "thumbnail_design": owner.thumbnail_design if owner.thumbnail_id else None,
    }


async def set_thumbnail(
    owner: Module | Episode, data: bytes, source: str, design: dict | None,
) -> None:
    """Store a new image for this course or episode, replacing its old one."""
    encoded = encode_thumbnail(data)
    kind = OWNER_MODULE if isinstance(owner, Module) else OWNER_EPISODE
    thumb = Thumbnail(owner_kind=kind, owner_id=owner.id, data=encoded, source=source)
    await thumb.insert()
    previous = owner.thumbnail_id
    owner.thumbnail_id = thumb.id
    owner.thumbnail_source = source
    owner.thumbnail_design = design if source == "text" else None
    await owner.save()
    if previous:
        await Thumbnail.find(Thumbnail.id == previous).delete()


async def clear_thumbnail(owner: Module | Episode) -> None:
    """Drop the studio image; any older Bunny thumbnail shows again."""
    previous = owner.thumbnail_id
    owner.thumbnail_id = owner.thumbnail_source = owner.thumbnail_design = None
    await owner.save()
    if previous:
        await Thumbnail.find(Thumbnail.id == previous).delete()


async def delete_thumbnails(owner_kind: str, owner_ids: list[str]) -> None:
    """For purges: remove every stored image belonging to these rows."""
    if owner_ids:
        await Thumbnail.find(
            Thumbnail.owner_kind == owner_kind, In(Thumbnail.owner_id, owner_ids)
        ).delete()
