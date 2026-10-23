// Video studio edits, as the players apply them. Mirrors the backend's
// services/video_edits.py: nothing on Bunny is cut, so every edit is applied
// while the video plays. The learner's player gets them in clip time; the
// studio works in source time. Every helper here takes one time base and
// doesn't care which.
import type { TranscriptSegment } from '$lib/api/client';

export interface Cut { start: number; end: number; }
export interface Chapter { start: number; title: string; }
export type OverlayPosition = 'top' | 'center' | 'bottom' | 'lower-third';
export type OverlayStyle = 'title' | 'callout' | 'label' | 'quote';
export type OverlayAnim = 'rise' | 'fade' | 'pop' | 'type' | 'none';
export interface Overlay {
  start: number; end: number; text: string; subtext?: string | null;
  position: OverlayPosition; style: OverlayStyle;
  // Optional, for overlays saved before they existed: m, rise, the style's colour.
  size?: 's' | 'm' | 'l'; anim?: OverlayAnim; color?: string | null;
}
export type CaptionPreset = 'classic' | 'bold' | 'pop' | 'karaoke' | 'minimal';
export type CaptionFont = 'sans' | 'display' | 'serif' | 'rounded' | 'mono';
export interface CaptionStyle {
  preset: CaptionPreset; position: 'bottom' | 'middle' | 'top'; size: 's' | 'm' | 'l'; default_on: boolean;
  font: CaptionFont; color: string; highlight: string; uppercase: boolean;
}
export interface Look {
  brightness: number; contrast: number; saturation: number;
  zoom: number; focus_x: number; focus_y: number; fade_in: boolean; fade_out: boolean;
}
export interface Brand {
  watermark: boolean; position: 'tl' | 'tr' | 'bl' | 'br'; opacity: number;
  progress_bar: boolean; progress_color: string;
}
/**
 * A stretch of the video played differently, without cutting it:
 *   zoom   punch in to `scale` about (x, y), easing in and out
 *   speed  play at `rate` (a screen loading, typing, a slow demo)
 *   mute   silence the sound (a name, a phone ringing)
 *   blur   hide a box of the picture: x, y, w, h in % of the frame
 */
export type EffectKind = 'zoom' | 'speed' | 'mute' | 'blur';
export interface Effect {
  kind: EffectKind; start: number; end: number;
  scale?: number; rate?: number;
  x?: number; y?: number; w?: number; h?: number; mode?: 'blur' | 'black';
}
export interface VideoEdits {
  cuts?: Cut[]; chapters?: Chapter[]; overlays?: Overlay[]; effects?: Effect[];
  captions?: CaptionStyle; look?: Look; brand?: Brand;
}

export const CAPTION_DEFAULTS: CaptionStyle = {
  preset: 'classic', position: 'bottom', size: 'm', default_on: false,
  font: 'sans', color: '#ffffff', highlight: '#ffd23f', uppercase: false,
};
export const LOOK_DEFAULTS: Look = {
  brightness: 100, contrast: 100, saturation: 100, zoom: 1, focus_x: 50, focus_y: 50, fade_in: false, fade_out: false,
};
export const BRAND_DEFAULTS: Brand = {
  watermark: false, position: 'tr', opacity: 0.85, progress_bar: false, progress_color: '#ff3b45',
};
/** What a new effect of each kind starts as. */
export const EFFECT_DEFAULTS: Record<EffectKind, Partial<Effect>> = {
  zoom: { scale: 1.4, x: 50, y: 50 },
  speed: { rate: 2 },
  mute: {},
  blur: { x: 35, y: 35, w: 30, h: 22, mode: 'blur' },
};

/** The cut playing at `t`, if any: playback jumps to its end. */
export function cutAt(cuts: Cut[] | undefined, t: number): Cut | null {
  for (const c of cuts ?? []) if (t >= c.start - 0.02 && t < c.end - 0.05) return c;
  return null;
}

/** Seconds of cuts between a and b: what a jump over them skips without playing. */
export function cutSecondsBetween(cuts: Cut[] | undefined, a: number, b: number): number {
  let total = 0;
  for (const c of cuts ?? []) {
    const lo = Math.max(c.start, a), hi = Math.min(c.end, b);
    if (hi > lo) total += hi - lo;
  }
  return total;
}

/**
 * How long [from, to] takes to watch at normal speed: its cuts skipped, and
 * its sped-up (or slowed) stretches taking their own time.
 */
export function playedLength(edits: Pick<VideoEdits, 'cuts' | 'effects'> | undefined, from: number, to: number): number {
  let total = to - from - cutSecondsBetween(edits?.cuts, from, to);
  for (const e of edits?.effects ?? []) {
    if (e.kind !== 'speed' || !e.rate || e.rate === 1) continue;
    const lo = Math.max(e.start, from), hi = Math.min(e.end, to);
    if (hi <= lo) continue;
    const plays = hi - lo - cutSecondsBetween(edits?.cuts, lo, hi);
    total -= plays * (1 - 1 / e.rate);
  }
  return Math.max(0, total);
}

export function effectsAt(effects: Effect[] | undefined, t: number, kind?: EffectKind): Effect[] {
  return (effects ?? []).filter(e => t >= e.start && t < e.end && (!kind || e.kind === kind));
}

/** The playback speed the edits set at `t`: 1 outside every speed effect. */
export function speedAt(effects: Effect[] | undefined, t: number): number {
  return effectsAt(effects, t, 'speed')[0]?.rate ?? 1;
}

export function mutedAt(effects: Effect[] | undefined, t: number): boolean {
  return effectsAt(effects, t, 'mute').length > 0;
}

/**
 * Zoom and focus at `t`: the look's steady framing, with any zoom effect
 * eased in over its first moments and out over its last.
 */
export function frameAt(look: Look | undefined, effects: Effect[] | undefined, t: number): { scale: number; x: number; y: number } {
  const base = { scale: look?.zoom ?? 1, x: look?.focus_x ?? 50, y: look?.focus_y ?? 50 };
  const z = effectsAt(effects, t, 'zoom')[0];
  if (!z) return base;
  const ramp = Math.min(0.45, (z.end - z.start) / 3);
  const lin = Math.min(1, (t - z.start) / ramp, (z.end - t) / ramp);
  const f = lin * lin * (3 - 2 * lin); // smoothstep
  const mix = (a: number, b: number) => a + (b - a) * f;
  return { scale: mix(base.scale, Math.max(base.scale, z.scale ?? 1.4)), x: mix(base.x, z.x ?? 50), y: mix(base.y, z.y ?? 50) };
}

/** CSS for the framing at `t`, or '' when the picture is untouched. */
export function frameStyle(look: Look | undefined, effects: Effect[] | undefined, t: number): string {
  const f = frameAt(look, effects, t);
  if (f.scale <= 1.001) return '';
  return `transform: scale(${f.scale.toFixed(4)}); transform-origin: ${f.x}% ${f.y}%;`;
}

/**
 * Filler words dropped from a caption line, and a word said twice in a row
 * said once. Only the caption text changes: the sound is untouched.
 */
export function stripFillers(text: string): string {
  return text
    .replace(/(^|[\s,.;:!?-])(?:u+m+|u+h+m*|e+r+m*|h+m+|a+h+)(?=$|[\s,.;:!?-])/gi, '$1')
    .replace(/\b(\w+)(\s+\1\b)+/gi, '$1')
    .replace(/\s+([,.;:!?])/g, '$1')
    .replace(/([,;:])(?:\s*[,;:])+/g, '$1')
    .replace(/^[\s,.;:-]+/, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/** Sorted, with overlapping ranges joined. */
export function mergeCuts(cuts: Cut[]): Cut[] {
  const out: Cut[] = [];
  for (const c of [...cuts].sort((a, b) => a.start - b.start)) {
    const last = out[out.length - 1];
    if (last && c.start <= last.end + 0.05) last.end = Math.max(last.end, c.end);
    else out.push({ start: c.start, end: c.end });
  }
  return out.filter(c => c.end - c.start >= 0.5);
}

/** The chapter playing at `t`: its index, or -1 before the first. */
export function chapterIndexAt(chapters: Chapter[] | undefined, t: number): number {
  let i = -1;
  (chapters ?? []).forEach((c, n) => { if (c.start <= t + 0.05) i = n; });
  return i;
}

export function overlaysAt(overlays: Overlay[] | undefined, t: number): Overlay[] {
  return (overlays ?? []).filter(o => t >= o.start && t < o.end);
}

/** CSS filter for the look's colour settings, or '' when untouched. */
export function lookFilter(look: Look | undefined): string {
  if (!look) return '';
  const parts = [];
  if (look.brightness !== 100) parts.push(`brightness(${look.brightness}%)`);
  if (look.contrast !== 100) parts.push(`contrast(${look.contrast}%)`);
  if (look.saturation !== 100) parts.push(`saturate(${look.saturation}%)`);
  return parts.join(' ');
}

/** Opacity of the black fade over the video at `t`, for a range that plays from..to. */
export function fadeOpacity(look: Look | undefined, t: number, from: number, to: number): number {
  if (!look) return 0;
  const F = 1.2;
  let o = 0;
  if (look.fade_in && t < from + F) o = Math.max(o, 1 - Math.max(0, t - from) / F);
  if (look.fade_out && to > from && t > to - F) o = Math.max(o, 1 - Math.max(0, to - t) / F);
  return Math.min(1, Math.max(0, o));
}

/** The caption line on screen at `t`, if any. */
export function segmentAt(segments: TranscriptSegment[], t: number): TranscriptSegment | null {
  for (let i = segments.length - 1; i >= 0; i--) {
    const s = segments[i];
    if (s.start <= t + 0.1) return t < Math.max(s.end, s.start + 0.5) + 0.3 ? s : null;
  }
  return null;
}

/**
 * The line's words and which one is being said at `t`. Transcripts are timed
 * by line, not word, so each word gets a share of the line's time by its
 * length, which is close enough for the word highlight to follow the speaker.
 */
export function wordsAt(seg: TranscriptSegment, t: number): { words: string[]; active: number } {
  const words = seg.text.split(/\s+/).filter(Boolean);
  const span = Math.max(0.5, seg.end - seg.start);
  const weights = words.map(w => w.length + 2);
  const total = weights.reduce((a, b) => a + b, 0) || 1;
  const into = ((t - seg.start) / span) * total;
  let acc = 0, active = words.length - 1;
  for (let i = 0; i < words.length; i++) {
    acc += weights[i];
    if (into < acc) { active = i; break; }
  }
  return { words, active: t < seg.start ? -1 : active };
}

/** Whether a package changes anything a learner sees. */
export function hasEdits(e: VideoEdits | null | undefined): boolean {
  return !!e && Object.keys(e).length > 0;
}
