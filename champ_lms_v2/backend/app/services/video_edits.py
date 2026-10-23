"""
Video studio edits: what an episode's video does on top of its trim and split.

Like a trim (services/clips.py), nothing here touches the video on Bunny. An
edit is a small package the players apply while they play:

  cuts      ranges skipped in playback (a cough, a tangent, dead air)
  chapters  named points, marked on the player's scrub bar
  overlays  text over the video for a while (a hook title, a callout)
  effects   stretches played differently without cutting them: a punch-in
            zoom, a speed change, the sound muted, a box of the picture blurred
  captions  how the CC captions look, and whether they start on
  look      colour, zoom and framing, fade in and out
  brand     the Champions Group mark in a corner, a progress bar

The package is stored in source time, and the same package sits on every part
of a split video (like transcript_segments), so moving a split never loses an
edit. Each part shows what falls inside its own clip, in clip time.
"""
from __future__ import annotations

from app.models.episode import Episode
from app.services.clips import clip_bounds, source_length

# Shortest stretch worth cutting; anything shorter is a slip of the mouse.
MIN_CUT_SECONDS = 0.5

CAPTION_DEFAULTS = {
    "preset": "classic", "position": "bottom", "size": "m", "default_on": False,
    "font": "sans", "color": "#ffffff", "highlight": "#ffd23f", "uppercase": False,
}
LOOK_DEFAULTS = {
    "brightness": 100, "contrast": 100, "saturation": 100,
    "zoom": 1.0, "focus_x": 50, "focus_y": 50, "fade_in": False, "fade_out": False,
}
BRAND_DEFAULTS = {
    "watermark": False, "position": "tr", "opacity": 0.85, "progress_bar": False, "progress_color": "#ff3b45",
}
# What each effect keeps besides its range; anything else sent is dropped.
EFFECT_FIELDS = {
    "zoom": ("scale", "x", "y"),
    "speed": ("rate",),
    "mute": (),
    "blur": ("x", "y", "w", "h", "mode"),
}


def merge_ranges(ranges: list[dict]) -> list[dict]:
    """Sorted, with overlapping or touching ranges joined."""
    out: list[dict] = []
    for r in sorted(ranges, key=lambda r: r["start"]):
        if out and r["start"] <= out[-1]["end"] + 0.05:
            out[-1]["end"] = max(out[-1]["end"], r["end"])
        else:
            out.append({"start": r["start"], "end": r["end"]})
    return out


def normalize(edits: dict, length: float) -> dict | None:
    """
    A clean package in source time: held inside the video, sorted, cuts
    merged, settings left at their defaults dropped. None when nothing is set.
    """
    def inside(x: float) -> float:
        return round(min(max(0.0, float(x)), length), 2)

    cuts = merge_ranges([
        {"start": inside(c["start"]), "end": inside(c["end"])}
        for c in edits.get("cuts") or [] if c["end"] > c["start"]
    ])
    cuts = [c for c in cuts if c["end"] - c["start"] >= MIN_CUT_SECONDS]

    chapters: list[dict] = []
    for c in sorted(edits.get("chapters") or [], key=lambda c: c["start"]):
        title = c["title"].strip()
        # Two chapters a moment apart would read as one tick on the bar.
        if title and not (chapters and inside(c["start"]) - chapters[-1]["start"] < 1):
            chapters.append({"start": inside(c["start"]), "title": title})

    overlays = sorted(
        (
            {**o, "start": inside(o["start"]), "end": inside(o["end"]), "text": o["text"].strip()}
            for o in edits.get("overlays") or []
        ),
        key=lambda o: o["start"],
    )
    overlays = [o for o in overlays if o["text"] and o["end"] - o["start"] >= 0.5]

    effects: list[dict] = []
    for e in sorted(edits.get("effects") or [], key=lambda e: e["start"]):
        e = {"kind": e["kind"], "start": inside(e["start"]), "end": inside(e["end"]),
             **{k: e[k] for k in EFFECT_FIELDS[e["kind"]] if e.get(k) is not None}}
        if e["end"] - e["start"] < 0.5:
            continue
        # Two speeds at once can't both play: a later one starts where the earlier stops.
        if e["kind"] == "speed":
            before = [x for x in effects if x["kind"] == "speed"]
            if before and e["start"] < before[-1]["end"]:
                e["start"] = before[-1]["end"]
                if e["end"] - e["start"] < 0.5:
                    continue
        effects.append(e)
    effects.sort(key=lambda e: e["start"])

    out: dict = {}
    if cuts:
        out["cuts"] = cuts
    if chapters:
        out["chapters"] = chapters
    if overlays:
        out["overlays"] = overlays
    if effects:
        out["effects"] = effects
    for key, defaults in (("captions", CAPTION_DEFAULTS), ("look", LOOK_DEFAULTS), ("brand", BRAND_DEFAULTS)):
        given = {k: v for k, v in (edits.get(key) or {}).items() if k in defaults}
        if given and any(given[k] != defaults[k] for k in given):
            out[key] = {**defaults, **given}
    return out or None


def _clip_range(ep: Episode) -> tuple[float, float]:
    start, end = clip_bounds(ep)
    return start, end if end is not None else (source_length(ep) or 0.0)


def edits_in_clip(ep: Episode) -> dict | None:
    """What the learner's player applies for this part, in clip time."""
    if not ep.edits:
        return None
    start, end = _clip_range(ep)
    if end <= start:
        return None

    def rel(x: float) -> float:
        return round(x - start, 2)

    out: dict = {}
    cuts = [
        {"start": rel(max(c["start"], start)), "end": rel(min(c["end"], end))}
        for c in ep.edits.get("cuts") or [] if c["end"] > start and c["start"] < end
    ]
    if cuts:
        out["cuts"] = cuts
    chapters = [
        {"start": rel(c["start"]), "title": c["title"]}
        for c in ep.edits.get("chapters") or [] if start - 0.5 <= c["start"] < end
    ]
    if chapters:
        # A part that starts mid-chapter opens with that chapter's name.
        before = [c for c in ep.edits.get("chapters") or [] if c["start"] < start - 0.5]
        if before and chapters[0]["start"] > 0.5:
            chapters.insert(0, {"start": 0.0, "title": before[-1]["title"]})
        out["chapters"] = [{**c, "start": max(0.0, c["start"])} for c in chapters]
    overlays = [
        {**o, "start": max(0.0, rel(o["start"])), "end": rel(min(o["end"], end))}
        for o in ep.edits.get("overlays") or [] if o["end"] > start and o["start"] < end
    ]
    if overlays:
        out["overlays"] = overlays
    effects = [
        {**e, "start": max(0.0, rel(e["start"])), "end": rel(min(e["end"], end))}
        for e in ep.edits.get("effects") or [] if e["end"] > start and e["start"] < end
    ]
    if effects:
        out["effects"] = effects
    for key in ("captions", "look", "brand"):
        if ep.edits.get(key):
            out[key] = ep.edits[key]
    return out or None


def _overlap(ranges: list[dict], a: float, b: float) -> float:
    return sum(max(0.0, min(r["end"], b) - max(r["start"], a)) for r in ranges)


def cut_seconds_between(ep: Episode, a: float, b: float) -> float:
    """
    Seconds between two clip-time positions that playback gets through
    without spending them: cuts are jumped over, and a sped-up stretch saves
    the time it doesn't take.
    """
    if not ep.edits or b <= a:
        return 0.0
    start, _ = _clip_range(ep)
    a, b = a + start, b + start
    cuts = ep.edits.get("cuts") or []
    total = _overlap(cuts, a, b)
    for e in ep.edits.get("effects") or []:
        if e["kind"] == "speed" and (e.get("rate") or 1) > 1:
            lo, hi = max(e["start"], a), min(e["end"], b)
            if hi > lo:
                total += (hi - lo - _overlap(cuts, lo, hi)) * (1 - 1 / e["rate"])
    return total


def played_seconds(edits: dict | None, start: float, end: float) -> float:
    """How long [start, end] of the source takes to watch: cuts skipped, speed changes applied."""
    cuts = (edits or {}).get("cuts") or []
    total = end - start - _overlap(cuts, start, end)
    for e in (edits or {}).get("effects") or []:
        if e["kind"] == "speed" and e.get("rate") and e["rate"] != 1:
            lo, hi = max(e["start"], start), min(e["end"], end)
            if hi > lo:
                total -= (hi - lo - _overlap(cuts, lo, hi)) * (1 - 1 / e["rate"])
    return max(0.0, total)
