/**
 * Automatic transcripts, made in the admin's browser.
 *
 * Bunny is used for video only, so the transcript does not come from Bunny.
 * While a video uploads, the browser decodes the file's audio, downmixes it to
 * 16 kHz mono and cuts it into short WAV clips. Each clip goes to the backend,
 * which has the AI write timed lines for it. The lines are collected here and
 * saved as one transcript, so a half-finished run never leaves a partial one.
 */
import { api, type TranscriptSegment } from '$lib/api/client';

const SAMPLE_RATE = 16_000;
const CLIP_SECONDS = 120;
// Decoding holds the whole file and its audio in memory. Past this size a
// browser tab is likely to run out, so we stop and ask for captions instead.
export const MAX_AUTO_TRANSCRIPT_BYTES = 800 * 1024 * 1024;
// Clips this quiet are skipped: there is nothing to transcribe and each call costs.
const SILENCE_RMS = 0.004;

export class TranscribeError extends Error {}

function encodeWav(samples: Float32Array): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buffer);
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); str(8, 'WAVE');
  str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, SAMPLE_RATE, true); v.setUint32(28, SAMPLE_RATE * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, 'data'); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

function rms(samples: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < samples.length; i += 16) sum += samples[i] * samples[i];
  return Math.sqrt(sum / Math.max(1, samples.length / 16));
}

/** The file's audio as 16 kHz mono clips, with each clip's start time. */
export async function audioClips(file: File): Promise<{ start: number; seconds: number; wav: Blob }[]> {
  if (file.size > MAX_AUTO_TRANSCRIPT_BYTES) {
    throw new TranscribeError('This file is too large for an automatic transcript. Upload a caption file instead.');
  }
  const Offline = (window as any).OfflineAudioContext || (window as any).webkitOfflineAudioContext;
  if (!Offline) throw new TranscribeError('This browser cannot read audio from video files.');
  // An offline context at 16 kHz makes decodeAudioData resample for us.
  const ctx = new Offline(1, 1, SAMPLE_RATE);
  let audio: AudioBuffer;
  try {
    audio = await ctx.decodeAudioData(await file.arrayBuffer());
  } catch {
    throw new TranscribeError("The browser couldn't read the audio in this file. Upload a caption file instead.");
  }
  const length = audio.length;
  const mono = new Float32Array(length);
  for (let ch = 0; ch < audio.numberOfChannels; ch++) {
    const data = audio.getChannelData(ch);
    for (let i = 0; i < length; i++) mono[i] += data[i] / audio.numberOfChannels;
  }
  const per = CLIP_SECONDS * SAMPLE_RATE;
  const clips: { start: number; seconds: number; wav: Blob }[] = [];
  for (let at = 0; at < length; at += per) {
    const slice = mono.subarray(at, Math.min(length, at + per));
    if (rms(slice) < SILENCE_RMS) continue;
    clips.push({ start: at / SAMPLE_RATE, seconds: slice.length / SAMPLE_RATE, wav: encodeWav(slice) });
  }
  return clips;
}

/**
 * Transcribe a video file for an episode and save the result.
 * `onProgress(done, total)` reports clips finished.
 */
export async function autoTranscribe(
  episodeId: string,
  file: File,
  onProgress?: (done: number, total: number) => void,
): Promise<TranscriptSegment[]> {
  await api.setTranscriptStatus(episodeId, 'processing').catch(() => {});
  try {
    const clips = await audioClips(file);
    const segments: TranscriptSegment[] = [];
    let done = 0;
    onProgress?.(0, clips.length);
    // Two clips in flight: quicker than one at a time, gentle on the API.
    let next = 0;
    async function worker() {
      while (next < clips.length) {
        const clip = clips[next++];
        const res = await api.transcribeChunk(episodeId, clip.wav, clip.start, clip.seconds);
        segments.push(...res.segments);
        onProgress?.(++done, clips.length);
      }
    }
    await Promise.all([worker(), worker()]);
    segments.sort((a, b) => a.start - b.start);
    // Times from the start of the file: shared by every part split from it.
    await api.saveTranscript(episodeId, segments, 'auto', 'source');
    return segments;
  } catch (e) {
    await api.setTranscriptStatus(episodeId, 'failed').catch(() => {});
    throw e;
  }
}

function toSeconds(stamp: string): number {
  const parts = stamp.trim().replace(',', '.').split(':').map(Number);
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

/** Read a .vtt or .srt caption file into transcript lines. */
export function parseCaptions(text: string): TranscriptSegment[] {
  const out: TranscriptSegment[] = [];
  const blocks = text.replace(/\r/g, '').split(/\n\s*\n/);
  for (const block of blocks) {
    const lines = block.split('\n').map(l => l.trim()).filter(Boolean);
    const cue = lines.findIndex(l => l.includes('-->'));
    if (cue === -1) continue;
    const [from, to] = lines[cue].split('-->');
    const words = lines.slice(cue + 1).join(' ').replace(/<[^>]+>/g, '').trim();
    if (!words) continue;
    out.push({ start: toSeconds(from), end: toSeconds(to.split(' ').filter(Boolean)[0] ?? from), text: words });
  }
  return out;
}

/** Transcript lines as editable text, one "[m:ss] words" per line. */
export function segmentsToText(segments: TranscriptSegment[]): string {
  return segments.map(s => `[${clock(s.start)}] ${s.text}`).join('\n');
}

/** The reverse of segmentsToText. Lines without a time stamp are dropped. */
export function textToSegments(text: string): TranscriptSegment[] {
  const rows = text.split('\n').map(l => l.match(/^\s*\[(\d+):(\d{1,2})(?::(\d{1,2}))?\]\s*(.*)$/)).filter(Boolean) as RegExpMatchArray[];
  const starts = rows.map(m => (m[3] !== undefined ? (+m[1] * 3600 + +m[2] * 60 + +m[3]) : (+m[1] * 60 + +m[2])));
  return rows
    .map((m, i) => ({ start: starts[i], end: starts[i + 1] ?? starts[i] + 5, text: m[4].trim() }))
    .filter(s => s.text);
}

/** 75 -> "1:15"; 3725 -> "1:02:05". */
export function clock(seconds: number | null | undefined): string {
  const s = Math.max(0, Math.floor(seconds ?? 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
}

/** 1830 -> "31 min"; 5400 -> "1 h 30 min". */
export function runtime(seconds: number): string {
  const m = Math.round(seconds / 60);
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
}
