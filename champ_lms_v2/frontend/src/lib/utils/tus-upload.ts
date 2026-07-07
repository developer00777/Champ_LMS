/**
 * Lightweight TUS upload client for Bunny Stream
 * Supports resumable uploads with progress tracking.
 */

export interface TusUploadOptions {
  uploadUrl: string;
  file: File;
  onProgress?: (bytesUploaded: number, bytesTotal: number) => void;
  onSuccess?: () => void;
  onError?: (error: Error) => void;
}

export async function uploadWithTus(options: TusUploadOptions): Promise<void> {
  const { uploadUrl, file, onProgress, onSuccess, onError } = options;
  
  const chunkSize = 5 * 1024 * 1024; // 5MB chunks
  const fileSize = file.size;
  
  try {
    // Step 1: Create TUS upload (POST with TUS headers)
    // For Bunny Stream, the uploadUrl from create_video IS the TUS endpoint
    const createResponse = await fetch(uploadUrl, {
      method: 'POST',
      headers: {
        'Tus-Resumable': '1.0.0',
        'Upload-Length': String(fileSize),
        'Content-Type': 'application/json',
        'Upload-Metadata': `filename ${btoa(file.name)},filetype ${btoa(file.type || 'video/mp4')}`
      }
    });
    
    if (!createResponse.ok) {
      throw new Error(`TUS creation failed: ${createResponse.status}`);
    }
    
    const location = createResponse.headers.get('Location');
    if (!location) {
      throw new Error('TUS server did not return Location header');
    }
    
    // Step 2: Upload chunks (PATCH)
    let offset = 0;
    while (offset < fileSize) {
      const chunk = file.slice(offset, Math.min(offset + chunkSize, fileSize));
      const chunkData = await chunk.arrayBuffer();
      
      const patchResponse = await fetch(location, {
        method: 'PATCH',
        headers: {
          'Tus-Resumable': '1.0.0',
          'Upload-Offset': String(offset),
          'Content-Type': 'application/offset+octet-stream'
        },
        body: chunkData
      });
      
      if (!patchResponse.ok) {
        throw new Error(`TUS upload failed at offset ${offset}: ${patchResponse.status}`);
      }
      
      offset = parseInt(patchResponse.headers.get('Upload-Offset') || String(offset + chunkData.byteLength), 10);
      onProgress?.(offset, fileSize);
    }
    
    onSuccess?.();
  } catch (error) {
    onError?.(error instanceof Error ? error : new Error(String(error)));
  }
}

/**
 * Simple PUT upload with progress tracking (fallback for non-TUS endpoints)
 */
export async function uploadWithProgress(
  url: string,
  file: File,
  onProgress?: (loaded: number, total: number) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        onProgress?.(e.loaded, e.total);
      }
    });
    
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`));
      }
    });
    
    xhr.addEventListener('error', () => reject(new Error('Upload failed')));
    xhr.addEventListener('abort', () => reject(new Error('Upload aborted')));
    
    xhr.open('PUT', url);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.send(file);
  });
}
