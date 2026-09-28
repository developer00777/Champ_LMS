<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, type AdminCourseSummary } from '$lib/api/client';
  import { runtime } from '$lib/utils/transcribe';
  import { icons } from '$lib/components/course/icons';

  let courses: AdminCourseSummary[] = [];
  let loading = true;
  let error = '';
  let title = '';
  let creating = false;

  onMount(async () => {
    try { courses = await api.adminCourses(); }
    catch (e: any) { error = e.message; }
    finally { loading = false; }
  });

  async function create() {
    if (!title.trim()) return;
    creating = true; error = '';
    try {
      const c = await api.createCourse({ title: title.trim() });
      goto(`/admin/courses/${c.id}`);
    } catch (e: any) { error = e.message; creating = false; }
  }
</script>

<svelte:head><title>Courses — Champ LMS</title></svelte:head>

<div class="page">
  <header class="head">
    <div>
      <a href="/admin" class="crumb">Admin</a>
      <h1>Courses</h1>
      <p class="sub">
        Build each course on one canvas: videos, AI quizzes, tests and notes in one order.
        Learners get a series player when a course is only videos, and the full course player once it has anything else.
        New courses start closed. Nobody sees one until you add people.
      </p>
    </div>
    <form class="new" on:submit|preventDefault={create}>
      <input type="text" bind:value={title} placeholder="New course title" aria-label="New course title" maxlength="200" />
      <button class="btn primary" disabled={creating || !title.trim()}>{@html icons.plus} Create course</button>
    </form>
  </header>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <p class="muted">Loading courses…</p>
  {:else if !courses.length}
    <div class="empty">
      <h2>No courses yet</h2>
      <p>Give your first course a title above. You'll land on its canvas, ready for videos.</p>
    </div>
  {:else}
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Course</th><th>Learner view</th><th>Contents</th><th>Status</th><th>Who can watch</th><th>Test requests</th></tr>
        </thead>
        <tbody>
          {#each courses as c (c.id)}
            <tr on:click={() => goto(`/admin/courses/${c.id}`)} class="rowlink">
              <td>
                <div class="title-cell">
                  <span class="thumb" style={c.thumbnail_url ? `background-image:url(${c.thumbnail_url})` : ''}></span>
                  <div><a href="/admin/courses/{c.id}" class="t">{c.title}</a><div class="s">{c.category ?? 'No category'}</div></div>
                </div>
              </td>
              <td>
                {#if c.format === 'series'}<span class="pill series">Series</span>
                {:else if c.format === 'course'}<span class="pill course">Full course</span>
                {:else}<span class="pill">Empty</span>{/if}
              </td>
              <td>
                <div class="num">{c.counts.video} videos · {runtime(c.runtime_seconds)}</div>
                <div class="s">{c.counts.quiz} quizzes · {c.counts.test} tests · {c.counts.notes} notes</div>
              </td>
              <td>{#if c.is_published}<span class="pill ok">Published</span>{:else}<span class="pill">Draft</span>{/if}</td>
              <td>{#if c.can_watch_count}<span class="pill ok">{c.can_watch_count} people</span>{:else}<span class="pill bad">Nobody yet</span>{/if}</td>
              <td>{#if c.pending_requests}<span class="pill acc">{c.pending_requests} waiting</span>{:else}<span class="muted">None</span>{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .page { display: grid; gap: 1.5rem; }
  .head { display: flex; gap: 1.5rem; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; }
  .crumb { font-size: 0.8rem; color: var(--muted); }
  h1 { font-size: 1.9rem; font-weight: 800; margin: 0.2rem 0 0.4rem; }
  .sub { color: var(--text-secondary); max-width: 68ch; font-size: 0.92rem; line-height: 1.55; }
  .new { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .new input {
    min-width: 240px; font: inherit; color: var(--text); background: var(--surface);
    border: 1px solid var(--border-hover); border-radius: 8px; padding: 0 0.8rem; height: 38px;
  }
  .btn {
    display: inline-flex; align-items: center; gap: 0.4rem; height: 38px; padding: 0 1rem;
    border-radius: 8px; font-weight: 600; font-size: 0.88rem; border: 1px solid var(--border-hover);
    background: var(--surface2); color: var(--text); white-space: nowrap;
  }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .error { color: #ff6b6b; }
  .muted { color: var(--muted); }
  .empty { padding: 3rem 1rem; text-align: center; border: 1px dashed var(--border-hover); border-radius: 12px; color: var(--muted); }
  .empty h2 { color: var(--text); margin-bottom: 0.4rem; }
  .table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
  table { width: 100%; min-width: 820px; border-collapse: collapse; }
  th {
    text-align: left; font-size: 0.68rem; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase;
    color: var(--muted); padding: 0.75rem 1rem; border-bottom: 1px solid var(--border);
  }
  td { padding: 0.8rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.88rem; vertical-align: middle; }
  tr:last-child td { border-bottom: 0; }
  .rowlink { cursor: pointer; }
  .rowlink:hover td { background: var(--surface2); }
  .title-cell { display: flex; gap: 0.75rem; align-items: center; }
  .thumb {
    width: 64px; aspect-ratio: 16/9; border-radius: 6px; flex: none; background-size: cover; background-position: center;
    background-color: var(--surface3);
    background-image: radial-gradient(120% 100% at 15% 10%, rgba(229, 9, 20, 0.7), transparent 60%);
  }
  .t { font-weight: 600; color: var(--text); }
  .s { font-size: 0.78rem; color: var(--muted); }
  .num { font-variant-numeric: tabular-nums; }
  .pill {
    display: inline-flex; align-items: center; height: 22px; padding: 0 9px; border-radius: 99px;
    font-size: 0.72rem; font-weight: 600; background: var(--surface3); color: var(--text-secondary); white-space: nowrap;
  }
  .pill.ok { background: rgba(46, 204, 113, 0.14); color: #2ecc71; }
  .pill.bad { background: rgba(255, 91, 98, 0.13); color: #ff6b70; }
  .pill.acc { background: rgba(229, 9, 20, 0.16); color: #ff4d55; }
  .pill.series { background: rgba(110, 168, 255, 0.15); color: #6ea8ff; }
  .pill.course { background: rgba(181, 150, 255, 0.15); color: #b596ff; }
</style>
