<script lang="ts">
  import { api } from '$lib/api/client';
  import { uploadVideoHybrid } from '$lib/utils/upload-client';
  import ThumbnailField from '$lib/components/ThumbnailField.svelte';
  import type { PickedThumbnail } from '$lib/thumbnails/designer';
  import Icon from '$lib/components/Icon.svelte';
  import Select from '$lib/components/Select.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';

  // Purely visual: highlights the video dropzone while a file is dragged over
  // it. The file input inside still receives the drop and fires its own change.
  let hotZone: 'video' | null = null;
  const STEPS = [
    { key: 'module', label: 'Module', icon: 'layers' },
    { key: 'episode', label: 'Episode', icon: 'film' },
    { key: 'video', label: 'Upload', icon: 'upload' },
  ] as const;
  const ORDER = ['module', 'episode', 'video', 'done'];

  let moduleTitle = '';
  let moduleCategory = '';
  let episodeTitle = '';
  let episodeOrder = 1;
  let videoFile: File | null = null;
  let thumbPick: PickedThumbnail | null = null;
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
  const CATEGORY_OPTIONS = [
    { value: '', label: 'No category' },
    ...CATEGORIES.map(c => ({ value: c, label: c[0].toUpperCase() + c.slice(1) })),
  ];
  const MAX_DIRECT_UPLOAD_SIZE = 1024 * 1024 * 1024; // 1GB limit for direct upload

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

      if (thumbPick) {
        statusMsg = 'Saving thumbnail...';
        await api.saveThumbnail('episode', episodeId, thumbPick.blob, thumbPick.source, thumbPick.design);
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

      if (thumbPick) {
        statusMsg = 'Saving thumbnail...';
        await api.saveThumbnail('episode', episodeId, thumbPick.blob, thumbPick.source, thumbPick.design);
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
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Upload Video' }]} />
  <header class="head">
    <p class="eyebrow ui-rise" style="--i:1">Bunny Stream · auto-transcoded to 360p / 720p / 1080p HLS</p>
    <h1 class="ui-rise" style="--i:2">
      Upload a video
      <span class="title-mark" aria-hidden="true"><Icon name="upload" size={22} /></span>
    </h1>
  </header>

  <ol class="steps ui-rise" style="--i:3" aria-label="Progress">
    {#each STEPS as s, n}
      {@const state = ORDER.indexOf(step) > n ? 'done' : step === s.key ? 'active' : 'todo'}
      <li class="step {state}">
        <span class="s-dot">
          {#if state === 'done'}<Icon name="check" size={15} stroke={2.4} />{:else}<Icon name={s.icon} size={15} />{/if}
        </span>
        <span class="s-txt"><small>Step {n + 1}</small>{s.label}</span>
      </li>
      {#if n < STEPS.length - 1}<li class="s-line" class:filled={ORDER.indexOf(step) > n} aria-hidden="true"><span></span></li>{/if}
    {/each}
  </ol>

  {#key step}
    {#if step === 'module'}
      <section class="card ui-rise" style="--i:4">
        <div class="card-h"><span class="k-ico lilac"><Icon name="layers" size={20} /></span><div><h2>Create the module</h2><p>The course this video belongs to.</p></div></div>
        <label class="field">Module title *
          <input bind:value={moduleTitle} placeholder="e.g. Sales Fundamentals" />
        </label>
        <!-- svelte-ignore a11y-label-has-associated-control -->
        <label class="field">Category
          <Select bind:value={moduleCategory} size="lg" placeholder="Choose a category" options={CATEGORY_OPTIONS} />
        </label>
        {#if error}<p class="msg bad"><Icon name="alert" size={16} /> {error}</p>{/if}
        <button class="btn-primary go" on:click={createModule} disabled={uploading}>
          {#if uploading}<span class="spin"></span> Creating...{:else}Create module <Icon name="arrowRight" size={17} />{/if}
        </button>
      </section>
    {:else if step === 'episode'}
      <section class="card ui-rise" style="--i:4">
        <div class="card-h"><span class="k-ico butter"><Icon name="film" size={20} /></span><div><h2>Add an episode</h2><p>Name it and set where it sits in the module.</p></div></div>
        <label class="field">Episode title *
          <input bind:value={episodeTitle} placeholder="e.g. Understanding the Sales Funnel" />
        </label>
        <label class="field">Episode order
          <input type="number" bind:value={episodeOrder} min="1" />
        </label>
        {#if error}<p class="msg bad"><Icon name="alert" size={16} /> {error}</p>{/if}
        <button class="btn-primary go" on:click={createEpisode} disabled={uploading}>
          {#if uploading}<span class="spin"></span> Creating...{:else}Create episode <Icon name="arrowRight" size={17} />{/if}
        </button>
      </section>
    {:else if step === 'video'}
      <section class="card ui-rise" style="--i:4">
        <div class="card-h"><span class="k-ico sky"><Icon name="video" size={20} /></span><div><h2>Upload the video</h2><p>A file from your computer, or a link Bunny can pull from.</p></div></div>

        <div class="seg" role="tablist" aria-label="Upload method">
          <span class="seg-thumb" class:right={uploadMode === 'url'} aria-hidden="true"></span>
          <button class="mode-btn" role="tab" aria-selected={uploadMode === 'direct'} class:active={uploadMode === 'direct'} on:click={() => uploadMode = 'direct'}>
            <Icon name="upload" size={16} /> Upload file
          </button>
          <button class="mode-btn" role="tab" aria-selected={uploadMode === 'url'} class:active={uploadMode === 'url'} on:click={() => uploadMode = 'url'}>
            <Icon name="link" size={16} /> External URL
          </button>
        </div>

        {#if uploadMode === 'direct'}
          <p class="info"><Icon name="info" size={16} /> Direct upload, up to {formatBytes(MAX_DIRECT_UPLOAD_SIZE)}. Files go straight to Bunny Stream in resumable chunks. For anything bigger, use External URL.</p>
          <label class="drop" class:hot={hotZone === 'video'} class:has={!!videoFile}
            on:dragenter={() => (hotZone = 'video')} on:dragleave={() => (hotZone = null)} on:drop={() => (hotZone = null)}>
            <input type="file" accept="video/*" on:change={handleVideoFileChange} aria-label="Video file" />
            <span class="d-ico"><Icon name={videoFile ? 'checkCircle' : 'upload'} size={26} /></span>
            {#if videoFile}
              <b class="d-title">{videoFile.name}</b>
              <span class="d-sub">{formatBytes(videoFile.size)} · click or drop to replace</span>
            {:else}
              <b class="d-title">Drop a video here, or click to choose</b>
              <span class="d-sub">MP4, MOV, WebM, MKV</span>
            {/if}
          </label>

          {#if videoFile && videoFile.size > MAX_DIRECT_UPLOAD_SIZE}
            <div class="warning-card">
              <span class="w-ico"><Icon name="alert" size={18} /></span>
              <div>
                <strong>File too large</strong>
                <p>This file is {formatBytes(videoFile.size)}, over the {formatBytes(MAX_DIRECT_UPLOAD_SIZE)} direct-upload limit. Switch to <strong>External URL</strong> mode and give Bunny a link to pull from instead.</p>
              </div>
            </div>
          {/if}

          {#if uploading && uploadProgress > 0}
            <div class="progress-container">
              <div class="progress-bar" style="width: {uploadProgress}%"></div>
              <span class="progress-text">{uploadProgress}%</span>
            </div>
          {/if}

          {#if statusMsg}<p class="msg status"><span class="spin"></span> {statusMsg}</p>{/if}
          {#if error}<p class="msg bad"><Icon name="alert" size={16} /> {error}</p>{/if}

          <button
            class="btn-primary go"
            on:click={uploadVideoDirect}
            disabled={uploading || !videoFile || (videoFile?.size || 0) > MAX_DIRECT_UPLOAD_SIZE}
          >
            {#if uploading}<span class="spin"></span> Uploading...{:else}Upload to Bunny Stream <Icon name="arrowRight" size={17} />{/if}
          </button>

        {:else}
          <p class="info"><Icon name="info" size={16} /> Point Bunny Stream at a video that already lives somewhere public: S3, a Drive direct link, another CDN. Use this for files over {formatBytes(MAX_DIRECT_UPLOAD_SIZE)}, or when you already have a hosted copy.</p>

          <label class="field">Video URL *
            <span class="url-in">
              <Icon name="link" size={17} />
              <input
                bind:value={externalVideoUrl}
                placeholder="https://example.com/videos/session.mp4"
              />
            </span>
          </label>
          <p class="hint">Bunny Stream will download directly from this URL. Make sure the link is public and doesn't expire immediately.</p>

          {#if statusMsg}<p class="msg status"><span class="spin"></span> {statusMsg}</p>{/if}
          {#if error}<p class="msg bad"><Icon name="alert" size={16} /> {error}</p>{/if}

          <button
            class="btn-primary go"
            on:click={uploadVideoFromUrl}
            disabled={uploading || !externalVideoUrl.trim()}
          >
            {#if uploading}<span class="spin"></span> Queuing...{:else}Fetch from URL <Icon name="arrowRight" size={17} />{/if}
          </button>
        {/if}

        <hr class="divider-line" />

        <div class="field thumb-field">
          <span>Thumbnail (optional)</span>
          <span class="hint">Design one with text, generate it with AI, or upload an image.</span>
          <ThumbnailField kind="episode" title={episodeTitle || 'New episode'} kicker={moduleCategory}
            context={`Part of the course: ${moduleTitle}`} bind:picked={thumbPick} />
        </div>
      </section>
    {:else if step === 'done'}
      <section class="done-card ui-rise" style="--i:4">
        <div class="checkmark"><Icon name="check" size={40} stroke={2.4} /></div>
        <h2>Upload complete</h2>
        <p>Video is being transcoded by Bunny Stream. The episode will be ready once encoding finishes (the webhook updates its status automatically).</p>
        {#if uploadMethod}
          <span class="ui-pill sky method-info"><Icon name={uploadMethod === 'url' ? 'link' : 'upload'} size={14} /> Uploaded via {uploadMethod === 'url' ? 'external URL (fast)' : 'direct upload'}</span>
        {/if}
        <p class="studio-tip"><Icon name="film" size={15} /> Once it's ready, trim, cut, add chapters, text and captions, or let AI find the highlights, in the video studio.</p>
        <div class="done-actions">
          <a href="/admin" class="btn-ghost">Back to dashboard</a>
          <a href="/admin/modules/{moduleId}?edit={episodeId}" class="btn-ghost">Edit in video studio</a>
          <a href="/module/{moduleId}" class="btn-primary">View module <Icon name="arrowRight" size={17} /></a>
        </div>
      </section>
    {/if}
  {/key}
</div>

<style>
  .page { max-width: 680px; margin: 0 auto; }
  .studio-tip { display: inline-flex; gap: 0.45rem; align-items: center; font-size: 0.85rem; color: var(--muted); }
  .head { margin-bottom: 1.25rem; }
  .eyebrow { color: var(--muted); font-size: 0.92rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.04; display: flex; align-items: center; gap: 0.6rem; }
  .title-mark {
    display: inline-grid; place-items: center; width: 46px; height: 46px; border-radius: 50%;
    background: var(--tile-sky); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }

  /* ---------- stepper ---------- */
  .steps { list-style: none; display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1.5rem; padding: 0.6rem; border-radius: 999px; background: var(--surface2); }
  .step { display: flex; align-items: center; gap: 0.55rem; padding-right: 0.6rem; }
  .s-dot {
    width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; flex: none;
    background: var(--surface); color: var(--muted);
    transition: background-color var(--dur-3) var(--ease-out), color var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .step.active .s-dot { background: var(--accent); color: var(--on-accent); scale: 1.08; animation: pop 420ms var(--ease-out); }
  .step.done .s-dot { background: var(--tile-mint); color: var(--tile-ink); animation: pop 420ms var(--ease-out); }
  .s-txt { display: flex; flex-direction: column; font-size: 0.86rem; font-weight: 600; line-height: 1.15; color: var(--muted); white-space: nowrap; }
  .s-txt small { font-size: 0.68rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; }
  .step.active .s-txt, .step.done .s-txt { color: var(--text); }
  .s-line { flex: 1; height: 3px; border-radius: 99px; background: var(--surface3); overflow: hidden; min-width: 16px; }
  .s-line span { display: block; height: 100%; width: 100%; background: var(--success); transform: scaleX(0); transform-origin: left; transition: transform 600ms var(--ease-out); }
  .s-line.filled span { transform: scaleX(1); }

  /* ---------- cards ---------- */
  .card { background: var(--surface); border-radius: 30px; padding: 1.6rem; box-shadow: var(--shadow-sm); display: flex; flex-direction: column; gap: 1.1rem; }
  .card-h { display: flex; gap: 0.9rem; align-items: center; }
  .card-h p { color: var(--muted); font-size: 0.88rem; }
  h2 { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em; }
  .k-ico { width: 46px; height: 46px; border-radius: 16px; display: grid; place-items: center; color: var(--tile-ink); flex: none; transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out); }
  .card:hover .k-ico { rotate: -8deg; scale: 1.06; }
  .k-ico.lilac { background: var(--tile-lilac); }
  .k-ico.butter { background: var(--tile-butter); }
  .k-ico.sky { background: var(--tile-sky); }

  .field { display: flex; flex-direction: column; gap: 0.45rem; font-size: 0.85rem; font-weight: 600; color: var(--text-secondary); }
  input:not([type='file']) {
    background: var(--surface2); border: 1px solid transparent;
    color: var(--text); border-radius: 14px; padding: 0.75rem 0.95rem;
    font-size: 0.95rem; font-weight: 400; outline: none;
    transition: background-color var(--dur-2) var(--ease-out), border-color var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out);
  }
  input:not([type='file']):focus { background: var(--surface); border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent); }
  .url-in { position: relative; display: flex; align-items: center; color: var(--muted); }
  .url-in :global(.icon) { position: absolute; left: 0.9rem; pointer-events: none; }
  .url-in input { width: 100%; padding-left: 2.6rem; }
  .hint { font-size: 0.78rem; font-weight: 400; color: var(--muted); margin-top: -0.4rem; }
  .field .hint { margin-top: -0.2rem; }
  .info { display: flex; gap: 0.55rem; align-items: flex-start; font-size: 0.84rem; line-height: 1.5; color: var(--text-secondary); background: var(--surface2); padding: 0.75rem 0.9rem; border-radius: 16px; }
  .info :global(.icon) { margin-top: 2px; color: var(--muted); }
  .msg { display: flex; gap: 0.5rem; align-items: center; font-size: 0.86rem; font-weight: 500; animation: rise 360ms var(--ease-out); }
  .msg.bad { color: var(--danger); }
  .msg.status { color: var(--text-secondary); }

  /* ---------- segmented upload mode ---------- */
  .seg { position: relative; display: grid; grid-template-columns: 1fr 1fr; padding: 0.3rem; border-radius: 999px; background: var(--surface2); }
  .seg-thumb {
    position: absolute; top: 0.3rem; bottom: 0.3rem; left: 0.3rem; width: calc(50% - 0.3rem);
    border-radius: 999px; background: var(--accent); box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out);
  }
  .seg-thumb.right { translate: 100% 0; }
  .mode-btn {
    position: relative; z-index: 1; height: 42px; border-radius: 999px;
    display: inline-flex; align-items: center; justify-content: center; gap: 0.45rem;
    font-size: 0.9rem; font-weight: 600; color: var(--muted); background: transparent;
    transition: color var(--dur-2) var(--ease-out);
  }
  .mode-btn:hover { color: var(--text); }
  .mode-btn.active { color: var(--on-accent); }

  /* ---------- dropzone ---------- */
  .drop {
    position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.35rem;
    min-height: 190px; padding: 1.5rem; border-radius: 24px; text-align: center; cursor: pointer;
    background: var(--surface2);
    /* Animated dashed border: a repeating gradient on each edge that slides when hot. */
    background-image:
      repeating-linear-gradient(90deg, var(--border-hover) 0 10px, transparent 10px 18px),
      repeating-linear-gradient(90deg, var(--border-hover) 0 10px, transparent 10px 18px),
      repeating-linear-gradient(0deg, var(--border-hover) 0 10px, transparent 10px 18px),
      repeating-linear-gradient(0deg, var(--border-hover) 0 10px, transparent 10px 18px);
    background-size: 100% 2px, 100% 2px, 2px 100%, 2px 100%;
    background-position: 0 0, 0 100%, 0 0, 100% 0;
    background-repeat: no-repeat;
    transition: background-color var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .drop:hover { background-color: var(--surface3); }
  .drop.hot {
    background-color: var(--tile-sky); scale: 1.01;
    background-image:
      repeating-linear-gradient(90deg, var(--tile-ink) 0 10px, transparent 10px 18px),
      repeating-linear-gradient(90deg, var(--tile-ink) 0 10px, transparent 10px 18px),
      repeating-linear-gradient(0deg, var(--tile-ink) 0 10px, transparent 10px 18px),
      repeating-linear-gradient(0deg, var(--tile-ink) 0 10px, transparent 10px 18px);
    animation: march 700ms linear infinite;
  }
  @keyframes march {
    to { background-position: 18px 0, -18px 100%, 0 -18px, 100% 18px; }
  }
  .drop.has { background-color: var(--tile-mint); }
  .drop input { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%; }
  .drop:focus-within { box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
  /* Drops must land on the file input under these; the icon's animation
     would otherwise lift it above the input and the browser opens the file. */
  .d-ico, .d-title, .d-sub { pointer-events: none; }
  .d-ico {
    width: 58px; height: 58px; border-radius: 50%; display: grid; place-items: center; margin-bottom: 0.35rem;
    background: var(--surface); color: var(--text);
    transition: translate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .drop:hover .d-ico { translate: 0 -4px; }
  .drop.hot .d-ico { scale: 1.12; animation: float 1.6s var(--ease-in-out) infinite; }
  .drop.has .d-ico { animation: pop 460ms var(--ease-out); }
  .d-title { font-size: 0.98rem; font-weight: 600; color: var(--text); overflow-wrap: anywhere; }
  .drop.hot .d-title, .drop.has .d-title, .drop.has .d-sub { color: var(--tile-ink); }
  .d-sub { font-size: 0.8rem; color: var(--muted); }
  .thumb-field { max-width: 380px; }

  .warning-card {
    display: flex; gap: 0.75rem; align-items: flex-start;
    background: var(--tile-butter); color: var(--tile-ink);
    border-radius: 20px; padding: 1rem 1.1rem;
    animation: rise 380ms var(--ease-out);
  }
  .w-ico { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); flex: none; animation: wiggle 700ms var(--ease-out) 200ms; }
  .warning-card strong { display: block; margin-bottom: 0.25rem; }
  .warning-card p { margin: 0; font-size: 0.85rem; line-height: 1.5; }

  .divider-line { border: none; border-top: 1px dashed var(--border-hover); margin: 0.3rem 0; }

  /* ---------- progress ---------- */
  .progress-container {
    width: 100%; height: 28px; background: var(--surface2);
    border-radius: 999px; overflow: hidden; position: relative;
    animation: rise 320ms var(--ease-out);
  }
  .progress-bar {
    position: relative; overflow: hidden;
    height: 100%; background: var(--accent);
    transition: width 0.3s var(--ease-out);
    border-radius: 999px;
  }
  .progress-bar::after {
    content: ''; position: absolute; inset: 0;
    background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--on-accent) 28%, transparent), transparent);
    animation: sweep 1.4s linear infinite;
  }
  @keyframes sweep { from { translate: -100% 0; } to { translate: 100% 0; } }
  .progress-text {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-size: 0.78rem;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    /* Sits over a part-filled bar: difference keeps it legible on both the
       fill and the empty track, in either theme. */
    color: #fff;
    mix-blend-mode: difference;
  }

  .go { align-self: flex-start; }
  .go :global(.icon) { transition: translate var(--dur-2) var(--ease-out); }
  .go:hover:not(:disabled) :global(.icon) { translate: 3px 0; }
  .spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid currentColor; border-right-color: transparent; display: inline-block; animation: upspin 0.8s linear infinite; flex: none; }
  @keyframes upspin { to { rotate: 360deg; } }

  /* ---------- done ---------- */
  .done-card { display: flex; flex-direction: column; align-items: center; text-align: center; padding: 3rem 2rem; background: var(--surface); border-radius: 32px; box-shadow: var(--shadow-sm); }
  .checkmark {
    width: 88px; height: 88px; border-radius: 50%; display: grid; place-items: center; margin-bottom: 1rem;
    background: var(--tile-mint); color: var(--tile-ink);
    animation: pop 620ms var(--ease-out) 150ms backwards;
  }
  .done-card p { color: var(--muted); margin: 0.5rem 0 1.2rem; line-height: 1.55; max-width: 46ch; }
  .method-info { margin-bottom: 1.5rem; }
  .done-actions { display: flex; gap: 0.75rem; justify-content: center; flex-wrap: wrap; }

  @media (max-width: 560px) {
    .card { padding: 1.15rem; border-radius: 24px; }
    .s-txt small { display: none; }
    .step { padding-right: 0; }
    .s-txt { font-size: 0.78rem; }
  }
</style>
