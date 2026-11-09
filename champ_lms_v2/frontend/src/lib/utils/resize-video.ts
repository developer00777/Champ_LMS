/**
 * The video resizer: turn any video into a new shape (9:16 for a short or a
 * reel, 4:5, 1:1, 16:9 or any size), in this browser.
 *
 * The preview and the export draw every frame with the same function
 * (drawFrame), so the file that comes out is exactly what the preview showed.
 * The export plays the video once, in real time, onto a canvas the size of
 * the output and records it with its sound (MediaRecorder): MP4 where the
 * browser can record MP4 (Chrome, Edge, Safari), WebM elsewhere (Firefox).
 * Bunny accepts both. Nothing is sent anywhere until the admin publishes.
 */

export interface SizePreset {
  key: string; label: string; ratio: string; use: string; width: number; height: number;
}

export const SIZE_PRESETS: SizePreset[] = [
  { key: '9:16', label: 'Short / Reel', ratio: '9:16', use: 'Shorts, Reels, TikTok, Stories', width: 1080, height: 1920 },
  { key: '4:5', label: 'Portrait', ratio: '4:5', use: 'Feed posts', width: 1080, height: 1350 },
  { key: '1:1', label: 'Square', ratio: '1:1', use: 'Feeds, previews', width: 1080, height: 1080 },
  { key: '16:9', label: 'Landscape', ratio: '16:9', use: 'Course videos, YouTube', width: 1920, height: 1080 },
];

export type FitMode = 'cover' | 'contain';
export type Backdrop = 'blur' | 'color' | 'black';

export interface ResizeOptions {
  width: number;
  height: number;
  fit: FitMode;          // cover = fill and crop; contain = the whole picture
  backdrop: Backdrop;    // what fills the space around a contained picture
  color: string;         // for backdrop 'color'
  zoom: number;          // 1..3, on top of the fit
  x: number;             // 0..100: where the picture sits horizontally
  y: number;             // 0..100: and vertically
  start: number;         // trim, seconds of the source
  end: number;
}

export interface VideoMeta { width: number; height: number; duration: number; }

export interface RenderResult {
  blob: Blob; mime: string; ext: 'mp4' | 'webm';
  width: number; height: number; duration: number;
}

export class RenderCancelled extends Error {
  constructor() { super('Rendering was cancelled'); }
}

/** Width, height and length of a video file, read without playing it. */
export function readVideoMeta(file: Blob): Promise<VideoMeta> {
  return new Promise((resolve, reject) => {
    const v = document.createElement('video');
    const url = URL.createObjectURL(file);
    v.preload = 'metadata';
    v.muted = true;
    const done = () => URL.revokeObjectURL(url);
    v.onloadedmetadata = () => {
      // Some recorded WebM files report Infinity until they are read through.
      if (!isFinite(v.duration)) {
        v.currentTime = 1e7;
        v.ontimeupdate = () => {
          v.ontimeupdate = null;
          resolve({ width: v.videoWidth, height: v.videoHeight, duration: v.duration });
          done();
        };
        return;
      }
      resolve({ width: v.videoWidth, height: v.videoHeight, duration: v.duration });
      done();
    };
    v.onerror = () => { done(); reject(new Error("This browser can't read that video. Try an MP4 (H.264) file.")); };
    v.src = url;
  });
}

/** The named size nearest to a width and height, e.g. 1920x1080 -> 16:9. */
export function nearestPreset(width: number, height: number): SizePreset {
  const r = width / height;
  return SIZE_PRESETS.reduce((best, p) =>
    Math.abs(p.width / p.height - r) < Math.abs(best.width / best.height - r) ? p : best);
}

// Common shapes, for naming a source file's size (a 4:3 slide recording is
// "4:3", not "≈ 1:1").
const NAMED_RATIOS: [string, number][] = [
  ['9:16', 9 / 16], ['2:3', 2 / 3], ['3:4', 3 / 4], ['4:5', 4 / 5], ['1:1', 1],
  ['5:4', 5 / 4], ['4:3', 4 / 3], ['3:2', 3 / 2], ['16:10', 16 / 10], ['16:9', 16 / 9], ['21:9', 21 / 9],
];

export function ratioLabel(width?: number | null, height?: number | null): string {
  if (!width || !height) return '';
  const r = width / height;
  const [name, v] = NAMED_RATIOS.reduce((best, n) => (Math.abs(n[1] - r) < Math.abs(best[1] - r) ? n : best));
  return Math.abs(v - r) / v < 0.02 ? name : `≈ ${name}`;
}

// A tiny canvas, scaled up, is a cheap blur that works in every browser
// (Safari has no canvas filter).
let blurCanvas: HTMLCanvasElement | null = null;

/** Draw one frame of `video` onto `ctx` (sized w x h) the way `o` says. */
export function drawFrame(ctx: CanvasRenderingContext2D, video: HTMLVideoElement, w: number, h: number, o: ResizeOptions) {
  const vw = video.videoWidth, vh = video.videoHeight;
  if (!vw || !vh) return;
  const cover = Math.max(w / vw, h / vh);
  const contain = Math.min(w / vw, h / vh);

  ctx.save();
  ctx.fillStyle = o.backdrop === 'color' ? o.color : '#000';
  ctx.fillRect(0, 0, w, h);

  if (o.fit === 'contain' && o.backdrop === 'blur') {
    if (!blurCanvas) blurCanvas = document.createElement('canvas');
    const bw = 24, bh = Math.max(8, Math.round((24 * h) / w));
    blurCanvas.width = bw; blurCanvas.height = bh;
    const b = blurCanvas.getContext('2d');
    if (b) {
      const s = Math.max(bw / vw, bh / vh);
      b.drawImage(video, (bw - vw * s) / 2, (bh - vh * s) / 2, vw * s, vh * s);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      // Drawn a little larger than the frame, so the soft edges sit outside it.
      ctx.drawImage(blurCanvas, -w * 0.08, -h * 0.08, w * 1.16, h * 1.16);
      ctx.fillStyle = 'rgba(0, 0, 0, 0.32)';
      ctx.fillRect(0, 0, w, h);
    }
  }

  const s = (o.fit === 'cover' ? cover : contain) * o.zoom;
  const dw = vw * s, dh = vh * s;
  // x/y slide the picture along whatever room there is: across the overflow
  // when it is bigger than the frame, across the gap when it is smaller.
  const dx = (w - dw) * (o.x / 100);
  const dy = (h - dh) * (o.y / 100);
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(video, dx, dy, dw, dh);
  ctx.restore();
}

const MIME_CHOICES: [string, 'mp4' | 'webm'][] = [
  ['video/mp4;codecs=avc1.640028,mp4a.40.2', 'mp4'],
  ['video/mp4;codecs=avc1,mp4a', 'mp4'],
  ['video/mp4', 'mp4'],
  ['video/webm;codecs=vp9,opus', 'webm'],
  ['video/webm;codecs=vp8,opus', 'webm'],
  ['video/webm', 'webm'],
];

export function recordingFormat(): { mime: string; ext: 'mp4' | 'webm' } | null {
  if (typeof MediaRecorder === 'undefined') return null;
  for (const [mime, ext] of MIME_CHOICES) if (MediaRecorder.isTypeSupported(mime)) return { mime, ext };
  return null;
}

function once(el: EventTarget, ev: string): Promise<void> {
  return new Promise(r => el.addEventListener(ev, () => r(), { once: true }));
}

/**
 * Render `source` at the size in `o`, trimmed to o.start..o.end. Plays in real
 * time; `onProgress` gets 0..1. A hidden tab would stall the browser's frame
 * clock, so the render pauses while the tab is hidden and carries on after.
 */
export async function renderResized(
  source: Blob,
  o: ResizeOptions,
  onProgress: (p: number, note?: string) => void,
  signal?: AbortSignal,
): Promise<RenderResult> {
  const fmt = recordingFormat();
  if (!fmt) throw new Error("This browser can't record video. Use a recent Chrome, Edge, Firefox or Safari.");

  const url = URL.createObjectURL(source);
  const video = document.createElement('video');
  video.src = url;
  video.playsInline = true;
  video.preload = 'auto';
  video.crossOrigin = 'anonymous';
  await once(video, 'loadedmetadata');

  const canvas = document.createElement('canvas');
  // Encoders want even dimensions.
  canvas.width = Math.round(o.width / 2) * 2;
  canvas.height = Math.round(o.height / 2) * 2;
  const ctx = canvas.getContext('2d', { alpha: false })!;

  // Sound: routed into the recording only, not to the speakers.
  const AC: typeof AudioContext = (window as any).AudioContext ?? (window as any).webkitAudioContext;
  const audio = new AC();
  const src = audio.createMediaElementSource(video);
  const dest = audio.createMediaStreamDestination();
  src.connect(dest);

  const stream = canvas.captureStream(30);
  for (const t of dest.stream.getAudioTracks()) stream.addTrack(t);
  const pixels = canvas.width * canvas.height;
  const recorder = new MediaRecorder(stream, {
    mimeType: fmt.mime,
    videoBitsPerSecond: Math.min(12_000_000, Math.max(2_500_000, Math.round(pixels * 30 * 0.12))),
    audioBitsPerSecond: 160_000,
  });
  const chunks: Blob[] = [];
  recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };

  const start = Math.max(0, o.start);
  const end = Math.min(o.end || video.duration, video.duration);
  const length = Math.max(0.1, end - start);

  video.currentTime = start;
  await once(video, 'seeked');
  drawFrame(ctx, video, canvas.width, canvas.height, o);

  let finished = false;
  let fail: ((e: Error) => void) | null = null;
  const stopped = new Promise<void>((resolve, reject) => {
    recorder.onstop = () => resolve();
    fail = reject;
  });

  const cleanup = () => {
    document.removeEventListener('visibilitychange', onVisibility);
    signal?.removeEventListener('abort', onAbort);
    video.pause();
    stream.getTracks().forEach(t => t.stop());
    audio.close().catch(() => {});
    URL.revokeObjectURL(url);
  };
  const finish = () => {
    if (finished) return;
    finished = true;
    video.pause();
    if (recorder.state !== 'inactive') recorder.stop();
  };
  function onVisibility() {
    if (finished) return;
    if (document.hidden) {
      video.pause();
      if (recorder.state === 'recording') recorder.pause();
      onProgress((video.currentTime - start) / length, 'Paused: keep this tab open and visible while it renders.');
    } else {
      if (recorder.state === 'paused') recorder.resume();
      video.play().catch(() => {});
    }
  }
  function onAbort() {
    finished = true;
    if (recorder.state !== 'inactive') recorder.stop();
    fail?.(new RenderCancelled());
  }
  document.addEventListener('visibilitychange', onVisibility);
  signal?.addEventListener('abort', onAbort);
  video.addEventListener('ended', finish);

  // Each new video frame (or each screen frame where the browser can't say).
  const rvfc = (video as any).requestVideoFrameCallback?.bind(video);
  const step = () => {
    if (finished) return;
    if (video.currentTime >= end - 0.01) { finish(); return; }
    drawFrame(ctx, video, canvas.width, canvas.height, o);
    onProgress(Math.min(1, (video.currentTime - start) / length));
    if (rvfc) rvfc(step); else requestAnimationFrame(step);
  };

  try {
    if (audio.state === 'suspended') await audio.resume();
    recorder.start(1000);
    await video.play();
    if (rvfc) rvfc(step); else requestAnimationFrame(step);
    // The frame callback stops with the video; this catches the end point too.
    const watch = setInterval(() => { if (!finished && video.currentTime >= end - 0.01) finish(); }, 100);
    try { await stopped; } finally { clearInterval(watch); }
  } finally {
    cleanup();
  }
  if (signal?.aborted) throw new RenderCancelled();
  onProgress(1);
  const blob = new Blob(chunks, { type: fmt.mime.split(';')[0] });
  return { blob, mime: blob.type, ext: fmt.ext, width: canvas.width, height: canvas.height, duration: length };
}

/** A still from `video` as a JPEG, its long edge at most `maxEdge` pixels. */
export function grabPoster(video: HTMLVideoElement, o?: ResizeOptions, maxEdge = 1280): Promise<Blob | null> {
  const w0 = o?.width ?? video.videoWidth, h0 = o?.height ?? video.videoHeight;
  if (!w0 || !h0 || !video.videoWidth) return Promise.resolve(null);
  const k = Math.min(1, maxEdge / Math.max(w0, h0));
  const c = document.createElement('canvas');
  c.width = Math.round(w0 * k); c.height = Math.round(h0 * k);
  const ctx = c.getContext('2d');
  if (!ctx) return Promise.resolve(null);
  if (o) drawFrame(ctx, video, c.width, c.height, o);
  else ctx.drawImage(video, 0, 0, c.width, c.height);
  return new Promise(r => c.toBlob(b => r(b), 'image/jpeg', 0.86));
}

/** A poster for a file: the frame `at` seconds in. */
export async function posterFromFile(file: Blob, at = 0.5): Promise<Blob | null> {
  const url = URL.createObjectURL(file);
  const v = document.createElement('video');
  v.muted = true; v.preload = 'auto'; v.playsInline = true; v.src = url;
  try {
    await once(v, 'loadeddata');
    v.currentTime = Math.min(at, Math.max(0, (v.duration || 1) - 0.1));
    await once(v, 'seeked');
    return await grabPoster(v);
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function clock(s: number | null | undefined): string {
  if (s == null || !isFinite(s)) return '–:––';
  s = Math.max(0, Math.round(s));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export function downloadBlob(blob: Blob, name: string) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
}
