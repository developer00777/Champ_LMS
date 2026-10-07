"""
Thumbnail studio router: course and episode thumbnails.

An admin makes a thumbnail one of three ways, all ending in the same save:

  upload — picks an image file.
  ai     — asks an image model for a picture (POST /admin/thumbnails/generate),
           previews it, then saves the one they like.
  text   — designs a text thumbnail from a template; the browser draws it on
           a canvas, so the preview is exactly what is saved. The design's
           settings are kept so it can be reopened and edited.

Images are stored in MongoDB (models/thumbnail.py), not Bunny: Bunny is used
for video only.
"""
from __future__ import annotations

import base64
import json
from typing import Annotated

from beanie.operators import In
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from app.core.auth import require_admin
from app.models.episode import Episode
from app.models.module import ITEM_VIDEO, LAYOUT_CANVAS, Module
from app.models.thumbnail import OWNER_KINDS, OWNER_MODULE, SOURCES, Thumbnail
from app.models.user import User
from app.services.ai_service import THUMBNAIL_STYLES, AIServiceError, ai_service
from app.services.thumbnails import (
    ThumbnailError, clear_thumbnail, encode_thumbnail, set_thumbnail, thumbnail_view,
)

router = APIRouter(tags=["thumbnails"])

MAX_DESIGN_BYTES = 4096


class GenerateIn(BaseModel):
    # Either name the course/episode, so its title and contents describe the
    # picture, or pass title/context directly (an episode not created yet).
    owner_kind: str | None = None
    owner_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    context: str | None = Field(default=None, max_length=1500)
    style: str = "illustration"
    direction: str = Field(default="", max_length=500)
    # Keep the left half quiet, for a title to be added on top in the studio.
    leave_space: bool = False


async def _owner_or_404(owner_kind: str, owner_id: str) -> Module | Episode:
    if owner_kind not in OWNER_KINDS:
        raise HTTPException(status_code=404, detail="Not found")
    owner = await (Module.get(owner_id) if owner_kind == OWNER_MODULE else Episode.get(owner_id))
    if not owner:
        raise HTTPException(status_code=404, detail=f"{owner_kind.capitalize()} not found")
    return owner


async def _describe(owner: Module | Episode) -> tuple[str, str]:
    """(title, a few lines about it) for the image prompt."""
    if isinstance(owner, Episode):
        module = await Module.get(owner.module_id)
        lines = []
        if module:
            lines.append(f"Part of the course: {module.title}")
        if owner.description:
            lines.append(f"About: {owner.description}")
        if owner.notes:
            lines.append(f"Key points: {owner.notes[:600]}")
        return owner.title, "\n".join(lines)

    lines = []
    if owner.description:
        lines.append(f"About: {owner.description}")
    if owner.category:
        lines.append(f"Category: {owner.category}")
    if owner.layout == LAYOUT_CANVAS:
        topics = [s.title for s in owner.sections if s.title.strip()]
        ids = [i.ref_id for i in owner.items if i.kind == ITEM_VIDEO][:10]
        found = {e.id: e.title for e in await Episode.find(In(Episode.id, ids)).to_list()} if ids else {}
        videos = [found[i] for i in ids if i in found]
    else:
        topics = []
        videos = [e.title for e in await Episode.find(Episode.module_id == owner.id).limit(10).to_list()]
    # "Section 1" and the like say nothing about the subject.
    topics = [t for t in topics if not t.lower().startswith("section ")]
    if topics:
        lines.append("Sections: " + "; ".join(topics[:8]))
    if videos:
        lines.append("Lessons: " + "; ".join(videos))
    return owner.title, "\n".join(lines)


@router.post("/admin/thumbnails/generate")
async def generate_thumbnail(body: GenerateIn, admin: Annotated[User, Depends(require_admin)]):
    """
    Ask the image model for a thumbnail. Nothing is saved: the studio shows
    the result and the admin saves the one they want.
    """
    if not ai_service.enabled:
        raise HTTPException(status_code=503, detail="AI is not set up: OPENROUTER_API_KEY is empty.")
    if body.style not in THUMBNAIL_STYLES:
        raise HTTPException(status_code=422, detail=f"Unknown style “{body.style}”")
    title, about = (body.title or "").strip(), (body.context or "").strip()
    if body.owner_kind and body.owner_id:
        owner_title, owner_about = await _describe(await _owner_or_404(body.owner_kind, body.owner_id))
        title = title or owner_title
        about = "\n".join(x for x in (owner_about, about) if x)
    if not title:
        raise HTTPException(status_code=422, detail="Give it a title first, so the AI knows what to draw.")
    try:
        raw = await ai_service.generate_thumbnail(
            title, about, body.style, body.direction, body.leave_space,
        )
        image = encode_thumbnail(raw)
    except AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ThumbnailError as exc:
        raise HTTPException(status_code=502, detail=f"The AI image couldn't be read: {exc}") from exc
    return {"image": "data:image/webp;base64," + base64.b64encode(image).decode("ascii")}


@router.post("/admin/thumbnails/{owner_kind}/{owner_id}")
async def save_thumbnail(
    owner_kind: str,
    owner_id: str,
    admin: Annotated[User, Depends(require_admin)],
    file: UploadFile = File(...),
    source: str = Form("upload"),
    design: str | None = Form(None),
):
    """Save a thumbnail for a course or an episode, replacing the current one."""
    owner = await _owner_or_404(owner_kind, owner_id)
    if source not in SOURCES:
        raise HTTPException(status_code=422, detail=f"Unknown source “{source}”")
    design_obj = None
    if design:
        if len(design) > MAX_DESIGN_BYTES:
            raise HTTPException(status_code=422, detail="Design settings are too large")
        try:
            design_obj = json.loads(design)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Design settings aren't valid JSON") from exc
        if not isinstance(design_obj, dict):
            raise HTTPException(status_code=422, detail="Design settings must be an object")
    try:
        await set_thumbnail(owner, await file.read(), source, design_obj)
    except ThumbnailError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return thumbnail_view(owner)


@router.delete("/admin/thumbnails/{owner_kind}/{owner_id}")
async def delete_thumbnail(
    owner_kind: str, owner_id: str, admin: Annotated[User, Depends(require_admin)],
):
    owner = await _owner_or_404(owner_kind, owner_id)
    await clear_thumbnail(owner)
    return thumbnail_view(owner)


@router.get("/thumbnails/{thumbnail_id}")
async def get_thumbnail(thumbnail_id: str):
    """
    The image itself. Public, because <img> and CSS can't send a bearer token;
    ids are random UUIDs and a course picture is not sensitive. Every saved
    image gets a new id, so caching it forever is safe.
    """
    thumb = await Thumbnail.get(thumbnail_id)
    if not thumb:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return Response(
        content=thumb.data,
        media_type=thumb.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
