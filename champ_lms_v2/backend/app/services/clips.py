"""
Trimmed and split episodes: an episode that plays part of its Bunny video.

The video on Bunny is never cut. An episode carries clip_start / clip_end in
seconds of the source video, and splitting makes more episodes sharing the
same bunny_video_guid with neighbouring ranges. So a trim is instant, works on
videos already uploaded, and can be changed or undone at any time.

Two time bases meet here, and the rule is simple:
  * stored: source time. Transcript segments cover the whole source video and
    are shared as-is by every part, so moving a trim never loses a line.
  * shown: clip time. Everything an admin edits or a learner sees starts at 0
    at the clip's start, and only covers the clip.
"""
from __future__ import annotations

from app.models.episode import Episode

# Shortest part a trim or split may leave, so an episode is never a blink.
MIN_CLIP_SECONDS = 10


def source_length(ep: Episode) -> float | None:
    """Length of the whole Bunny video, when known."""
    if ep.source_duration_seconds:
        return float(ep.source_duration_seconds)
    # Episodes from before trimming existed only ever stored one length, and it
    # was the source's, because nothing could be clipped then.
    if ep.clip_start is None and ep.clip_end is None and ep.duration_seconds:
        return float(ep.duration_seconds)
    return None


def clip_bounds(ep: Episode) -> tuple[float, float | None]:
    """(start, end) in source seconds. end is None when the length is unknown."""
    start = ep.clip_start or 0.0
    end = ep.clip_end if ep.clip_end is not None else source_length(ep)
    return start, end


def is_clipped(ep: Episode) -> bool:
    return bool(ep.clip_start) or ep.clip_end is not None


def apply_source_length(ep: Episode, seconds: float | int | None) -> None:
    """
    Record the source video's length (from Bunny) and keep the episode's own
    length in step with its clip. Called wherever Bunny reports a length.
    """
    if not seconds:
        return
    ep.source_duration_seconds = int(seconds)
    start, end = clip_bounds(ep)
    ep.duration_seconds = int(round((end if end is not None else seconds) - start))


def segments_in_clip(ep: Episode, relative: bool = True) -> list[dict]:
    """The episode's transcript lines inside its clip, in clip time by default."""
    segs = ep.transcript_segments or []
    if not is_clipped(ep):
        return list(segs)
    start, end = clip_bounds(ep)
    out = []
    for s in segs:
        # A line belongs to the clip when it starts inside it.
        if s["start"] < start - 0.25 or (end is not None and s["start"] >= end):
            continue
        if relative:
            s = {
                "start": round(max(0.0, s["start"] - start), 2),
                "end": round(max(0.0, min(s["end"], end if end is not None else s["end"]) - start), 2),
                "text": s["text"],
            }
        out.append(s)
    return out


def refresh_transcript_text(ep: Episode) -> None:
    """Plain text of the clip's lines, which the quiz and notes writers read."""
    text = " ".join(s["text"] for s in segments_in_clip(ep, relative=False) if s.get("text")).strip()
    ep.transcript = text or None


def merge_clip_segments(ep: Episode, clip_segments: list[dict]) -> list[dict]:
    """
    Replace the lines inside the clip with an admin's edit (given in clip
    time), keeping the lines outside it, which other parts still show.
    """
    start, end = clip_bounds(ep)
    outside = [
        s for s in (ep.transcript_segments or [])
        if s["start"] < start - 0.25 or (end is not None and s["start"] >= end)
    ]
    inside = [
        {"start": round(s["start"] + start, 2), "end": round(s["end"] + start, 2), "text": s["text"]}
        for s in clip_segments
    ]
    return sorted(outside + inside, key=lambda s: s["start"])
