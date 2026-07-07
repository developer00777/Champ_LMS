<script lang="ts">
  import { api } from '$lib/api/client';
  import { uploadVideoHybrid, uploadThumbnail } from '$lib/utils/upload-client';

  let moduleTitle = '';
  let moduleCategory = '';
  let episodeTitle = '';
  let episodeOrder = 1;
  let videoFile: File | null = null;
  let thumbnailFile: File | null = null;
  let externalVideoUrl = '';

  let step: 'module' | 'episode' | 'video' | 'done' = 'module';
  let moduleId = '';
  let episodeId = '';
  let uploading = false;
  let error = '';
  let statusMsg = '';
  let uploadMethod: string | null = null;
  let uploadProgress = 0;
  let uploadMode: 'direct' | 'url' = 'direct'; // direct = file upload, url = external URL

  const CATEGORIES = ['sales', 'leadership', 'onboarding', 'product', 'engineering', 'ops'];
  const MAX_DIRECT_UPLOAD_SIZE = 50 * 1024 * 1024; // 50MB limit for direct upload

  function pickedFile(e: Event): File | null {
    return (e.target as HTMLInputElement).files?.[0] ?? null;
  }

  function formatBytes(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function handleVideoFileChange(e: Event) {
    videoFile = pickedFile(e);
    if (videoFile && videoFile.size > MAX_DIRECT_UPLOAD_SIZE) {
      // Auto-switch to URL mode for large files
      uploadMode = 'url';
      error = `File is ${formatBytes(videoFile.size)}. Files larger than ${formatBytes(MAX_DIRECT_UPLOAD_SIZE)} must use external URL upload.`;
    } else {
      error = '';
    }
  }

  async function createModule() {
    if (!moduleTitle) { error = 'Title required'; return; }
    uploading = true; error = '';
    try {
      const res = await api.createModule({ title: moduleTitle, category: moduleCategory || undefined });
      moduleId = res.id;
      step = 'episode';
    } catch (e: any) { error = e.message; }
    finally { uploading = false; }
  }

  async function createEpisode() {
    if (!episodeTitle) { error = 'Episode title required'; return; }
    uploading = true; error = '';
    try {
      const res = await api.addEpisode(moduleId, { title: episodeTitle, sequence_order: episodeOrder });
      episodeId = res.id;
      step = 'video';
    } catch (e: any) { error = e.message; }
    finally { uploading = false; }
  }

  async function uploadVideoDirect() {
    if (!videoFile) { error = 'Select a video file'; return; }
    if (videoFile.size > MAX_DIRECT_UPLOAD_SIZE) {
      error = `File too large (${formatBytes(videoFile.size)}). Use external URL upload instead.`;
      return;
    }

    uploading = true; error = ''; statusMsg = '';
    uploadProgress = 0;
    const token = localStorage.getItem('champ_token') || '';

    try {
      const result = await uploadVideoHybrid({
        file: videoFile,
        episodeId,
        token,
        onProgress: (loaded, total) => {
          uploadProgress = Math.round((loaded / total) * 100);
        },
        onStatus: (msg) => {
          statusMsg = msg;
        },
      });

      uploadMethod = result.method;
      statusMsg = `Video uploaded. Bunny Stream is transcoding...`;

      if (thumbnailFile) {
        statusMsg = 'Uploading thumbnail...';
        await uploadThumbnail({ episodeId, file: thumbnailFile, token });
      }

      await api.publishModule(moduleId);
      step = 'done';
    } catch (e: any) {
      error = e.message;
      statusMsg = '';
    } finally {
      uploading = false;
      uploadProgress = 0;
    }
  }

  async function uploadVideoFromUrl() {
    if (!externalVideoUrl.trim()) { error = 'Enter a video URL'; return; }
    
    uploading = true; error = ''; statusMsg = '';
    const token = localStorage.getItem('champ_token') || '';

    try {
      statusMsg = 'Sending URL to Bunny Stream...';
      
      // Call API to fetch from URL
      const res = await fetch(`/api/admin/episodes/${episodeId}/upload-from-url`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ video_url: externalVideoUrl.trim() }),
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(`Failed to queue video fetch: ${err}`);
      }

      uploadMethod = 'url';
      statusMsg = 'Bunny Stream is downloading and transcoding video...';

      if (thumbnailFile) {
        statusMsg = 'Uploading thumbnail...';
        await uploadThumbnail({ episodeId, file: thumbnailFile, token });
      }

      await api.publishModule(moduleId);
      step = 'done';
    } catch (e: any) {
      error = e.message;
      statusMsg = '';
    } finally {
      uploading = false;
    }
  }
</script>

<svelte:head><title>Upload Video — Admin</title></svelte:head>

<div class="page">
  <div class="breadcrumb"><a href="/admin">Admin</a> / Upload Video</div>
  <h1>Upload Video to Bunny Stream</h1>
  <p class="sub">Video is automatically transcoded to 360p / 720p / 1080p HLS by Bunny Stream.</p>

  <div class="steps">
    <div class="step" class:active={step === 'module'} class:done={step !== 'module'}>1. Module</div>
    <div class="divider">→</div>
    <div class="step" class:active={step === 'episode'} class:done={step === 'video' || step === 'done'}>2. Episode</div>
    <div class="divider">→</div>
    <div class="step" class:active={step === 'video'} class:done={step === 'done'}>3. Upload</div>
  </div>

  {#if step === 'module'}
    <div class="form-card">
      <h2>Create Module</h2>
      <label>Module Title *
        <input bind:value={moduleTitle} placeholder="e.g. Sales Fundamentals" />
      </label>
      <label>Category
        <select bind:value={moduleCategory}>
          <option value="">Select...</option>
          {#each CATEGORIES as c}<option value={c}>{c}</option>{/each}
        </select>
      </label>
      {#if error}<p class="error">{error}</p>{/if}
      <button class="btn-primary" on:click={createModule} disabled={uploading}>
        {uploading ? 'Creating...' : 'Create Module →'}
      </button>
    </div>
  {:else if step === 'episode'}
    <div class="form-card">
      <h2>Add Episode to Module</h2>
      <label>Episode Title *
        <input bind:value={episodeTitle} placeholder="e.g. Understanding the Sales Funnel" />
      </label>
      <label>Episode Order
        <input type="number" bind:value={episodeOrder} min="1" />
      </label>
      {#if error}<p class="error">{error}</p>{/if}
      <button class="btn-primary" on:click={createEpisode} disabled={uploading}>
        {uploading ? 'Creating...' : 'Create Episode →'}
      </button>
    </div>
  {:else if step === 'video'}
    <div class="form-card">
      <h2>Upload Video File</h2>
      
      <!-- Upload Mode Toggle -->
      <div class="upload-mode-toggle">
        <button 
          class="mode-btn" 
          class:active={uploadMode === 'direct'}
          on:click={() => uploadMode = 'direct'}
        >
          Upload File
        </button>
        <button 
          class="mode-btn" 
          class:active={uploadMode === 'url'}
          on:click={() => uploadMode = 'url'}
        >
          External URL
        </button>
      </div>

      {#if uploadMode === 'direct'}
        <p class="info">Direct file upload. Max: {formatBytes(MAX_DIRECT_UPLOAD_SIZE)}. For larger files, use External URL.</p>
        <label>Video File *
          <input type="file" accept="video/*" on:change={handleVideoFileChange} />
          {#if videoFile}
            <span class="file-info">{videoFile.name} ({formatBytes(videoFile.size)})</span>
          {/if}
        </label>

        {#if videoFile && videoFile.size > MAX_DIRECT_UPLOAD_SIZE}
          <div class="warning-card">
            <strong>⚠️ File too large</strong>
            <p>This file is {formatBytes(videoFile.size)}. Please switch to <strong>External URL</strong> mode and upload to a temporary file host first.</p>
          </div>
        {/if}

        {#if uploading && uploadProgress > 0}
          <div class="progress-container">
            <div class="progress-bar" style="width: {uploadProgress}%"></div>
            <span class="progress-text">{uploadProgress}%</span>
          </div>
        {/if}

        {#if statusMsg}<p class="status">{statusMsg}</p>{/if}
        {#if error}<p class="error">{error}</p>{/if}

        <button 
          class="btn-primary" 
          on:click={uploadVideoDirect} 
          disabled={uploading || !videoFile || (videoFile?.size || 0) > MAX_DIRECT_UPLOAD_SIZE}
        >
          {uploading ? 'Uploading...' : 'Upload to Bunny Stream →'}
        </button>

      {:else}
        <p class="info">For files larger than {formatBytes(MAX_DIRECT_UPLOAD_SIZE)}, use a temporary file host:</p>
        <ul class="host-list">
          <li><a href="https://file.io" target="_blank">file.io</a> — upload file, paste URL here</li>
          <li><a href="https://transfer.sh" target="_blank">transfer.sh</a> — command line: <code>curl --upload-file vid.mp4 https://transfer.sh/vid.mp4</code></li>
          <li><a href="https://tmp.link" target="_blank">tmp.link</a> — upload and get direct URL</li>
        </ul>
        
        <label>Video URL *
          <input 
            bind:value={externalVideoUrl} 
            placeholder="https://file.io/xxxxx or https://transfer.sh/xxxxx/vid.mp4" 
          />
        </label>
        <p class="hint">Bunny Stream will download directly from this URL. Make sure the link is public and doesn't expire immediately.</p>

        {#if statusMsg}<p class="status">{statusMsg}</p>{/if}
        {#if error}<p class="error">{error}</p>{/if}

        <button 
          class="btn-primary" 
          on:click={uploadVideoFromUrl} 
          disabled={uploading || !externalVideoUrl.trim()}
        >
          {uploading ? 'Queuing...' : 'Fetch from URL →'}
        </button>
      {/if}

      <hr class="divider-line" />
      
      <label>Thumbnail Image (optional)
        <p class="hint">Served via Bunny CDN with Optimizer (auto-WebP, resized to 480×270)</p>
        <input type="file" accept="image/*" on:change={e => thumbnailFile = pickedFile(e)} />
      </label>
    </div>
  {:else if step === 'done'}
    <div class="done-card">
      <div class="checkmark">✓</div>
      <h2>Upload Complete</h2>
      <p>Video is being transcoded by Bunny Stream. Episode will be ready once encoding finishes (webhook auto-updates status).</p>
      {#if uploadMethod}
        <p class="method-info">Uploaded via: {uploadMethod === 'url' ? 'External URL (fast)' : 'Direct upload'}</p>
      {/if}
      <div class="done-actions">
        <a href="/admin" class="btn-ghost">Back to Dashboard</a>
        <a href="/module/{moduleId}" class="btn-primary">View Module</a>
      </div>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 600px; margin: 0 auto; }
  .breadcrumb { font-size: 0.83rem; color: var(--muted); margin-bottom: 1rem; }
  .breadcrumb a { color: var(--accent); }
  h1 { font-size: 1.6rem; font-weight: 800; margin-bottom: 0.4rem; }
  .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }
  .steps { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 2rem; }
  .step { padding: 0.3rem 0.8rem; border-radius: 4px; font-size: 0.83rem; font-weight: 600; color: var(--muted); border: 1px solid var(--border); }
  .step.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .step.done { color: var(--success); border-color: var(--success); }
  .divider { color: var(--muted); }
  .form-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.75rem;
    display: flex; flex-direction: column; gap: 1.1rem;
  }
  h2 { font-size: 1.15rem; font-weight: 700; }
  label { display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.85rem; color: var(--muted); }
  input, select {
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--text); border-radius: 6px; padding: 0.6rem 0.8rem;
    font-size: 0.9rem; outline: none;
  }
  input:focus, select:focus { border-color: var(--accent); }
  .hint { font-size: 0.75rem; margin-bottom: 0.25rem; }
  .info { font-size: 0.83rem; color: var(--muted); background: var(--surface2); padding: 0.6rem 0.8rem; border-radius: 6px; }
  .status { color: var(--gold); font-size: 0.85rem; }
  .error { color: var(--accent); font-size: 0.85rem; }
  .file-info { font-size: 0.8rem; color: var(--muted); margin-top: 0.2rem; }
  
  .upload-mode-toggle {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }
  .mode-btn {
    flex: 1;
    padding: 0.6rem 1rem;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    cursor: pointer;
    font-size: 0.9rem;
    transition: all 0.2s;
  }
  .mode-btn:hover { background: var(--surface); }
  .mode-btn.active { 
    background: var(--accent); 
    color: #fff; 
    border-color: var(--accent); 
  }
  
  .warning-card {
    background: rgba(255, 193, 7, 0.1);
    border: 1px solid #ffc107;
    border-radius: 6px;
    padding: 1rem;
    color: #ffc107;
  }
  .warning-card strong { display: block; margin-bottom: 0.5rem; }
  .warning-card p { margin: 0; font-size: 0.85rem; }
  
  .host-list {
    margin: 0;
    padding-left: 1.2rem;
    font-size: 0.85rem;
    color: var(--muted);
  }
  .host-list li { margin-bottom: 0.4rem; }
  .host-list a { color: var(--accent); }
  .host-list code {
    background: var(--surface2);
    padding: 0.1rem 0.3rem;
    border-radius: 3px;
    font-size: 0.75rem;
  }
  
  .divider-line {
    border: none;
    border-top: 1px solid var(--border);
    margin: 1rem 0;
  }
  
  .progress-container {
    width: 100%;
    height: 24px;
    background: var(--surface2);
    border-radius: 12px;
    overflow: hidden;
    position: relative;
  }
  .progress-bar {
    height: 100%;
    background: var(--accent);
    transition: width 0.3s ease;
    border-radius: 12px;
  }
  .progress-text {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 0.75rem;
    font-weight: 600;
    color: #fff;
    text-shadow: 0 1px 2px rgba(0,0,0,0.3);
  }
  .done-card { text-align: center; padding: 3rem; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
  .checkmark { font-size: 3rem; color: var(--success); margin-bottom: 0.75rem; }
  .done-card p { color: var(--muted); margin: 0.5rem 0 2rem; line-height: 1.5; }
  .method-info { font-size: 0.85rem; color: var(--accent); margin-bottom: 1rem; }
  .done-actions { display: flex; gap: 0.75rem; justify-content: center; }
</style>
