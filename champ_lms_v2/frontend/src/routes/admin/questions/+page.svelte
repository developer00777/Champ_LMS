<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type AdminQuestion } from '$lib/api/client';
  import { clock } from '$lib/utils/transcribe';

  let tab: 'open' | 'answered' | 'all' = 'open';
  let courseId = '';
  let rows: AdminQuestion[] = [];
  let courses: { id: string; title: string }[] = [];
  let openCount = 0;
  let loading = true;
  let error = '';
  let drafts: Record<string, string> = {};
  let editing: string | null = null;
  let busy = '';

  async function load() {
    loading = true; error = '';
    try {
      const r = await api.adminQuestions(tab, courseId || undefined);
      rows = r.questions; courses = r.courses; openCount = r.open;
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }
  onMount(load);

  async function answer(q: AdminQuestion) {
    const text = (drafts[q.id] ?? '').trim();
    if (!text) return;
    busy = q.id; error = '';
    try {
      const saved = await api.answerQuestion(q.id, text);
      if (!q.answer) openCount = Math.max(0, openCount - 1);
      // Answered questions leave the "Waiting" list; elsewhere they update in place.
      rows = tab === 'open' ? rows.filter(r => r.id !== q.id) : rows.map(r => (r.id === q.id ? { ...r, ...saved } : r));
      editing = null; delete drafts[q.id]; drafts = drafts;
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  async function reopen(q: AdminQuestion) {
    busy = q.id; error = '';
    try {
      const saved = await api.clearAnswer(q.id);
      openCount += 1;
      rows = tab === 'answered' ? rows.filter(r => r.id !== q.id) : rows.map(r => (r.id === q.id ? { ...r, ...saved } : r));
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  async function remove(q: AdminQuestion) {
    if (!confirm('Delete this question for everyone? Its answer goes too.')) return;
    busy = q.id; error = '';
    try {
      await api.deleteQuestion(q.id);
      if (!q.answer) openCount = Math.max(0, openCount - 1);
      rows = rows.filter(r => r.id !== q.id);
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

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

<svelte:head><title>Questions — Champ LMS</title></svelte:head>

<div class="page">
  <header class="head">
    <div>
      <a href="/admin" class="crumb">Admin</a>
      <h1>Questions</h1>
      <p class="sub">
        What learners ask from the Q&amp;A button on course videos. Your answer shows under the question
        for everyone on the course, and the person who asked is notified.
      </p>
    </div>
    <div class="filters">
      <select bind:value={courseId} on:change={load} aria-label="Course">
        <option value="">All courses</option>
        {#each courses as c (c.id)}<option value={c.id}>{c.title}</option>{/each}
      </select>
      <div class="seg" role="tablist">
        <button class:on={tab === 'open'} on:click={() => { tab = 'open'; load(); }}>Waiting ({openCount})</button>
        <button class:on={tab === 'answered'} on:click={() => { tab = 'answered'; load(); }}>Answered</button>
        <button class:on={tab === 'all'} on:click={() => { tab = 'all'; load(); }}>All</button>
      </div>
    </div>
  </header>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading && !rows.length}
    <p class="muted">Loading…</p>
  {:else if !rows.length}
    <div class="empty">{tab === 'open' ? 'No questions waiting. New ones appear here as learners ask them.' : 'Nothing here yet.'}</div>
  {:else}
    <div class="list">
      {#each rows as q (q.id)}
        <article class="q">
          <span class="av">{initials(q.full_name)}</span>
          <div class="body">
            <div class="t">
              <b>{q.full_name}</b>
              <span class="muted">{q.team ?? 'No team'} · {ago(q.created_at)}</span>
              {#if !q.answer}<span class="pill wait">Waiting</span>{/if}
            </div>
            <a class="where" href="/course/{q.course_id}?ref={q.episode_id}" target="_blank" rel="noopener">
              {q.course_title} › {q.episode_title}{#if q.at_seconds !== null} <span class="mono">at {clock(q.at_seconds)}</span>{/if}
            </a>
            <p class="text">{q.body}</p>

            {#if q.answer && editing !== q.id}
              <div class="ans">
                <div class="t"><span class="pill ok">Answered</span><span class="muted">by {q.answered_by_name} · {ago(q.answered_at)}</span></div>
                <p class="text">{q.answer}</p>
                <div class="acts">
                  <button class="btn sm ghost" on:click={() => { editing = q.id; drafts[q.id] = q.answer ?? ''; }}>Edit answer</button>
                  <button class="btn sm ghost" on:click={() => reopen(q)} disabled={busy === q.id}>Mark unanswered</button>
                  <button class="btn sm ghost danger" on:click={() => remove(q)} disabled={busy === q.id}>Delete</button>
                </div>
              </div>
            {:else}
              <textarea rows="3" bind:value={drafts[q.id]} placeholder="Write an answer everyone on the course will see"
                on:keydown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) answer(q); }}></textarea>
              <div class="acts">
                <button class="btn sm ghost danger" on:click={() => remove(q)} disabled={busy === q.id}>Delete question</button>
                <span class="grow"></span>
                {#if editing === q.id}<button class="btn sm ghost" on:click={() => (editing = null)}>Cancel</button>{/if}
                <button class="btn sm primary" on:click={() => answer(q)} disabled={!(drafts[q.id] ?? '').trim() || busy === q.id}>
                  {busy === q.id ? 'Saving…' : editing === q.id ? 'Save answer' : 'Post answer'}
                </button>
              </div>
            {/if}
          </div>
        </article>
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
  .filters { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  select { height: 36px; max-width: 240px; padding: 0 0.6rem; border-radius: 9px; font: inherit; font-size: 0.84rem; color: var(--text); background: var(--surface2); border: 1px solid var(--border-hover); }
  .seg { display: inline-flex; padding: 3px; gap: 2px; border-radius: 10px; background: var(--surface2); }
  .seg button { height: 30px; padding: 0 0.9rem; border-radius: 7px; font-weight: 600; font-size: 0.84rem; color: var(--muted); }
  .seg button.on { background: var(--surface); color: var(--text); }
  .error { color: #ff6b6b; }
  .muted { color: var(--muted); font-weight: 400; }
  .mono { font-family: ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; }
  .empty { padding: 2.5rem 1rem; text-align: center; color: var(--muted); border: 1px dashed var(--border-hover); border-radius: 12px; }
  .list { display: grid; gap: 0.6rem; }
  .q { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.9rem; padding: 1rem; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; }
  .av { display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; background: var(--surface3); font-weight: 700; font-size: 0.8rem; }
  .body { display: grid; gap: 0.45rem; min-width: 0; }
  .t { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; font-size: 0.86rem; }
  .where { font-size: 0.8rem; color: var(--text-secondary); width: fit-content; }
  .where:hover { color: var(--text); text-decoration: underline; }
  .text { font-size: 0.93rem; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
  .ans { padding: 0.7rem 0.85rem; border-left: 3px solid #2ecc71; border-radius: 0 8px 8px 0; background: var(--surface2); display: grid; gap: 0.35rem; }
  textarea {
    width: 100%; resize: vertical; font: inherit; font-size: 0.9rem; color: var(--text); line-height: 1.45;
    background: var(--bg); border: 1px solid var(--border-hover); border-radius: 8px; padding: 0.55rem 0.7rem;
  }
  textarea:focus { outline: none; border-color: var(--accent); }
  .acts { display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; }
  .grow { flex: 1; }
  .pill { display: inline-flex; align-items: center; height: 22px; padding: 0 9px; border-radius: 99px; font-size: 0.72rem; font-weight: 600; }
  .pill.ok { background: rgba(46, 204, 113, 0.14); color: #2ecc71; }
  .pill.wait { background: rgba(240, 165, 64, 0.13); color: #f0a540; }
  .btn { display: inline-flex; align-items: center; height: 34px; padding: 0 1rem; border-radius: 8px; font-weight: 600; font-size: 0.85rem; border: 1px solid var(--border-hover); background: var(--surface2); color: var(--text); }
  .btn.sm { height: 30px; padding: 0 0.8rem; font-size: 0.8rem; }
  .btn.primary { border-color: var(--accent); background: var(--accent); color: #fff; }
  .btn.ghost { background: transparent; }
  .btn.danger { color: #ff6b70; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
