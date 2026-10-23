<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, type AdminModuleDetail, type AdminEpisodeDetail } from '$lib/api/client';
  import { uploadVideoHybrid } from '$lib/utils/upload-client';
  import ThumbnailField from '$lib/components/ThumbnailField.svelte';
  import ThumbnailStudio from '$lib/components/ThumbnailStudio.svelte';
  import VideoStudio from '$lib/components/studio/VideoStudio.svelte';
  import type { PickedThumbnail } from '$lib/thumbnails/designer';
  import Icon from '$lib/components/Icon.svelte';
  import Select from '$lib/components/Select.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import Thumb from '$lib/components/Thumb.svelte';

  const CATEGORIES = ['sales', 'leadership', 'onboarding', 'product', 'engineering', 'ops'];
  const CATEGORY_OPTIONS = [
    { value: '', label: 'No category' },
    ...CATEGORIES.map(c => ({ value: c, label: c[0].toUpperCase() + c.slice(1) })),
  ];
  const MAX_DIRECT_UPLOAD_SIZE = 1024 * 1024 * 1024;
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
  let thumbPick: PickedThumbnail | null = null;
  // The episode whose thumbnail is open in the studio, from the list below.
  let thumbEp: AdminEpisodeDetail | null = null;
  let externalUrl = '';
  let addMode: 'file' | 'url' | 'later' = 'file';
  let uploading = false;
  let uploadProgress = 0;
  let statusMsg = '';
  let addError = '';

  // The episode open in the video studio. ?edit=<episode id> opens it on
  // arrival (the upload wizard links here once a video is up).
  let studioEp = $page.url.searchParams.get('edit') ?? '';

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

  function resetAddForm() {
    epTitle = ''; epDescription = ''; videoFile = null; thumbPick = null;
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

      if (thumbPick) {
        statusMsg = 'Saving thumbnail…';
        await api.saveThumbnail('episode', newEpisodeId, thumbPick.blob, thumbPick.source, thumbPick.design);
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

  const MODES = [
    { key: 'file', label: 'Upload file', icon: 'upload' },
    { key: 'url', label: 'External URL', icon: 'link' },
    { key: 'later', label: 'Add video later', icon: 'clock' },
  ] as const;
  const STATUS_TONE: Record<string, string> = { ready: 'mint', processing: 'butter', pending: 'sky', failed: 'danger' };
</script>

<svelte:head><title>{mod?.title ?? 'Module'} — Admin</title></svelte:head>

<div class="page">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Content Library', href: '/admin/content' }, { label: mod?.title || 'Module' }]} />

  {#if loading && !mod}
    <div class="ui-skeleton" style="height:96px;border-radius:24px;margin-bottom:1.25rem"></div>
    <div class="ui-skeleton" style="height:300px;border-radius:28px;margin-bottom:1.25rem"></div>
    {#each Array(3) as _}<div class="ui-skeleton" style="height:84px;border-radius:22px;margin-bottom:0.6rem"></div>{/each}
  {:else if !mod}
    <div class="state ui-rise">
      <span class="state-ico danger"><Icon name="alert" size={26} /></span>
      <h2>Module not available</h2>
      <p>{error || 'Module not found'}</p>
      <a class="btn-ghost" href="/admin/content">Back to the library</a>
    </div>
  {:else}
    <header class="head">
      <div class="head-copy">
        <p class="eyebrow ui-rise" style="--i:1">Module editor</p>
        <h1 class="ui-rise" style="--i:2">
          <span class="title-text">{mod.title}</span>
          <span class="title-mark" aria-hidden="true"><Icon name="layers" size={22} /></span>
        </h1>
        <div class="meta ui-rise" style="--i:3">
          <span class="ui-pill sky"><Icon name="film" size={14} /> {mod.episodes.length} episode{mod.episodes.length === 1 ? '' : 's'}</span>
          {#if mod.category}<span class="ui-pill lilac cap">{mod.category}</span>{/if}
          <span class="ui-pill butter cap">{mod.module_type}</span>
        </div>
      </div>
      <div class="head-actions ui-rise" style="--i:3">
        <span class="status" class:live={mod.is_published}>
          <span class="s-dot"></span>{mod.is_published ? 'Published' : 'Draft'}
        </span>
        <a href="/module/{mod.id}" class="btn-ghost"><Icon name="eye" size={16} /> View as learner</a>
      </div>
    </header>

    {#if error}<p class="note bad" role="alert"><Icon name="alert" size={16} /> {error}</p>{/if}
    {#if saved}<p class="note good" role="status"><Icon name="checkCircle" size={16} /> {saved}</p>{/if}

    <section class="card ui-rise" style="--i:4">
      <div class="card-head">
        <span class="c-ico lilac"><Icon name="edit" size={18} /></span>
        <h2>Module details</h2>
      </div>
      <div class="thumb-field">
        <span class="lbl">Thumbnail</span>
        <ThumbnailField kind="module" ownerId={mod.id} title={mod.title} kicker={mod.category ?? ''}
          state={mod} onChange={s => mod && (mod = { ...mod, ...s })} />
      </div>
      <label>Title<input bind:value={title} /></label>
      <label>Description<input bind:value={description} placeholder="Optional" /></label>
      <div class="row">
        <!-- svelte-ignore a11y-label-has-associated-control -->
        <label>Category
          <Select bind:value={category} size="lg" placeholder="No category" options={CATEGORY_OPTIONS} />
        </label>
        <label>Tags (comma separated)<input bind:value={tagsText} placeholder="pricing, discovery" /></label>
      </div>
      <div class="btn-row">
        <button class="btn-primary" disabled={busy} on:click={saveDetails}>
          <Icon name="save" size={16} /> {busy ? 'Saving…' : 'Save details'}
        </button>
        <button class="btn-ghost" disabled={busy} on:click={togglePublish}>
          <Icon name={mod.is_published ? 'eyeOff' : 'send'} size={16} />
          {mod.is_published ? 'Unpublish' : 'Publish'}
        </button>
      </div>
    </section>

    <div class="ep-head ui-rise" style="--i:5">
      <h2>Episodes <span class="count">{mod.episodes.length}</span></h2>
      <button class="btn-primary add-toggle" class:open={showAdd} on:click={() => { showAdd = !showAdd; addError = ''; }}>
        <span class="plus"><Icon name="plus" size={16} /></span>
        {showAdd ? 'Cancel' : 'Add episode'}
      </button>
    </div>

    {#if showAdd}
      <section class="card add">
        <div class="card-head">
          <span class="c-ico mint"><Icon name="video" size={18} /></span>
          <h3>New episode — appended as #{mod.episodes.length + 1}</h3>
        </div>
        <label>Episode title *<input bind:value={epTitle} placeholder="e.g. Handling Price Objections" /></label>
        <label>Description<input bind:value={epDescription} placeholder="Optional" /></label>

        <div class="mode-toggle" role="group" aria-label="How the video arrives">
          {#each MODES as m}
            <button class="mode-btn" class:active={addMode === m.key} on:click={() => (addMode = m.key)}>
              <Icon name={m.icon} size={16} /> {m.label}
            </button>
          {/each}
        </div>

        {#key addMode}
          <div class="mode-body">
            {#if addMode === 'file'}
              <p class="info"><Icon name="info" size={16} /> Direct upload, up to {formatBytes(MAX_DIRECT_UPLOAD_SIZE)} — sent to Bunny in resumable chunks. Larger files go through External URL.</p>
              <label>Video file *
                <input type="file" accept="video/*" on:change={pickVideo} />
                {#if videoFile}<span class="file-info"><Icon name="file" size={14} /> {videoFile.name} ({formatBytes(videoFile.size)})</span>{/if}
              </label>
            {:else if addMode === 'url'}
              <label>Video URL *
                <input bind:value={externalUrl} placeholder="https://…" />
              </label>
              <p class="hint">Bunny Stream downloads straight from this link — it must be public and not expire immediately.</p>
            {:else}
              <p class="info">
                <Icon name="info" size={16} />
                <span>Creates the episode slot now with no video. It stays in <b>pending</b> and
                is hidden from learners until you upload one.</span>
              </p>
            {/if}
          </div>
        {/key}

        <div class="thumb-field">
          <span class="lbl">Thumbnail (optional)</span>
          <ThumbnailField kind="episode" title={epTitle.trim() || 'New episode'} kicker={`Episode ${mod.episodes.length + 1}`}
            context={`Part of the course: ${mod.title}${epDescription.trim() ? `
About: ${epDescription.trim()}` : ''}`}
            bind:picked={thumbPick} />
        </div>

        {#if uploading && uploadProgress > 0}
          <div class="progress" role="progressbar" aria-valuenow={uploadProgress} aria-valuemin="0" aria-valuemax="100">
            <div class="bar" style="width: {uploadProgress}%"></div>
            <span class="pct">{uploadProgress}%</span>
          </div>
        {/if}
        {#if statusMsg}<p class="status-msg"><span class="spin"></span> {statusMsg}</p>{/if}
        {#if addError}<p class="note bad"><Icon name="alert" size={16} /> {addError}</p>{/if}

        <div class="btn-row">
          <button class="btn-primary" disabled={uploading} on:click={addEpisode}>
            <Icon name="plus" size={16} /> {uploading ? 'Working…' : 'Add episode'}
          </button>
        </div>
      </section>
    {/if}

    {#if mod.episodes.length === 0}
      <div class="state small ui-rise" style="--i:6">
        <span class="state-ico"><Icon name="film" size={24} /></span>
        <h2>No episodes yet</h2>
        <p>Add the first one above.</p>
      </div>
    {:else}
      <div class="ep-list">
        {#each mod.episodes as ep, i (ep.id)}
          <div class="ep ui-rise" style="--i:{Math.min(i + 6, 12)}">
            <button class="ep-thumb" on:click={() => (thumbEp = ep)} aria-label="Thumbnail for {ep.title}" title="Change thumbnail">
              {#if ep.thumbnail_url}<Thumb src={ep.thumbnail_url} />{:else}<Icon name="plus" size={16} />{/if}
            </button>
            <div class="ord">
              <button class="arrow" disabled={i === 0 || busy} on:click={() => move(i, -1)} aria-label="Move up">
                <Icon name="chevronUp" size={16} />
              </button>
              <span class="num">{ep.sequence_order}</span>
              <button class="arrow" disabled={i === mod.episodes.length - 1 || busy}
                      on:click={() => move(i, 1)} aria-label="Move down">
                <Icon name="chevronDown" size={16} />
              </button>
            </div>
            <span class="ep-ico {STATUS_TONE[ep.status] ?? 'sky'}" aria-hidden="true">
              <Icon name={ep.has_remote_video ? 'play' : 'video'} size={18} stroke={ep.has_remote_video ? 0 : 1.75} />
            </span>
            <div class="ep-body">
              {#if editingEp === ep.id}
                <div class="rename">
                  <input bind:value={editTitle} />
                  <button class="btn-primary sm" disabled={busy} on:click={saveRename}>Save</button>
                  <button class="btn-ghost sm" on:click={() => (editingEp = '')}>Cancel</button>
                </div>
              {:else}
                <div class="ep-title">
                  <b>{ep.title}</b>
                  <button class="link" on:click={() => startRename(ep)}><Icon name="edit" size={13} /> rename</button>
                  <button class="link" on:click={() => (thumbEp = ep)}><Icon name="sparkles" size={13} /> thumbnail</button>
                  {#if ep.status === 'ready'}
                    <button class="link" on:click={() => (studioEp = ep.id)}><Icon name="film" size={13} /> edit video</button>
                  {/if}
                </div>
              {/if}
              <div class="chips">
                <span class="chip s-{ep.status}"><span class="c-dot"></span>{ep.status}</span>
                <span class="chip"><Icon name="clock" size={12} /> {fmtDuration(ep.duration_seconds)}</span>
                {#if !ep.has_remote_video}<span class="chip warn"><Icon name="alert" size={12} /> no video uploaded</span>{/if}
              </div>
            </div>
          </div>
        {/each}
      </div>
      {#if studioEp}
        <VideoStudio episodeId={studioEp} onClose={() => { studioEp = ''; load(); }}
          onSaved={s => { flash(s.part ? `Saved. The video is now ${s.part[1]} episodes.` : 'Video edits saved.'); load(); }} />
      {/if}
      {#if thumbEp}
        <ThumbnailStudio kind="episode" ownerId={thumbEp.id} title={thumbEp.title}
          kicker={`Episode ${thumbEp.sequence_order}`} current={thumbEp}
          onClose={() => (thumbEp = null)} onSaved={s => {
            // Update the row in place: a full reload would flash the skeleton.
            if (mod && thumbEp) mod = { ...mod, episodes: mod.episodes.map(e => (e.id === thumbEp?.id ? { ...e, ...s } : e)) };
            flash(s.thumbnail_source ? 'Thumbnail saved.' : 'Thumbnail removed.');
          }} />
      {/if}
      <p class="foot-note">
        <Icon name="info" size={14} />
        <span>To delete an episode or its Bunny video permanently, use the
        <a href="/admin/content">Content Library</a>.</span>
      </p>
    {/if}
  {/if}
</div>

<style>
  .page { max-width: 880px; margin: 0 auto; }

  /* ---------- header ---------- */
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1.25rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
  .head-copy { min-width: 0; }
  .eyebrow { color: var(--muted); font-size: 0.92rem; font-weight: 500; margin-bottom: 0.3rem; }
  h1 { font-size: clamp(1.6rem, 1.1rem + 1.6vw, 2.3rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.08; display: flex; align-items: center; gap: 0.6rem; }
  .title-text { min-width: 0; overflow-wrap: anywhere; }
  .title-mark {
    flex: none; display: inline-grid; place-items: center; width: 44px; height: 44px; border-radius: 50%;
    background: var(--tile-mint); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .meta { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.75rem; }
  .cap { text-transform: capitalize; }
  .head-actions { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
  .status {
    display: inline-flex; align-items: center; gap: 0.45rem; height: 34px; padding: 0 0.85rem;
    border-radius: 999px; font-size: 0.78rem; font-weight: 700; background: var(--surface2); color: var(--muted);
  }
  .status.live { background: color-mix(in srgb, var(--success) 15%, transparent); color: var(--success); }
  .s-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .status.live .s-dot { animation: pulse-ring 1.6s var(--ease-out) infinite; }

  /* ---------- notes ---------- */
  .note {
    display: flex; align-items: flex-start; gap: 0.5rem; font-size: 0.86rem; font-weight: 500;
    padding: 0.7rem 0.95rem; border-radius: 16px; margin-bottom: 1rem; animation: rise 360ms var(--ease-out);
  }
  .note :global(.icon) { flex: none; margin-top: 1px; }
  .note.bad { background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger); }
  .note.good { background: color-mix(in srgb, var(--success) 13%, transparent); color: var(--success); }

  /* ---------- cards / forms ---------- */
  .card {
    background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-sm);
    padding: 1.4rem 1.5rem 1.5rem; display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.5rem;
  }
  .card.add { box-shadow: 0 0 0 2px var(--accent), var(--shadow); animation: rise 420ms var(--ease-out); }
  .card-head { display: flex; align-items: center; gap: 0.7rem; }
  .c-ico { width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; color: var(--tile-ink); transition: rotate var(--dur-3) var(--ease-out); }
  .card:hover .c-ico { rotate: -12deg; }
  .c-ico.lilac { background: var(--tile-lilac); }
  .c-ico.mint { background: var(--tile-mint); }
  h2 { font-size: 1.2rem; font-weight: 700; letter-spacing: -0.02em; }
  h3 { font-size: 1.02rem; font-weight: 700; }
  label { display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.82rem; font-weight: 500; color: var(--muted); flex: 1; min-width: 200px; }
  input {
    background: var(--surface2); border: 1px solid transparent; color: var(--text);
    border-radius: 14px; padding: 0.7rem 0.9rem; font-size: 0.9rem; font-family: inherit; width: 100%;
    transition: background-color var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out);
  }
  input:hover { background: var(--surface3); }
  input:focus { background: var(--surface); box-shadow: 0 0 0 2px var(--accent); outline: none; }
  input[type='file'] { padding: 0.55rem; cursor: pointer; }
  .row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .btn-row { display: flex; gap: 0.6rem; flex-wrap: wrap; }
  .btn-row :global(.icon), .add-toggle :global(.icon), .head-actions :global(.icon) { flex: none; }
  .sm { height: 36px; padding: 0 0.9rem; font-size: 0.8rem; }

  .info {
    display: flex; gap: 0.55rem; align-items: flex-start;
    font-size: 0.84rem; color: var(--tile-ink); background: var(--tile-sky);
    padding: 0.75rem 0.95rem; border-radius: 16px; line-height: 1.55;
  }
  .info :global(.icon) { flex: none; margin-top: 2px; }
  .hint { font-size: 0.78rem; color: var(--muted); }
  .file-info { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.78rem; color: var(--text-secondary); margin-top: 0.15rem; animation: fade 300ms var(--ease-out); }
  .mode-body { display: flex; flex-direction: column; gap: 0.75rem; animation: rise 320ms var(--ease-out); }
  .status-msg { display: inline-flex; align-items: center; gap: 0.5rem; color: var(--text-secondary); font-size: 0.84rem; font-weight: 500; }
  .spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--surface3); border-top-color: var(--accent); animation: spin 800ms linear infinite; }
  @keyframes spin { to { rotate: 360deg; } }

  .mode-toggle { display: flex; gap: 0.3rem; padding: 0.3rem; border-radius: 999px; background: var(--surface2); }
  .mode-btn {
    flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 0.4rem;
    height: 40px; padding: 0 0.8rem; border-radius: 999px; background: transparent; color: var(--muted);
    font-size: 0.84rem; font-weight: 600;
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2) var(--ease-out), box-shadow var(--dur-2);
  }
  .mode-btn:hover { color: var(--text); }
  .mode-btn.active { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); }
  .mode-btn.active :global(.icon) { animation: pop 360ms var(--ease-out); }

  .progress { width: 100%; height: 26px; background: var(--surface2); border-radius: 999px; overflow: hidden; position: relative; }
  .bar { height: 100%; background: var(--accent); border-radius: inherit; transition: width 0.3s var(--ease-out); }
  .pct { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 0.74rem; font-weight: 700; color: #fff; mix-blend-mode: difference; }

  /* ---------- episodes ---------- */
  .ep-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-bottom: 0.9rem; }
  .ep-head h2 { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 1.4rem; }
  .count { min-width: 26px; height: 24px; padding: 0 7px; border-radius: 99px; font-size: 0.78rem; display: inline-grid; place-items: center; background: var(--surface2); color: var(--text-secondary); }
  .plus { display: inline-grid; transition: rotate var(--dur-3) var(--ease-out); }
  .add-toggle.open .plus { rotate: 45deg; }
  .add-toggle:hover .plus { scale: 1.15; }

  .ep-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .ep {
    display: flex; gap: 0.9rem; align-items: center; background: var(--surface);
    border-radius: 22px; padding: 0.7rem 1.1rem 0.7rem 0.7rem; box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .ep:hover { translate: 4px 0; box-shadow: var(--shadow); }
  .ord { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; background: var(--surface2); border-radius: 16px; padding: 0.15rem 0.2rem; }
  .arrow {
    width: 30px; height: 24px; display: grid; place-items: center; border-radius: 10px;
    background: none; color: var(--muted); transition: color var(--dur-2), background-color var(--dur-2), translate var(--dur-2) var(--ease-out);
  }
  .arrow:hover:not(:disabled) { color: var(--text); background: var(--surface3); }
  .arrow:first-child:hover:not(:disabled) { translate: 0 -2px; }
  .arrow:last-child:hover:not(:disabled) { translate: 0 2px; }
  .arrow:disabled { opacity: 0.25; cursor: not-allowed; }
  .num { font-size: 0.85rem; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
  .ep-ico { flex: none; width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center; color: var(--tile-ink); transition: scale var(--dur-3) var(--ease-out), rotate var(--dur-3) var(--ease-out); }
  .ep-ico :global(svg[stroke-width='0']) { fill: currentColor; translate: 1px 0; }
  .ep:hover .ep-ico { scale: 1.08; rotate: -8deg; }
  .ep-ico.mint { background: var(--tile-mint); }
  .ep-ico.butter { background: var(--tile-butter); }
  .ep-ico.sky { background: var(--tile-sky); }
  .ep-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }
  .ep-body { flex: 1; min-width: 0; }
  /* Episode thumbnail: opens the thumbnail studio. */
  .ep-thumb {
    position: relative; overflow: hidden; flex-shrink: 0; width: 96px; aspect-ratio: 16 / 9; border-radius: 12px; cursor: pointer;
    display: grid; place-items: center; background: var(--surface2); color: var(--muted);
    box-shadow: inset 0 0 0 1px var(--border-hover);
    transition: box-shadow var(--dur-2), color var(--dur-2);
  }
  .ep-thumb:hover { box-shadow: inset 0 0 0 2px var(--accent); color: var(--text); }
  .ep-thumb:hover :global(.thumb-media) { scale: 1.06; }
  .thumb-field { display: grid; gap: 0.35rem; max-width: 380px; }
  .lbl { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
  .ep-title { display: flex; align-items: baseline; gap: 0.3rem; flex-wrap: wrap; }
  .ep-title b { font-size: 0.98rem; font-weight: 600; overflow-wrap: anywhere; }
  .rename { display: flex; gap: 0.45rem; align-items: center; flex-wrap: wrap; animation: fade 240ms var(--ease-out); }
  .rename input { flex: 1; min-width: 160px; padding: 0.5rem 0.8rem; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.4rem; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.3rem;
    font-size: 0.72rem; font-weight: 600; color: var(--muted); background: var(--surface2);
    border-radius: 999px; padding: 0.2rem 0.6rem; text-transform: capitalize;
  }
  .c-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .chip.warn { color: var(--warn); background: color-mix(in srgb, var(--warn) 13%, transparent); text-transform: none; }
  .chip.s-ready { color: var(--success); background: color-mix(in srgb, var(--success) 13%, transparent); }
  .chip.s-processing { color: var(--warn); background: color-mix(in srgb, var(--warn) 13%, transparent); }
  .chip.s-processing .c-dot { animation: pulse-ring 1.4s var(--ease-out) infinite; }
  .chip.s-failed { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }
  .link {
    display: inline-flex; align-items: center; gap: 0.25rem;
    background: none; color: var(--muted); font-size: 0.76rem; font-weight: 600;
    padding: 0.15rem 0.5rem; border-radius: 99px; opacity: 0.8;
    transition: color var(--dur-2), background-color var(--dur-2), opacity var(--dur-2);
  }
  .ep:hover .link { opacity: 1; }
  .link:hover { color: var(--text); background: var(--surface2); }

  /* ---------- states ---------- */
  .state { display: flex; flex-direction: column; align-items: center; gap: 0.7rem; text-align: center; padding: 3rem 1.5rem; border-radius: 28px; background: var(--surface); }
  .state.small { padding: 2.6rem 1rem; }
  .state h2 { font-size: 1.25rem; }
  .state p { color: var(--muted); }
  .state-ico { width: 60px; height: 60px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }
  .state-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }
  .foot-note { display: flex; gap: 0.45rem; align-items: flex-start; font-size: 0.8rem; color: var(--muted); margin-top: 1.1rem; padding-left: 0.3rem; }
  .foot-note :global(.icon) { flex: none; margin-top: 2px; }
  .foot-note a { color: var(--text); font-weight: 600; text-decoration: underline; text-underline-offset: 2px; }

  @media (max-width: 760px) {
    .card { padding: 1.1rem; border-radius: 24px; }
    .mode-toggle { flex-direction: column; border-radius: 20px; }
    .ep { padding-right: 0.8rem; gap: 0.65rem; }
    .ep-ico { display: none; }
    .head-actions { width: 100%; }
  }
</style>
