<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api, moduleHref, type Badge, type FeedRow, type Module, type ProgressEntry, type RequiredModule,
    type StreakData, type XpEvent,
  } from '$lib/api/client';
  import { gamification } from '$lib/stores/gamification';
  import Icon from '$lib/components/Icon.svelte';
  import Thumb from '$lib/components/Thumb.svelte';
  import LevelBadge from '$lib/components/LevelBadge.svelte';
  import { countUp } from '$lib/actions/motion';
  import { tilt } from '$lib/actions/auto-motion';

  /** What a history row needs about an episode; /progress/me only has its id. */
  interface EpisodeInfo {
    title: string; order: number; duration: number | null; thumb: string | null; moduleId: string;
  }
  /** A course the learner has touched, as /modules/{id} described it. */
  interface CourseInfo {
    id: string; title: string; thumb: string | null; layout?: string; category: string | null; total: number;
  }

  let progress: ProgressEntry[] = [];
  let streak: StreakData | null = null;
  // Modules an admin marked mandatory for this learner (their team, or them
  // specifically). Failing to load these must not break the page.
  let required: RequiredModule[] = [];
  let badges: Badge[] = [];
  let xp: XpEvent[] = [];
  let info: Record<string, EpisodeInfo> = {};
  let courses: Record<string, CourseInfo> = {};
  let loading = true;
  let resolving = false;
  let error = '';

  type Filter = 'all' | 'progress' | 'done';
  let filter: Filter = 'all';
  let limit = 12;

  // Episode and course names change rarely, so remember them between visits:
  // a returning learner's rows are named before any lookup finishes.
  const CACHE_KEY = 'champ_my_learning_v1';
  // Episodes no visible course contains (deleted, unpublished or access
  // removed). Remembered for a day so each visit doesn't re-read every course.
  const MISS_TTL = 24 * 3600 * 1000;
  let missing: Record<string, number> = {};
  function readCache() {
    try {
      const c = JSON.parse(localStorage.getItem(CACHE_KEY) ?? 'null');
      if (c?.info && c?.courses) { info = c.info; courses = c.courses; }
      const now = Date.now();
      for (const [id, t] of Object.entries((c?.missing ?? {}) as Record<string, number>)) {
        if (now - t < MISS_TTL) missing[id] = t;
      }
    } catch { /* no cache: everything resolves from the API */ }
  }
  function writeCache() {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ info, courses, missing })); } catch { /* storage full or blocked */ }
  }

  onMount(async () => {
    readCache();
    // The feed only helps order the name lookups; it is the slowest call, so
    // the page never waits on it.
    const feedP = api.feed().catch(() => [] as FeedRow[]);
    try {
      let raw: ProgressEntry[];
      [raw, streak, required, badges, xp] = await Promise.all([
        api.myProgress(),
        api.myStreak().catch(() => null),
        api.requiredModules().catch(() => [] as RequiredModule[]),
        api.myBadges().catch(() => [] as Badge[]),
        api.xpHistory(8).catch(() => [] as XpEvent[]),
      ]);
      // /progress/me is newest first; keep one row per episode (two player
      // syncs racing can leave duplicate records, which would also break the
      // keyed list below).
      const seen = new Set<string>();
      progress = (raw ?? []).filter((p) => p?.episode_id && !seen.has(p.episode_id) && seen.add(p.episode_id));
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
    if (progress.length) resolveEpisodes(await feedP);
  });

  /**
   * Name each watched episode. /progress/me returns only episode ids, so read
   * courses (/modules/{id}) until every id is matched. The feed's "Continue
   * Watching" row names the courses holding unfinished episodes, so those go
   * first, then required courses, then the rest — the top of the page fills
   * in after a request or two instead of after a walk of the whole catalogue.
   */
  async function resolveEpisodes(feed: FeedRow[]) {
    const want = new Set(progress.map((p) => p.episode_id).filter((id) => !info[id] && !missing[id]));
    if (!want.size) return;
    resolving = true;
    // Set when a lookup fails for a reason other than "not found", so a
    // network blip never marks real episodes as gone.
    let failed = false;

    const continuing = feed.find((r) => /continue/i.test(r.row_title))?.modules ?? [];
    const all: Module[] = await api.modules().catch(() => { failed = true; return [] as Module[]; });
    const order = [...continuing.map((m) => m.id), ...required.map((m) => m.id), ...all.map((m) => m.id)];
    const queue = [...new Set(order)];

    const worker = async () => {
      while (queue.length && want.size) {
        const id = queue.shift()!;
        try {
          const d = await api.module(id);
          const modThumb = usable(d.thumbnail_url);
          courses[d.id] = {
            id: d.id, title: d.title, thumb: modThumb, layout: d.layout, category: d.category,
            total: d.episodes.length || d.total_episodes,
          };
          // Keep every episode of the course, not just the watched ones, so the
          // next one this learner starts is already named on their next visit.
          for (const ep of d.episodes) {
            info[ep.id] = {
              title: ep.title, order: ep.sequence_order, duration: ep.duration_seconds,
              thumb: usable(ep.thumbnail_url) ?? modThumb, moduleId: d.id,
            };
            want.delete(ep.id);
          }
          info = info; courses = courses;
        } catch (e: any) {
          // A course that fails to load just leaves its rows unnamed.
          if (e?.status !== 404) failed = true;
        }
      }
    };
    await Promise.all(Array.from({ length: 6 }, worker));
    // Only trust "not found" after every course was actually read.
    if (!failed) {
      const now = Date.now();
      for (const id of want) missing[id] = now;
    }
    resolving = false;
    writeCache();
  }

  const usable = (u: string | null | undefined) => (u && u !== '/placeholder-thumb.svg' ? u : null);

  const pct = (p: ProgressEntry) =>
    p.completed ? 100 : p.total_seconds ? Math.min(100, Math.round((p.watched_seconds / p.total_seconds) * 100)) : 0;

  // Canvas courses play inside their own player; ?ref= opens the right video.
  // info and courses are passed in, not read from the closure, so Svelte
  // re-renders each link once the names resolve after the first load.
  function hrefFor(p: ProgressEntry, inf: typeof info, cs: typeof courses) {
    const c = cs[inf[p.episode_id]?.moduleId];
    if (c?.layout === 'canvas') return `/course/${c.id}?ref=${p.episode_id}`;
    // ?module= lets the player name its course in the breadcrumb.
    return c ? `/watch/${p.episode_id}?module=${c.id}` : `/watch/${p.episode_id}`;
  }

  function clock(sec: number) {
    sec = Math.max(0, Math.round(sec));
    const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
  }
  function human(sec: number) {
    const m = Math.round(sec / 60);
    if (m < 1) return 'under a minute';
    if (m < 60) return `${m} min`;
    const h = Math.floor(m / 60), r = m % 60;
    return r ? `${h}h ${r}m` : `${h}h`;
  }
  function ago(iso?: string) {
    if (!iso) return '';
    const d = (Date.now() - new Date(iso).getTime()) / 1000;
    if (d < 60) return 'just now';
    if (d < 3600) return `${Math.floor(d / 60)} min ago`;
    if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
    const days = Math.floor(d / 86400);
    if (days === 1) return 'yesterday';
    if (days < 7) return `${days} days ago`;
    return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  }

  // Group the history by when it was last watched.
  function bucket(iso?: string) {
    if (!iso) return 'Earlier';
    const t = new Date(iso); const now = new Date();
    const day = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = Math.round((day(now) - day(t)) / 86400000);
    if (diff <= 0) return 'Today';
    if (diff === 1) return 'Yesterday';
    if (diff < 7) return 'This week';
    return 'Earlier';
  }

  const TONES = ['sky', 'lilac', 'mint', 'butter', 'peach'];
  const tone = (id: string) => TONES[[...id].reduce((a, c) => a + c.charCodeAt(0), 0) % TONES.length];

  const XP_LABELS: Record<string, string> = {
    complete_episode: 'Finished an episode',
    complete_module: 'Finished a module',
    pass_quiz: 'Passed a quiz',
    perfect_quiz: 'Perfect quiz score',
    streak_7day: '7-day streak',
    first_to_complete: 'First to complete',
    module_mastery: 'Mastered a module',
    quest_complete: 'Quest complete',
  };
  const xpLabel = (r: string) => XP_LABELS[r] ?? r.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

  $: completed = progress.filter((p) => p.completed);
  $: inProgress = progress.filter((p) => !p.completed && p.watched_seconds > 0);
  $: watchedSeconds = progress.reduce((a, p) => a + (p.watched_seconds || 0), 0);
  $: watchedMinutes = Math.round(watchedSeconds / 60);
  // The most recent unfinished episode leads the page.
  $: resume = inProgress[0] ?? null;
  $: lvl = $gamification.levelInfo;

  // Courses the learner has started, most recently watched first. Progress is
  // the share of the course's episodes finished, with partly watched ones
  // counting for how far in they are.
  interface MyCourse {
    course: CourseInfo; done: number; started: number; percent: number; last?: string; next: ProgressEntry | null;
  }
  $: myCourses = (() => {
    const by = new Map<string, MyCourse>();
    for (const p of progress) {
      const course = courses[info[p.episode_id]?.moduleId];
      if (!course) continue;
      let c = by.get(course.id);
      if (!c) by.set(course.id, (c = { course, done: 0, started: 0, percent: 0, last: p.last_watched_at, next: null }));
      c.started += 1;
      if (p.completed) c.done += 1;
      else if (!c.next) c.next = p;
      c.percent += pct(p);
    }
    return [...by.values()].map((c) => ({
      ...c, percent: Math.min(100, Math.round(c.percent / Math.max(1, c.course.total))),
    }));
  })();
  $: requiredIds = new Set(required.map((m) => m.id));
  // Required courses the learner hasn't opened yet lead the rail.
  $: requiredTodo = required.filter((m) => !myCourses.some((c) => c.course.id === m.id));

  $: filtered = filter === 'progress' ? inProgress : filter === 'done' ? completed : progress;
  $: shown = filtered.slice(0, limit);
  $: groups = shown.reduce((acc, p) => {
    const b = bucket(p.last_watched_at);
    const g = acc.find((x) => x.label === b);
    g ? g.items.push(p) : acc.push({ label: b, items: [p] });
    return acc;
  }, [] as { label: string; items: ProgressEntry[] }[]);

  function setFilter(f: Filter) { filter = f; limit = 12; }
  const TABS: { key: Filter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'progress', label: 'In progress' },
    { key: 'done', label: 'Completed' },
  ];
  $: counts = { all: progress.length, progress: inProgress.length, done: completed.length } as Record<Filter, number>;
</script>

<svelte:head><title>My Learning — Champ LMS</title></svelte:head>

<header class="head">
  <div>
    <p class="eyebrow ui-rise">Your progress, all in one place</p>
    <h1 class="ui-rise" style="--i:1">
      My Learning
      <span class="title-mark" aria-hidden="true"><Icon name="book" size={24} /></span>
    </h1>
  </div>
  {#if lvl}
    <a class="level ui-rise" style="--i:2" href="/leaderboard">
      <LevelBadge level={lvl.level} xp={lvl.xp - (lvl.current_level_xp ?? 0)} xpToNextLevel={(lvl.next_level_xp ?? lvl.xp + lvl.xp_to_next_level) - (lvl.current_level_xp ?? 0)} compact size={52} />
      <span>
        <b>Level {lvl.level}{#if lvl.tier} · {lvl.tier}{/if}</b>
        <small>{lvl.xp} XP · {lvl.xp_to_next_level} to level {lvl.level + 1}</small>
      </span>
    </a>
  {/if}
</header>

{#if loading}
  <div class="stats">
    {#each Array(5) as _}<div class="ui-skeleton" style="height:118px;border-radius:24px"></div>{/each}
  </div>
  <div class="grid">
    <div class="col">
      <div class="ui-skeleton" style="height:230px;border-radius:30px"></div>
      {#each Array(4) as _}<div class="ui-skeleton" style="height:116px;border-radius:24px"></div>{/each}
    </div>
    <aside class="rail"><div class="ui-skeleton" style="height:260px;border-radius:26px"></div></aside>
  </div>
{:else if error}
  <div class="state ui-rise">
    <span class="state-ico danger"><Icon name="alert" size={28} /></span>
    <h2>Couldn't load your learning</h2>
    <p>{error}</p>
    <button class="btn-primary" on:click={() => window.location.reload()}>Try again</button>
  </div>
{:else}
  <!-- ---------- stat tiles ---------- -->
  <section class="stats" aria-label="Your numbers">
    <div class="tile butter ui-rise" style="--i:2">
      <span class="t-ico"><Icon name="star" size={18} /></span>
      <b use:countUp={streak?.points ?? 0}></b><span>Total points</span>
    </div>
    <div class="tile peach ui-rise" style="--i:3">
      <span class="t-ico flame"><Icon name="flame" size={18} /></span>
      <b use:countUp={streak?.streak_days ?? 0}></b><span>Day streak</span>
    </div>
    <div class="tile mint ui-rise" style="--i:4">
      <span class="t-ico"><Icon name="check" size={18} /></span>
      <b use:countUp={completed.length}></b><span>Episodes completed</span>
    </div>
    <div class="tile lilac ui-rise" style="--i:5">
      <span class="t-ico"><Icon name="play" size={16} /></span>
      <b use:countUp={inProgress.length}></b><span>In progress</span>
    </div>
    <div class="tile sky ui-rise" style="--i:6">
      <span class="t-ico"><Icon name="clock" size={18} /></span>
      {#if watchedMinutes >= 60}
        <b><span use:countUp={Math.floor(watchedMinutes / 60)}></span><i>h</i> <span use:countUp={watchedMinutes % 60}></span><i>m</i></b>
      {:else}
        <b><span use:countUp={watchedMinutes}></span><i>m</i></b>
      {/if}
      <span>Time watched</span>
    </div>
  </section>

  <div class="grid">
    <div class="col">
      {#if progress.length === 0}
        <div class="state ui-rise">
          <span class="state-ico"><Icon name="film" size={26} /></span>
          <h2>Nothing watched yet</h2>
          <p>Videos you start show up here, with how far you got.</p>
          <a href="/" class="btn-primary">Browse your plan <Icon name="arrowRight" size={17} /></a>
        </div>
      {:else}
        <!-- ---------- continue watching ---------- -->
        {#if resume}
          {@const i = info[resume.episode_id]}
          {@const c = i ? courses[i.moduleId] : null}
          <a class="resume ui-rise" style="--i:3" href={hrefFor(resume, info, courses)}>
            <span class="r-art {tone(resume.episode_id)}" use:tilt={{ max: 5 }}>
              {#if i?.thumb}
                <Thumb src={i.thumb} eager />
              {:else}
                <span class="fallback"><Icon name="film" size={44} stroke={1.4} /></span>
              {/if}
              <span class="r-play"><span><Icon name="play" size={22} stroke={0} /></span></span>
              <span class="r-bar"><span style="--p:{pct(resume)}%"></span></span>
            </span>
            <span class="r-copy">
              <span class="ui-pill lilac"><span class="live-dot"></span> Continue watching</span>
              {#if i}
                <h2>{i.title}</h2>
                {#if c}<span class="r-mod"><Icon name="book" size={15} /> {c.title} · Episode {i.order}</span>{/if}
              {:else if resolving}
                <span class="ui-skeleton" style="height:28px;width:80%;border-radius:10px"></span>
                <span class="ui-skeleton" style="height:16px;width:45%;border-radius:8px"></span>
              {:else}
                <h2>Your last video</h2>
              {/if}
              <span class="r-meter">
                <b>{pct(resume)}%</b> watched
                {#if resume.total_seconds}
                  · {human(Math.max(0, resume.total_seconds - resume.watched_seconds))} left
                {/if}
              </span>
              <span class="btn-primary r-btn">
                <Icon name="play" size={14} stroke={0} /> Resume from {clock(resume.watched_seconds)}
              </span>
            </span>
          </a>
        {/if}

        <!-- ---------- your courses ---------- -->
        {#if myCourses.length || resolving}
          <div class="sec-head ui-rise" style="--i:4">
            <h2><Icon name="book" size={22} /> Your courses</h2>
            {#if myCourses.length}<span class="ui-pill sky">{myCourses.length}</span>{/if}
          </div>
          <div class="courses">
            {#each myCourses as m, n (m.course.id)}
              <a class="course ui-rise" style="--i:{Math.min(n, 6)}" href={moduleHref(m.course)} class:finished={m.percent >= 100}>
                <span class="c-art {tone(m.course.id)}">
                  {#if m.course.thumb}
                    <Thumb src={m.course.thumb} />
                  {:else}
                    <span class="fallback"><Icon name="book" size={30} stroke={1.5} /></span>
                  {/if}
                  <span class="c-scrim" aria-hidden="true"></span>
                  <span class="c-cta" aria-hidden="true">
                    <span class="c-cta-ico"><Icon name={m.percent >= 100 ? 'refresh' : 'play'} size={13} stroke={m.percent >= 100 ? 2.2 : 0} /></span>
                    {m.percent >= 100 ? 'Watch again' : m.percent > 0 ? 'Resume' : 'Start watching'}
                  </span>
                  {#if requiredIds.has(m.course.id)}<span class="ui-pill butter c-flag"><Icon name="flag" size={12} /> Required</span>{/if}
                </span>
                <span class="c-body">
                  <b class="c-title">{m.course.title}</b>
                  <span class="c-sub">
                    {m.done} of {m.course.total} episode{m.course.total === 1 ? '' : 's'} done
                    {#if m.last}<span class="dot-sep"></span>{ago(m.last)}{/if}
                  </span>
                  <span class="meter">
                    <span class="bar" class:full={m.percent >= 100}><span style="--p:{m.percent}%"></span></span>
                    <span class="m-txt"><b>{m.percent}%</b></span>
                  </span>
                </span>
              </a>
            {/each}
            {#if resolving && myCourses.length < 3}
              {#each Array(3 - myCourses.length) as _}<div class="ui-skeleton" style="height:230px;border-radius:22px"></div>{/each}
            {/if}
          </div>
        {/if}

        <!-- ---------- watch history ---------- -->
        <div class="sec-head ui-rise" style="--i:4">
          <h2><Icon name="history" size={22} /> Watch history</h2>
          <div class="tabs" role="tablist" aria-label="Filter watch history">
            {#each TABS as t}
              <button
                role="tab" aria-selected={filter === t.key}
                class:on={filter === t.key}
                on:click={() => setFilter(t.key)}
              >{t.label} <span class="n">{counts[t.key]}</span></button>
            {/each}
          </div>
        </div>

        {#if filtered.length === 0}
          <div class="state small">
            <span class="state-ico"><Icon name="target" size={24} /></span>
            <h2>{filter === 'done' ? 'Nothing finished yet' : 'Nothing in progress'}</h2>
            <p>{filter === 'done' ? 'Episodes you watch to the end land here.' : 'Everything you started is finished. Nice.'}</p>
          </div>
        {:else}
          {#key filter}
            <div class="history">
              {#each groups as g}
                <h3 class="day">{g.label}</h3>
                {#each g.items as p, n (p.episode_id)}
                  {@const i = info[p.episode_id]}
                  {@const c = i ? courses[i.moduleId] : null}
                  {@const v = pct(p)}
                  <a class="row ui-rise" style="--i:{Math.min(n, 8)}" href={hrefFor(p, info, courses)} class:done={p.completed}>
                    <span class="thumb {tone(p.episode_id)}">
                      {#if i?.thumb}
                        <Thumb src={i.thumb} />
                      {:else if i || !resolving}
                        <span class="fallback"><Icon name="film" size={28} stroke={1.5} /></span>
                      {:else}
                        <span class="ui-skeleton fill"></span>
                      {/if}
                      <span class="t-play" aria-hidden="true"><Icon name="play" size={16} stroke={0} /></span>
                      {#if p.total_seconds}<span class="dur">{clock(p.total_seconds)}</span>{/if}
                      <span class="t-bar"><span style="--p:{v}%"></span></span>
                    </span>

                    <span class="info">
                      {#if i}
                        <b class="title">{i.title}</b>
                        <span class="sub">
                          {#if c}<span class="mod">{c.title}</span><span class="dot-sep"></span>{/if}Episode {i.order}
                          {#if p.last_watched_at}<span class="dot-sep"></span>{ago(p.last_watched_at)}{/if}
                        </span>
                      {:else if resolving}
                        <span class="ui-skeleton" style="height:18px;width:70%;border-radius:8px"></span>
                        <span class="ui-skeleton" style="height:13px;width:40%;border-radius:6px"></span>
                      {:else}
                        <b class="title muted">Video no longer available</b>
                        <span class="sub">{ago(p.last_watched_at)}</span>
                      {/if}
                      <span class="meter">
                        <span class="bar" class:full={p.completed}><span style="--p:{v}%"></span></span>
                        <span class="m-txt">
                          {#if p.completed}
                            Watched in full
                          {:else if p.total_seconds}
                            {clock(p.watched_seconds)} of {clock(p.total_seconds)} · <b>{v}%</b>
                          {:else}
                            {human(p.watched_seconds)} watched
                          {/if}
                        </span>
                      </span>
                    </span>

                    <span class="act">
                      {#if p.completed}
                        <span class="ui-pill mint"><Icon name="check" size={14} /> Completed</span>
                      {:else}
                        <span class="ui-pill lilac"><Icon name="play" size={13} /> {v}%</span>
                      {/if}
                      <span class="ui-round ink go" class:solid={!p.completed} aria-hidden="true">
                        {#if p.completed}<Icon name="history" size={16} />{:else}<Icon name="play" size={15} stroke={0} />{/if}
                      </span>
                    </span>
                  </a>
                {/each}
              {/each}
            </div>
          {/key}
          {#if filtered.length > limit}
            <button class="btn-ghost more" on:click={() => (limit += 12)}>
              Show more <span class="n">{filtered.length - limit}</span>
            </button>
          {/if}
        {/if}
      {/if}
    </div>

    <!-- ---------- right rail ---------- -->
    <aside class="rail">
      {#if requiredTodo.length}
        <div class="rail-head ui-rise" style="--i:3">
          <h2>Required for you</h2>
          <span class="ui-pill butter">{requiredTodo.length}</span>
        </div>
        <p class="rail-note ui-rise" style="--i:3">Assigned by your administrator, not started yet.</p>
        <div class="req-list">
          {#each requiredTodo as m, n (m.id)}
            <a class="req ui-rise" style="--i:{4 + Math.min(n, 6)}" href={`/module/${m.id}`}>
              <span class="req-art {tone(m.id)}">
                {#if usable(m.thumbnail_url)}<Thumb src={m.thumbnail_url} />{:else}<Icon name="flag" size={20} />{/if}
              </span>
              <span class="req-txt">
                <b>{m.title}</b>
                <small>{#if m.category}{m.category} · {/if}{m.total_episodes} episode{m.total_episodes === 1 ? '' : 's'}</small>
              </span>
              <span class="ui-round go"><Icon name="arrowRight" size={15} /></span>
            </a>
          {/each}
        </div>
      {/if}

      <div class="rail-head ui-rise" style="--i:5">
        <h2>Badges</h2>
        {#if badges.length}<a href="/leaderboard" class="rail-link">All <Icon name="arrowRight" size={14} /></a>{/if}
      </div>
      {#if badges.length}
        <div class="badges">
          {#each badges.slice(0, 6) as b, n (b.badge_id)}
            <div class="bdg ui-rise" style="--i:{6 + n}" title={b.description ?? b.name}>
              <span class="b-ico {TONES[n % TONES.length]}">
                {#if b.icon_url}<img src={b.icon_url} alt="" />{:else}<Icon name="award" size={22} />{/if}
              </span>
              <small>{b.name}</small>
            </div>
          {/each}
        </div>
      {:else}
        <p class="rail-empty ui-rise" style="--i:6"><Icon name="award" size={18} /> Finish a module or pass a quiz to earn your first badge.</p>
      {/if}

      <div class="rail-head ui-rise" style="--i:7">
        <h2>Recent XP</h2>
      </div>
      {#if xp.length}
        <ul class="xp">
          {#each xp as e, n}
            <li class="ui-rise" style="--i:{8 + Math.min(n, 6)}">
              <span class="x-ico"><Icon name="zap" size={15} /></span>
              <span class="x-txt"><b>{xpLabel(e.reason)}</b><small>{ago(e.created_at)}</small></span>
              <span class="x-amt">+{e.amount}</span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="rail-empty ui-rise" style="--i:8"><Icon name="zap" size={18} /> XP you earn from videos, quizzes and quests is listed here.</p>
      {/if}
    </aside>
  </div>
{/if}

<style>
  /* ---------- header ---------- */
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 1.5rem; flex-wrap: wrap; margin: 0 0 1.25rem; }
  .eyebrow { color: var(--muted); font-size: 0.95rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; display: flex; align-items: center; gap: 0.6rem; }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-lilac); color: var(--tile-ink); rotate: 8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: -8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .level {
    display: flex; align-items: center; gap: 0.8rem; padding: 0.55rem 1.1rem 0.55rem 0.6rem;
    border-radius: 999px; background: var(--surface); box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .level:hover { translate: 0 -2px; box-shadow: var(--shadow); }
  .level span { display: flex; flex-direction: column; }
  .level b { font-size: 0.98rem; text-transform: capitalize; }
  .level small { font-size: 0.78rem; color: var(--muted); }

  /* ---------- stat tiles ---------- */
  .stats { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 0.9rem; margin-bottom: 2rem; }
  .tile {
    position: relative; overflow: hidden;
    display: flex; flex-direction: column; gap: 0.15rem;
    padding: 1rem 1.1rem 1.05rem; border-radius: 24px; color: var(--tile-ink);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .tile:hover { translate: 0 -3px; box-shadow: var(--shadow); }
  .tile b { font-size: clamp(1.6rem, 1.2rem + 1vw, 2.1rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.1; font-variant-numeric: tabular-nums; margin-top: 0.6rem; }
  .tile b i { font-style: normal; font-size: 0.55em; font-weight: 600; opacity: 0.65; margin-left: 1px; }
  .tile > span:last-child { font-size: 0.8rem; opacity: 0.72; font-weight: 500; }
  .tile:hover b { animation: pop 420ms var(--ease-out); }
  .t-ico {
    width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
    background: var(--tile-inner); transition: transform var(--dur-3) var(--ease-out);
  }
  .tile:hover .t-ico { transform: rotate(-14deg) scale(1.1); }
  .t-ico.flame { animation: flicker 2.4s var(--ease-in-out) infinite; }
  @keyframes flicker { 0%, 100% { scale: 1; } 45% { scale: 1.12; } 60% { scale: 0.96; } }
  .butter { background: var(--tile-butter); }
  .peach { background: var(--tile-peach); }
  .mint { background: var(--tile-mint); }
  .lilac { background: var(--tile-lilac); }
  .sky { background: var(--tile-sky); }

  /* ---------- layout ---------- */
  .grid { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 2rem; align-items: start; }
  .col { min-width: 0; display: flex; flex-direction: column; }

  /* ---------- continue watching ---------- */
  .resume {
    display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 1.4rem;
    padding: 0.75rem; border-radius: 32px; background: var(--surface); box-shadow: var(--shadow-sm);
    color: var(--text); margin-bottom: 2rem;
    transition: box-shadow var(--dur-3) var(--ease-out), translate var(--dur-3) var(--ease-out);
  }
  .resume:hover { box-shadow: var(--shadow-md); translate: 0 -3px; }
  .r-art { position: relative; display: block; overflow: hidden; border-radius: 24px; aspect-ratio: 16 / 9; color: var(--tile-ink); }
  .resume:hover .r-art :global(.thumb-media) { scale: 1.06; }
  .fallback { position: absolute; inset: 0; display: grid; place-items: center; opacity: 0.55; }
  .r-play {
    position: absolute; inset: 0; margin: auto; width: 84px; height: 84px; border-radius: 50%;
    display: grid; place-items: center;
    background: color-mix(in srgb, var(--surface) 45%, transparent);
    box-shadow: inset 0 0 0 8px color-mix(in srgb, var(--surface) 30%, transparent);
    animation: float 4s var(--ease-in-out) infinite;
  }
  .r-play > span {
    width: 50px; height: 50px; border-radius: 50%; display: grid; place-items: center;
    background: var(--surface); color: var(--text); transition: transform var(--dur-3) var(--ease-out);
  }
  .r-play :global(svg) { fill: currentColor; translate: 2px 0; }
  .resume:hover .r-play > span { transform: scale(1.14); }
  .r-bar { position: absolute; left: 0; right: 0; bottom: 0; height: 5px; background: color-mix(in srgb, #000 30%, transparent); }
  .r-bar span, .t-bar span, .bar span {
    display: block; height: 100%; width: var(--p); background: var(--brand);
    transform-origin: left; animation: grow 1s var(--ease-out) 350ms backwards;
  }
  @keyframes grow { from { transform: scaleX(0); } }
  .r-copy { display: flex; flex-direction: column; align-items: flex-start; gap: 0.6rem; padding: 1.2rem 1rem 1rem 0.2rem; min-width: 0; }
  .r-copy h2 {
    font-size: clamp(1.35rem, 1rem + 1vw, 1.9rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.12; margin-top: 0.3rem;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .r-mod { display: inline-flex; align-items: center; gap: 0.4rem; color: var(--muted); font-size: 0.9rem; font-weight: 500; }
  .r-meter { color: var(--muted); font-size: 0.88rem; }
  .r-meter b { color: var(--text); }
  .r-btn { margin-top: auto; }
  .r-btn :global(svg) { fill: currentColor; }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--brand); animation: pulse-ring 1.6s var(--ease-out) infinite; }

  /* ---------- section head + tabs ---------- */
  .sec-head { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
  .sec-head h2 { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 1.45rem; letter-spacing: -0.025em; }
  .tabs { display: inline-flex; gap: 0.25rem; padding: 0.3rem; border-radius: 999px; background: var(--surface2); }
  .tabs button {
    height: 36px; padding: 0 0.95rem; border-radius: 999px; font-size: 0.85rem; font-weight: 600;
    color: var(--muted); background: transparent; display: inline-flex; align-items: center; gap: 0.4rem;
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2) var(--ease-out);
  }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); }
  .n {
    min-width: 22px; height: 20px; padding: 0 6px; border-radius: 99px; font-size: 0.72rem;
    display: inline-grid; place-items: center; background: var(--surface3); color: var(--text-secondary);
  }
  .tabs button.on .n { background: var(--accent); color: var(--on-accent); animation: pop 320ms var(--ease-out); }

  /* ---------- your courses ---------- */
  /* Capped column width: with 1fr a lone course stretched across the whole
     page. Same size and inset-art layout as the Home cards. */
  .courses {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 250px)); gap: 1rem;
    margin-bottom: 2rem;
  }
  .course {
    display: flex; flex-direction: column;
    padding: 0.45rem 0.45rem 0.7rem;
    border-radius: 22px; background: var(--surface); box-shadow: var(--shadow-sm); color: var(--text);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  /* Same hover as the Home cards (VideoCard): lift + ring, zoom under a
     scrim, and a "Start / Resume" pill rising into the art. */
  .course:hover, .course:focus-visible { translate: 0 -6px; box-shadow: var(--shadow-lg), 0 0 0 1px var(--border-hover); }
  .course:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
  .c-art { position: relative; display: block; overflow: hidden; aspect-ratio: 16 / 9; border-radius: 17px; color: var(--tile-ink); }
  .course:hover .c-art :global(.thumb-media), .course:focus-visible .c-art :global(.thumb-media) { scale: 1.07; }
  .c-art .fallback { transition: scale var(--dur-3) var(--ease-out), rotate var(--dur-3) var(--ease-out); }
  .course:hover .c-art .fallback, .course:focus-visible .c-art .fallback { scale: 1.12; rotate: -6deg; }
  .c-scrim {
    position: absolute; inset: 0; pointer-events: none;
    background: linear-gradient(to top, rgba(8, 8, 10, 0.62), rgba(8, 8, 10, 0.18) 55%, rgba(8, 8, 10, 0.05));
    opacity: 0; transition: opacity var(--dur-3) var(--ease-out);
  }
  .course:hover .c-scrim, .course:focus-visible .c-scrim { opacity: 1; }
  .c-cta {
    position: absolute; left: 50%; top: 50%;
    display: inline-flex; align-items: center; gap: 0.45rem;
    padding: 0.35rem 0.9rem 0.35rem 0.35rem; border-radius: var(--radius-pill);
    background: var(--on-frame); color: var(--frame);
    font-size: 0.78rem; font-weight: 700; white-space: nowrap;
    box-shadow: 0 10px 24px -8px rgba(0, 0, 0, 0.5);
    opacity: 0; transform: translate(-50%, -30%) scale(0.9);
    transition: opacity var(--dur-2) var(--ease-out), transform var(--dur-3) var(--ease-out);
  }
  .c-cta-ico { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; background: var(--brand); color: #fff; }
  .c-cta-ico :global(svg[stroke-width="0"]) { fill: currentColor; }
  .course:hover .c-cta, .course:focus-visible .c-cta { opacity: 1; transform: translate(-50%, -50%); }
  .c-flag { position: absolute; top: 8px; left: 8px; z-index: 1; }
  @media (prefers-reduced-motion: reduce) {
    .course:hover, .course:focus-visible { translate: none; }
    .c-cta, .course:hover .c-cta { transform: translate(-50%, -50%); }
  }
  .c-body { flex: 1; display: flex; flex-direction: column; gap: 0.3rem; padding: 0.65rem 0.4rem 0; min-width: 0; }
  .c-title {
    font-size: 0.94rem; font-weight: 600; line-height: 1.3; letter-spacing: -0.01em;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .c-sub { display: flex; align-items: center; gap: 0.45rem; font-size: 0.74rem; color: var(--muted); }
  .course .meter { margin-top: auto; padding-top: 0.3rem; gap: 0.55rem; }
  .course .bar { max-width: none; }

  /* ---------- history rows ---------- */
  .history { display: flex; flex-direction: column; gap: 0.7rem; }
  .day { font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin: 0.9rem 0 0.1rem 0.3rem; }
  .day:first-child { margin-top: 0.3rem; }
  .row {
    display: grid; grid-template-columns: 200px minmax(0, 1fr) auto; gap: 1.1rem; align-items: center;
    padding: 0.6rem 1rem 0.6rem 0.6rem; border-radius: 24px;
    background: var(--surface); box-shadow: var(--shadow-sm); color: var(--text);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out), background-color var(--dur-2);
  }
  .row:hover { translate: 4px 0; box-shadow: var(--shadow); }
  .thumb {
    position: relative; display: block; overflow: hidden; aspect-ratio: 16 / 9;
    border-radius: 18px; color: var(--tile-ink);
  }
  .row:hover .thumb :global(.thumb-media) { scale: 1.08; }
  .thumb .fill { position: absolute; inset: 0; border-radius: 0; }
  .t-play {
    position: absolute; inset: 0; margin: auto; width: 40px; height: 40px; border-radius: 50%;
    display: grid; place-items: center; background: var(--surface); color: var(--text);
    opacity: 0; scale: 0.6; transition: opacity var(--dur-2) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .t-play :global(svg) { fill: currentColor; translate: 1px 0; }
  .row:hover .t-play, .row:focus-visible .t-play { opacity: 1; scale: 1; }
  .dur {
    position: absolute; right: 8px; bottom: 11px; padding: 0.1rem 0.45rem; border-radius: 6px;
    background: rgba(10, 10, 12, 0.72); color: #f4f4f6; font-size: 0.7rem; font-weight: 600; font-variant-numeric: tabular-nums;
  }
  .t-bar { position: absolute; left: 0; right: 0; bottom: 0; height: 4px; background: color-mix(in srgb, #000 30%, transparent); }
  .row.done .t-bar span { background: var(--success); }

  .info { display: flex; flex-direction: column; gap: 0.3rem; min-width: 0; }
  .title { font-size: 1.02rem; font-weight: 600; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .title.muted { color: var(--muted); font-weight: 500; }
  .sub { display: flex; align-items: center; gap: 0.45rem; font-size: 0.8rem; color: var(--muted); min-width: 0; white-space: nowrap; overflow: hidden; }
  .mod { overflow: hidden; text-overflow: ellipsis; color: var(--text-secondary); font-weight: 500; }
  .dot-sep { width: 3px; height: 3px; border-radius: 50%; background: currentColor; opacity: 0.6; flex: none; }
  .meter { display: flex; align-items: center; gap: 0.7rem; margin-top: 0.35rem; }
  .bar { flex: 1; max-width: 280px; height: 6px; border-radius: 99px; overflow: hidden; background: var(--surface3); }
  .bar span { border-radius: inherit; }
  .bar.full span { background: var(--success); }
  .m-txt { font-size: 0.78rem; color: var(--muted); white-space: nowrap; font-variant-numeric: tabular-nums; }
  .m-txt b { color: var(--text); }

  .act { display: flex; align-items: center; gap: 0.6rem; }
  .go { width: 40px; height: 40px; transition: transform var(--dur-3) var(--ease-out), background-color var(--dur-2); }
  .go.solid :global(svg) { fill: currentColor; translate: 1px 0; }
  .row:hover .go { transform: scale(1.1) rotate(-8deg); }
  .row:hover .ui-pill { animation: pop 380ms var(--ease-out); }
  .more { align-self: center; margin-top: 1.2rem; }

  /* ---------- rail ---------- */
  .rail {
    position: sticky; top: 1.5rem;
    display: flex; flex-direction: column; gap: 0.8rem;
    padding: 1.1rem; border-radius: 32px; background: var(--bg-alt);
  }
  .rail-head { display: flex; align-items: center; justify-content: space-between; padding: 0.4rem 0.35rem 0; }
  .rail-head h2 { font-size: 1.35rem; letter-spacing: -0.025em; }
  .rail-note { color: var(--muted); font-size: 0.8rem; margin: -0.5rem 0.35rem 0; }
  .rail-link { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.85rem; font-weight: 600; color: var(--muted); }
  .rail-link:hover { color: var(--text); }
  .rail-empty { display: flex; gap: 0.6rem; align-items: flex-start; padding: 0.9rem 1rem; border-radius: 20px; background: var(--surface); color: var(--muted); font-size: 0.84rem; line-height: 1.45; }
  .rail-empty :global(.icon) { flex: none; margin-top: 1px; }

  .req-list { display: flex; flex-direction: column; gap: 0.5rem; }
  .req {
    display: flex; align-items: center; gap: 0.75rem; padding: 0.5rem 0.6rem 0.5rem 0.5rem;
    border-radius: 20px; background: var(--surface); color: var(--text);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .req:hover { translate: 0 -2px; box-shadow: var(--shadow); }
  .req-art { position: relative; flex: none; width: 72px; aspect-ratio: 16 / 9; border-radius: 12px; overflow: hidden; display: grid; place-items: center; color: var(--tile-ink); }
  .req-txt { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .req-txt b { font-size: 0.9rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .req-txt small { font-size: 0.74rem; color: var(--muted); text-transform: capitalize; }
  .req .go { width: 32px; height: 32px; }
  .req:hover .go { transform: translateX(3px); }

  .badges { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; }
  .bdg { display: flex; flex-direction: column; align-items: center; gap: 0.4rem; padding: 0.8rem 0.4rem; border-radius: 20px; background: var(--surface); text-align: center; }
  .b-ico { width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center; color: var(--tile-ink); overflow: hidden; transition: transform var(--dur-3) var(--ease-out); }
  .b-ico img { width: 70%; height: 70%; object-fit: contain; }
  .bdg:hover .b-ico { transform: rotate(-12deg) scale(1.12); }
  .bdg small { font-size: 0.72rem; font-weight: 600; line-height: 1.25; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

  .xp { list-style: none; display: flex; flex-direction: column; gap: 0.35rem; padding: 0.4rem; border-radius: 22px; background: var(--surface); }
  .xp li { display: flex; align-items: center; gap: 0.7rem; padding: 0.5rem 0.55rem; border-radius: 16px; transition: background-color var(--dur-2); }
  .xp li:hover { background: var(--surface2); }
  .x-ico { flex: none; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-butter); color: var(--tile-ink); }
  .xp li:hover .x-ico { animation: wiggle 500ms var(--ease-out); }
  .x-txt { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .x-txt b { font-size: 0.85rem; font-weight: 600; }
  .x-txt small { font-size: 0.72rem; color: var(--muted); }
  .x-amt { font-weight: 700; font-size: 0.88rem; color: var(--success); font-variant-numeric: tabular-nums; }

  /* ---------- states ---------- */
  .state { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; text-align: center; padding: 3rem 1.5rem; border-radius: 32px; background: var(--surface); }
  .state.small { padding: 2.75rem 1rem; }
  .state h2 { font-size: 1.35rem; }
  .state p { color: var(--muted); margin-bottom: 0.5rem; }
  .state-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }
  .state-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }

  /* ---------- responsive ---------- */
  @media (max-width: 1180px) {
    .grid { grid-template-columns: 1fr; }
    .rail { position: static; }
    .stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  }
  @media (max-width: 760px) {
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .resume { grid-template-columns: 1fr; }
    .r-copy { padding: 0.4rem 0.5rem 0.6rem; }
    .courses { grid-template-columns: repeat(auto-fill, minmax(155px, 1fr)); gap: 0.75rem; }
    .row { grid-template-columns: 128px minmax(0, 1fr); gap: 0.8rem; padding-right: 0.8rem; }
    .act { grid-column: 1 / -1; justify-content: space-between; }
    .bar { max-width: none; }
    .tabs { width: 100%; }
    .tabs button { flex: 1; justify-content: center; padding: 0 0.5rem; }
  }
</style>
