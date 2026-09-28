<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type TestRequestRow } from '$lib/api/client';
  import { openRequest, pendingRequests, refreshRequests, activeRequest } from '$lib/stores/test-requests';

  let tab: 'pending' | 'decided' = 'pending';
  let decided: TestRequestRow[] = [];
  let loading = true;
  let error = '';

  async function load() {
    loading = true; error = '';
    try {
      if (tab === 'pending') await refreshRequests();
      else decided = await api.testRequests('decided');
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }
  onMount(load);

  // The dialog closing usually means a decision was made: refresh the list.
  let wasOpen = false;
  $: { if (wasOpen && !$activeRequest) load(); wasOpen = !!$activeRequest; }

  $: rows = tab === 'pending' ? $pendingRequests : decided;

  function ago(iso: string | null) {
    if (!iso) return '';
    const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m} min ago`;
    if (m < 1440) return `${Math.round(m / 60)} h ago`;
    return `${Math.round(m / 1440)} d ago`;
  }
  const initials = (n: string) => n.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
</script>

<svelte:head><title>Test requests — Champ LMS</title></svelte:head>

<div class="page">
  <header class="head">
    <div>
      <a href="/admin" class="crumb">Admin</a>
      <h1>Test requests</h1>
      <p class="sub">
        When someone opens a course test, their request pops up on your screen and waits here.
        You decide how many attempts they get. Once those are used, they ask again.
      </p>
    </div>
    <div class="seg" role="tablist">
      <button class:on={tab === 'pending'} on:click={() => { tab = 'pending'; load(); }}>Waiting ({$pendingRequests.length})</button>
      <button class:on={tab === 'decided'} on:click={() => { tab = 'decided'; load(); }}>Decided</button>
    </div>
  </header>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading && !rows.length}
    <p class="muted">Loading…</p>
  {:else if !rows.length}
    <div class="empty">{tab === 'pending' ? 'No one is waiting. New requests pop up on your screen as they arrive.' : 'Nothing decided yet.'}</div>
  {:else}
    <div class="list">
      {#each rows as r (r.id)}
        <div class="req">
          <span class="av">{initials(r.full_name)}</span>
          <div class="body">
            <div class="t">{r.full_name} <span class="muted">wants to take</span> {r.test_title}</div>
            <div class="s">
              {r.team ?? 'No team'}{r.course_title ? ` · ${r.course_title}` : ''} · watched {r.course_progress}% ·
              {r.previous_attempts ? `${r.previous_attempts} earlier attempts` : 'first attempt'} · {ago(r.created_at)}
            </div>
          </div>
          <div class="acts">
            {#if r.status === 'pending'}
              <button class="btn primary" on:click={() => openRequest(r)}>Review</button>
            {:else if r.status === 'approved'}
              <span class="pill ok">Approved · {r.attempts_granted} attempt{r.attempts_granted === 1 ? '' : 's'}</span>
            {:else}
              <span class="pill bad" title={r.reason ?? ''}>Denied{r.reason ? `: ${r.reason}` : ''}</span>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { display: grid; gap: 1.5rem; max-width: 1000px; }
  .head { display: flex; gap: 1.5rem; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; }
  .crumb { font-size: 0.8rem; color: var(--muted); }
  h1 { font-size: 1.9rem; font-weight: 800; margin: 0.2rem 0 0.4rem; }
  .sub { color: var(--text-secondary); max-width: 62ch; font-size: 0.92rem; line-height: 1.55; }
  .seg { display: inline-flex; padding: 3px; gap: 2px; border-radius: 10px; background: var(--surface2); }
  .seg button { height: 30px; padding: 0 0.9rem; border-radius: 7px; font-weight: 600; font-size: 0.84rem; color: var(--muted); }
  .seg button.on { background: var(--surface); color: var(--text); }
  .error { color: #ff6b6b; }
  .muted { color: var(--muted); font-weight: 400; }
  .empty { padding: 2.5rem 1rem; text-align: center; color: var(--muted); border: 1px dashed var(--border-hover); border-radius: 12px; }
  .list { display: grid; gap: 0.5rem; }
  .req {
    display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 0.9rem; align-items: center;
    padding: 0.9rem 1rem; background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
  }
  @media (max-width: 640px) { .req { grid-template-columns: auto minmax(0, 1fr); } .acts { grid-column: 1 / -1; } }
  .av {
    display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%;
    background: var(--surface3); font-weight: 700; font-size: 0.8rem;
  }
  .t { font-weight: 600; }
  .s { font-size: 0.8rem; color: var(--text-secondary); margin-top: 2px; }
  .btn { height: 34px; padding: 0 1rem; border-radius: 8px; font-weight: 600; font-size: 0.85rem; border: 1px solid var(--accent); background: var(--accent); color: #fff; }
  .pill {
    display: inline-flex; align-items: center; height: 24px; padding: 0 10px; border-radius: 99px;
    font-size: 0.75rem; font-weight: 600; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .pill.ok { background: rgba(46, 204, 113, 0.14); color: #2ecc71; }
  .pill.bad { background: rgba(255, 91, 98, 0.13); color: #ff6b70; }
</style>
