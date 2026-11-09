/**
 * Publishing a short: create it, send the file to Bunny through the same
 * resumable upload course videos use, then save its poster frame (Mongo).
 */
import { api, type AdminShort, type ShortCreate } from '$lib/api/client';
import { uploadVideoHybrid } from '$lib/utils/upload-client';
import { posterFromFile } from '$lib/utils/resize-video';

export const MAX_SHORT_SECONDS = 180;

export async function publishShort(
  file: File,
  meta: ShortCreate,
  onProgress: (fraction: number, status: string) => void,
  poster?: Blob | null,
): Promise<AdminShort> {
  onProgress(0, 'Creating the short…');
  const short = await api.createShort(meta);
  const token = localStorage.getItem('champ_token') || '';
  await uploadVideoHybrid({
    file,
    episodeId: short.id,
    endpoint: `/api/admin/shorts/${short.id}`,
    token,
    onProgress: (sent, total) => onProgress(total ? sent / total : 0, 'Uploading to Bunny Stream…'),
    onStatus: (msg) => onProgress(0, msg),
  });
  onProgress(1, 'Saving the poster…');
  const still = poster ?? (await posterFromFile(file, Math.min(1, (meta.duration_seconds ?? 2) / 3)));
  // A missing poster isn't worth failing the upload over: Bunny makes one too.
  if (still) await api.uploadShortPoster(short.id, still).catch(() => {});
  return { ...short, status: 'processing', has_video: true };
}
