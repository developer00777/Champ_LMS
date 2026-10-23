"""
Video studio router: one editor for any video, in a canvas course or a
classic (directly uploaded) module.

The studio edits on top of the video, never the video itself (Bunny is used
for video only, and its files are never cut or re-encoded):

  trim and split   which part plays, and parts with room for a quiz between
                   (services/clips.py; canvas courses reuse the course routes)
  edits            cuts, chapters, text overlays, effects (zoom, speed, mute,
                   blur), caption style, look, brand mark and progress bar
                   (services/video_edits.py)
  AI               highlights, chapters, an opening hook, cuts to tighten it,
                   moments to zoom in on, and a title and description,
                   suggested from the transcript; nothing is saved until the
                   admin keeps them and presses Save

A classic module has no canvas, so its parts are episodes next to each other
in sequence_order, and joining or splitting renumbers the episodes after them.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Annotated, Literal

import redis.asyncio as aioredis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import require_admin
from app.core.redis import get_redis
from app.models.episode import Episode
from app.models.module import ITEM_VIDEO, LAYOUT_CANVAS, Module
from app.models.user import User
from app.routers.courses import (
    _PART_TITLE, ClipIn, _draft_episode_notes, _set_range, absorb_next_part, insert_part,
    join_next, move_questions_to_parts, retitle_parts_in_order, set_clip,
)
from app.services.ai_service import AIServiceError, ai_service
from app.services.bunny_stream import bunny_stream
from app.services.clips import MIN_CLIP_SECONDS, apply_source_length, clip_bounds, source_length
from app.services.purge_service import PurgeError, purge_episode
from app.services.thumbnails import thumbnail_view
from app.services.video_edits import normalize, played_seconds

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/episodes", tags=["video-studio"])


# ==========================================================================
# Schemas. All times are seconds of the whole Bunny video.
# ==========================================================================
class CutIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class ChapterIn(BaseModel):
    start: float = Field(ge=0)
    title: str = Field(min_length=1, max_length=120)


HexColor = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class OverlayIn(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=200)
    subtext: str | None = Field(default=None, max_length=200)
    position: Literal["top", "center", "bottom", "lower-third"] = "lower-third"
    style: Literal["title", "callout", "label", "quote"] = "callout"
    size: Literal["s", "m", "l"] = "m"
    anim: Literal["rise", "fade", "pop", "type", "none"] = "rise"
    # The style's accent (callout fill, label bar, quote mark); None = its own.
    color: HexColor | None = None


class EffectIn(BaseModel):
    kind: Literal["zoom", "speed", "mute", "blur"]
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    scale: float | None = Field(default=None, ge=1.05, le=3.0)   # zoom
    rate: float | None = Field(default=None, ge=0.5, le=4.0)     # speed
    # zoom: the point it centres on; blur: the box's top-left corner. % of the frame.
    x: float | None = Field(default=None, ge=0, le=100)
    y: float | None = Field(default=None, ge=0, le=100)
    w: float | None = Field(default=None, ge=2, le=100)          # blur
    h: float | None = Field(default=None, ge=2, le=100)
    mode: Literal["blur", "black"] | None = None


class CaptionStyleIn(BaseModel):
    # classic: a dark box. bold: big white with an outline. pop: the word being
    # said lights up. karaoke: words fill in as they are said. minimal: no box.
    preset: Literal["classic", "bold", "pop", "karaoke", "minimal"] = "classic"
    position: Literal["bottom", "middle", "top"] = "bottom"
    size: Literal["s", "m", "l"] = "m"
    default_on: bool = False
    font: Literal["sans", "display", "serif", "rounded", "mono"] = "sans"
    color: HexColor = "#ffffff"
    # The word being said, for pop and karaoke.
    highlight: HexColor = "#ffd23f"
    uppercase: bool = False


class LookIn(BaseModel):
    brightness: int = Field(default=100, ge=50, le=150)
    contrast: int = Field(default=100, ge=50, le=150)
    saturation: int = Field(default=100, ge=0, le=200)
    zoom: float = Field(default=1.0, ge=1.0, le=2.5)
    focus_x: int = Field(default=50, ge=0, le=100)
    focus_y: int = Field(default=50, ge=0, le=100)
    fade_in: bool = False
    fade_out: bool = False


class BrandIn(BaseModel):
    watermark: bool = False
    position: Literal["tl", "tr", "bl", "br"] = "tr"
    opacity: float = Field(default=0.85, ge=0.2, le=1.0)
    # A thin bar along the top showing how far through the part the learner is.
    progress_bar: bool = False
    progress_color: HexColor = "#ff3b45"


class EditsIn(BaseModel):
    cuts: list[CutIn] = Field(default_factory=list, max_length=200)
    chapters: list[ChapterIn] = Field(default_factory=list, max_length=60)
    overlays: list[OverlayIn] = Field(default_factory=list, max_length=60)
    effects: list[EffectIn] = Field(default_factory=list, max_length=120)
    captions: CaptionStyleIn | None = None
    look: LookIn | None = None
    brand: BrandIn | None = None


class StudioSaveIn(BaseModel):
    """The kept part, where to split it, and the edits on top."""
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    split_at: list[float] = Field(default_factory=list, max_length=20)
    edits: EditsIn = Field(default_factory=EditsIn)


class StudioAiIn(BaseModel):
    task: Literal["highlights", "chapters", "hook", "tighten", "zooms", "details"]
    # Only the transcript inside this range is read; omit for the whole video.
    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, gt=0)
    count: int = Field(default=5, ge=1, le=12)


# ==========================================================================
# Helpers
# ==========================================================================
async def _episode_or_404(episode_id: str) -> Episode:
    ep = await Episode.get(episode_id)
    if not ep:
        raise HTTPException(status_code=404, detail="Episode not found")
    return ep


async def _ordered_videos(module: Module) -> list[Episode]:
    """The module's episodes in playing order: canvas order, or sequence_order."""
    eps = await Episode.find(Episode.module_id == module.id).sort(+Episode.sequence_order).to_list()
    if module.layout != LAYOUT_CANVAS:
        return eps
    by_id = {e.id: e for e in eps}
    return [by_id[it.ref_id] for it in module.items if it.kind == ITEM_VIDEO and it.ref_id in by_id]


def _parts_of(ep: Episode, ordered: list[Episode]) -> list[Episode]:
    """Every episode playing the same Bunny video as `ep`, in playing order."""
    if not ep.bunny_video_guid:
        return [ep]
    return [e for e in ordered if e.bunny_video_guid == ep.bunny_video_guid]


def _next_part(ep: Episode, ordered: list[Episode], length: float | None) -> Episode | None:
    """The part right after `ep` that carries on from where it stops, if any."""
    i = next((n for n, e in enumerate(ordered) if e.id == ep.id), None)
    if i is None or i + 1 >= len(ordered) or not length:
        return None
    other = ordered[i + 1]
    if (
        not ep.bunny_video_guid or other.bunny_video_guid != ep.bunny_video_guid
        or abs((clip_bounds(ep)[1] or length) - clip_bounds(other)[0]) > 0.5
    ):
        return None
    return other


def _course_item_id(module: Module, ep: Episode) -> str | None:
    for it in module.items:
        if it.kind == ITEM_VIDEO and it.ref_id == ep.id:
            return it.id
    return None


async def _studio_view(ep: Episode) -> dict:
    module = await Module.get(ep.module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    ordered = await _ordered_videos(module)
    parts = _parts_of(ep, ordered)
    length = source_length(ep)
    canvas = module.layout == LAYOUT_CANVAS
    return {
        "id": ep.id,
        "title": ep.title,
        "description": ep.description,
        "status": ep.status,
        "module_id": module.id,
        "module_title": module.title,
        "layout": "canvas" if canvas else "classic",
        "course_item_id": _course_item_id(module, ep) if canvas else None,
        "source_duration_seconds": length,
        "clip_start": ep.clip_start,
        "clip_end": ep.clip_end,
        "part": [parts.index(ep) + 1, len(parts)] if len(parts) > 1 else None,
        "parts": [
            {"id": p.id, "title": p.title, "clip_start": clip_bounds(p)[0],
             "clip_end": clip_bounds(p)[1], "is_this": p.id == ep.id}
            for p in parts
        ],
        "can_join_next": _next_part(ep, ordered, length) is not None,
        # Source time: the studio's timeline is the whole video.
        "transcript_segments": ep.transcript_segments or [],
        "edits": ep.edits or {},
        **thumbnail_view(ep),
    }


# ==========================================================================
# Endpoints
# ==========================================================================
@router.get("/{episode_id}/studio")
async def get_studio(episode_id: str, admin: Annotated[User, Depends(require_admin)]):
    """Everything the studio needs for one episode, in source time."""
    ep = await _episode_or_404(episode_id)
    if ep.status != "ready" and ep.bunny_video_guid:
        # The webhook may not have arrived (see content.get_stream_url); ask
        # Bunny, so a video that has finished encoding opens straight away.
        try:
            video = await bunny_stream.get_video(ep.bunny_video_guid)
        except Exception as exc:  # Bunny unreachable: report what we have
            logger.warning("Bunny status check failed for %s: %s", ep.id, exc)
            video = {}
        if video.get("status") == 4:
            ep.status = "ready"
            if video.get("length"):
                apply_source_length(ep, video["length"])
            await ep.save()
    return await _studio_view(ep)


@router.put("/{episode_id}/studio")
async def save_studio(
    episode_id: str,
    body: StudioSaveIn,
    background: BackgroundTasks,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Save the studio: the edits, then the trim and any splits.

    The edits go on every part of the video, so a part made by this save (or
    a later one) carries them too. The trim and splits follow the same rules
    as the course canvas: the first part stays this episode, further parts
    become new episodes right after it.
    """
    ep = await _episode_or_404(episode_id)
    module = await Module.get(ep.module_id)
    length = source_length(ep)
    if not module or ep.status != "ready" or not length or not ep.bunny_video_guid:
        raise HTTPException(
            status_code=409, detail="The video can be edited once it has finished processing.",
        )

    edits = normalize(body.edits.model_dump(), length)
    start, end = round(body.start, 2), round(min(body.end, length), 2)
    cuts = sorted({round(t, 2) for t in body.split_at})
    if any(not (start < t < end) for t in cuts):
        raise HTTPException(status_code=422, detail="Split points must fall inside the part you keep.")
    points = [start, *cuts, end]
    ranges = list(zip(points, points[1:]))
    if any(played_seconds(edits, a, b) < MIN_CLIP_SECONDS for a, b in ranges):
        raise HTTPException(
            status_code=422,
            detail=f"Each part needs at least {MIN_CLIP_SECONDS} seconds left to play after its cuts.",
        )

    ordered = await _ordered_videos(module)
    for part in _parts_of(ep, ordered):
        part.edits = edits
        await part.save()

    cur_start, cur_end = clip_bounds(ep)
    cur_end = cur_end if cur_end is not None else length
    if cuts or abs(start - cur_start) > 0.01 or abs(end - cur_end) > 0.01:
        if module.layout == LAYOUT_CANVAS:
            item_id = _course_item_id(module, ep)
            if not item_id:
                raise HTTPException(status_code=409, detail="This video is not on its course canvas.")
            await set_clip(module.id, item_id, ClipIn(start=start, end=end, split_at=cuts), background, admin)
        else:
            await _classic_clip(module, await _episode_or_404(episode_id), ranges, length, background)

    return await _studio_view(await _episode_or_404(episode_id))


async def _classic_clip(
    module: Module, ep: Episode, ranges: list[tuple[float, float]], length: float,
    background: BackgroundTasks,
) -> None:
    """Trim and split in a classic module: parts go right after it in sequence_order."""
    ep.source_duration_seconds = int(length)
    _set_range(ep, *ranges[0], length)
    base = (_PART_TITLE.match(ep.title) or re.match(r"^(.*)$", ep.title)).group(1)
    if len(ranges) > 1 and not _PART_TITLE.match(ep.title):
        ep.title = f"{base} (part 1)"
    await ep.save()

    extra = len(ranges) - 1
    if extra:
        for later in await Episode.find(
            Episode.module_id == module.id, Episode.sequence_order > ep.sequence_order,
        ).to_list():
            later.sequence_order += extra
            await later.save()
    new_parts = [
        await insert_part(ep, f"{base} (part {n})", a, b, length, sequence_order=ep.sequence_order + n - 1)
        for n, (a, b) in enumerate(ranges[1:], start=2)
    ]
    await move_questions_to_parts(ep, new_parts, length)
    await _settle_classic(module)
    for target in [ep, *new_parts]:
        if target.transcript and target.notes_source != "manual":
            background.add_task(_draft_episode_notes, target.id)


async def _settle_classic(module: Module) -> None:
    """Number a classic module's episodes 1..N, retitle parts, recount."""
    eps = await Episode.find(Episode.module_id == module.id).sort(+Episode.sequence_order).to_list()
    for n, e in enumerate(eps, start=1):
        if e.sequence_order != n:
            e.sequence_order = n
            await e.save()
    await retitle_parts_in_order(eps)
    if module.total_episodes != len(eps):
        module.total_episodes = len(eps)
        await module.save()


@router.post("/{episode_id}/join-next")
async def join_next_part(
    episode_id: str,
    background: BackgroundTasks,
    admin: Annotated[User, Depends(require_admin)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    """Undo a split, in a course or a classic module: join this part with the next."""
    ep = await _episode_or_404(episode_id)
    module = await Module.get(ep.module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    if module.layout == LAYOUT_CANVAS:
        item_id = _course_item_id(module, ep)
        if not item_id:
            raise HTTPException(status_code=409, detail="This video is not on its course canvas.")
        await join_next(module.id, item_id, background, admin, redis)
        return await _studio_view(await _episode_or_404(episode_id))

    length = source_length(ep)
    other = _next_part(ep, await _ordered_videos(module), length)
    if not other or not length:
        raise HTTPException(
            status_code=409, detail="Only a part and the part right after it, from the same video, can be joined.",
        )
    await absorb_next_part(ep, other, length)
    try:
        # Keeps the Bunny video: this part still plays it (see purge_service).
        await purge_episode(other, redis=redis)
    except PurgeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    await _settle_classic(module)
    if ep.transcript and ep.notes_source != "manual":
        background.add_task(_draft_episode_notes, ep.id)
    return await _studio_view(await _episode_or_404(episode_id))


def _snap_lines(lines: list[dict], i: int) -> dict | None:
    return lines[i] if 0 <= i < len(lines) else None


@router.post("/{episode_id}/studio/ai")
async def studio_ai(
    episode_id: str, body: StudioAiIn, admin: Annotated[User, Depends(require_admin)],
):
    """
    AI suggestions from the transcript, in source time. Nothing is saved: the
    studio shows them, and the admin keeps the ones they want.
    """
    ep = await _episode_or_404(episode_id)
    if not ai_service.enabled:
        raise HTTPException(status_code=503, detail="AI suggestions need OPENROUTER_API_KEY.")
    lo = body.start if body.start is not None else 0.0
    hi = body.end if body.end is not None else float("inf")
    lines = [s for s in ep.transcript_segments or [] if lo - 0.25 <= s["start"] < hi and s.get("text")]
    if len(lines) < 3:
        raise HTTPException(
            status_code=409,
            detail="The AI works from the transcript, and this video has too little of one yet. "
                   "Add or generate the transcript first.",
        )

    def mmss(x: float) -> str:
        x = int(x)
        return f"{x // 60}:{x % 60:02d}"

    numbered = "\n".join(f"[{n}] {mmss(s['start'])} {s['text']}" for n, s in enumerate(lines))
    try:
        raw = await ai_service.studio_suggestions(body.task, ep.title, numbered, body.count)
    except AIServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("Studio AI %s for %s returned unreadable JSON: %s", body.task, ep.id, exc)
        raise HTTPException(status_code=502, detail="The AI's answer couldn't be read. Try again.") from exc

    def as_int(x) -> int:
        try:
            return int(x)
        except (TypeError, ValueError):
            return -1

    out: list[dict] = []
    if body.task == "hook":
        hook = raw if isinstance(raw, dict) else {}
        title = str(hook.get("title") or "").strip()[:120]
        if not title:
            raise HTTPException(status_code=502, detail="The AI didn't suggest a hook. Try again.")
        return {"task": "hook", "hook": {"title": title, "subtitle": str(hook.get("subtitle") or "").strip()[:160]}}
    if body.task == "details":
        det = raw if isinstance(raw, dict) else {}
        title = str(det.get("title") or "").strip()[:200]
        if not title:
            raise HTTPException(status_code=502, detail="The AI didn't suggest a title. Try again.")
        return {"task": "details", "details": {"title": title, "description": str(det.get("description") or "").strip()[:1000]}}

    for row in raw if isinstance(raw, list) else []:
        if not isinstance(row, dict):
            continue
        if body.task == "chapters":
            line = _snap_lines(lines, as_int(row.get("line")))
            title = str(row.get("title") or "").strip()[:120]
            if line and title:
                out.append({"start": round(line["start"], 2), "title": title})
            continue
        first = _snap_lines(lines, as_int(row.get("first_line")))
        last = _snap_lines(lines, as_int(row.get("last_line")))
        if not first or not last or last["start"] < first["start"]:
            continue
        item = {
            "start": round(first["start"], 2),
            "end": round(max(last["end"], last["start"] + 0.5), 2),
            "reason": str(row.get("reason") or "").strip()[:300],
        }
        if body.task == "zooms":
            # A punch-in reads as emphasis for a few seconds, not a whole minute.
            item["end"] = round(min(item["end"], item["start"] + 8), 2)
        if body.task == "highlights":
            item["title"] = str(row.get("title") or "Highlight").strip()[:120]
            item["score"] = max(0, min(100, as_int(row.get("score")) if as_int(row.get("score")) >= 0 else 50))
        out.append(item)
    if body.task == "chapters":
        out.sort(key=lambda c: c["start"])
    return {"task": body.task, "suggestions": out}
