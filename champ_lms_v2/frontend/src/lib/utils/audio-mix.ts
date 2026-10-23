// Music and voice-overs from the video studio, played alongside the video.
// Nothing is mixed into the file on Bunny: each track is its own <audio>,
// kept in step with the video from frame to frame. A track runs in watch
// time from where it starts (see trackPosition), so it carries on smoothly
// over cuts and speed changes instead of jumping with the picture.
import { playedLength, trackPosition, trackVolume, type VideoEdits } from './video-edits';

export interface MixState {
  playing: boolean;
  // The viewer's own speed; tracks keep pace with it.
  rate: number;
  // 0 when the viewer has muted the player.
  master: number;
  // Where what plays ends (the part's end), for fade-outs.
  end: number;
}

export class AudioMixer {
  private els = new Map<string, HTMLAudioElement>();
  private urls: string[] = [];
  private loading = new Set<string>();
  private dead = false;

  /** `load` fetches a track's file (with the viewer's sign-in). */
  constructor(private load: (id: string) => Promise<Blob>) {}

  /** A file already in hand, just uploaded or recorded: no download needed. */
  add(id: string, blob: Blob) {
    if (this.els.has(id) || this.dead) return;
    this.els.set(id, this.make(blob));
  }

  /** Bring every track in step with the video at `t` (in the edits' time base). */
  sync(edits: VideoEdits | null | undefined, t: number, s: MixState) {
    const tracks = edits?.audio?.tracks ?? [];
    for (const [id, el] of this.els) if (!tracks.some(x => x.id === id) && !el.paused) el.pause();
    for (const tr of tracks) {
      const el = this.get(tr.id);
      if (!el) continue;
      const pos = trackPosition(edits ?? undefined, tr, t);
      if (pos === null) { if (!el.paused) el.pause(); continue; }
      if (!s.playing) {
        if (!el.paused) el.pause();
        if (Math.abs(el.currentTime - pos) > 0.3) el.currentTime = pos;
        continue;
      }
      el.volume = Math.min(1, trackVolume(tr, pos, playedLength(edits ?? undefined, t, s.end)) * s.master);
      if (Math.abs(el.playbackRate - s.rate) > 0.01) el.playbackRate = s.rate;
      if (Math.abs(el.currentTime - pos) > 0.35) el.currentTime = pos;
      if (el.paused) el.play().catch(() => {});
    }
  }

  pauseAll() { for (const el of this.els.values()) el.pause(); }

  destroy() {
    this.dead = true;
    this.pauseAll();
    this.els.clear();
    for (const u of this.urls) URL.revokeObjectURL(u);
  }

  private get(id: string): HTMLAudioElement | null {
    const el = this.els.get(id);
    if (el) return el;
    if (!this.loading.has(id)) {
      this.loading.add(id);
      this.load(id)
        .then(blob => { if (!this.dead && !this.els.has(id)) this.els.set(id, this.make(blob)); })
        .catch(() => { /* a missing track just doesn't play */ });
    }
    return null;
  }

  private make(blob: Blob): HTMLAudioElement {
    const url = URL.createObjectURL(blob);
    this.urls.push(url);
    const el = new Audio(url);
    el.preload = 'auto';
    return el;
  }
}

/** An audio file's length in seconds, or null when the browser can't tell. */
export async function durationOf(blob: Blob): Promise<number | null> {
  const url = URL.createObjectURL(blob);
  try {
    const a = new Audio();
    a.preload = 'metadata';
    a.src = url;
    await new Promise((res, rej) => { a.onloadedmetadata = res; a.onerror = rej; });
    if (!Number.isFinite(a.duration)) {
      // Recorded WebM often reports Infinity until the end has been seen.
      a.currentTime = 1e9;
      await new Promise(res => { a.ondurationchange = res; setTimeout(res, 1500); });
    }
    return Number.isFinite(a.duration) && a.duration > 0 ? a.duration : null;
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}
