/**
 * Video uploads and automatic transcripts started from the course canvas.
 *
 * Kept in a store rather than in the canvas page so work keeps going if the
 * admin moves to another admin page and back. Each file goes to Bunny through
 * the existing resumable upload (Bunny is used for the video only), while its
 * audio is transcribed in this browser from the same file.
 *
 * The file stays in memory for the session, so a transcript that fails for a
 * passing reason (the AI provider busy, the network, the account short of
 * credit) is tried again on its own a few times without the admin doing
 * anything.
 */
import { writable, get } from 'svelte/store';
import { ApiError } from '$lib/api/client';
import { uploadVideoHybrid } from '$lib/utils/upload-client';
import { autoTranscribe, TranscribeError } from '$lib/utils/transcribe';

export type UploadStage = 'queued' | 'uploading' | 'uploaded' | 'failed';
export type TranscriptStage = 'waiting' | 'working' | 'done' | 'failed';

export interface UploadState {
  itemId: string;
  episodeId: string;
  fileName: string;
  // null when only a transcript was asked for (the video is already uploaded).
  stage: UploadStage | null;
  progress: number; // 0..1 of bytes sent
  error?: string;
  transcript: TranscriptStage;
  transcriptProgress: number; // 0..1 of clips done
  transcriptError?: string;
  // When the next automatic retry is due, if one is scheduled.
  retryAt?: number;
}

export const uploads = writable<Record<string, UploadState>>({});

// Retry delays after a failure that might clear up by itself.
const RETRY_DELAYS_MS = [30_000, 120_000, 600_000];
const files = new Map<string, File>();
const attempts = new Map<string, number>();

function patch(itemId: string, change: Partial<UploadState>) {
  uploads.update(all => (all[itemId] ? { ...all, [itemId]: { ...all[itemId], ...change } } : all));
}

// One upload at a time keeps the admin's connection responsive; audio decoding
// is memory-heavy, so transcripts also run one at a time.
let uploadChain: Promise<void> = Promise.resolve();
let transcriptChain: Promise<void> = Promise.resolve();

/**
 * Failures worth trying again. A file the browser can't read, a transcript an
 * admin already edited (409), a missing AI key (503) or a bad request will
 * fail the same way next time, so those are left for the admin.
 */
function retryable(e: unknown): boolean {
  if (e instanceof TranscribeError) return false;
  if (e instanceof ApiError) return ![400, 404, 409, 413, 422, 503].includes(e.status);
  return true;
}

function queueTranscript(itemId: string, episodeId: string, onChange?: () => void) {
  transcriptChain = transcriptChain.then(async () => {
    const file = files.get(itemId);
    if (!file) return;
    patch(itemId, { transcript: 'working', transcriptProgress: 0, transcriptError: undefined, retryAt: undefined });
    try {
      await autoTranscribe(episodeId, file, (done, total) =>
        patch(itemId, { transcriptProgress: total ? done / total : 1 }));
      patch(itemId, { transcript: 'done', transcriptProgress: 1 });
      attempts.delete(itemId);
    } catch (e: any) {
      const n = attempts.get(itemId) ?? 0;
      const message = e?.message ?? 'Transcript failed';
      if (retryable(e) && n < RETRY_DELAYS_MS.length) {
        attempts.set(itemId, n + 1);
        const wait = RETRY_DELAYS_MS[n];
        patch(itemId, { transcript: 'waiting', transcriptError: message, retryAt: Date.now() + wait });
        setTimeout(() => queueTranscript(itemId, episodeId, onChange), wait);
      } else {
        patch(itemId, { transcript: 'failed', transcriptError: message, retryAt: undefined });
      }
    }
    onChange?.();
  });
}

/** Queue a file for an episode that already sits on the canvas: upload it and transcribe it. */
export function startVideoUpload(itemId: string, episodeId: string, file: File, onChange?: () => void) {
  files.set(itemId, file);
  attempts.delete(itemId);
  uploads.update(all => ({
    ...all,
    [itemId]: {
      itemId, episodeId, fileName: file.name, stage: 'queued', progress: 0,
      transcript: 'waiting', transcriptProgress: 0,
    },
  }));

  uploadChain = uploadChain.then(async () => {
    patch(itemId, { stage: 'uploading' });
    try {
      await uploadVideoHybrid({
        file,
        episodeId,
        token: localStorage.getItem('champ_token') ?? '',
        onProgress: (sent, total) => patch(itemId, { progress: total ? sent / total : 0 }),
      });
      patch(itemId, { stage: 'uploaded', progress: 1 });
    } catch (e: any) {
      patch(itemId, { stage: 'failed', error: e?.message ?? 'Upload failed' });
    }
    onChange?.();
  });

  queueTranscript(itemId, episodeId, onChange);
}

/**
 * Transcribe episodes whose video is already uploaded, from files the admin
 * picked again. Nothing is uploaded.
 */
export function transcribeFiles(jobs: { itemId: string; episodeId: string; file: File }[], onChange?: () => void) {
  for (const j of jobs) {
    files.set(j.itemId, j.file);
    attempts.delete(j.itemId);
    uploads.update(all => ({
      ...all,
      [j.itemId]: {
        itemId: j.itemId, episodeId: j.episodeId, fileName: j.file.name, stage: all[j.itemId]?.stage ?? null,
        progress: all[j.itemId]?.progress ?? 1, transcript: 'waiting', transcriptProgress: 0,
      },
    }));
    queueTranscript(j.itemId, j.episodeId, onChange);
  }
}

/** Try a failed transcript again now, if this session still has its file. */
export function retryTranscript(itemId: string, onChange?: () => void): boolean {
  const state = get(uploads)[itemId];
  if (!state || !files.has(itemId)) return false;
  attempts.delete(itemId);
  queueTranscript(itemId, state.episodeId, onChange);
  return true;
}

/** The file this session uploaded for an item, if it still has it (for a quick preview). */
export function fileFor(itemId: string): File | null {
  return files.get(itemId) ?? null;
}

/** Anything still sending or transcribing? Used to warn before closing the tab. */
export function hasActiveUploads(): boolean {
  return Object.values(get(uploads)).some(
    u => u.stage === 'queued' || u.stage === 'uploading' || u.transcript === 'working' || u.transcript === 'waiting',
  );
}

export function forgetUpload(itemId: string) {
  files.delete(itemId);
  attempts.delete(itemId);
  uploads.update(all => { const { [itemId]: _, ...rest } = all; return rest; });
}
