<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api, type AdminContent, type AdminModuleRow, type AdminEpisodeRow,
    type EpisodeDeletePreview, type ModuleDeletePreview, type PurgeResult,
  } from '$lib/api/client';

  let content: AdminContent | null = null;
  let loading = true;
  let error = '';
  let expanded: Record<string, boolean> = {};

  // delete modal state
  type Target =
    | { kind: 'episode'; id: string; title: string; preview: EpisodeDeletePreview }
    | { kind: 'module'; id: string; title: string; preview: ModuleDeletePreview };
  let target: Target | null = null;
  let typed = '';
  let deleting = false;
  let modalError = '';
  let lastResult: PurgeResult | null = null;
  let loadingPreview = '';

  onMount(load);

  async function load() {
    loading = true;
    try { content = await api.adminContent(); error = ''; }
    catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  function toggle(id: string) { expanded[id] = !expanded[id]; expanded = expanded; }

  async function askEpisode(ep: AdminEpisodeRow) {
    loadingPreview = ep.id; modalError = ''; lastResult = null;
    try {
      const preview = await api.previewEpisodeDelete(ep.id);
      target = { kind: 'episode', id: ep.id, title: ep.title, preview };
      typed = '';
    } catch (e: any) { error = e.message; }
    finally { loadingPreview = ''; }
  }

  async function askModule(m: AdminModuleRow) {
    loadingPreview = m.id; modalError = ''; lastResult = null;
    try {
      const preview = await api.previewModuleDelete(m.id);
      target = { kind: 'module', id: m.id, title: m.title, preview };
      typed = '';
    } catch (e: any) { error = e.message; }
    finally { loadingPreview = ''; }
  }

  function closeModal() { target = null; typed = ''; modalError = ''; }

  // * typing the exact title is the gate — an irreversible remote deletion
  // * should never be one stray click away
  $: confirmed = target !== null && typed.trim() === target.title.trim();

  async function confirmDelete() {
    if (!target || !confirmed) return;
    deleting = true; modalError = '';
    try {
      lastResult = target.kind === 'episode'
        ? await api.deleteEpisodePermanently(target.id)
        : await api.deleteModulePermanently(target.id);
      closeModal();
      await load();
    } catch (e: any) { modalError = e.message; }
    finally { deleting = false; }
  }

  function fmtDuration(s: number | null): string {
    if (!s) return '—';
    const m = Math.floor(s / 60);
    return `${m}:${String(s % 60).padStart(2, '0')}`;
  }
</script>

<svelte:head><title>Content Library — Admin</title></svelte:head>

<div class="page">
  <p class="breadcrumb"><a href="/admin">← Admin</a></p>
  <h1>Content Library</h1>
  <p class="sub">
    Every module and video. Open a module to rename it, reorder it, or add more
    episodes at any time. Deleting here is <b>permanent</b> — it removes the video
    from Bunny Stream and the CDN, not just from this app.
  </p>

  {#if error}<p class="error">{error}</p>{/if}

  {#if lastResult}
    <div class="result">
      <b>Deleted permanently.</b>
      {lastResult.deleted.episodes} episode(s),
      {lastResult.deleted.watch_progress} progress record(s),
      {lastResult.deleted.assessments} quiz(zes)
      {#if lastResult.deleted.enrollments}, {lastResult.deleted.enrollments} enrollment(s){/if}
      removed.
      {#each lastResult.remote.filter((r) => r.asset === 'stream') as r}
        <div class="remote-line">
          Bunny video {r.guid ?? '—'}: <span class="st">{r.status}</span>
          {#if r.detail}— {r.detail}{/if}
        </div>
      {/each}
      <div class="kept">XP and points already earned were kept.</div>
      <button class="link" on:click={() => (lastResult = null)}>dismiss</button>
    </div>
  {/if}

  {#if loading}
    <div class="skeleton-list">{#each Array(3) as _}<div class="skeleton"></div>{/each}</div>
  {:else if content}
    {#if content.orphan_episodes.length}
      <div class="orphans">
        <b>{content.orphan_episodes.length} orphaned episode(s)</b> — their module no longer exists.
        {#each content.orphan_episodes as o}
          <div class="orphan-row">
            <span>{o.title}</span>
            <button class="btn danger sm"
                    on:click={() => askEpisode({ ...o, sequence_order: 0, status: 'unknown',
                      duration_seconds: null, has_remote_video: !!o.bunny_video_guid,
                      thumbnail_bunny_path: null, thumbnail_url: null })}>
              Delete permanently
            </button>
          </div>
        {/each}
      </div>
    {/if}

    {#if content.modules.length === 0}
      <div class="empty">
        <div class="empty-icon">🎬</div>
        <h2>No modules yet</h2>
        <p>Upload a video to create your first module.</p>
        <a href="/admin/upload" class="btn">Upload Video</a>
      </div>
    {:else}
      <div class="list">
        {#each content.modules as m (m.id)}
          <div class="mod">
            <div class="mod-head">
              <button class="chev" on:click={() => toggle(m.id)} aria-label="Toggle episodes">
                {expanded[m.id] ? '▾' : '▸'}
              </button>
              <div class="mod-info">
                <b>{m.title}</b>
                <div class="chips">
                  {#if m.category}<span class="chip">{m.category}</span>{/if}
                  <span class="chip" class:live={m.is_published}>
                    {m.is_published ? 'published' : 'draft'}
                  </span>
                  <span class="chip">{m.live_episode_count} episode{m.live_episode_count === 1 ? '' : 's'}</span>
                  {#if m.total_episodes !== m.live_episode_count}
                    <span class="chip warn">counter says {m.total_episodes}</span>
                  {/if}
                </div>
              </div>
              <a href="/admin/modules/{m.id}" class="btn">Edit / add episodes</a>
              <button class="btn danger" disabled={loadingPreview === m.id}
                      on:click={() => askModule(m)}>
                {loadingPreview === m.id ? 'Checking…' : 'Delete module'}
              </button>
            </div>

            {#if expanded[m.id]}
              {#if m.episodes.length === 0}
                <p class="no-eps">No episodes in this module.</p>
              {:else}
                <table class="eps">
                  <thead>
                    <tr><th>#</th><th>Episode</th><th>Status</th><th>Length</th><th>Bunny video</th><th></th></tr>
                  </thead>
                  <tbody>
                    {#each m.episodes as ep (ep.id)}
                      <tr>
                        <td class="num">{ep.sequence_order}</td>
                        <td>{ep.title}</td>
                        <td><span class="status s-{ep.status}">{ep.status}</span></td>
                        <td class="num">{fmtDuration(ep.duration_seconds)}</td>
                        <td class="guid">
                          {#if ep.has_remote_video}
                            <code>{ep.bunny_video_guid?.slice(0, 14)}…</code>
                          {:else}
                            <span class="none">no video</span>
                          {/if}
                        </td>
                        <td class="right">
                          <button class="btn danger sm" disabled={loadingPreview === ep.id}
                                  on:click={() => askEpisode(ep)}>
                            {loadingPreview === ep.id ? '…' : 'Delete'}
                          </button>
                        </td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              {/if}
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<!-- Confirmation modal. Not a native confirm() — those block the page. -->
{#if target}
  <div class="overlay">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="del-title">
      <h2 id="del-title">Permanently delete this {target.kind}?</h2>
      <p class="warn-box">
        This cannot be undone. The video will be erased from <b>Bunny Stream and the CDN</b> —
        not just hidden in this app.
      </p>

      <div class="what">
        <div class="what-title">{target.title}</div>
        <ul>
          {#if target.kind === 'module'}
            <li><b>{target.preview.episodes}</b> episode(s), including
              <b>{target.preview.remote_videos}</b> video(s) on Bunny</li>
            <li><b>{target.preview.enrollments}</b> enrollment(s) removed</li>
          {:else}
            <li>
              {#if target.preview.has_remote_video}
                Bunny video <code>{target.preview.bunny_video_guid}</code> deleted
              {:else}
                No Bunny video attached (nothing to delete remotely)
              {/if}
            </li>
            <li>From module: <b>{target.preview.module_title ?? '—'}</b></li>
          {/if}
          <li><b>{target.preview.watch_progress}</b> learner progress record(s) erased</li>
          {#if target.preview.assessments}
            <li><b>{target.preview.assessments}</b> quiz(zes) and
              <b>{target.preview.assessment_attempts}</b> attempt(s) erased</li>
          {/if}
          <li class="ok">XP and points already earned are <b>kept</b> — nobody loses a level.</li>
        </ul>
      </div>

      <label class="confirm-label">
        Type <b>{target.title}</b> to confirm
        <input bind:value={typed} placeholder={target.title} autocomplete="off" />
      </label>

      {#if modalError}<p class="error">{modalError}</p>{/if}

      <div class="modal-actions">
        <button class="btn" on:click={closeModal} disabled={deleting}>Cancel</button>
        <button class="btn danger solid" disabled={!confirmed || deleting} on:click={confirmDelete}>
          {deleting ? 'Deleting…' : 'Delete permanently'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .page { max-width: 1000px; margin: 0 auto; padding-bottom: 4rem; }
  .breadcrumb { font-size: 0.83rem; margin-bottom: 1rem; }
  .breadcrumb a { color: var(--accent); text-decoration: none; }
  h1 { font-size: 1.6rem; font-weight: 800; margin-bottom: 0.35rem; }
  .sub { color: var(--muted); font-size: 0.88rem; margin-bottom: 1.5rem; line-height: 1.6; }
  .error { color: #e05260; font-size: 0.85rem; margin-bottom: 0.75rem; }

  .result { background: var(--surface); border: 1px solid var(--success);
            border-left: 3px solid var(--success); border-radius: 8px;
            padding: 0.9rem 1.1rem; margin-bottom: 1.25rem; font-size: 0.85rem; line-height: 1.6; }
  .remote-line { font-size: 0.78rem; color: var(--muted); margin-top: 0.25rem; }
  .st { color: var(--text); }
  .kept { font-size: 0.78rem; color: var(--muted); margin-top: 0.4rem; }

  .orphans { background: rgba(255,193,7,0.08); border: 1px solid rgba(255,193,7,0.4);
             border-radius: 8px; padding: 0.9rem 1.1rem; margin-bottom: 1.25rem; font-size: 0.85rem; }
  .orphan-row { display: flex; justify-content: space-between; align-items: center;
                gap: 1rem; margin-top: 0.5rem; }

  .list { display: flex; flex-direction: column; gap: 0.75rem; }
  .mod { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.15rem; }
  .mod-head { display: flex; align-items: center; gap: 0.75rem; }
  .chev { background: none; border: none; color: var(--muted); font-size: 0.9rem;
          cursor: pointer; padding: 0.2rem 0.3rem; flex-shrink: 0; }
  .mod-info { flex: 1; min-width: 0; }
  .mod-info b { font-size: 0.98rem; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.35rem; }
  .chip { font-size: 0.7rem; color: var(--muted); background: var(--surface2);
          border-radius: 999px; padding: 0.16rem 0.5rem; }
  .chip.live { color: var(--success); }
  .chip.warn { color: #ffc107; }

  .no-eps { font-size: 0.82rem; color: var(--muted); margin-top: 0.85rem; padding-left: 1.8rem; }
  .eps { width: 100%; margin-top: 0.9rem; border-collapse: collapse; font-size: 0.82rem; }
  .eps th { text-align: left; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em;
            color: var(--muted); font-weight: 700; padding: 0.4rem 0.5rem;
            border-bottom: 1px solid var(--border); }
  .eps td { padding: 0.55rem 0.5rem; border-bottom: 1px solid var(--border); }
  .eps tr:last-child td { border-bottom: none; }
  .num { font-variant-numeric: tabular-nums; color: var(--muted); }
  .right { text-align: right; }
  .guid code { font-size: 0.72rem; background: var(--surface2); padding: 0.1rem 0.35rem; border-radius: 3px; }
  .none { color: var(--muted); font-size: 0.75rem; }
  .status { font-size: 0.7rem; font-weight: 700; padding: 0.12rem 0.45rem;
            border-radius: 999px; border: 1px solid currentColor; }
  .s-ready { color: var(--success); }
  .s-processing { color: #ffc107; }
  .s-failed { color: #e05260; }
  .s-pending, .s-unknown { color: var(--muted); }

  .btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 6px; padding: 0.45rem 0.9rem; font-size: 0.82rem; font-weight: 600;
         cursor: pointer; text-decoration: none; white-space: nowrap; }
  .btn:hover:not(:disabled) { border-color: var(--accent); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.sm { padding: 0.32rem 0.7rem; font-size: 0.76rem; }
  .btn.danger { color: #e05260; border-color: rgba(224,82,96,0.45); }
  .btn.danger:hover:not(:disabled) { border-color: #e05260; background: rgba(224,82,96,0.1); }
  .btn.danger.solid { background: #c0392b; border-color: #c0392b; color: #fff; }
  .btn.danger.solid:hover:not(:disabled) { background: #a93226; }
  .link { background: none; border: none; color: var(--accent); font-size: 0.76rem;
          cursor: pointer; padding: 0; margin-top: 0.4rem; display: block; }

  .empty { text-align: center; padding: 3.5rem 1rem; background: var(--surface);
           border: 1px solid var(--border); border-radius: 10px; }
  .empty-icon { font-size: 2.4rem; margin-bottom: 0.6rem; }
  .empty h2 { font-size: 1.1rem; margin-bottom: 0.35rem; }
  .empty p { color: var(--muted); font-size: 0.86rem; margin-bottom: 1.1rem; }

  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.72);
             display: grid; place-items: center; padding: 1rem; z-index: 100; }
  .modal { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
           padding: 1.6rem; max-width: 480px; width: 100%; max-height: 90vh; overflow-y: auto; }
  .modal h2 { font-size: 1.15rem; font-weight: 800; margin-bottom: 0.8rem; }
  .warn-box { font-size: 0.84rem; line-height: 1.6; color: #e05260;
              background: rgba(224,82,96,0.1); border: 1px solid rgba(224,82,96,0.35);
              border-radius: 7px; padding: 0.7rem 0.85rem; margin-bottom: 1rem; }
  .what { background: var(--surface2); border-radius: 8px; padding: 0.85rem 1rem; margin-bottom: 1.1rem; }
  .what-title { font-weight: 700; font-size: 0.92rem; margin-bottom: 0.5rem; }
  .what ul { margin: 0 0 0 1.1rem; font-size: 0.82rem; line-height: 1.75; color: var(--muted); }
  .what li b { color: var(--text); }
  .what code { font-size: 0.74rem; background: var(--surface); padding: 0.08rem 0.3rem; border-radius: 3px; }
  .what li.ok { color: var(--success); }
  .confirm-label { display: flex; flex-direction: column; gap: 0.4rem;
                   font-size: 0.82rem; color: var(--muted); margin-bottom: 1rem; }
  .confirm-label input { background: var(--surface2); border: 1px solid var(--border);
                         color: var(--text); border-radius: 6px; padding: 0.55rem 0.75rem;
                         font-size: 0.88rem; outline: none; font-family: inherit; }
  .confirm-label input:focus { border-color: #e05260; }
  .modal-actions { display: flex; gap: 0.6rem; justify-content: flex-end; }

  .skeleton-list { display: flex; flex-direction: column; gap: 0.75rem; }
  .skeleton { height: 78px; border-radius: 10px;
              background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
              background-size: 200% 100%; animation: shimmer 1.4s infinite; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

  @media (max-width: 680px) {
    .eps thead { display: none; }
    .eps td { display: block; border: none; padding: 0.2rem 0; }
    .eps tr { display: block; padding: 0.6rem 0; border-bottom: 1px solid var(--border); }
    .right { text-align: left; margin-top: 0.4rem; }
  }
</style>
