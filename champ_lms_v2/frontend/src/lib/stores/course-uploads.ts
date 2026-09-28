/**
 * Video uploads started from the course canvas.
 *
 * Kept in a store rather than in the canvas page so an upload keeps going if
 * the admin moves to another admin page and back. Each file goes to Bunny
 * through the existing resumable upload (Bunny is used for the video only),
 * while its audio is transcribed in this browser at the same time.
 */
import { writable, get } from 'svelte/store';
import { uploadVideoHybrid } from '$lib/utils/upload-client';
import { autoTranscribe } from '$lib/utils/transcribe';

export type UploadStage = 'queued' | 'uploading' | 'uploaded' | 'failed';
export type TranscriptStage = 'waiting' | 'working' | 'done' | 'failed';

export interface UploadState {
  itemId: string;
  episodeId: string;
  fileName: string;
  stage: UploadStage;
  progress: number; // 0..1 of bytes sent
  error?: string;
  transcript: TranscriptStage;
  transcriptProgress: number; // 0..1 of clips done
  transcriptError?: string;
}

export const uploads = writable<Record<string, UploadState>>({});

function patch(itemId: string, change: Partial<UploadState>) {
  uploads.update(all => (all[itemId] ? { ...all, [itemId]: { ...all[itemId], ...change } } : all));
}

// One upload at a time keeps the admin's connection responsive; audio decoding
// is memory-heavy, so transcripts also run one at a time.
let uploadChain: Promise<void> = Promise.resolve();
let transcriptChain: Promise<void> = Promise.resolve();

/** Queue a file for an episode that already sits on the canvas. */
export function startVideoUpload(itemId: string, episodeId: string, file: File, onChange?: () => void) {
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

  transcriptChain = transcriptChain.then(async () => {
    patch(itemId, { transcript: 'working' });
    try {
      await autoTranscribe(episodeId, file, (done, total) =>
        patch(itemId, { transcriptProgress: total ? done / total : 1 }));
      patch(itemId, { transcript: 'done', transcriptProgress: 1 });
    } catch (e: any) {
      patch(itemId, { transcript: 'failed', transcriptError: e?.message ?? 'Transcript failed' });
    }
    onChange?.();
  });
}

/** Anything still sending or transcribing? Used to warn before closing the tab. */
export function hasActiveUploads(): boolean {
  return Object.values(get(uploads)).some(
    u => u.stage === 'queued' || u.stage === 'uploading' || u.transcript === 'working' || u.transcript === 'waiting',
  );
}

export function forgetUpload(itemId: string) {
  uploads.update(all => { const { [itemId]: _, ...rest } = all; return rest; });
}
