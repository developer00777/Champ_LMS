<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api, type AdminContent, type AdminModuleRow, type AdminEpisodeRow,
    type EpisodeDeletePreview, type ModuleDeletePreview, type PurgeResult,
  } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import { countUp } from '$lib/actions/motion';
  import SortHeader from '$lib/components/SortHeader.svelte';
  import { ariaSort, sortRows, type SortAccessors, type SortState } from '$lib/utils/table-sort';

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

  // Summary tiles (presentation only).
  $: mods = content?.modules ?? [];
  $: publishedCount = mods.filter((m) => m.is_published).length;
  $: episodeCount = mods.reduce((a, m) => a + m.episodes.length, 0);
  $: remoteCount = mods.reduce((a, m) => a + m.episodes.filter((e) => e.has_remote_video).length, 0);
  const TONES = ['sky', 'lilac', 'mint', 'butter', 'peach'];

  // Each module's episode table sorts on its own.
  let epSort: Record<string, SortState> = {};
  const STATUS_RANK: Record<string, number> = { ready: 0, processing: 1, pending: 2, failed: 3 };
  const EP_SORT: SortAccessors<AdminEpisodeRow> = {
    seq: (e) => e.sequence_order,
    title: (e) => e.title,
    status: (e) => STATUS_RANK[e.status] ?? 4,
    length: (e) => e.duration_seconds,
    video: (e) => (e.has_remote_video ? e.bunny_video_guid : null),
  };
</script>

<svelte:head><title>Content Library — Admin</title></svelte:head>

<div class="page">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Content Library' }]} />
  <header class="head">
    <h1 class="ui-rise" style="--i:1">
      Content Library
      <span class="title-mark" aria-hidden="true"><Icon name="folder" size={24} /></span>
    </h1>
    <p class="sub ui-rise" style="--i:2">
      Every module and video. Open a module to rename it, reorder it, or add more
      episodes at any time. Deleting here is <b>permanent</b> — it removes the video
      from Bunny Stream and the CDN, not just from this app.
    </p>
  </header>

  {#if error}<p class="error pop-in"><Icon name="alert" size={16} /> {error}</p>{/if}

  {#if lastResult}
    <div class="result pop-in">
      <span class="r-ico"><Icon name="checkCircle" size={20} /></span>
      <div class="r-body">
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
      </div>
      <button class="x ui-round" aria-label="Dismiss" on:click={() => (lastResult = null)}><Icon name="close" size={15} /></button>
    </div>
  {/if}

  {#if loading}
    <div class="tiles">{#each Array(4) as _}<div class="ui-skeleton" style="height:112px;border-radius:24px"></div>{/each}</div>
    <div class="list">{#each Array(4) as _, i}<div class="ui-skeleton" style="height:84px;border-radius:24px;opacity:{1 - i * 0.15}"></div>{/each}</div>
  {:else if content}
    <section class="tiles" aria-label="Library summary">
      <div class="tile sky ui-rise" style="--i:3"><span class="t-ico"><Icon name="layers" size={18} /></span><b use:countUp={mods.length}></b><span>Modules</span></div>
      <div class="tile mint ui-rise" style="--i:4"><span class="t-ico"><Icon name="checkCircle" size={18} /></span><b use:countUp={publishedCount}></b><span>Published</span></div>
      <div class="tile lilac ui-rise" style="--i:5"><span class="t-ico"><Icon name="film" size={18} /></span><b use:countUp={episodeCount}></b><span>Episodes</span></div>
      <div class="tile butter ui-rise" style="--i:6"><span class="t-ico"><Icon name="video" size={18} /></span><b use:countUp={remoteCount}></b><span>Videos on Bunny</span></div>
    </section>

    {#if content.orphan_episodes.length}
      <div class="orphans ui-rise" style="--i:7">
        <div class="o-head">
          <span class="o-ico"><Icon name="alert" size={18} /></span>
          <span><b>{content.orphan_episodes.length} orphaned episode(s)</b> — their module no longer exists.</span>
        </div>
        {#each content.orphan_episodes as o}
          <div class="orphan-row">
            <span>{o.title}</span>
            <button class="btn danger sm"
                    on:click={() => askEpisode({ ...o, sequence_order: 0, status: 'unknown',
                      duration_seconds: null, has_remote_video: !!o.bunny_video_guid,
                      thumbnail_bunny_path: null, thumbnail_url: null })}>
              <Icon name="trash" size={14} /> Delete permanently
            </button>
          </div>
        {/each}
      </div>
    {/if}

    {#if content.modules.length === 0}
      <div class="empty ui-rise" style="--i:4">
        <span class="e-ico"><Icon name="film" size={28} /></span>
        <h2>No modules yet</h2>
        <p>Upload a video to create your first module.</p>
        <a href="/admin/upload" class="btn primary"><Icon name="upload" size={16} /> Upload Video</a>
      </div>
    {:else}
      <div class="list">
        {#each content.modules as m, n (m.id)}
          <div class="mod ui-rise" class:open={expanded[m.id]} style="--i:{Math.min(n + 7, 14)}">
            <div class="mod-head">
              <button class="chev ui-round" on:click={() => toggle(m.id)} aria-label="Toggle episodes" aria-expanded={!!expanded[m.id]}>
                <Icon name="chevronRight" size={16} />
              </button>
              <span class="m-art {TONES[n % TONES.length]}" aria-hidden="true"><Icon name="layers" size={20} /></span>
              <div class="mod-info">
                <b>{m.title}</b>
                <div class="chips">
                  {#if m.category}<span class="chip">{m.category}</span>{/if}
                  <span class="chip" class:live={m.is_published}>
                    {#if m.is_published}<span class="dot"></span>{/if}{m.is_published ? 'published' : 'draft'}
                  </span>
                  <span class="chip">{m.live_episode_count} episode{m.live_episode_count === 1 ? '' : 's'}</span>
                  {#if m.total_episodes !== m.live_episode_count}
                    <span class="chip warn">counter says {m.total_episodes}</span>
                  {/if}
                </div>
              </div>
              <div class="m-actions">
                <a href="/admin/modules/{m.id}" class="btn"><Icon name="edit" size={15} /> Edit / add episodes</a>
                <button class="btn danger" disabled={loadingPreview === m.id}
                        on:click={() => askModule(m)}>
                  <Icon name="trash" size={15} /> {loadingPreview === m.id ? 'Checking…' : 'Delete module'}
                </button>
              </div>
            </div>

            {#if expanded[m.id]}
              <div class="eps-wrap">
                {#if m.episodes.length === 0}
                  <p class="no-eps">No episodes in this module.</p>
                {:else}
                  <table class="eps">
                    <thead>
                      <tr>
                        <th aria-sort={ariaSort(epSort[m.id], 'seq')}><SortHeader field="seq" bind:sort={epSort[m.id]}>#</SortHeader></th>
                        <th aria-sort={ariaSort(epSort[m.id], 'title')}><SortHeader field="title" bind:sort={epSort[m.id]}>Episode</SortHeader></th>
                        <th aria-sort={ariaSort(epSort[m.id], 'status')}><SortHeader field="status" bind:sort={epSort[m.id]}>Status</SortHeader></th>
                        <th aria-sort={ariaSort(epSort[m.id], 'length')}><SortHeader field="length" bind:sort={epSort[m.id]}>Length</SortHeader></th>
                        <th aria-sort={ariaSort(epSort[m.id], 'video')}><SortHeader field="video" bind:sort={epSort[m.id]}>Bunny video</SortHeader></th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {#each sortRows(m.episodes, epSort[m.id], EP_SORT) as ep, k (ep.id)}
                        <tr style="--i:{Math.min(k, 10)}">
                          <td class="num"><span class="seq">{ep.sequence_order}</span></td>
                          <td class="ep-title">{ep.title}</td>
                          <td><span class="status s-{ep.status}"><span class="dot"></span>{ep.status}</span></td>
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
                              <Icon name="trash" size={13} /> {loadingPreview === ep.id ? '…' : 'Delete'}
                            </button>
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                {/if}
              </div>
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
      <span class="m-warn" aria-hidden="true"><Icon name="trash" size={24} /></span>
      <h2 id="del-title">Permanently delete this {target.kind}?</h2>
      <p class="warn-box">
        <Icon name="alert" size={16} />
        <span>This cannot be undone. The video will be erased from <b>Bunny Stream and the CDN</b> —
        not just hidden in this app.</span>
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
        <input bind:value={typed} placeholder={target.title} autocomplete="off" class:match={confirmed} />
      </label>

      {#if modalError}<p class="error pop-in"><Icon name="alert" size={16} /> {modalError}</p>{/if}

      <div class="modal-actions">
        <button class="btn" on:click={closeModal} disabled={deleting}>Cancel</button>
        <button class="btn danger solid" class:armed={confirmed} disabled={!confirmed || deleting} on:click={confirmDelete}>
          <Icon name="trash" size={15} /> {deleting ? 'Deleting…' : 'Delete permanently'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .head { margin-bottom: 1.25rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.6rem; }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-butter); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .sub { color: var(--muted); font-size: 0.9rem; line-height: 1.6; max-width: 72ch; }
  .error { display: flex; align-items: center; gap: 0.45rem; color: var(--danger); font-size: 0.86rem; margin-bottom: 0.75rem; }
  .pop-in { animation: modal-in 380ms var(--ease-out) backwards; }

  /* ---------- tiles ---------- */
  .tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.9rem; margin-bottom: 1.6rem; }
  .tile {
    display: flex; flex-direction: column; gap: 0.1rem; padding: 1rem 1.1rem; border-radius: 24px; color: var(--tile-ink);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .tile:hover { translate: 0 -3px; box-shadow: var(--shadow); }
  .tile b { font-size: clamp(1.5rem, 1.1rem + 1vw, 2rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.1; margin-top: 0.55rem; font-variant-numeric: tabular-nums; }
  .tile:hover b { animation: pop 420ms var(--ease-out); }
  .tile > span:last-child { font-size: 0.8rem; opacity: 0.72; font-weight: 500; }
  .t-ico { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); transition: transform var(--dur-3) var(--ease-out); }
  .tile:hover .t-ico { transform: rotate(-14deg) scale(1.1); }
  .sky { background: var(--tile-sky); } .mint { background: var(--tile-mint); } .lilac { background: var(--tile-lilac); }
  .butter { background: var(--tile-butter); } .peach { background: var(--tile-peach); }

  /* ---------- result / orphans ---------- */
  .result {
    display: flex; gap: 0.85rem; align-items: flex-start; background: var(--tile-mint); color: var(--tile-ink);
    border-radius: 22px; padding: 1rem 1.1rem; margin-bottom: 1.25rem; font-size: 0.86rem; line-height: 1.6;
  }
  .r-ico { flex: none; width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); color: var(--success); animation: pop 500ms var(--ease-out) 120ms backwards; }
  .r-body { flex: 1; min-width: 0; }
  .remote-line { font-size: 0.78rem; opacity: 0.75; margin-top: 0.25rem; }
  .st { font-weight: 600; }
  .kept { font-size: 0.78rem; opacity: 0.75; margin-top: 0.4rem; }
  .x { flex: none; width: 32px; height: 32px; background: var(--tile-inner); }

  .orphans { background: var(--tile-butter); color: var(--tile-ink); border-radius: 22px; padding: 1rem 1.1rem; margin-bottom: 1.25rem; font-size: 0.86rem; }
  .o-head { display: flex; align-items: center; gap: 0.6rem; }
  .o-ico { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); color: var(--warn); }
  .orphan-row { display: flex; justify-content: space-between; align-items: center; gap: 1rem; margin-top: 0.55rem; padding: 0.45rem 0.4rem 0.45rem 0.8rem; border-radius: 14px; background: var(--tile-inner); }

  /* ---------- module list ---------- */
  .list { display: flex; flex-direction: column; gap: 0.65rem; }
  .mod {
    background: var(--surface); border-radius: 24px; padding: 0.85rem 1rem 0.85rem 0.85rem; box-shadow: var(--shadow-sm);
    transition: box-shadow var(--dur-3) var(--ease-out), translate var(--dur-3) var(--ease-out);
  }
  .mod:not(.open):hover { box-shadow: var(--shadow); translate: 0 -2px; }
  .mod.open { box-shadow: var(--shadow-md); }
  .mod-head { display: flex; align-items: center; gap: 0.8rem; flex-wrap: wrap; }
  .chev { flex: none; width: 34px; height: 34px; transition: rotate var(--dur-3) var(--ease-out), background-color var(--dur-2); }
  .mod.open .chev { rotate: 90deg; background: var(--accent); color: var(--on-accent); }
  .m-art { flex: none; width: 46px; height: 46px; border-radius: 16px; display: grid; place-items: center; color: var(--tile-ink); transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out); }
  .mod:hover .m-art { rotate: -8deg; scale: 1.06; }
  .mod-info { flex: 1; min-width: 200px; }
  .mod-info b { font-size: 1rem; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-top: 0.35rem; }
  .chip { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.72rem; font-weight: 500; color: var(--text-secondary); background: var(--surface2); border-radius: 999px; padding: 0.18rem 0.6rem; text-transform: capitalize; }
  .chip.live { background: var(--tile-mint); color: var(--tile-ink); }
  .chip .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--success); animation: pulse-ring 2s var(--ease-out) infinite; }
  .chip.warn { background: var(--tile-butter); color: var(--tile-ink); }
  .m-actions { display: flex; gap: 0.45rem; flex-wrap: wrap; }

  .eps-wrap { margin-top: 0.85rem; padding: 0.4rem; border-radius: 18px; background: var(--surface2); overflow-x: auto; animation: open-down 420ms var(--ease-out) backwards; }
  @keyframes open-down { from { opacity: 0; translate: 0 -8px; } }
  .no-eps { font-size: 0.84rem; color: var(--muted); padding: 0.7rem 0.8rem; }
  .eps { width: 100%; border-collapse: collapse; font-size: 0.84rem; }
  .eps th { text-align: left; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 700; padding: 0.5rem 0.65rem; }
  .eps td { padding: 0.55rem 0.65rem; border-top: 1px solid var(--border); }
  .eps tbody tr { animation: rise 420ms var(--ease-out) backwards; animation-delay: calc(var(--i, 0) * 35ms); transition: background-color var(--dur-2); }
  .eps tbody tr:hover { background: var(--surface); }
  .num { font-variant-numeric: tabular-nums; color: var(--muted); }
  .seq { display: inline-grid; place-items: center; min-width: 26px; height: 26px; border-radius: 50%; background: var(--surface); font-weight: 700; font-size: 0.76rem; color: var(--text); }
  .ep-title { font-weight: 500; }
  .right { text-align: right; }
  .guid code { font-size: 0.72rem; background: var(--surface); padding: 0.15rem 0.45rem; border-radius: 6px; }
  .none { color: var(--muted); font-size: 0.75rem; }
  .status { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.72rem; font-weight: 700; padding: 0.18rem 0.6rem; border-radius: 999px; text-transform: capitalize; }
  .status .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .s-ready { color: var(--success); background: color-mix(in srgb, var(--success) 13%, transparent); }
  .s-processing { color: var(--warn); background: color-mix(in srgb, var(--warn) 15%, transparent); }
  .s-processing .dot { animation: pulse-ring 1.4s var(--ease-out) infinite; }
  .s-failed { color: var(--danger); background: color-mix(in srgb, var(--danger) 13%, transparent); }
  .s-pending, .s-unknown { color: var(--muted); background: var(--surface); }

  /* ---------- buttons ---------- */
  .btn {
    display: inline-flex; align-items: center; gap: 0.4rem;
    background: var(--surface2); border: none; color: var(--text);
    border-radius: 999px; padding: 0.55rem 1rem; font-size: 0.83rem; font-weight: 600;
    cursor: pointer; text-decoration: none; white-space: nowrap;
    transition: background-color var(--dur-2), color var(--dur-2), translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .btn:hover:not(:disabled) { background: var(--surface3); translate: 0 -1px; }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.primary { background: var(--accent); color: var(--on-accent); }
  .btn.primary:hover { background: var(--accent-hover); box-shadow: var(--shadow); }
  .btn.sm { padding: 0.34rem 0.7rem; font-size: 0.76rem; gap: 0.3rem; }
  .btn.danger { color: var(--danger); background: color-mix(in srgb, var(--danger) 9%, transparent); }
  .btn.danger:hover:not(:disabled) { background: color-mix(in srgb, var(--danger) 16%, transparent); }
  .btn.danger.solid { background: var(--danger); color: var(--on-accent); }
  .btn.danger.solid:hover:not(:disabled) { background: color-mix(in srgb, var(--danger) 85%, #000); box-shadow: var(--shadow); }
  .btn.armed { animation: pop 360ms var(--ease-out); }
  .btn :global(.icon) { transition: transform var(--dur-3) var(--ease-out); }
  .btn:hover:not(:disabled) :global(.icon) { transform: rotate(-10deg) scale(1.1); }

  .empty { display: flex; flex-direction: column; align-items: center; gap: 0.4rem; text-align: center; padding: 2.75rem 1rem; background: var(--surface); border-radius: 28px; }
  .e-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); margin-bottom: 0.5rem; animation: pop 520ms var(--ease-out); }
  .empty h2 { font-size: 1.2rem; }
  .empty p { color: var(--muted); font-size: 0.88rem; margin-bottom: 0.9rem; }

  /* ---------- modal (entrance comes from the global .overlay rule) ---------- */
  .overlay { position: fixed; inset: 0; background: var(--scrim); display: grid; place-items: center; padding: 1rem; z-index: 200; }
  .modal { background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-lg); padding: 1.6rem; max-width: 500px; width: 100%; max-height: 90vh; overflow-y: auto; }
  .m-warn { width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center; margin-bottom: 0.8rem; color: var(--danger); background: color-mix(in srgb, var(--danger) 13%, transparent); animation: wiggle 600ms var(--ease-out) 250ms backwards; }
  .modal h2 { font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.8rem; }
  .warn-box { display: flex; gap: 0.55rem; align-items: flex-start; font-size: 0.84rem; line-height: 1.6; color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); border-radius: 16px; padding: 0.75rem 0.9rem; margin-bottom: 1rem; }
  .warn-box :global(.icon) { flex: none; margin-top: 3px; }
  .what { background: var(--surface2); border-radius: 18px; padding: 0.9rem 1.05rem; margin-bottom: 1.1rem; }
  .what-title { font-weight: 700; font-size: 0.94rem; margin-bottom: 0.5rem; }
  .what ul { margin: 0 0 0 1.1rem; font-size: 0.83rem; line-height: 1.75; color: var(--muted); }
  .what li b { color: var(--text); }
  .what code { font-size: 0.74rem; background: var(--surface); padding: 0.08rem 0.35rem; border-radius: 6px; }
  .what li.ok { color: var(--success); }
  .confirm-label { display: flex; flex-direction: column; gap: 0.45rem; font-size: 0.83rem; color: var(--muted); margin-bottom: 1rem; }
  .confirm-label input {
    background: var(--surface2); border: 1px solid transparent; color: var(--text); border-radius: 14px; padding: 0.65rem 0.85rem;
    font-size: 0.9rem; outline: none; font-family: inherit; transition: border-color var(--dur-2), box-shadow var(--dur-2), background-color var(--dur-2);
  }
  .confirm-label input:focus { border-color: var(--danger); background: var(--surface); box-shadow: 0 0 0 3px color-mix(in srgb, var(--danger) 14%, transparent); }
  .confirm-label input.match { border-color: var(--success); box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 16%, transparent); }
  .modal-actions { display: flex; gap: 0.6rem; justify-content: flex-end; }

  @media (max-width: 900px) { .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 680px) {
    .m-actions { width: 100%; }
    .m-actions .btn { flex: 1; justify-content: center; }
    .eps thead { display: none; }
    .eps td { display: block; border: none; padding: 0.2rem 0.5rem; }
    .eps tr { display: block; padding: 0.6rem 0; border-top: 1px solid var(--border); }
    .right { text-align: left; margin-top: 0.4rem; }
  }
</style>
