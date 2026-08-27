<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type AdminTestSummary } from '$lib/api/client';

  let tests: AdminTestSummary[] = [];
  let loading = true;
  let error = '';
  let busy = '';

  onMount(load);

  async function load() {
    loading = true;
    try {
      tests = await api.adminTestList();
      error = '';
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  async function togglePublish(t: AdminTestSummary) {
    busy = t.id;
    try {
      await api.publishTestSeries(t.id, !t.is_published);
      await load();
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  async function remove(t: AdminTestSummary) {
    // * no window.confirm — a modal dialog would block the page; the button is
    // * two-step instead (click arms, second click deletes)
    if (armedDelete !== t.id) { armedDelete = t.id; return; }
    busy = t.id;
    try {
      await api.deleteTestSeries(t.id);
      armedDelete = '';
      await load();
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }
  let armedDelete = '';
</script>

<div class="page">
  <div class="head">
    <div>
      <h1>Test Series</h1>
      <p class="sub">Upload a question-and-answer PDF, review it, publish it, then score your team.</p>
    </div>
    <a href="/admin/tests/new" class="btn primary">+ New from PDF</a>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <div class="skeleton-list">
      {#each Array(3) as _}<div class="skeleton"></div>{/each}
    </div>
  {:else if tests.length === 0}
    <div class="empty">
      <div class="empty-icon">📄</div>
      <h2>No test series yet</h2>
      <p>Upload a PDF containing questions and answers to create your first interactive test.</p>
      <a href="/admin/tests/new" class="btn primary">Upload a Q&amp;A PDF</a>
    </div>
  {:else}
    <div class="grid">
      {#each tests as t (t.id)}
        <div class="card">
          <div class="card-top">
            <div class="titles">
              <a href="/admin/tests/{t.id}" class="card-title">{t.title}</a>
              <div class="meta">
                {#if t.category}<span class="chip">{t.category}</span>{/if}
                {#if t.department}<span class="chip">{t.department}</span>{/if}
                <span class="chip">{t.total_questions} questions</span>
                <span class="chip">pass {t.pass_threshold}%</span>
                {#if t.duration_minutes}<span class="chip">{t.duration_minutes} min</span>{/if}
              </div>
            </div>
            <div class="badges">
              <span class="status" class:live={t.is_live}>
                {t.is_published ? 'Published' : 'Draft'}
              </span>
              <span class="status appr {t.approval_status}">
                {t.approval_status === 'approved' ? 'Approved'
                  : t.approval_status === 'rejected' ? 'Rejected' : 'Awaiting approval'}
              </span>
            </div>
          </div>

          {#if !t.is_ready}
            <p class="warn">
              {t.unscorable_count} question{t.unscorable_count === 1 ? '' : 's'} missing a correct
              answer — fix before publishing.
            </p>
          {/if}
          {#if t.approval_status !== 'approved'}
            <p class="warn">
              {t.approval_status === 'rejected'
                ? 'Rejected — nobody can take this test until it is fixed and approved again.'
                : 'Awaiting approval — nobody can take this test until an admin approves it.'}
              {#if t.approval_note}<br />{t.approval_note}{/if}
            </p>
          {/if}

          <div class="stats">
            <div class="stat"><b>{t.attempt_count}</b><span>attempts</span></div>
            <div class="stat"><b>{t.average_score ?? '—'}{t.average_score != null ? '%' : ''}</b><span>avg score</span></div>
            <div class="stat"><b>{t.pass_rate ?? '—'}{t.pass_rate != null ? '%' : ''}</b><span>pass rate</span></div>
          </div>

          <div class="actions">
            <a href="/admin/tests/{t.id}" class="btn">Review / Edit</a>
            <a href="/admin/tests/{t.id}/results" class="btn">Results</a>
            <button
              class="btn"
              disabled={busy === t.id
                || (!t.is_published && (!t.is_ready || t.approval_status !== 'approved'))}
              title={!t.is_published && t.approval_status !== 'approved'
                ? 'This test must be approved before it can be published'
                : ''}
              on:click={() => togglePublish(t)}
            >
              {t.is_published ? 'Unpublish' : 'Publish'}
            </button>
            <button class="btn danger" disabled={busy === t.id} on:click={() => remove(t)}>
              {armedDelete === t.id ? 'Click again to delete' : 'Delete'}
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { max-width: 1000px; margin: 0 auto; padding-bottom: 3rem; }
  .head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1.75rem; flex-wrap: wrap; }
  h1 { font-size: 1.6rem; font-weight: 800; margin-bottom: 0.3rem; }
  .sub { color: var(--muted); font-size: 0.9rem; }
  .error { color: var(--accent); font-size: 0.85rem; margin-bottom: 1rem; }

  .grid { display: flex; flex-direction: column; gap: 1rem; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; }
  .card-top { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
  .card-title { font-size: 1.05rem; font-weight: 700; color: var(--text); text-decoration: none; }
  .card-title:hover { color: var(--accent); }
  .meta { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.5rem; }
  .chip { font-size: 0.72rem; color: var(--muted); background: var(--surface2); border-radius: 999px; padding: 0.18rem 0.55rem; }
  .status { font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
            color: var(--muted); border: 1px solid var(--border); border-radius: 999px; padding: 0.2rem 0.6rem; white-space: nowrap; }
  .status.live { color: var(--success); border-color: var(--success); }
  .badges { display: flex; flex-direction: column; align-items: flex-end; gap: 0.3rem; }
  .status.appr.approved { color: var(--success); border-color: var(--success); }
  .status.appr.pending { color: #ffc107; border-color: #ffc107; }
  .status.appr.rejected { color: var(--danger, #ff5470); border-color: var(--danger, #ff5470); }
  .warn { margin-top: 0.75rem; font-size: 0.8rem; color: #ffc107; background: rgba(255,193,7,0.1);
          border: 1px solid rgba(255,193,7,0.35); border-radius: 6px; padding: 0.5rem 0.7rem; }

  .stats { display: flex; gap: 1.5rem; margin: 1rem 0 0.25rem; }
  .stat { display: flex; flex-direction: column; }
  .stat b { font-size: 1.15rem; font-weight: 800; }
  .stat span { font-size: 0.72rem; color: var(--muted); }

  .actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1rem; }
  .btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 6px; padding: 0.45rem 0.9rem; font-size: 0.83rem; font-weight: 600;
         cursor: pointer; text-decoration: none; display: inline-block; }
  .btn:hover:not(:disabled) { border-color: var(--accent); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
  .btn.danger:hover:not(:disabled) { border-color: #e05260; color: #e05260; }

  .empty { text-align: center; padding: 3.5rem 1rem; background: var(--surface);
           border: 1px solid var(--border); border-radius: 10px; }
  .empty-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
  .empty h2 { font-size: 1.15rem; margin-bottom: 0.4rem; }
  .empty p { color: var(--muted); font-size: 0.88rem; margin-bottom: 1.25rem; }

  .skeleton-list { display: flex; flex-direction: column; gap: 1rem; }
  .skeleton { height: 150px; border-radius: 10px; background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
              background-size: 200% 100%; animation: shimmer 1.4s infinite; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

  @media (max-width: 640px) {
    .card-top { flex-direction: column; }
    .stats { gap: 1rem; }
  }
</style>
