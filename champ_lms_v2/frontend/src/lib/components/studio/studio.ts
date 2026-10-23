// State shared by the video studio's stage, timeline and panels, through
// Svelte context. Everything is in source time: seconds of the whole Bunny
// video, which is what the studio's timeline shows.
import { getContext, setContext } from 'svelte';
import { derived, get, writable, type Readable, type Writable } from 'svelte/store';
import type { StudioEpisode, StudioTighten, TranscriptSegment } from '$lib/api/client';
import {
  BRAND_DEFAULTS, CAPTION_DEFAULTS, EFFECT_DEFAULTS, LOOK_DEFAULTS, mergeCuts, playedLength,
  type Brand, type CaptionStyle, type Chapter, type Cut, type Effect, type EffectKind, type Look, type Overlay,
  type VideoEdits,
} from '$lib/utils/video-edits';

// Keep in step with backend services/clips.py MIN_CLIP_SECONDS.
export const MIN_PART = 10;

export interface FullEdits {
  cuts: Cut[]; chapters: Chapter[]; overlays: Overlay[]; effects: Effect[];
  captions: CaptionStyle; look: Look; brand: Brand;
}
/**
 * What Save sends: the kept part, the splits, and the edits on top. The
 * caption lines ride along so fixing a word is undoable like any edit; Save
 * stores them as the transcript when they changed.
 */
export interface Doc { start: number; end: number; splits: number[]; edits: FullEdits; segments: TranscriptSegment[]; }
export interface Part { from: number; to: number; len: number; played: number; }
export type Selected = { kind: 'cut' | 'chapter' | 'overlay' | 'effect'; index: number } | null;
export interface PreviewRun { from: number; to: number; label: string; seq: number | null; }
export type Tab = 'ai' | 'trim' | 'cuts' | 'captions' | 'text' | 'effects' | 'chapters' | 'look' | 'details' | 'thumb';

export const round = (x: number) => Math.round(x * 100) / 100;

export function fullEdits(e: VideoEdits | null | undefined): FullEdits {
  return {
    cuts: (e?.cuts ?? []).map(c => ({ ...c })),
    chapters: (e?.chapters ?? []).map(c => ({ ...c })),
    overlays: (e?.overlays ?? []).map(o => ({ ...o })),
    effects: (e?.effects ?? []).map(x => ({ ...EFFECT_DEFAULTS[x.kind], ...x })),
    captions: { ...CAPTION_DEFAULTS, ...(e?.captions ?? {}) },
    look: { ...LOOK_DEFAULTS, ...(e?.look ?? {}) },
    brand: { ...BRAND_DEFAULTS, ...(e?.brand ?? {}) },
  };
}

export function docFrom(ep: StudioEpisode): Doc {
  const length = ep.source_duration_seconds ?? 0;
  return {
    start: ep.clip_start ?? 0, end: ep.clip_end ?? length, splits: [], edits: fullEdits(ep.edits),
    segments: ep.transcript_segments.map(s => ({ ...s })),
  };
}

export function partsOf(d: Doc): Part[] {
  const pts = [d.start, ...[...d.splits].sort((a, b) => a - b), d.end];
  return pts.slice(1).map((to, i) => ({
    from: pts[i], to, len: to - pts[i], played: playedLength(d.edits, pts[i], to),
  }));
}

/** Cuts with [a, b] taken out of them, splitting a cut that spans it. */
export function subtractRange(cuts: Cut[], a: number, b: number): Cut[] {
  const out: Cut[] = [];
  for (const c of cuts) {
    if (c.end <= a || c.start >= b) { out.push(c); continue; }
    if (c.start < a) out.push({ start: c.start, end: a });
    if (c.end > b) out.push({ start: b, end: c.end });
  }
  return out.filter(c => c.end - c.start >= 0.5);
}

export function addCut(d: Doc, a: number, b: number) {
  d.edits.cuts = mergeCuts([...d.edits.cuts, { start: round(Math.min(a, b)), end: round(Math.max(a, b)) }]);
}

export interface Studio {
  ep: Writable<StudioEpisode>;
  length: number;
  doc: Writable<Doc>;
  parts: Readable<Part[]>;
  time: Writable<number>;
  playing: Writable<boolean>;
  rate: Writable<number>;
  mark: Writable<{ in: number | null; out: number | null }>;
  selected: Writable<Selected>;
  preview: Writable<PreviewRun | null>;
  tab: Writable<Tab>;
  ccOn: Writable<boolean>;
  tighten: Writable<StudioTighten[] | null>;
  notice: Writable<{ text: string; tone: 'ok' | 'bad' } | null>;
  canUndo: Readable<boolean>;
  canRedo: Readable<boolean>;
  /** Anything changed since the last save (or since opening). */
  dirty: Readable<boolean>;
  /** The doc as it is now is what's saved. */
  markSaved(): void;
  /**
   * A transcript saved outside the doc (generated or uploaded here): the doc,
   * the saved state and the undo history all take its lines, so it isn't
   * saved again or undone away.
   */
  adoptSegments(segments: TranscriptSegment[]): void;
  /** Snapshot for undo, then change the doc. A `key` folds rapid edits (typing) into one step. */
  commit(fn: (d: Doc) => void, key?: string): void;
  /** Start of a drag: one undo step for the whole gesture. */
  begin(): void;
  /** Change the doc during a drag, without a new undo step. */
  live(fn: (d: Doc) => void): void;
  /** End of a drag: drop its undo step if nothing changed. */
  end(): void;
  undo(): void;
  redo(): void;
  reset(ep: StudioEpisode): void;
  attach(el: HTMLVideoElement | null): void;
  video(): HTMLVideoElement | null;
  seek(t: number): void;
  play(): void;
  pause(): void;
  toggle(): void;
  playRange(from: number, to: number, label: string, seq?: number | null): void;
  stopPreview(): void;
  say(text: string, tone?: 'ok' | 'bad'): void;
}

const KEY = Symbol('video-studio');

export function createStudio(initial: StudioEpisode): Studio {
  const length = initial.source_duration_seconds ?? 0;
  const ep = writable(initial);
  const doc = writable(docFrom(initial));
  const past = writable<string[]>([]);
  const future = writable<string[]>([]);
  const preview = writable<PreviewRun | null>(null);
  const baseline = writable(JSON.stringify(get(doc)));
  const notice = writable<{ text: string; tone: 'ok' | 'bad' } | null>(null);
  let videoEl: HTMLVideoElement | null = null;
  let lastKey = '';
  let lastAt = 0;
  let dragSnap: string | null = null;
  let noticeTimer: ReturnType<typeof setTimeout> | null = null;

  const snap = () => JSON.stringify(get(doc));
  const push = (s: string) => {
    past.update(p => [...p.slice(-99), s]);
    future.set([]);
  };

  const s: Studio = {
    ep,
    length,
    doc,
    parts: derived(doc, partsOf),
    time: writable(initial.clip_start ?? 0),
    playing: writable(false),
    rate: writable(1),
    mark: writable({ in: null, out: null }),
    selected: writable(null),
    preview,
    tab: writable('ai'),
    ccOn: writable(false),
    tighten: writable(null),
    notice,
    canUndo: derived(past, p => p.length > 0),
    canRedo: derived(future, f => f.length > 0),
    dirty: derived([doc, baseline], ([d, b]) => JSON.stringify(d) !== b),
    markSaved() { baseline.set(snap()); },
    adoptSegments(segments) {
      const swap = (j: string) => { const d = JSON.parse(j); d.segments = segments.map(x => ({ ...x })); return JSON.stringify(d); };
      ep.update(e => ({ ...e, transcript_segments: segments }));
      doc.update(d => { d.segments = segments.map(x => ({ ...x })); return d; });
      baseline.update(swap);
      past.update(p => p.map(swap));
      future.update(f => f.map(swap));
    },
    commit(fn, key) {
      const now = Date.now();
      if (!key || key !== lastKey || now - lastAt > 1500) push(snap());
      lastKey = key ?? '';
      lastAt = now;
      doc.update(d => { fn(d); return d; });
    },
    begin() { dragSnap = snap(); lastKey = ''; },
    live(fn) { doc.update(d => { fn(d); return d; }); },
    end() {
      if (dragSnap !== null && dragSnap !== snap()) push(dragSnap);
      dragSnap = null;
    },
    undo() {
      const p = get(past);
      if (!p.length) return;
      future.update(f => [...f, snap()]);
      past.set(p.slice(0, -1));
      doc.set(JSON.parse(p[p.length - 1]));
      lastKey = '';
      s.selected.set(null);
    },
    redo() {
      const f = get(future);
      if (!f.length) return;
      past.update(p => [...p, snap()]);
      future.set(f.slice(0, -1));
      doc.set(JSON.parse(f[f.length - 1]));
      lastKey = '';
      s.selected.set(null);
    },
    reset(next) {
      ep.set(next);
      doc.set(docFrom(next));
      baseline.set(snap());
      past.set([]);
      future.set([]);
      s.selected.set(null);
      s.mark.set({ in: null, out: null });
      s.tighten.set(null);
    },
    attach(el) { videoEl = el; },
    video: () => videoEl,
    seek(t) {
      preview.set(null);
      if (videoEl) videoEl.currentTime = Math.min(length, Math.max(0, t));
      s.time.set(Math.min(length, Math.max(0, t)));
    },
    play() { videoEl?.play().catch(() => {}); },
    pause() { videoEl?.pause(); },
    toggle() {
      if (!videoEl) return;
      if (videoEl.paused) s.play(); else { preview.set(null); s.pause(); }
    },
    playRange(from, to, label, seq = null) {
      if (!videoEl) return;
      preview.set({ from, to, label, seq });
      videoEl.currentTime = from;
      s.play();
    },
    stopPreview() { preview.set(null); },
    say(text, tone = 'ok') {
      notice.set({ text, tone });
      if (noticeTimer) clearTimeout(noticeTimer);
      noticeTimer = setTimeout(() => notice.set(null), tone === 'bad' ? 6000 : 3500);
    },
  };
  return s;
}

export function provideStudio(s: Studio) { setContext(KEY, s); }
export function useStudio(): Studio { return getContext<Studio>(KEY); }

/** Gaps between transcript lines of at least `min` seconds inside [from, to], padded so words aren't clipped. */
export function deadAir(
  segments: { start: number; end: number }[], from: number, to: number, min: number, pad = 0.3,
): Cut[] {
  const lines = segments.filter(s => s.end > from && s.start < to).sort((a, b) => a.start - b.start);
  if (!lines.length) return [];
  const gaps: Cut[] = [];
  let cursor = from;
  for (const l of lines) {
    if (l.start - cursor >= min) gaps.push({ start: round(cursor === from ? from : cursor + pad), end: round(l.start - pad) });
    cursor = Math.max(cursor, l.end);
  }
  if (to - cursor >= min) gaps.push({ start: round(cursor + pad), end: round(to) });
  return gaps.filter(g => g.end - g.start >= 0.5);
}

// ---- actions shared by the panels and the keyboard ---------------------------
export function trimStart(st: Studio, x: number) {
  st.commit(d => {
    d.start = round(Math.max(0, Math.min(x, d.end - MIN_PART)));
    d.splits = d.splits.filter(s => s > d.start + 0.01);
  });
}

export function trimEnd(st: Studio, x: number) {
  st.commit(d => {
    d.end = round(Math.min(st.length, Math.max(x, d.start + MIN_PART)));
    d.splits = d.splits.filter(s => s < d.end - 0.01);
  });
}

export function splitAt(st: Studio, x: number) {
  const d = get(st.doc);
  x = round(x);
  if (x <= d.start + MIN_PART - 0.01 || x >= d.end - MIN_PART + 0.01) {
    st.say(`A split needs at least ${MIN_PART} seconds on each side.`, 'bad');
    return;
  }
  if (d.splits.some(s => Math.abs(s - x) < MIN_PART)) { st.say('There is already a split right there.', 'bad'); return; }
  st.commit(dd => { dd.splits = [...dd.splits, x]; });
}

/** Cut the marked range (I and O), if there is one. */
export function cutMarked(st: Studio) {
  const m = get(st.mark);
  if (m.in === null || m.out === null || Math.abs(m.out - m.in) < 0.5) {
    st.say('Mark a range first: I at its start, O at its end, or Shift-drag on the timeline.', 'bad');
    return;
  }
  st.commit(d => addCut(d, m.in!, m.out!));
  st.mark.set({ in: null, out: null });
  st.say(`Cut ${clockShort(Math.abs(m.out - m.in))}. Learners skip it.`);
}

/** Remove whatever is selected on the timeline. */
export function removeSelected(st: Studio) {
  const sel = get(st.selected);
  if (!sel) return false;
  st.commit(d => {
    if (sel.kind === 'cut') d.edits.cuts.splice(sel.index, 1);
    else if (sel.kind === 'chapter') d.edits.chapters.splice(sel.index, 1);
    else if (sel.kind === 'effect') d.edits.effects.splice(sel.index, 1);
    else d.edits.overlays.splice(sel.index, 1);
  });
  st.selected.set(null);
  return true;
}

export const EFFECT_NAMES: Record<EffectKind, string> = { zoom: 'Zoom', speed: 'Speed', mute: 'Mute', blur: 'Blur' };

/**
 * Add an effect over the marked range, or from the playhead for a few
 * seconds, and select it.
 */
export function addEffect(st: Studio, kind: EffectKind, patch: Partial<Effect> = {}): number {
  const m = get(st.mark);
  const t = get(st.time);
  const marked = m.in !== null && m.out !== null && Math.abs(m.out - m.in) >= 0.5;
  const start = round(marked ? Math.min(m.in!, m.out!) : t);
  const end = round(marked ? Math.max(m.in!, m.out!) : Math.min(st.length, t + (kind === 'zoom' ? 4 : 6)));
  if (end - start < 0.5) { st.say('Move the playhead back a little: the effect needs room before the end.', 'bad'); return -1; }
  const e: Effect = { kind, start, end, ...EFFECT_DEFAULTS[kind], ...patch };
  let index = 0;
  st.commit(d => {
    d.edits.effects = [...d.edits.effects, e].sort((a, b) => a.start - b.start);
    index = d.edits.effects.indexOf(e);
  });
  if (marked) st.mark.set({ in: null, out: null });
  st.selected.set({ kind: 'effect', index });
  return index;
}

export function clockShort(s: number): string {
  return s < 60 ? `${Math.round(s * 10) / 10} s` : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;
}
