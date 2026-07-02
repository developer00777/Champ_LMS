<script lang="ts">
  import { api } from '$lib/api/client';

  let moduleTitle = '';
  let moduleCategory = '';
  let episodeTitle = '';
  let episodeOrder = 1;
  let videoFile: File | null = null;
  let thumbnailFile: File | null = null;

  let step: 'module' | 'episode' | 'video' | 'done' = 'module';
  let moduleId = '';
  let episodeId = '';
  let uploading = false;
  let error = '';
  let statusMsg = '';

  const CATEGORIES = ['sales', 'leadership', 'onboarding', 'product', 'engineering', 'ops'];

  function pickedFile(e: Event): File | null {
    return (e.target as HTMLInputElement).files?.[0] ?? null;
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

  async function uploadVideo() {
    if (!videoFile) { error = 'Select a video file'; return; }
    uploading = true; error = ''; statusMsg = '';

    try {
      // Upload video directly to Bunny Stream via backend
      const formData = new FormData();
      formData.append('video', videoFile);
      const token = localStorage.getItem('champ_token');
      statusMsg = 'Uploading to Bunny Stream...';
      const res = await fetch(`/api/admin/episodes/${episodeId}/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      statusMsg = 'Video uploaded. Bunny Stream is transcoding (360p/720p/1080p)...';

      // Upload thumbnail if provided
      if (thumbnailFile) {
        const thumbForm = new FormData();
        thumbForm.append('image', thumbnailFile);
        statusMsg = 'Uploading thumbnail to Bunny Storage...';
        const tr = await fetch(`/api/admin/episodes/${episodeId}/thumbnail`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
          body: thumbForm,
        });
        if (!tr.ok) throw new Error(await tr.text());
      }

      await api.publishModule(moduleId);
      step = 'done';
    } catch (e: any) { error = e.message; }
    finally { uploading = false; }
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
      <p class="info">Bunny Stream accepts MP4, MOV, AVI. Max recommended: 10 GB.</p>
      <label>Video File *
        <input type="file" accept="video/*" on:change={e => videoFile = pickedFile(e)} />
      </label>
      <label>Thumbnail Image (optional)
        <p class="hint">Served via Bunny CDN with Optimizer (auto-WebP, resized to 480×270)</p>
        <input type="file" accept="image/*" on:change={e => thumbnailFile = pickedFile(e)} />
      </label>
      {#if statusMsg}<p class="status">{statusMsg}</p>{/if}
      {#if error}<p class="error">{error}</p>{/if}
      <button class="btn-primary" on:click={uploadVideo} disabled={uploading || !videoFile}>
        {uploading ? 'Uploading...' : 'Upload to Bunny Stream →'}
      </button>
    </div>
  {:else if step === 'done'}
    <div class="done-card">
      <div class="checkmark">✓</div>
      <h2>Upload Complete</h2>
      <p>Video is being transcoded by Bunny Stream. Episode will be ready once encoding finishes (webhook auto-updates status).</p>
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
  .done-card { text-align: center; padding: 3rem; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; }
  .checkmark { font-size: 3rem; color: var(--success); margin-bottom: 0.75rem; }
  .done-card p { color: var(--muted); margin: 0.5rem 0 2rem; line-height: 1.5; }
  .done-actions { display: flex; gap: 0.75rem; justify-content: center; }
</style>
