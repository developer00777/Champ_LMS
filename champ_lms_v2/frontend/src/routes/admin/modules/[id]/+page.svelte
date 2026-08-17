<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, type AdminModuleDetail, type AdminEpisodeDetail } from '$lib/api/client';
  import { uploadVideoHybrid, uploadThumbnail } from '$lib/utils/upload-client';

  const CATEGORIES = ['sales', 'leadership', 'onboarding', 'product', 'engineering', 'ops'];
  const MAX_DIRECT_UPLOAD_SIZE = 50 * 1024 * 1024;
  const id = $page.params.id;

  let mod: AdminModuleDetail | null = null;
  let loading = true;
  let error = '';
  let saved = '';
  let busy = false;

  // editable copies of module details — never bind straight to `mod`, so a
  // failed save doesn't leave the form showing values the server rejected
  let title = '';
  let description = '';
  let category = '';
  let tagsText = '';

  // add-episode form
  let showAdd = false;
  let epTitle = '';
  let epDescription = '';
  let videoFile: File | null = null;
  let thumbFile: File | null = null;
  let externalUrl = '';
  let addMode: 'file' | 'url' | 'later' = 'file';
  let uploading = false;
  let uploadProgress = 0;
  let statusMsg = '';
  let addError = '';

  // inline episode rename
  let editingEp = '';
  let editTitle = '';

  onMount(load);

  async function load() {
    loading = true;
    try {
      mod = await api.adminModule(id);
      title = mod.title;
      description = mod.description ?? '';
      category = mod.category ?? '';
      tagsText = (mod.tags ?? []).join(', ');
      error = '';
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  function flash(msg: string) {
    saved = msg;
    setTimeout(() => (saved = ''), 3000);
  }

  function formatBytes(b: number): string {
    if (!b) return '0 B';
    const k = 1024, sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(b) / Math.log(k));
    return `${parseFloat((b / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  }

  function fmtDuration(s: number | null): string {
    if (!s) return '—';
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  }

  async function saveDetails() {
    busy = true; error = '';
    try {
      mod = await api.updateModule(id, {
        title: title.trim(),
        description: description.trim() || null,
        category: category || null,
        tags: tagsText.split(',').map((t) => t.trim()).filter(Boolean),
      });
      flash('Module details saved.');
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  async function togglePublish() {
    if (!mod) return;
    busy = true; error = '';
    try {
      const r = await api.publishModule(id, !mod.is_published);
      mod.is_published = r.published;
      mod = mod;
      flash(r.published ? 'Module is now live.' : 'Module unpublished.');
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  function pickVideo(e: Event) {
    videoFile = (e.target as HTMLInputElement).files?.[0] ?? null;
    addError = '';
    if (videoFile && videoFile.size > MAX_DIRECT_UPLOAD_SIZE) {
      addMode = 'url';
      addError = `That file is ${formatBytes(videoFile.size)}. Anything over `
        + `${formatBytes(MAX_DIRECT_UPLOAD_SIZE)} has to come in by URL.`;
    }
  }

  function pickThumb(e: Event) {
    thumbFile = (e.target as HTMLInputElement).files?.[0] ?? null;
  }

  function resetAddForm() {
    epTitle = ''; epDescription = ''; videoFile = null; thumbFile = null;
    externalUrl = ''; addMode = 'file'; statusMsg = ''; addError = ''; uploadProgress = 0;
  }

  // Adds one more episode to a module that already exists. The episode row is
  // created first so the upload has something to attach to — the same order the
  // original wizard uses, just without recreating the module.
  async function addEpisode() {
    if (!epTitle.trim()) { addError = 'Give the episode a title'; return; }
    if (addMode === 'file' && !videoFile) { addError = 'Choose a video file'; return; }
    if (addMode === 'url' && !externalUrl.trim()) { addError = 'Paste a video URL'; return; }

    uploading = true; addError = ''; statusMsg = ''; uploadProgress = 0;
    const token = localStorage.getItem('champ_token') || '';
    let newEpisodeId = '';

    try {
      statusMsg = 'Creating episode…';
      // sequence_order left out — the backend appends after the last episode
      const created = await api.addEpisode(id, {
        title: epTitle.trim(),
        description: epDescription.trim() || undefined,
      });
      newEpisodeId = created.id;

      if (addMode === 'file' && videoFile) {
        await uploadVideoHybrid({
          file: videoFile,
          episodeId: newEpisodeId,
          token,
          onProgress: (loaded, total) => { uploadProgress = Math.round((loaded / total) * 100); },
          onStatus: (m) => { statusMsg = m; },
        });
        statusMsg = 'Uploaded — Bunny Stream is transcoding.';
      } else if (addMode === 'url') {
        statusMsg = 'Handing the URL to Bunny Stream…';
        const res = await fetch(`/api/admin/episodes/${newEpisodeId}/upload-from-url`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          body: JSON.stringify({ video_url: externalUrl.trim() }),
        });
        if (!res.ok) throw new Error(`Bunny could not fetch that URL: ${await res.text()}`);
        statusMsg = 'Bunny Stream is downloading and transcoding.';
      }

      if (thumbFile) {
        statusMsg = 'Uploading thumbnail…';
        await uploadThumbnail({ episodeId: newEpisodeId, file: thumbFile, token });
      }

      resetAddForm();
      showAdd = false;
      await load();
      flash(
        addMode === 'later'
          ? 'Episode added. Upload its video whenever you are ready.'
          : 'Episode added — it will show as ready once transcoding finishes.',
      );
    } catch (e: any) {
      // The episode row survives a failed upload on purpose: it keeps its slot
      // in the module and can be retried instead of being silently lost.
      addError = newEpisodeId
        ? `${e.message} — the episode was created, so you can retry the upload from the list below.`
        : e.message;
      statusMsg = '';
      if (newEpisodeId) { showAdd = false; resetAddForm(); await load(); }
    } finally {
      uploading = false;
      uploadProgress = 0;
    }
  }

  function startRename(ep: AdminEpisodeDetail) {
    editingEp = ep.id;
    editTitle = ep.title;
  }

  async function saveRename() {
    if (!editTitle.trim()) return;
    busy = true;
    try {
      await api.updateEpisode(editingEp, { title: editTitle.trim() });
      editingEp = '';
      await load();
      flash('Episode renamed.');
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  // Reordering renumbers the whole module in one request, so the sequence can
  // never end up with a gap or a tie.
  async function move(index: number, delta: number) {
    if (!mod) return;
    const ids = mod.episodes.map((e) => e.id);
    const target = index + delta;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    busy = true;
    try {
      await api.reorderEpisodes(id, ids);
      await load();
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }
</script>

<svelte:head><title>{mod?.title ?? 'Module'} — Admin</title></svelte:head>

<div class="page">
  <p class="breadcrumb"><a href="/admin/content">← Content Library</a></p>

  {#if loading}
    <div class="skeleton big"></div>
  {:else if !mod}
    <p class="error">{error || 'Module not found'}</p>
  {:else}
    <div class="head">
      <div>
        <h1>{mod.title}</h1>
        <p class="sub">
          {mod.episodes.length} episode{mod.episodes.length === 1 ? '' : 's'}
          {#if mod.category}· {mod.category}{/if}
          · {mod.module_type}
        </p>
      </div>
      <div class="head-actions">
        <span class="status" class:live={mod.is_published}>
          {mod.is_published ? 'Published' : 'Draft'}
        </span>
        <a href="/module/{mod.id}" class="btn">View as learner</a>
      </div>
    </div>

    {#if error}<p class="error">{error}</p>{/if}
    {#if saved}<p class="ok">{saved}</p>{/if}

    <div class="form-card">
      <h2>Module details</h2>
      <label>Title<input bind:value={title} /></label>
      <label>Description<input bind:value={description} placeholder="Optional" /></label>
      <div class="row">
        <label>Category
          <select bind:value={category}>
            <option value="">—</option>
            {#each CATEGORIES as c}<option value={c}>{c}</option>{/each}
          </select>
        </label>
        <label>Tags (comma separated)<input bind:value={tagsText} placeholder="pricing, discovery" /></label>
      </div>
      <div class="btn-row">
        <button class="btn primary" disabled={busy} on:click={saveDetails}>
          {busy ? 'Saving…' : 'Save details'}
        </button>
        <button class="btn" disabled={busy} on:click={togglePublish}>
          {mod.is_published ? 'Unpublish' : 'Publish'}
        </button>
      </div>
    </div>

    <div class="ep-head">
      <h2>Episodes</h2>
      <button class="btn primary" on:click={() => { showAdd = !showAdd; addError = ''; }}>
        {showAdd ? 'Cancel' : '+ Add episode'}
      </button>
    </div>

    {#if showAdd}
      <div class="form-card add">
        <h3>New episode — appended as #{mod.episodes.length + 1}</h3>
        <label>Episode title *<input bind:value={epTitle} placeholder="e.g. Handling Price Objections" /></label>
        <label>Description<input bind:value={epDescription} placeholder="Optional" /></label>

        <div class="mode-toggle">
          <button class="mode-btn" class:active={addMode === 'file'} on:click={() => (addMode = 'file')}>Upload file</button>
          <button class="mode-btn" class:active={addMode === 'url'} on:click={() => (addMode = 'url')}>External URL</button>
          <button class="mode-btn" class:active={addMode === 'later'} on:click={() => (addMode = 'later')}>Add video later</button>
        </div>

        {#if addMode === 'file'}
          <p class="info">Direct upload, max {formatBytes(MAX_DIRECT_UPLOAD_SIZE)}. Larger files go through External URL.</p>
          <label>Video file *
            <input type="file" accept="video/*" on:change={pickVideo} />
            {#if videoFile}<span class="file-info">{videoFile.name} ({formatBytes(videoFile.size)})</span>{/if}
          </label>
        {:else if addMode === 'url'}
          <label>Video URL *
            <input bind:value={externalUrl} placeholder="https://…" />
          </label>
          <p class="hint">Bunny Stream downloads straight from this link — it must be public and not expire immediately.</p>
        {:else}
          <p class="info">
            Creates the episode slot now with no video. It stays in <b>pending</b> and
            is hidden from learners until you upload one.
          </p>
        {/if}

        <label>Thumbnail (optional)
          <input type="file" accept="image/*" on:change={pickThumb} />
        </label>

        {#if uploading && uploadProgress > 0}
          <div class="progress"><div class="bar" style="width: {uploadProgress}%"></div>
            <span class="pct">{uploadProgress}%</span></div>
        {/if}
        {#if statusMsg}<p class="status-msg">{statusMsg}</p>{/if}
        {#if addError}<p class="error">{addError}</p>{/if}

        <button class="btn primary" disabled={uploading} on:click={addEpisode}>
          {uploading ? 'Working…' : 'Add episode'}
        </button>
      </div>
    {/if}

    {#if mod.episodes.length === 0}
      <div class="empty">
        <p>No episodes yet. Add the first one above.</p>
      </div>
    {:else}
      <div class="ep-list">
        {#each mod.episodes as ep, i (ep.id)}
          <div class="ep">
            <div class="ord">
              <button class="arrow" disabled={i === 0 || busy} on:click={() => move(i, -1)} aria-label="Move up">▲</button>
              <span class="num">{ep.sequence_order}</span>
              <button class="arrow" disabled={i === mod.episodes.length - 1 || busy}
                      on:click={() => move(i, 1)} aria-label="Move down">▼</button>
            </div>
            <div class="ep-body">
              {#if editingEp === ep.id}
                <div class="rename">
                  <input bind:value={editTitle} />
                  <button class="btn sm primary" disabled={busy} on:click={saveRename}>Save</button>
                  <button class="btn sm" on:click={() => (editingEp = '')}>Cancel</button>
                </div>
              {:else}
                <b>{ep.title}</b>
                <button class="link" on:click={() => startRename(ep)}>rename</button>
              {/if}
              <div class="chips">
                <span class="chip s-{ep.status}">{ep.status}</span>
                <span class="chip">{fmtDuration(ep.duration_seconds)}</span>
                {#if !ep.has_remote_video}<span class="chip warn">no video uploaded</span>{/if}
              </div>
            </div>
          </div>
        {/each}
      </div>
      <p class="foot-note">
        To delete an episode or its Bunny video permanently, use the
        <a href="/admin/content">Content Library</a>.
      </p>
    {/if}
  {/if}
</div>

<style>
  .page { max-width: 820px; margin: 0 auto; padding-bottom: 4rem; }
  .breadcrumb { font-size: 0.83rem; margin-bottom: 1rem; }
  .breadcrumb a { color: var(--accent); text-decoration: none; }
  .head { display: flex; justify-content: space-between; align-items: flex-start;
          gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
  .head-actions { display: flex; align-items: center; gap: 0.6rem; }
  h1 { font-size: 1.5rem; font-weight: 800; margin-bottom: 0.3rem; }
  .sub { color: var(--muted); font-size: 0.85rem; }
  .status { font-size: 0.72rem; font-weight: 700; text-transform: uppercase; color: var(--muted);
            border: 1px solid var(--border); border-radius: 999px; padding: 0.2rem 0.6rem; }
  .status.live { color: var(--success); border-color: var(--success); }

  .form-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
               padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.25rem; }
  .form-card.add { border-color: var(--accent); }
  h2 { font-size: 1.1rem; font-weight: 700; }
  h3 { font-size: 0.98rem; font-weight: 700; }
  label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.82rem; color: var(--muted); flex: 1; }
  input, select { background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 0.55rem 0.75rem; font-size: 0.88rem; outline: none;
    font-family: inherit; width: 100%; }
  input:focus, select:focus { border-color: var(--accent); }
  .row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .btn-row { display: flex; gap: 0.6rem; }

  .info { font-size: 0.82rem; color: var(--muted); background: var(--surface2);
          padding: 0.65rem 0.8rem; border-radius: 6px; line-height: 1.55; }
  .hint { font-size: 0.75rem; color: var(--muted); }
  .file-info { font-size: 0.78rem; color: var(--muted); margin-top: 0.2rem; }
  .error { color: #e05260; font-size: 0.85rem; }
  .ok { color: var(--success); font-size: 0.85rem; margin-bottom: 1rem; }
  .status-msg { color: var(--gold); font-size: 0.83rem; }

  .mode-toggle { display: flex; gap: 0.5rem; }
  .mode-btn { flex: 1; padding: 0.55rem 0.8rem; background: var(--surface2);
              border: 1px solid var(--border); border-radius: 6px; color: var(--text);
              cursor: pointer; font-size: 0.83rem; }
  .mode-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }

  .progress { width: 100%; height: 22px; background: var(--surface2);
              border-radius: 11px; overflow: hidden; position: relative; }
  .bar { height: 100%; background: var(--accent); transition: width 0.3s ease; }
  .pct { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
         font-size: 0.72rem; font-weight: 600; color: #fff; }

  .ep-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.9rem; }
  .ep-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .ep { display: flex; gap: 0.9rem; align-items: center; background: var(--surface);
        border: 1px solid var(--border); border-radius: 9px; padding: 0.85rem 1rem; }
  .ord { display: flex; flex-direction: column; align-items: center; gap: 0.1rem; flex-shrink: 0; }
  .arrow { background: none; border: none; color: var(--muted); font-size: 0.6rem;
           cursor: pointer; padding: 0.1rem; line-height: 1; }
  .arrow:hover:not(:disabled) { color: var(--accent); }
  .arrow:disabled { opacity: 0.25; cursor: not-allowed; }
  .num { font-size: 0.82rem; font-weight: 700; color: var(--muted); font-variant-numeric: tabular-nums; }
  .ep-body { flex: 1; min-width: 0; }
  .ep-body b { font-size: 0.93rem; }
  .rename { display: flex; gap: 0.45rem; align-items: center; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.35rem; }
  .chip { font-size: 0.7rem; color: var(--muted); background: var(--surface2);
          border-radius: 999px; padding: 0.16rem 0.5rem; }
  .chip.warn { color: #ffc107; }
  .chip.s-ready { color: var(--success); }
  .chip.s-processing { color: #ffc107; }
  .chip.s-failed { color: #e05260; }

  .btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 6px; padding: 0.55rem 1rem; font-size: 0.85rem; font-weight: 600;
         cursor: pointer; text-decoration: none; white-space: nowrap; }
  .btn:hover:not(:disabled) { border-color: var(--accent); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
  .btn.sm { padding: 0.35rem 0.7rem; font-size: 0.78rem; }
  .link { background: none; border: none; color: var(--accent); font-size: 0.74rem;
          cursor: pointer; padding: 0 0 0 0.5rem; font-weight: 600; }

  .empty { text-align: center; padding: 2.5rem 1rem; background: var(--surface);
           border: 1px solid var(--border); border-radius: 10px; color: var(--muted); font-size: 0.88rem; }
  .foot-note { font-size: 0.78rem; color: var(--muted); margin-top: 1rem; }
  .foot-note a { color: var(--accent); }

  .skeleton { border-radius: 10px; background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
              background-size: 200% 100%; animation: shimmer 1.4s infinite; }
  .skeleton.big { height: 320px; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
</style>
