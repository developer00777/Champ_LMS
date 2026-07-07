/**
 * Hybrid Upload Client for Bunny Stream
 * 
 * Strategy:
 * 1. Try TUS direct upload to Bunny Stream (fastest, no server bottleneck)
 * 2. If TUS fails (CORS, network), fallback to server-side upload with progress
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
  method: 'tus' | 'server' | null;
  error?: string;
}

const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB chunks for TUS

/**
 * Try TUS upload first, fallback to server-side
 */
export async function uploadVideoHybrid(options: UploadOptions): Promise<UploadResult> {
  const { file, episodeId, token, onProgress, onStatus } = options;

  // Step 1: Get upload URL from backend
  onStatus?.('Preparing upload...');
  const prepareRes = await fetch(`/api/admin/episodes/${episodeId}/prepare-upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!prepareRes.ok) {
    const errorText = await prepareRes.text();
    throw new Error(`Failed to prepare upload: ${errorText}`);
  }

  const { upload_url, bunny_video_guid } = await prepareRes.json();

  // Step 2: Try TUS direct upload
  try {
    onStatus?.('Uploading directly to Bunny Stream (TUS)...');
    await uploadWithTus({
      uploadUrl: upload_url,
      file,
      onProgress,
    });
    return { success: true, method: 'tus' };
  } catch (tusError) {
    console.warn('TUS upload failed, falling back to server-side:', tusError);
    
    // Step 3: Fallback to server-side upload with progress
    onStatus?.('Direct upload blocked, using server relay...');
    await uploadViaServer({
      episodeId,
      file,
      token,
      onProgress,
    });
    return { success: true, method: 'server' };
  }
}

/**
 * TUS Protocol Upload
 * Uploads file directly to Bunny Stream in resumable chunks
 */
async function uploadWithTus(options: {
  uploadUrl: string;
  file: File;
  onProgress?: (bytesUploaded: number, bytesTotal: number) => void;
}): Promise<void> {
  const { uploadUrl, file, onProgress } = options;
  const fileSize = file.size;

  // Step 1: Create TUS upload session
  const createRes = await fetch(uploadUrl, {
    method: 'POST',
    headers: {
      'Accept': 'application/vnd.bunnynet.v1+json',
      'Content-Type': 'application/json',
      'Tus-Resumable': '1.0.0',
      'Upload-Length': String(fileSize),
      'Upload-Metadata': `filename ${btoa(unescape(encodeURIComponent(file.name)))},filetype ${btoa(file.type || 'video/mp4')}`,
    },
  });

  if (!createRes.ok) {
    throw new Error(`TUS creation failed: ${createRes.status}`);
  }

  const location = createRes.headers.get('Location');
  if (!location) {
    throw new Error('TUS server did not return Location header');
  }

  // Step 2: Upload chunks
  let offset = 0;
  while (offset < fileSize) {
    const end = Math.min(offset + CHUNK_SIZE, fileSize);
    const chunk = file.slice(offset, end);
    const chunkData = await chunk.arrayBuffer();

    const patchRes = await fetch(location, {
      method: 'PATCH',
      headers: {
        'Accept': 'application/vnd.bunnynet.v1+json',
        'Tus-Resumable': '1.0.0',
        'Upload-Offset': String(offset),
        'Content-Type': 'application/offset+octet-stream',
      },
      body: chunkData,
    });

    if (!patchRes.ok) {
      throw new Error(`TUS chunk upload failed at offset ${offset}: ${patchRes.status}`);
    }

    offset = parseInt(patchRes.headers.get('Upload-Offset') || String(end), 10);
    onProgress?.(offset, fileSize);
  }
}

/**
 * Server-Side Upload with Progress Tracking
 * Fallback when TUS is blocked by CORS or network issues
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
