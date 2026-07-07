/**
 * Upload Client for Bunny Stream
 * 
 * Current approach: Server-side upload with progress tracking
 * (TUS direct upload requires Bunny API key which can't be exposed to browser)
 * 
 * Future: Add upload-from-URL option for very large files
 */

export interface UploadOptions {
  file: File;
  episodeId: string;
  token: string;
  onProgress?: (bytesUploaded: number, bytesTotal: number) => void;
  onStatus?: (message: string) => void;
}

export interface UploadResult {
  success: boolean;
  method: 'server' | null;
  error?: string;
}

/**
 * Upload video via server with progress tracking
 */
export async function uploadVideoHybrid(options: UploadOptions): Promise<UploadResult> {
  const { file, episodeId, token, onProgress, onStatus } = options;

  onStatus?.('Uploading via server...');
  await uploadViaServer({
    episodeId,
    file,
    token,
    onProgress,
  });
  return { success: true, method: 'server' };
}

/**
 * Server-Side Upload with Progress Tracking
 * Uses XMLHttpRequest for accurate progress events
 */
function uploadViaServer(options: {
  episodeId: string;
  file: File;
  token: string;
  onProgress?: (bytesUploaded: number, bytesTotal: number) => void;
}): Promise<void> {
  const { episodeId, file, token, onProgress } = options;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append('video', file);

    // Progress tracking
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        onProgress?.(e.loaded, e.total);
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Server upload failed: ${xhr.status}`));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Server upload failed')));
    xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));

    xhr.open('POST', `/api/admin/episodes/${episodeId}/upload`);
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.send(formData);
  });
}

/**
 * Upload thumbnail via server (Bunny Storage doesn't support direct browser upload)
 */
export async function uploadThumbnail(options: {
  episodeId: string;
  file: File;
  token: string;
}): Promise<void> {
  const { episodeId, file, token } = options;
  
  const formData = new FormData();
  formData.append('image', file);

  const res = await fetch(`/api/admin/episodes/${episodeId}/thumbnail`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }
}
