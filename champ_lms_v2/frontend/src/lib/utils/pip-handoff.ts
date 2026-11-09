// Picture in picture that keeps playing after the learner leaves the page.
//
// In Chrome the floating window outlives its <video>: the element can leave
// the page and go on playing there. So when a player goes away while in
// picture in picture, its video is "carried": it keeps playing in the window,
// still skipping Video studio cuts, applying speed and mute effects, mixing in
// music, stopping at the end of a trimmed part and recording progress, and
// the window's own play/pause and skip buttons keep working.
//
//  - "Back to tab" in the window opens the video's page again, at the moment
//    the window had reached.
//  - Closing the window (which pauses the video) ends it.
//  - The player was replaced right away (next episode, a playlist click,
//    auto-advance): the new video takes the window over (Chrome allows that
//    without a click while one is in the window).
//  - Any other video opened later plays in its page, and the window closes;
//    if it's the same video, it carries on from where the window had got to.

import { goto } from '$app/navigation';
import { get } from 'svelte/store';
import { player } from '$lib/stores/player';
import type { AudioMixer } from '$lib/utils/audio-mix';
import { cutAt, mutedAt, speedAt, type VideoEdits } from '$lib/utils/video-edits';

type Pip = Document & { pictureInPictureElement: Element | null; exitPictureInPicture(): Promise<void> };

export const pipSupported = () =>
  typeof document !== 'undefined' && 'pictureInPictureEnabled' in document && !!(document as any).pictureInPictureEnabled;

export const inPip = (video: Element | null | undefined) =>
  !!video && typeof document !== 'undefined' && (document as Pip).pictureInPictureElement === video;

export function exitPip() {
  if (typeof document !== 'undefined' && (document as Pip).pictureInPictureElement) {
    (document as Pip).exitPictureInPicture().catch(() => {});
  }
}

// ---- the window's skip buttons (Media Session), one owner at a time -------
let skipOwner: object | null = null;
export function setSkip(owner: object, by: (seconds: number) => void) {
  if (typeof navigator === 'undefined' || !('mediaSession' in navigator)) return;
  skipOwner = owner;
  try {
    navigator.mediaSession.setActionHandler('seekbackward', d => by(-(d.seekOffset || 10)));
    navigator.mediaSession.setActionHandler('seekforward', d => by(d.seekOffset || 10));
  } catch { /* action not supported */ }
}
export function clearSkip(owner: object) {
  if (skipOwner !== owner || typeof navigator === 'undefined' || !('mediaSession' in navigator)) return;
  skipOwner = null;
  try {
    navigator.mediaSession.setActionHandler('seekbackward', null);
    navigator.mediaSession.setActionHandler('seekforward', null);
  } catch { /* action not supported */ }
}

// ---- carrying a video after its player has gone ----------------------------
export type CarryInfo = {
  video: HTMLVideoElement;
  hls: { destroy(): void } | null;
  mixer: AudioMixer | null;
  edits: VideoEdits | null;
  episodeId: string;
  /** The page to return to ("Back to tab"). */
  href: string;
  clipStart: number;
  clipEnd: number | null;
  track: boolean;
  skipLimit: number | null;
  /** Furthest point reached, in clip time. */
  furthest: number;
  /** The learner's own speed, volume and mute. */
  rate: number;
  volume: number;
  muted: boolean;
  /** Paused only for a freeze effect: play on. */
  resume: boolean;
};
type Carried = CarryInfo & { replacing: boolean; timer: ReturnType<typeof setTimeout> | null; off: () => void; done: boolean };

/** Time for the page to show what comes next once a player goes. */
const SETTLE_MS = 700;
/** How long a replacing player may take to load before it no longer counts as one. */
const WAIT_MS = 15000;

let carried: Carried | null = null;
// "Back to tab": the moment to reopen the video at.
let backAt: { episodeId: string; t: number; until: number } | null = null;

const rel = (c: CarryInfo) => Math.max(0, c.video.currentTime - c.clipStart);
const len = (c: CarryInfo) => Math.max(0, (c.clipEnd ?? (c.video.duration || 0)) - c.clipStart);
const tracking = (c: CarryInfo) => c.track && get(player).episodeId === c.episodeId;

/** A player is going away with its video in picture in picture: keep it playing there. */
export function carry(info: CarryInfo) {
  release(carried);
  // A player arriving before the page settles is a replacement.
  const c: Carried = { ...info, replacing: true, timer: null, off: () => {}, done: false };
  carried = c;
  const v = c.video;

  function onTime() {
    if (c.done) return;
    const t = rel(c);
    if (!v.seeking) {
      if (c.clipEnd !== null && v.currentTime >= c.clipEnd - 0.05) { v.pause(); finish(); return; }
      const cut = cutAt(c.edits?.cuts ?? [], t);
      if (cut) { v.currentTime = c.clipStart + cut.end; return; }
    }
    const fx = c.edits?.effects ?? [];
    const want = c.rate * speedAt(fx, t);
    if (Math.abs(v.playbackRate - want) > 0.001) v.playbackRate = want;
    const mute = c.muted || mutedAt(fx, t);
    if (v.muted !== mute) v.muted = mute;
    c.mixer?.sync(c.edits, t, { playing: !v.paused, rate: c.rate, master: c.muted ? 0 : c.volume, end: len(c) });
    if (!v.seeking) c.furthest = Math.max(c.furthest, t);
    if (tracking(c)) player.updateTime(Math.floor(t), Math.floor(len(c)));
  }
  // Once: a part ending with its video gets both its clip end and `ended`.
  let finished = false;
  function finish() {
    if (finished) return;
    finished = true;
    if (tracking(c)) player.complete().catch(() => {});
  }
  const onPause = () => c.mixer?.pauseAll();
  // The window's close button pauses the video first; "Back to tab" doesn't.
  function onLeave() {
    const back = !v.paused && !c.done;
    const t = rel(c);
    release(c);
    if (back) {
      backAt = { episodeId: c.episodeId, t, until: Date.now() + 60000 };
      goto(c.href).catch(() => {});
    }
  }
  v.addEventListener('timeupdate', onTime);
  v.addEventListener('pause', onPause);
  v.addEventListener('ended', finish);
  v.addEventListener('leavepictureinpicture', onLeave);
  c.off = () => {
    v.removeEventListener('timeupdate', onTime);
    v.removeEventListener('pause', onPause);
    v.removeEventListener('ended', finish);
    v.removeEventListener('leavepictureinpicture', onLeave);
  };
  // Skips from the window: within the part, and no further ahead than the
  // course's skip limit allows (the server holds progress to it too).
  setSkip(c, by => {
    let to = rel(c) + by;
    if (by > 0 && c.skipLimit != null) to = Math.min(to, c.furthest + c.skipLimit);
    v.currentTime = c.clipStart + Math.min(Math.max(0, to), len(c) || Infinity);
  });
  if (c.resume) v.play().catch(() => {});
  // Replaced at once (the page shows the next video loading), or left?
  c.timer = setTimeout(() => {
    if (carried !== c) return;
    c.replacing = !!document.querySelector('[data-video-pending], [data-video-player]');
    if (c.replacing) c.timer = setTimeout(() => { c.replacing = false; }, WAIT_MS);
  }, SETTLE_MS);
}

/**
 * Stops carrying: the window closes (unless another video has taken it) and
 * the video's stream is freed. `handedOver`: a new player is already
 * tracking, so its progress tracking is left alone.
 */
function release(c: Carried | null, handedOver = false) {
  if (!c || c.done) return;
  c.done = true;
  if (carried === c) carried = null;
  if (c.timer) clearTimeout(c.timer);
  c.off();
  clearSkip(c);
  if (!handedOver && tracking(c)) { player.sync(); player.stopTracking(); }
  if (inPip(c.video)) exitPip();
  c.video.pause();
  c.mixer?.destroy();
  c.hls?.destroy();
}

/**
 * A new player is starting. Returns where to start it from when it's the
 * video the window was playing (or "Back to tab" brought the learner here).
 * Unless it replaced the carried video at once, the carried video stops.
 */
export function arrive(episodeId: string): number | null {
  let t: number | null = null;
  if (backAt && backAt.episodeId === episodeId && Date.now() < backAt.until) t = backAt.t;
  backAt = null;
  const c = carried;
  if (c) {
    if (c.episodeId === episodeId) t = rel(c);
    if (!c.replacing) release(c);
    // It plays on until the new video takes the window: record where it got
    // to now, before the new player takes over progress tracking.
    else if (tracking(c)) player.sync();
  }
  return t;
}

/** The new player's video has loaded: it takes over the window from a video it replaced. */
export function takeOver(video: HTMLVideoElement) {
  const c = carried;
  if (!c) return;
  if (!c.replacing || !inPip(c.video)) { release(c, true); return; }
  c.video.pause();
  (video as any).requestPictureInPicture().then(() => release(c, true), () => release(c, true));
}
