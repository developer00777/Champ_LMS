<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { api, type ModuleDetail } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import CourseOverview from '$lib/components/watch/CourseOverview.svelte';
  import { clock, runtime } from '$lib/utils/transcribe';

  // An older (non-canvas) course. Like a canvas course, /module/{id} is the
  // course page (cards and the player breadcrumb's course link link here);
  // ?play=1 (Start / Resume buttons) goes straight into the standard player
  // where the learner left off.
  let module: ModuleDetail | null = null;
  let error = '';
  let done = new Set<string>();
  let watched = new Map<string, number>();

  $: id = $page.params.id;
  $: overview = !$page.url.searchParams.has('play');

  let loadedFor = '';
  $: if (id && id !== loadedFor) load(id);

  async function load(mid: string) {
    loadedFor = mid; module = null; error = '';
    try {
      const m = await api.module(mid);
      // Canvas courses have their own player.
      if (m.layout === 'canvas') { goto(`/course/${mid}${overview ? '' : '?play=1'}`, { replaceState: true }); return; }
      try {
        const d = new Set<string>(), w = new Map<string, number>();
        for (const p of await api.myProgress()) {
          if (p.completed) d.add(p.episode_id);
          if (!w.has(p.episode_id) && p.total_seconds) w.set(p.episode_id, Math.round((p.watched_seconds / p.total_seconds) * 100));
        }
        done = d; watched = w;
      } catch { /* marks are optional */ }
      if (loadedFor !== mid) return;
      module = m;
    } catch (e: any) {
      error = e.message;
    }
  }

  // ?play=1 opens the player (once something can play).
  $: if (module && !overview && ready.length) resume();

  $: episodes = module ? [...module.episodes].sort((a, b) => a.sequence_order - b.sequence_order) : [];
  $: ready = episodes.filter(e => e.status === 'ready');
  $: doneCount = episodes.filter(e => done.has(e.id)).length;
  $: totalSecs = episodes.reduce((a, e) => a + (e.duration_seconds ?? 0), 0);
  $: hasImage = !!module?.thumbnail_url && module.thumbnail_url !== '/placeholder-thumb.svg';

  function open(epId: string, replace = false) {
    goto(`/watch/${epId}?module=${id}`, { replaceState: replace });
  }
  function resume() {
    const r = ready.find(e => !done.has(e.id)) ?? ready[0];
    if (r) open(r.id, !overview);
  }
  function resumeLabel(): string {
    if (!ready.length) return 'Nothing to play yet';
    if (!doneCount) return 'Start course';
    if (ready.every(e => done.has(e.id))) return 'Watch again';
    const n = episodes.indexOf(ready.find(e => !done.has(e.id))!) + 1;
    return `Resume episode ${n}`;
  }
</script>

<svelte:head>
  <title>{module?.title ?? 'Course'} — Champ LMS</title>
</svelte:head>

{#if error}
  <div class="state ui-rise">
    <span class="state-ico"><Icon name="alert" size={28} /></span>
    <h2>Couldn't open this course</h2>
    <p>{error}</p>
    <a href="/" class="btn-ghost"><Icon name="arrowLeft" size={16} /> Back to home</a>
  </div>
{:else if module && (overview || !ready.length)}
  <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: module.title }]} />
  <CourseOverview
    title={module.title}
    badge="Series"
    description={module.description}
    thumb={hasImage ? module.thumbnail_url : episodes[0]?.thumbnail_url ?? null}
    meta={[`${episodes.length} episode${episodes.length === 1 ? '' : 's'}`, totalSecs ? runtime(totalSecs) : '', module.category].filter(Boolean).join(' · ')}
    done={doneCount} total={episodes.length}
    resumeLabel={resumeLabel()}
    onResume={resume}
    onOpen={key => open(key)}
    sections={[{
      title: 'Episodes',
      rows: episodes.map((e, i) => ({
        key: e.id, title: e.title, kind: 'video',
        sub: e.status === 'ready' ? `Episode ${i + 1}${done.has(e.id) ? ' · watched' : ''}` : 'Still processing',
        thumb: e.thumbnail_url, duration: e.duration_seconds ? clock(e.duration_seconds) : '',
        done: done.has(e.id), locked: e.status !== 'ready', lockedHint: 'This video is still processing',
        progress: done.has(e.id) ? 100 : watched.get(e.id) ?? 0,
      })),
    }]}
  />
{:else}
  <!-- Same shape as the watch layout while it opens the player. -->
  <div class="sk-row">
    <div class="ui-skeleton" style="aspect-ratio:16/9;border-radius:28px"></div>
    <div class="ui-skeleton" style="height:420px;border-radius:28px"></div>
  </div>
{/if}

<style>
  .sk-row { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 1.2rem; align-items: start; }
  @media (max-width: 1079px) { .sk-row { grid-template-columns: 1fr; } }
  .state {
    max-width: 640px; margin: 2rem auto 0;
    display: flex; flex-direction: column; align-items: center; gap: 0.75rem; text-align: center;
    padding: 3rem 1.5rem; border-radius: 32px; background: var(--surface); box-shadow: var(--shadow-sm);
  }
  .state h2 { font-size: 1.35rem; }
  .state p { color: var(--muted); }
  .state-ico {
    width: 68px; height: 68px; border-radius: 50%; display: grid; place-items: center;
    background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger);
    animation: pop 520ms var(--ease-out);
  }
</style>
