<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, type AdminCourseSummary } from '$lib/api/client';
  import { runtime } from '$lib/utils/transcribe';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import Thumb from '$lib/components/Thumb.svelte';
  import SortHeader from '$lib/components/SortHeader.svelte';
  import { ariaSort, sortRows, NO_SORT, type SortAccessors } from '$lib/utils/table-sort';

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

  const TONES = ['sky', 'lilac', 'mint', 'butter', 'peach'];
  const tone = (id: string) => TONES[[...id].reduce((a, c) => a + c.charCodeAt(0), 0) % TONES.length];

  const FORMAT_RANK: Record<string, number> = { series: 0, course: 1 };
  const SORT_BY: SortAccessors<AdminCourseSummary> = {
    title: (c) => c.title,
    format: (c) => FORMAT_RANK[c.format] ?? 2,
    contents: (c) => c.runtime_seconds,
    status: (c) => c.is_published,
    watch: (c) => c.can_watch_count,
    requests: (c) => c.pending_requests,
  };
  let sort = NO_SORT;
  $: rows = sortRows(courses, sort, SORT_BY);
</script>

<svelte:head><title>Courses — Champ LMS</title></svelte:head>

<div class="page">
  <header class="head">
    <div>
      <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Courses' }]} />
      <h1 class="ui-rise" style="--i:1">
        Courses
        <span class="title-mark" aria-hidden="true"><Icon name="layers" size={23} /></span>
      </h1>
      <p class="sub ui-rise" style="--i:2">
        Build each course on one canvas: videos, AI quizzes, tests and notes in one order.
        Learners get a series player when a course is only videos, and the full course player once it has anything else.
        New courses start closed. Nobody sees one until you add people.
      </p>
    </div>
    <form class="new ui-rise" style="--i:3" on:submit|preventDefault={create}>
      <span class="new-field">
        <Icon name="edit" size={16} />
        <input type="text" bind:value={title} placeholder="New course title" aria-label="New course title" maxlength="200" />
      </span>
      <button class="btn-primary" disabled={creating || !title.trim()}>
        <span class="plus"><Icon name="plus" size={16} stroke={2.2} /></span>
        {creating ? 'Creating…' : 'Create course'}
      </button>
    </form>
  </header>

  {#if error}<p class="error"><Icon name="alert" size={16} /> {error}</p>{/if}

  {#if loading}
    <div class="table-wrap sk">
      {#each Array(5) as _}<div class="ui-skeleton" style="height:58px;border-radius:16px"></div>{/each}
    </div>
  {:else if !courses.length}
    <div class="empty ui-rise">
      <span class="e-ico"><Icon name="layers" size={28} /></span>
      <h2>No courses yet</h2>
      <p>Give your first course a title above. You'll land on its canvas, ready for videos.</p>
    </div>
  {:else}
    <div class="table-wrap ui-rise" style="--i:3">
      <table>
        <thead>
          <tr>
            <th aria-sort={ariaSort(sort, 'title')}><SortHeader field="title" bind:sort>Course</SortHeader></th>
            <th aria-sort={ariaSort(sort, 'format')}><SortHeader field="format" bind:sort>Learner view</SortHeader></th>
            <th aria-sort={ariaSort(sort, 'contents')}><SortHeader field="contents" bind:sort>Contents</SortHeader></th>
            <th aria-sort={ariaSort(sort, 'status')}><SortHeader field="status" bind:sort>Status</SortHeader></th>
            <th aria-sort={ariaSort(sort, 'watch')}><SortHeader field="watch" bind:sort>Who can watch</SortHeader></th>
            <th aria-sort={ariaSort(sort, 'requests')}><SortHeader field="requests" bind:sort>Test requests</SortHeader></th>
          </tr>
        </thead>
        <tbody>
          {#each rows as c (c.id)}
            <tr on:click={() => goto(`/admin/courses/${c.id}`)} class="rowlink">
              <td>
                <div class="title-cell">
                  <span class="thumb {tone(c.id)}">
                    {#if c.thumbnail_url}<Thumb src={c.thumbnail_url} />{:else}<Icon name="film" size={18} stroke={1.5} />{/if}
                  </span>
                  <div class="tc"><a href="/admin/courses/{c.id}" class="t">{c.title}</a><div class="s">{c.category ?? 'No category'}</div></div>
                </div>
              </td>
              <td>
                {#if c.format === 'series'}<span class="pill series"><Icon name="video" size={13} /> Series</span>
                {:else if c.format === 'course'}<span class="pill course"><Icon name="layers" size={13} /> Full course</span>
                {:else}<span class="pill">Empty</span>{/if}
              </td>
              <td>
                <div class="num">{c.counts.video} videos · {runtime(c.runtime_seconds)}</div>
                <div class="s">{c.counts.quiz} quizzes · {c.counts.test} tests · {c.counts.notes} notes</div>
              </td>
              <td>{#if c.is_published}<span class="pill ok"><span class="dot"></span> Published</span>{:else}<span class="pill">Draft</span>{/if}</td>
              <td>{#if c.can_watch_count}<span class="pill ok"><Icon name="users" size={13} /> {c.can_watch_count} people</span>{:else}<span class="pill bad"><Icon name="lock" size={13} /> Nobody yet</span>{/if}</td>
              <td>{#if c.pending_requests}<span class="pill acc"><Icon name="bell" size={13} /> {c.pending_requests} waiting</span>{:else}<span class="muted">None</span>{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .page { display: grid; gap: 1.25rem; }
  .head { display: flex; gap: 1.5rem; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; }
  h1 {
    font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.05;
    display: flex; align-items: center; gap: 0.6rem; margin: 0 0 0.6rem;
  }
  .title-mark {
    display: inline-grid; place-items: center; width: 46px; height: 46px; border-radius: 50%;
    background: var(--tile-mint); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .sub { color: var(--text-secondary); max-width: 68ch; font-size: 0.94rem; line-height: 1.55; }

  .new { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
  .new-field { position: relative; display: block; color: var(--muted); }
  .new-field :global(.icon) { position: absolute; left: 1rem; top: 50%; translate: 0 -50%; pointer-events: none; }
  .new-field input {
    min-width: 260px; height: 46px; padding: 0 1rem 0 2.6rem; color: var(--text);
    background: var(--surface); border: 1px solid var(--border); border-radius: 999px; box-shadow: var(--shadow-sm);
  }
  .plus { display: grid; transition: rotate var(--dur-3) var(--ease-out); }
  .btn-primary:hover:not(:disabled) .plus { rotate: 90deg; }

  .error {
    display: flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1rem; border-radius: 18px;
    background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); font-weight: 600; font-size: 0.88rem;
  }
  .muted { color: var(--muted); }
  .empty {
    display: flex; flex-direction: column; align-items: center; gap: 0.6rem; text-align: center;
    padding: 2.75rem 1rem; border-radius: 30px; background: var(--surface); color: var(--muted);
  }
  .empty h2 { color: var(--text); font-size: 1.35rem; }
  .e-ico {
    width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; margin-bottom: 0.3rem;
    background: var(--tile-mint); color: var(--tile-ink); animation: float 4s var(--ease-in-out) infinite;
  }

  .table-wrap {
    overflow-x: auto; border-radius: 28px; background: var(--surface); box-shadow: var(--shadow-sm); padding: 0.4rem;
  }
  .table-wrap.sk { display: grid; gap: 0.5rem; padding: 0.9rem; }
  table { width: 100%; min-width: 860px; border-collapse: separate; border-spacing: 0; }
  th {
    text-align: left; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--muted); padding: 0.85rem 1rem 0.7rem;
  }
  td { padding: 0.75rem 1rem; border-top: 1px solid var(--border); font-size: 0.88rem; vertical-align: middle; transition: background-color var(--dur-2) var(--ease-out); }
  .rowlink { cursor: pointer; }
  .rowlink:hover td { background: var(--surface2); border-top-color: transparent; }
  .rowlink:hover td:first-child { border-radius: 18px 0 0 18px; }
  .rowlink:hover td:last-child { border-radius: 0 18px 18px 0; }
  .rowlink:hover + .rowlink td { border-top-color: transparent; }
  .title-cell { display: flex; gap: 0.85rem; align-items: center; }
  .thumb {
    position: relative; overflow: hidden;
    width: 76px; aspect-ratio: 16/9; border-radius: 12px; flex: none;
    display: grid; place-items: center; color: var(--tile-ink);
    transition: scale var(--dur-3) var(--ease-out), rotate var(--dur-3) var(--ease-out);
  }
  .thumb :global(.icon) { opacity: 0.55; }
  .rowlink:hover .thumb { scale: 1.06; rotate: -2deg; }
  .tc { min-width: 0; }
  .t { font-weight: 600; color: var(--text); }
  .rowlink:hover .t { text-decoration: underline; text-underline-offset: 3px; }
  .s { font-size: 0.78rem; color: var(--muted); text-transform: none; }
  .num { font-variant-numeric: tabular-nums; }
  .sky { background-color: var(--tile-sky); }
  .lilac { background-color: var(--tile-lilac); }
  .mint { background-color: var(--tile-mint); }
  .butter { background-color: var(--tile-butter); }
  .peach { background-color: var(--tile-peach); }
  .pill {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 26px; padding: 0 0.7rem; border-radius: 99px;
    font-size: 0.74rem; font-weight: 600; background: var(--surface2); color: var(--text-secondary); white-space: nowrap;
  }
  .pill.ok { background: var(--tile-mint); color: var(--tile-ink); }
  .pill.bad { background: color-mix(in srgb, var(--danger) 13%, transparent); color: var(--danger); }
  .pill.acc { background: color-mix(in srgb, var(--brand) 16%, transparent); color: var(--brand); }
  .pill.acc :global(.icon) { animation: wiggle 1.8s var(--ease-out) infinite; }
  .pill.series { background: var(--tile-sky); color: var(--tile-ink); }
  .pill.course { background: var(--tile-lilac); color: var(--tile-ink); }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--success); }

  @media (max-width: 760px) {
    .new, .new-field, .new-field input { width: 100%; min-width: 0; }
    .new .btn-primary { width: 100%; }
  }
</style>
