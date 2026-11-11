"""
Shorts router: short videos in a swipeable, YouTube Shorts style feed.

Admin
  GET    /admin/shorts                      every short, with views and likes
  POST   /admin/shorts                      create one (metadata the browser read from the file)
  PATCH  /admin/shorts/{id}                 edit title, course link, fit, publish
  POST   /admin/shorts/{id}/prepare-upload  resumable upload session, browser -> Bunny
  POST   /admin/shorts/{id}/upload          server relay, when the direct upload is blocked
  POST   /admin/shorts/{id}/poster          the poster frame the browser captured (Mongo)
  GET    /admin/shorts/{id}/status          ask Bunny whether encoding finished
  DELETE /admin/shorts/{id}?confirm={id}    delete it, and its video on Bunny

Learner
  GET    /shorts                            the feed: ?start= first, then unseen, then seen
  GET    /shorts/{id}                       one short (a shared link)
  GET    /shorts/{id}/stream                its HLS URL
  POST   /shorts/{id}/like                  like or unlike
  POST   /shorts/{id}/view                  how much was watched

Bunny is used for the video only and nothing is re-encoded on the server: a
resized short is rendered in the admin's browser by the video resizer and
uploaded like any other file.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Annotated, AsyncIterator

import httpx
from beanie.operators import In
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, ImageOps
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.core.auth import get_current_user, require_admin
from app.models.module import Module
from app.models.short import FITS, MAX_SHORT_SECONDS, Short, ShortLike, ShortView, nearest_aspect
from app.models.thumbnail import OWNER_SHORT, Thumbnail
from app.models.user import User
from app.services import content_access
from app.services.bunny_stream import bunny_stream
from app.services.thumbnails import module_thumbnail_url, public_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["shorts"])

# Posters keep the short's own shape, fitted inside 720x1280 (or 1280x720).
POSTER_LONG_EDGE = 1280
MAX_POSTER_BYTES = 8 * 1024 * 1024
# A little over the limit, so a 3:00 file measured as 3:00.4 still fits.
DURATION_SLACK = 1.5


# ---------------------------------------------------------------- bodies ---
class CreateShortBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    module_id: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1, le=8192)
    height: int | None = Field(default=None, ge=1, le=8192)
    fit: str = "contain"
    focus_x: int = Field(default=50, ge=0, le=100)
    is_published: bool = True
    made_with: str | None = None


class UpdateShortBody(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    module_id: str | None = None
    fit: str | None = None
    focus_x: int | None = Field(default=None, ge=0, le=100)
    is_published: bool | None = None


class TusBody(BaseModel):
    file_size: int = Field(gt=0)
    file_name: str
    file_type: str = "video/mp4"


class ViewBody(BaseModel):
    watched_seconds: float = Field(ge=0)
    completed: bool = False


# --------------------------------------------------------------- helpers ---
async def _short_or_404(short_id: str) -> Short:
    s = await Short.get(short_id)
    if not s:
        raise HTTPException(status_code=404, detail="Short not found")
    return s


def _poster_url(s: Short) -> str | None:
    if s.poster_id:
        return public_url(s.poster_id)
    return s.bunny_thumbnail_url


async def _check_module(module_id: str | None) -> str | None:
    if not module_id:
        return None
    if not await Module.get(module_id):
        raise HTTPException(status_code=422, detail="That course no longer exists")
    return module_id


def _check_fit(fit: str) -> str:
    if fit not in FITS:
        raise HTTPException(status_code=422, detail=f"fit must be one of {', '.join(FITS)}")
    return fit


async def _refresh_status(s: Short) -> None:
    """Webhooks don't reach every deployment (or a laptop), so ask Bunny."""
    if s.status != "processing" or not s.bunny_video_guid:
        return
    try:
        video = await bunny_stream.get_video(s.bunny_video_guid)
    except Exception as exc:  # noqa: BLE001 - keep the cached status
        logger.info("Bunny status check failed for short %s: %s", s.id, exc)
        return
    _apply_bunny(s, video.get("status"), video.get("length"), video.get("thumbnailFileName"))
    await s.save()


def _apply_bunny(s: Short, status: int | None, length: float | None, thumb_file: str | None) -> None:
    if status == 4:  # Finished
        s.status = "ready"
        if length:
            s.duration_seconds = float(length)
        if thumb_file and s.bunny_video_guid:
            s.bunny_thumbnail_url = bunny_stream.get_thumbnail_url(s.bunny_video_guid, thumb_file)
    elif status in (5, 6):  # Error / UploadFailed
        s.status = "failed"


async def apply_bunny_webhook(video_guid: str, status: int | None, length: float | None) -> int:
    """Called by the Bunny webhook. Returns how many shorts it updated."""
    shorts = await Short.find(Short.bunny_video_guid == video_guid).to_list()
    thumb_file = None
    if shorts and status == 4:
        try:
            thumb_file = (await bunny_stream.get_video(video_guid)).get("thumbnailFileName")
        except Exception:  # noqa: BLE001 - a thumbnail is optional
            pass
    for s in shorts:
        _apply_bunny(s, status, length, thumb_file)
        await s.save()
    return len(shorts)


def _admin_view(s: Short, modules: dict[str, Module]) -> dict:
    m = modules.get(s.module_id or "")
    return {
        "id": s.id,
        "title": s.title,
        "description": s.description,
        "module_id": s.module_id,
        "module_title": m.title if m else None,
        "status": s.status,
        "duration_seconds": s.duration_seconds,
        "width": s.width,
        "height": s.height,
        "aspect": s.aspect,
        "fit": s.fit,
        "focus_x": s.focus_x,
        "made_with": s.made_with,
        "source_filename": s.source_filename,
        "poster_url": _poster_url(s),
        "is_published": s.is_published,
        "view_count": s.view_count,
        "like_count": s.like_count,
        "has_video": bool(s.bunny_video_guid),
        "created_at": s.created_at,
    }


async def _modules_for(shorts: list[Short]) -> dict[str, Module]:
    ids = list({s.module_id for s in shorts if s.module_id})
    if not ids:
        return {}
    return {m.id: m for m in await Module.find(In(Module.id, ids)).to_list()}


async def _learner_views(shorts: list[Short], user: User) -> list[dict]:
    ids = [s.id for s in shorts]
    liked = {l.short_id for l in await ShortLike.find(ShortLike.user_id == user.id, In(ShortLike.short_id, ids)).to_list()}
    seen = {v.short_id for v in await ShortView.find(ShortView.user_id == user.id, In(ShortView.short_id, ids)).to_list()}
    modules = await _modules_for(shorts)
    out = []
    for s in shorts:
        m = modules.get(s.module_id or "")
        # The course link shows only to people who may open the course.
        course = None
        if m and m.is_published and await content_access.can_access_module_id(m.id, user):
            course = {"id": m.id, "title": m.title, "layout": m.layout, "thumbnail_url": module_thumbnail_url(m)}
        out.append({
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "duration_seconds": s.duration_seconds,
            "width": s.width,
            "height": s.height,
            "aspect": s.aspect,
            "fit": s.fit,
            "focus_x": s.focus_x,
            "poster_url": _poster_url(s),
            "view_count": s.view_count,
            "like_count": s.like_count,
            "liked": s.id in liked,
            "seen": s.id in seen,
            "course": course,
            "created_at": s.created_at,
        })
    return out


def _encode_poster(data: bytes) -> bytes:
    if not data:
        raise HTTPException(status_code=422, detail="The poster is empty")
    if len(data) > MAX_POSTER_BYTES:
        raise HTTPException(status_code=413, detail="Posters can be up to 8 MB")
    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
        img.thumbnail((POSTER_LONG_EDGE, POSTER_LONG_EDGE), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="WEBP", quality=82, method=6)
        return out.getvalue()
    except Exception as exc:  # noqa: BLE001 - Pillow raises many kinds
        raise HTTPException(status_code=422, detail="That poster isn't an image we can read") from exc


# ----------------------------------------------------------------- admin ---
@router.get("/admin/shorts")
async def admin_list_shorts(admin: Annotated[User, Depends(require_admin)]):
    shorts = await Short.find_all().sort(-Short.created_at).to_list()
    # Anything still encoding gets one check per listing, so the page settles
    # without waiting on a webhook.
    for s in shorts:
        await _refresh_status(s)
    modules = await _modules_for(shorts)
    return [_admin_view(s, modules) for s in shorts]


@router.post("/admin/shorts", status_code=201)
async def admin_create_short(body: CreateShortBody, admin: Annotated[User, Depends(require_admin)]):
    if body.duration_seconds and body.duration_seconds > MAX_SHORT_SECONDS + DURATION_SLACK:
        raise HTTPException(
            status_code=422,
            detail=f"Shorts can be up to {MAX_SHORT_SECONDS // 60} minutes. Trim it in the video resizer first.",
        )
    s = Short(
        title=body.title.strip(),
        description=(body.description or "").strip() or None,
        module_id=await _check_module(body.module_id),
        duration_seconds=body.duration_seconds,
        width=body.width,
        height=body.height,
        aspect=nearest_aspect(body.width, body.height),
        fit=_check_fit(body.fit),
        focus_x=body.focus_x,
        is_published=body.is_published,
        made_with=body.made_with if body.made_with in ("resizer",) else None,
        created_by=admin.id,
    )
    await s.insert()
    return _admin_view(s, await _modules_for([s]))


@router.patch("/admin/shorts/{short_id}")
async def admin_update_short(short_id: str, body: UpdateShortBody, admin: Annotated[User, Depends(require_admin)]):
    s = await _short_or_404(short_id)
    data = body.model_dump(exclude_unset=True)
    if "title" in data:
        s.title = data["title"].strip()
    if "description" in data:
        s.description = (data["description"] or "").strip() or None
    if "module_id" in data:
        s.module_id = await _check_module(data["module_id"])
    if data.get("fit") is not None:
        s.fit = _check_fit(data["fit"])
    if data.get("focus_x") is not None:
        s.focus_x = data["focus_x"]
    if data.get("is_published") is not None:
        s.is_published = data["is_published"]
    await s.save()
    return _admin_view(s, await _modules_for([s]))


async def _new_bunny_video(s: Short, file_name: str) -> str:
    # One file per short: a replacement upload makes a new Bunny video, and
    # the old one goes once the new one is in place.
    video = await bunny_stream.create_video(f"[Short] {s.title}")
    return video["guid"]


async def _swap_video(s: Short, guid: str, file_name: str) -> None:
    old = s.bunny_video_guid
    s.bunny_video_guid = guid
    s.status = "processing"
    s.source_filename = file_name
    s.bunny_thumbnail_url = None
    await s.save()
    if old and old != guid:
        try:
            await bunny_stream.delete_video(old)
        except Exception as exc:  # noqa: BLE001 - a leftover is cheaper than a failed upload
            logger.warning("Could not delete replaced short video %s: %s", old, exc)


@router.post("/admin/shorts/{short_id}/prepare-upload")
async def admin_prepare_short_upload(short_id: str, body: TusBody, admin: Annotated[User, Depends(require_admin)]):
    s = await _short_or_404(short_id)
    guid = await _new_bunny_video(s, body.file_name)
    try:
        url = await bunny_stream.create_tus_upload_session(guid, body.file_size, body.file_name, body.file_type)
    except Exception as exc:  # noqa: BLE001
        logger.error("TUS session failed for short %s: %s", s.id, exc)
        # The empty video object would otherwise sit in the library forever;
        # the browser falls back to the server relay, which makes its own.
        try:
            await bunny_stream.delete_video(guid)
        except Exception:  # noqa: BLE001
            logger.warning("Could not remove unused Bunny video %s", guid)
        raise HTTPException(status_code=502, detail=f"Could not start the upload: {exc}") from exc
    await _swap_video(s, guid, body.file_name)
    return {"short_id": s.id, "bunny_video_guid": guid, "tus_upload_url": url, "status": s.status}


@router.post("/admin/shorts/{short_id}/upload")
async def admin_upload_short(short_id: str, admin: Annotated[User, Depends(require_admin)], video: UploadFile = File(...)):
    """Server relay: used only when the browser can't reach Bunny directly."""
    s = await _short_or_404(short_id)
    guid = await _new_bunny_video(s, video.filename or "short.mp4")

    async def chunks(size: int = 65536) -> AsyncIterator[bytes]:
        while chunk := await video.read(size):
            yield chunk

    await bunny_stream.upload_video_stream(guid, chunks(), total_size=video.size)
    await _swap_video(s, guid, video.filename or "short.mp4")
    return {"short_id": s.id, "bunny_video_guid": guid, "status": s.status}


@router.post("/admin/shorts/{short_id}/poster")
async def admin_short_poster(short_id: str, admin: Annotated[User, Depends(require_admin)], image: UploadFile = File(...)):
    s = await _short_or_404(short_id)
    thumb = Thumbnail(owner_kind=OWNER_SHORT, owner_id=s.id, data=_encode_poster(await image.read()), source="upload")
    await thumb.insert()
    previous, s.poster_id = s.poster_id, thumb.id
    await s.save()
    if previous:
        await Thumbnail.find(Thumbnail.id == previous).delete()
    return {"poster_url": _poster_url(s)}


@router.get("/admin/shorts/{short_id}/status")
async def admin_short_status(short_id: str, admin: Annotated[User, Depends(require_admin)]):
    s = await _short_or_404(short_id)
    await _refresh_status(s)
    return {"id": s.id, "status": s.status, "duration_seconds": s.duration_seconds, "poster_url": _poster_url(s)}


@router.delete("/admin/shorts/{short_id}")
async def admin_delete_short(short_id: str, admin: Annotated[User, Depends(require_admin)], confirm: str = ""):
    """Permanently delete a short: its Bunny video, poster, likes and views."""
    s = await _short_or_404(short_id)
    if confirm != short_id:
        raise HTTPException(status_code=428, detail="Confirmation required: pass ?confirm=<short_id>.")
    video = "nothing_to_delete"
    if s.bunny_video_guid:
        try:
            await bunny_stream.delete_video(s.bunny_video_guid)
            video = "deleted"
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in (404, 410):
                raise HTTPException(status_code=502, detail=f"Bunny refused to delete the video: {exc}. Nothing was removed.") from exc
            video = "already_absent"
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Could not reach Bunny: {exc}. Nothing was removed.") from exc
    await Thumbnail.find(Thumbnail.owner_kind == OWNER_SHORT, Thumbnail.owner_id == s.id).delete()
    await ShortLike.find(ShortLike.short_id == s.id).delete()
    await ShortView.find(ShortView.short_id == s.id).delete()
    await s.delete()
    logger.warning("PERMANENT DELETE short %s (%r) by admin %s — video %s", s.id, s.title, admin.email, video)
    return {"deleted": s.id, "video": video}


# --------------------------------------------------------------- learner ---
@router.get("/shorts")
async def shorts_feed(
    user: Annotated[User, Depends(get_current_user)],
    start: str | None = None,
    limit: int = 30,
):
    """
    Published shorts that are ready to play. `start` (a shared link) comes
    first; then ones this learner hasn't seen, newest first; then the rest.
    """
    limit = max(1, min(limit, 100))
    shorts = await Short.find(Short.is_published == True, Short.status == "ready").sort(-Short.created_at).to_list()  # noqa: E712
    seen = {v.short_id for v in await ShortView.find(ShortView.user_id == user.id).to_list()}
    first = [s for s in shorts if s.id == start]
    rest = [s for s in shorts if s.id != start]
    ordered = first + [s for s in rest if s.id not in seen] + [s for s in rest if s.id in seen]
    return await _learner_views(ordered[:limit], user)


@router.get("/shorts/{short_id}")
async def get_short(short_id: str, user: Annotated[User, Depends(get_current_user)]):
    s = await _short_or_404(short_id)
    if not s.is_published and not content_access.is_admin(user):
        raise HTTPException(status_code=404, detail="Short not found")
    return (await _learner_views([s], user))[0]


@router.get("/shorts/{short_id}/stream")
async def short_stream(short_id: str, user: Annotated[User, Depends(get_current_user)]):
    s = await _short_or_404(short_id)
    if not s.is_published and not content_access.is_admin(user):
        raise HTTPException(status_code=404, detail="Short not found")
    await _refresh_status(s)
    if s.status != "ready" or not s.bunny_video_guid:
        raise HTTPException(status_code=425, detail="This short is still processing")
    # Signed locally: Bunny has no API endpoint that issues these tokens.
    try:
        stream_url = bunny_stream.get_token_auth_url(s.bunny_video_guid, expires_in_seconds=14400)
    except RuntimeError:
        stream_url = bunny_stream.get_hls_url(s.bunny_video_guid)
    return {"stream_url": stream_url, "embed_url": bunny_stream.get_embed_url(s.bunny_video_guid), "expires_in": 14400}


@router.post("/shorts/{short_id}/like")
async def toggle_short_like(short_id: str, user: Annotated[User, Depends(get_current_user)]):
    s = await _short_or_404(short_id)
    existing = await ShortLike.find_one(ShortLike.short_id == s.id, ShortLike.user_id == user.id)
    if existing:
        await existing.delete()
        liked = False
    else:
        try:
            await ShortLike(short_id=s.id, user_id=user.id).insert()
        except DuplicateKeyError:
            pass  # a double tap raced itself; it is liked either way
        liked = True
    # Recount rather than increment, so a race can't drift the number.
    s.like_count = await ShortLike.find(ShortLike.short_id == s.id).count()
    await s.save()
    return {"liked": liked, "like_count": s.like_count}


@router.post("/shorts/{short_id}/view")
async def record_short_view(short_id: str, body: ViewBody, user: Annotated[User, Depends(get_current_user)]):
    s = await _short_or_404(short_id)
    now = datetime.now(timezone.utc)
    view = await ShortView.find_one(ShortView.short_id == s.id, ShortView.user_id == user.id)
    if view:
        view.watched_seconds = max(view.watched_seconds, body.watched_seconds)
        view.completed = view.completed or body.completed
        view.last_viewed_at = now
        await view.save()
    else:
        try:
            await ShortView(short_id=s.id, user_id=user.id, watched_seconds=body.watched_seconds,
                            completed=body.completed, last_viewed_at=now).insert()
        except DuplicateKeyError:
            pass
        # One view per person, as YouTube counts unique viewers here.
        s.view_count = await ShortView.find(ShortView.short_id == s.id).count()
        await s.save()
    return {"view_count": s.view_count}
