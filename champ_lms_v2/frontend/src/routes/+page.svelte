<script lang="ts">
  import { onMount } from 'svelte';
  import { api, moduleHref, type FeedRow, type Module, type ProgressEntry } from '$lib/api/client';
  import { gamification } from '$lib/stores/gamification';
  import { auth, isAdmin } from '$lib/stores/auth';
  import Avatar from '$lib/components/Avatar.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import LevelBadge from '$lib/components/LevelBadge.svelte';
  import ContentRow from '$lib/components/ContentRow.svelte';
  import Thumb from '$lib/components/Thumb.svelte';
  import UpskillingTrack from '$lib/components/UpskillingTrack.svelte';
  import QuestList from '$lib/components/QuestList.svelte';
  import { countUp } from '$lib/actions/motion';
  import { tilt } from '$lib/actions/auto-motion';

  let rows: FeedRow[] = [];
  // Episode id -> percent watched, from /progress/me.
  let episodePct: Record<string, number> = {};
  let loading = true;
  let error = '';
  let query = '';

  onMount(async () => {
    try {
      const [feedData, progressData] = await Promise.all([
        api.feed(),
        api.myProgress().catch(() => [] as ProgressEntry[]),
      ]);
      rows = feedData;

      for (const p of progressData) {
        if (p.completed) episodePct[p.episode_id] = 100;
        else if (p.total_seconds > 0) {
          episodePct[p.episode_id] = Math.min(100, Math.round(p.watched_seconds / p.total_seconds * 100));
        }
      }
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  });

  /**
   * Percent done per course, which is what the course cards show. The track
   * reports enrollment completion per module directly; for other courses,
   * fall back to the episode-to-course names My Learning keeps in this
   * browser (localStorage), averaging episode progress over the course.
   */
  function moduleProgress(epPct: Record<string, number>, t: typeof track): Record<string, number> {
    const out: Record<string, number> = {};
    try {
      const c = JSON.parse(localStorage.getItem('champ_my_learning_v1') ?? 'null');
      const info = (c?.info ?? {}) as Record<string, { moduleId: string }>;
      const courses = (c?.courses ?? {}) as Record<string, { total: number }>;
      const sum: Record<string, number> = {};
      for (const [ep, v] of Object.entries(epPct)) {
        const mid = info[ep]?.moduleId;
        if (mid) sum[mid] = (sum[mid] ?? 0) + v;
      }
      for (const [mid, s] of Object.entries(sum)) {
        out[mid] = Math.min(100, Math.round(s / Math.max(1, courses[mid]?.total ?? 1)));
      }
    } catch { /* no cached names yet: track progress below still applies */ }
    for (const m of t?.modules ?? []) out[m.module_id] = Math.max(0, Math.min(100, Math.round(m.progress || 0)));
    return out;
  }
  $: progressMap = moduleProgress(episodePct, track);

  $: modulesById = Object.fromEntries(rows.flatMap((r) => r.modules).map((m) => [m.id, m])) as Record<string, Module>;
  // The feed's "Continue Watching" row (built from unfinished episodes) leads
  // the page; with nothing in progress, the first course in the feed does.
  $: continueRow = rows.find((r) => /continue/i.test(r.row_title));
  $: spotlight = continueRow?.modules?.[0] ?? rows[0]?.modules?.[0] ?? null;
  $: resuming = !!continueRow?.modules?.length;
  $: spotPct = spotlight ? progressMap[spotlight.id] ?? 0 : 0;
  $: spotImg = spotlight?.thumbnail_url && spotlight.thumbnail_url !== '/placeholder-thumb.svg' ? spotlight.thumbnail_url : null;
  $: inProgressCount = continueRow?.modules?.length ?? 0;

  // Search filters the plan and every course row on the page, client-side.
  $: q = query.trim().toLowerCase();
  const matches = (m: Module, q: string) =>
    !q || m.title.toLowerCase().includes(q) || (m.category ?? '').toLowerCase().includes(q);
  $: shownRows = rows
    .map((r) => ({ ...r, modules: r.modules.filter((m) => matches(m, q)) }))
    .filter((r) => r.modules.length);

  $: firstName = ($auth.user?.full_name ?? '').trim().split(/\s+/)[0] || 'there';
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });

  $: lvl = $gamification.levelInfo;
  $: track = $gamification.upselling;
  $: quests = $gamification.quests;
  $: questsDone = quests.filter((x) => x.completed).length;
  // Progress through the current level's XP band (current_level_xp .. next_level_xp).
  $: band = lvl ? Math.max(1, (lvl.next_level_xp ?? lvl.xp + lvl.xp_to_next_level) - (lvl.current_level_xp ?? 0)) : 1;
  $: into = lvl ? Math.max(0, lvl.xp - (lvl.current_level_xp ?? 0)) : 0;
  $: levelPct = Math.min(100, Math.round((into / band) * 100));

  const TONES = ['sky', 'lilac', 'mint', 'butter', 'peach'];
  const tone = (s: string) => TONES[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % TONES.length];

  // Other places to go when there are no courses to show yet.
  const EXPLORE = [
    { href: '/daily', label: "Today's challenges", text: 'Three short challenges, refreshed every day.', icon: 'flame', tone: 'peach' },
    { href: '/tests', label: 'Tests', text: 'Take the tests assigned to you and see your scores.', icon: 'clipboard', tone: 'butter' },
    { href: '/paths', label: 'Learning paths', text: 'Follow a guided path through related courses.', icon: 'route', tone: 'sky' },
    { href: '/leaderboard', label: 'Leaderboard', text: 'See how you rank against your colleagues.', icon: 'trophy', tone: 'lilac' },
  ];

  const SHORTCUTS = [
    { href: '/admin/upload', label: 'Upload video', icon: 'upload', tone: 'sky' },
    { href: '/admin/courses', label: 'Courses', icon: 'layers', tone: 'lilac' },
    { href: '/admin/employees', label: 'Employees', icon: 'users', tone: 'mint' },
  ];
</script>

<svelte:head><title>Champ LMS — Home</title></svelte:head>

<header class="head">
  <div class="title-block">
    <p class="hello ui-rise">{today}</p>
    <h1 class="ui-rise" style="--i:1">
      {greeting}, {firstName}
      <span class="title-mark" aria-hidden="true"><Icon name="route" size={24} /></span>
    </h1>
    {#if !loading && !error}
      <p class="summary ui-rise" style="--i:2">
        {#if inProgressCount}
          You have <b>{inProgressCount}</b> course{inProgressCount === 1 ? '' : 's'} in progress
        {:else}
          Pick a course to start learning
        {/if}
        {#if quests.length} · <b>{quests.length - questsDone}</b> of {quests.length} quests left{/if}
      </p>
    {/if}
  </div>
  <label class="search ui-rise" style="--i:2">
    <Icon name="search" size={19} />
    <span class="sr">Search courses</span>
    <input type="search" placeholder="Search courses" bind:value={query} />
    {#if query}
      <button class="clear" on:click={() => (query = '')} aria-label="Clear search"><Icon name="close" size={14} /></button>
    {/if}
  </label>
</header>

{#if loading}
  <div class="band">
    <div class="ui-skeleton sk-band"></div>
    <div class="ui-skeleton sk-band"></div>
  </div>
  <div class="home-grid">
    <div class="home-main">
      <div class="ui-skeleton" style="height:34px;width:40%;border-radius:12px;margin-bottom:1rem"></div>
      <div class="sk-grid">{#each Array(4) as _}<div class="ui-skeleton" style="height:236px;border-radius:26px"></div>{/each}</div>
    </div>
    <aside class="rail">
      <div class="ui-skeleton" style="height:64px;border-radius:22px"></div>
      {#each Array(3) as _}<div class="ui-skeleton" style="height:150px;border-radius:26px"></div>{/each}
    </aside>
  </div>
{:else if error}
  <div class="state ui-rise">
    <span class="state-ico danger"><Icon name="alert" size={28} /></span>
    <h2>Something went wrong</h2>
    <p>{error}</p>
    <button class="btn-primary" on:click={() => window.location.reload()}>Try again</button>
  </div>
{:else}
  <!-- ---------- top band: spotlight + progress, one shared height ---------- -->
  {#if !q}
    <section class="band" aria-label="Pick up where you left off">
      {#if spotlight}
        <article class="spot ui-rise" style="--i:3">
          <a class="art {tone(spotlight.title)}" href={moduleHref(spotlight)} tabindex="-1" aria-hidden="true" use:tilt={{ max: 5 }}>
            {#if spotImg}
              <Thumb src={spotImg} eager />
            {:else}
              <span class="art-fallback"><Icon name="film" size={52} stroke={1.4} /></span>
            {/if}
            <span class="art-play"><span><Icon name="play" size={22} stroke={0} /></span></span>
            {#if spotPct > 0}<span class="art-bar"><span style="--p:{spotPct}%"></span></span>{/if}
          </a>
          <div class="copy">
            <span class="ui-pill {resuming ? 'lilac' : 'sky'}">
              <span class="live-dot"></span> {resuming ? 'Continue watching' : 'Featured for you'}
            </span>
            <h2>{spotlight.title}</h2>
            <p class="desc">{spotlight.description || 'Start learning with this course.'}</p>
            <div class="facts">
              {#if spotlight.category}<span><Icon name="hash" size={14} /> {spotlight.category}</span>{/if}
              <span><Icon name="film" size={14} /> {spotlight.total_episodes} episode{spotlight.total_episodes === 1 ? '' : 's'}</span>
              {#if spotPct > 0}<span><Icon name="check" size={14} /> {spotPct}% done</span>{/if}
            </div>
            <div class="actions">
              <a href={moduleHref(spotlight)} class="btn-primary play-btn">
                <span class="play-ico"><Icon name="play" size={13} stroke={0} /></span>
                {resuming ? 'Resume' : 'Start learning'}
              </a>
              <a href="/my-learning" class="btn-ghost">My learning</a>
            </div>
          </div>
        </article>
      {:else}
        <article class="spot empty ui-rise" style="--i:3">
          <div class="copy">
            <span class="ui-pill"><span class="live-dot"></span> Getting started</span>
            <h2>Welcome to Champ LMS</h2>
            <p class="desc">Your courses appear here as soon as they are published.</p>
            {#if $isAdmin}
              <div class="actions">
                <a href="/admin/upload" class="btn-primary">Upload the first video <Icon name="arrowRight" size={17} /></a>
              </div>
            {/if}
          </div>
        </article>
      {/if}

      {#if $isAdmin}
        <aside class="side ui-rise" style="--i:4">
          <div class="side-head">
            <h2>Admin shortcuts</h2>
            <a href="/admin" class="rail-link">Dashboard <Icon name="arrowRight" size={14} /></a>
          </div>
          <div class="tiles">
            {#each SHORTCUTS as s}
              <a class="tile {s.tone}" href={s.href}>
                <span class="t-ico"><Icon name={s.icon} size={19} /></span>
                <b>{s.label}</b>
                <span class="t-go"><Icon name="arrowRight" size={15} /></span>
              </a>
            {/each}
          </div>
        </aside>
      {:else}
        <aside class="side ui-rise" style="--i:4">
          <div class="side-head">
            <h2>Your progress</h2>
            <a href="/leaderboard" class="rail-link">Leaderboard <Icon name="arrowRight" size={14} /></a>
          </div>
          {#if lvl}
            <div class="level">
              <LevelBadge level={lvl.level} xp={into} xpToNextLevel={band} compact size={58} />
              <div class="level-txt">
                <b>Level {lvl.level}{#if lvl.tier} · {lvl.tier}{/if}</b>
                <span class="xp-bar" aria-label="{levelPct}% of this level"><span style="--p:{levelPct}%"></span></span>
                <small>{lvl.xp_to_next_level} XP to level {lvl.level + 1}</small>
              </div>
            </div>
          {/if}
          <div class="tiles">
            <div class="tile butter stat"><span class="t-ico"><Icon name="star" size={17} /></span><b use:countUp={$auth.user?.points ?? 0}></b><span>Points</span></div>
            <div class="tile peach stat"><span class="t-ico flame"><Icon name="flame" size={17} /></span><b use:countUp={$auth.user?.streak_days ?? 0}></b><span>Day streak</span></div>
            <div class="tile mint stat"><span class="t-ico"><Icon name="check" size={17} /></span><b use:countUp={questsDone}></b><span>Quests done</span></div>
          </div>
        </aside>
      {/if}
    </section>
  {/if}

  <div class="home-grid">
    <div class="home-main">
      {#if track && track.modules.length}
        <div class="section-head ui-rise" style="--i:5">
          <h2><Icon name="route" size={22} /> {track.track} plan</h2>
          {#if track.department_size !== 0}
            <span class="rank"><Icon name="award" size={15} /> #{track.rank_in_department} in your department</span>
          {/if}
          <span class="mastery">{Math.round(track.mastery_percentage || 0)}% mastered</span>
        </div>
        <UpskillingTrack {track} {modulesById} {query} />
        <div class="spacer"></div>
      {/if}

      {#each shownRows as row}
        <ContentRow title={row.row_title} modules={row.modules} {progressMap} />
      {/each}

      {#if !q && shownRows.length === 0 && !(track && track.modules.length)}
        <div class="section-head ui-rise" style="--i:5"><h2 class="plain"><Icon name="sparkles" size={22} /> While you wait</h2></div>
        <div class="explore">
          {#each EXPLORE as e, n}
            <a class="ex ui-rise {e.tone}" href={e.href} style="--i:{6 + n}">
              <span class="t-ico"><Icon name={e.icon} size={19} /></span>
              <b>{e.label}</b>
              <small>{e.text}</small>
              <span class="t-go"><Icon name="arrowRight" size={15} /></span>
            </a>
          {/each}
        </div>
      {/if}

      {#if q && shownRows.length === 0}
        <div class="state small">
          <span class="state-ico"><Icon name="target" size={24} /></span>
          <h2>No courses match “{query}”</h2>
          <p>Try a shorter word, or a category name.</p>
          <button class="btn-ghost" on:click={() => (query = '')}>Clear search</button>
        </div>
      {/if}
    </div>

    <aside class="rail">
      <!-- Who is signed in, up front: the picture, name and employee code the
           admin assigned, so people can confirm at a glance whose account
           they're in on a shared machine. -->
      <a class="whoami ui-rise" href="/settings" style="--i:5">
        <Avatar src={$auth.user?.avatar_url} name={$auth.user?.full_name} size={46} />
        <span class="whoami-text">
          <b>{$auth.user?.full_name ?? 'Welcome back'}</b>
          <span class="whoami-meta">
            {#if $auth.user?.employee_code}<span class="code">{$auth.user.employee_code}</span>{/if}
            {#if $auth.user?.department}<span>{$auth.user.department}</span>{/if}
          </span>
        </span>
        <span class="ui-round go"><Icon name="arrowRight" size={16} /></span>
      </a>

      <div class="rail-head ui-rise" style="--i:6">
        <h2>My Quests</h2>
        <a href="/daily" class="rail-link">Today <Icon name="arrowRight" size={14} /></a>
      </div>
      <QuestList {quests} />
    </aside>
  </div>
{/if}

<style>
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

  /* ---------- header ---------- */
  .head {
    display: flex; align-items: flex-end; justify-content: space-between; gap: 1.5rem; flex-wrap: wrap;
    margin: 0 0 1.25rem;
  }
  .hello { color: var(--muted); font-size: 0.92rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 {
    font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.04;
    display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
  }
  .title-mark {
    display: inline-grid; place-items: center; width: 46px; height: 46px; border-radius: 50%;
    background: var(--tile-butter); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .summary { margin-top: 0.55rem; color: var(--muted); font-size: 0.98rem; }
  .summary b { color: var(--text); font-variant-numeric: tabular-nums; }

  .search {
    position: relative; display: flex; align-items: center; gap: 0.6rem;
    width: min(380px, 100%); height: 54px; padding: 0 1.1rem;
    background: var(--surface2); border-radius: 999px; color: var(--muted);
    transition: background-color var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out);
  }
  .search:focus-within { background: var(--surface); box-shadow: 0 0 0 2px var(--accent), var(--shadow); }
  .search input { flex: 1; min-width: 0; height: 100%; background: none; border: none; font-size: 0.95rem; color: var(--text); }
  .search input:focus { box-shadow: none; outline: none; }
  .search input::-webkit-search-cancel-button { display: none; }
  .clear { width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: var(--surface3); color: var(--text); animation: pop 300ms var(--ease-out); }

  /* ---------- top band: two cards stretched to one height ---------- */
  .band {
    display: grid; grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr);
    align-items: stretch; gap: 1.25rem; margin-bottom: 2rem;
  }
  .sk-band { height: 240px; border-radius: 32px; }

  /* The art column is the wider one and the art keeps the video's 16:9, so
     the thumbnail shows whole instead of being cropped to whatever height
     the band happens to be. */
  .spot {
    display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); align-items: center; gap: 1.25rem;
    padding: 0.75rem; border-radius: 32px;
    background: var(--surface); box-shadow: var(--shadow-sm);
    transition: box-shadow var(--dur-3) var(--ease-out);
  }
  .spot:hover { box-shadow: var(--shadow-md); }
  .art {
    position: relative; display: block; overflow: hidden; border-radius: 24px; aspect-ratio: 16 / 9;
    color: var(--tile-ink);
  }
  .art.sky { background: var(--tile-sky); }
  .art.lilac { background: var(--tile-lilac); }
  .art.mint { background: var(--tile-mint); }
  .art.butter { background: var(--tile-butter); }
  .art.peach { background: var(--tile-peach); }
  .spot:hover .art :global(.thumb-media) { scale: 1.05; }
  .art-fallback { position: absolute; inset: 0; display: grid; place-items: center; opacity: 0.5; }
  .art-play {
    position: absolute; inset: 0; margin: auto; width: 86px; height: 86px; border-radius: 50%;
    display: grid; place-items: center;
    background: color-mix(in srgb, var(--surface) 45%, transparent);
    box-shadow: inset 0 0 0 8px color-mix(in srgb, var(--surface) 30%, transparent);
    animation: float 4s var(--ease-in-out) infinite;
  }
  .art-play > span {
    width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center;
    background: var(--surface); color: var(--text); transition: transform var(--dur-3) var(--ease-out);
  }
  .art-play :global(svg) { fill: currentColor; translate: 2px 0; }
  .spot:hover .art-play > span { transform: scale(1.14); }
  .art-bar { position: absolute; left: 0; right: 0; bottom: 0; height: 5px; background: color-mix(in srgb, #000 28%, transparent); }
  .art-bar span, .xp-bar span {
    display: block; height: 100%; width: var(--p); background: var(--brand);
    transform-origin: left; animation: grow 1s var(--ease-out) 350ms backwards;
  }
  @keyframes grow { from { transform: scaleX(0); } }

  .copy { display: flex; flex-direction: column; align-items: flex-start; gap: 0.7rem; padding: 1.3rem 1.1rem 1.1rem 0.4rem; min-width: 0; }
  .copy h2 {
    font-size: clamp(1.45rem, 1rem + 1.2vw, 2.1rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.1;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .desc {
    color: var(--muted); font-size: 0.95rem; line-height: 1.55;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .facts { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .facts span {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 28px; padding: 0 0.65rem; border-radius: 99px;
    background: var(--surface2); color: var(--text-secondary); font-size: 0.78rem; font-weight: 600; text-transform: capitalize;
  }
  .actions { display: flex; gap: 0.55rem; flex-wrap: wrap; margin-top: auto; }
  .play-ico {
    width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
    background: var(--on-accent); color: var(--accent); margin-left: -0.55rem;
    transition: transform var(--dur-3) var(--ease-out);
  }
  .play-ico :global(svg) { fill: currentColor; translate: 1px 0; }
  .play-btn:hover .play-ico { transform: scale(1.15) rotate(-8deg); }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--brand); animation: pulse-ring 1.6s var(--ease-out) infinite; }

  .spot.empty { grid-template-columns: 1fr; background: var(--tile-mint); color: var(--tile-ink); }
  .spot.empty .copy { padding: 1.6rem; }
  .spot.empty .desc { color: color-mix(in srgb, var(--tile-ink) 70%, transparent); }
  .spot.empty .ui-pill { background: var(--surface); color: var(--text); }

  .side {
    display: flex; flex-direction: column; gap: 1rem;
    padding: 1.15rem; border-radius: 32px; background: var(--bg-alt);
  }
  .side-head { display: flex; align-items: baseline; justify-content: space-between; padding: 0.15rem 0.2rem 0; }
  .side-head h2 { font-size: 1.3rem; letter-spacing: -0.025em; }
  .level { display: flex; align-items: center; gap: 0.9rem; padding: 0.8rem; border-radius: 22px; background: var(--surface); }
  .level-txt { display: flex; flex-direction: column; gap: 0.35rem; flex: 1; min-width: 0; }
  .level-txt b { font-size: 1rem; text-transform: capitalize; }
  .level-txt small { font-size: 0.76rem; color: var(--muted); }
  .xp-bar { display: block; height: 6px; border-radius: 99px; overflow: hidden; background: var(--surface3); }
  .xp-bar span { border-radius: inherit; }

  /* Three equal tiles that fill whatever height the band gives them. */
  .tiles { flex: 1; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.6rem; }
  .tile {
    position: relative; display: flex; flex-direction: column; justify-content: flex-end; gap: 0.15rem;
    min-height: 120px; padding: 0.8rem; border-radius: 22px; color: var(--tile-ink);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .tile:hover { translate: 0 -3px; box-shadow: var(--shadow); }
  .tile.sky { background: var(--tile-sky); }
  .tile.lilac { background: var(--tile-lilac); }
  .tile.mint { background: var(--tile-mint); }
  .tile.butter { background: var(--tile-butter); }
  .tile.peach { background: var(--tile-peach); }
  .t-ico {
    position: absolute; top: 0.75rem; left: 0.75rem;
    width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner);
    transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .tile:hover .t-ico { rotate: -14deg; scale: 1.1; }
  .t-ico.flame { animation: flicker 2.4s var(--ease-in-out) infinite; }
  @keyframes flicker { 0%, 100% { scale: 1; } 45% { scale: 1.12; } 60% { scale: 0.96; } }
  .tile b { font-size: 0.95rem; font-weight: 650; line-height: 1.25; }
  .tile.stat b { font-size: clamp(1.4rem, 1rem + 1vw, 1.85rem); font-weight: 700; letter-spacing: -0.03em; font-variant-numeric: tabular-nums; }
  .tile.stat > span:last-child { font-size: 0.74rem; opacity: 0.72; }
  .tile.stat:hover b { animation: pop 420ms var(--ease-out); }
  .t-go {
    position: absolute; top: 0.75rem; right: 0.75rem; width: 28px; height: 28px; border-radius: 50%;
    display: grid; place-items: center; background: var(--surface); color: var(--text);
    transition: transform var(--dur-3) var(--ease-out), background-color var(--dur-2);
  }
  .tile:hover .t-go { transform: rotate(-30deg); background: var(--accent); color: var(--on-accent); }

  /* Equal-height explore cards. */
  .explore { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); grid-auto-rows: 1fr; gap: 1rem; }
  .ex {
    position: relative; display: flex; flex-direction: column; justify-content: flex-end; gap: 0.35rem;
    min-height: 150px; padding: 1rem; border-radius: 26px; color: var(--tile-ink);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .ex:hover { translate: 0 -4px; box-shadow: var(--shadow-md); }
  .ex.sky { background: var(--tile-sky); }
  .ex.lilac { background: var(--tile-lilac); }
  .ex.butter { background: var(--tile-butter); }
  .ex.peach { background: var(--tile-peach); }
  .ex b { font-size: 1.05rem; font-weight: 650; }
  .ex small {
    font-size: 0.82rem; line-height: 1.4; opacity: 0.75; min-height: calc(2 * 1.4em);
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .ex:hover .t-ico { rotate: -14deg; scale: 1.1; }
  .ex:hover .t-go { transform: rotate(-30deg); background: var(--accent); color: var(--on-accent); }

  /* ---------- main grid ---------- */
  .home-grid {
    display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 2rem; align-items: start;
  }
  .home-main { min-width: 0; }
  .sk-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1rem; }

  .section-head { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .section-head h2 {
    display: inline-flex; align-items: center; gap: 0.5rem;
    font-size: 1.4rem; letter-spacing: -0.02em; text-transform: capitalize; margin-right: 0.25rem;
  }
  .section-head h2.plain { text-transform: none; }
  .rank, .mastery {
    display: inline-flex; align-items: center; gap: 0.35rem; height: 30px; padding: 0 0.75rem;
    border-radius: 99px; font-size: 0.8rem; font-weight: 600;
  }
  .rank { background: var(--tile-butter); color: var(--tile-ink); }
  .mastery { background: var(--surface2); color: var(--text-secondary); }
  .spacer { height: 2rem; }

  /* ---------- right rail ---------- */
  .rail {
    position: sticky; top: 1.5rem;
    display: flex; flex-direction: column; gap: 1rem;
    padding: 1.1rem; border-radius: 32px; background: var(--bg-alt);
  }
  .whoami {
    display: flex; align-items: center; gap: 0.8rem;
    padding: 0.7rem 0.7rem 0.7rem 0.75rem; border-radius: 22px; background: var(--surface);
    transition: box-shadow var(--dur-3) var(--ease-out);
  }
  .whoami:hover { box-shadow: var(--shadow); }
  .whoami:hover .go { transform: translateX(3px); }
  .whoami-text { display: flex; flex-direction: column; gap: 0.2rem; min-width: 0; flex: 1; }
  .whoami-text b { font-size: 0.98rem; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .whoami-meta { display: flex; gap: 0.45rem; align-items: center; flex-wrap: wrap; font-size: 0.76rem; color: var(--muted); }
  .whoami .code { font-weight: 700; letter-spacing: 0.04em; color: var(--tile-ink); background: var(--tile-sky); border-radius: 999px; padding: 0.1rem 0.5rem; }
  .go { width: 34px; height: 34px; }

  .rail-head { display: flex; align-items: baseline; justify-content: space-between; padding: 0.4rem 0.35rem 0; }
  .rail-head h2 { font-size: 1.45rem; letter-spacing: -0.03em; }
  .rail-link { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.85rem; font-weight: 600; color: var(--muted); }
  .rail-link:hover { color: var(--text); }
  .rail-link:hover :global(.icon) { transform: translateX(3px); transition: transform var(--dur-2) var(--ease-out); }

  /* ---------- states ---------- */
  .state {
    display: flex; flex-direction: column; align-items: center; gap: 0.75rem; text-align: center;
    padding: 3rem 1.5rem;
  }
  .state.small { padding: 3rem 1rem; }
  .state h2 { font-size: 1.4rem; }
  .state p { color: var(--muted); margin-bottom: 0.5rem; }
  .state-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }
  .state-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }

  /* ---------- responsive ---------- */
  @media (max-width: 1180px) {
    .home-grid { grid-template-columns: 1fr; }
    .rail { position: static; display: grid; grid-template-columns: 1fr 1fr; align-items: start; }
    .rail-head, .rail > :global(.list), .rail > :global(.empty) { grid-column: 1 / -1; }
    .rail > :global(.list) { grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
  }
  @media (max-width: 1000px) {
    .band { grid-template-columns: 1fr; }
  }
  @media (max-width: 760px) {
    .spot { grid-template-columns: 1fr; }
    .copy { padding: 0.6rem 0.6rem 0.8rem; }
    .rail { grid-template-columns: 1fr; padding: 0.8rem; border-radius: 26px; }
    .search { width: 100%; }
    .title-mark { width: 38px; height: 38px; }
    .tile { min-height: 104px; }
    /* Compact two-up explore tiles: one line of copy doesn't need 150px. */
    .explore { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.7rem; }
    .ex { min-height: 0; gap: 0.25rem; padding: 3.3rem 0.85rem 0.85rem; border-radius: 22px; }
    .ex b { font-size: 0.95rem; }
  }
</style>
