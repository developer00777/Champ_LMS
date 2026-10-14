<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { api, type LeaderboardEntry, type Badge } from '$lib/api/client';
  import { auth } from '$lib/stores/auth';
  import Avatar from '$lib/components/Avatar.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import { countUp } from '$lib/actions/motion';

  let entries: LeaderboardEntry[] = [];
  let badges: Badge[] = [];
  let loading = true;
  let dept = '';

  onMount(async () => {
    await Promise.all([loadBoard(), loadBadges()]);
  });

  // Each request is numbered, so a slow reply for an older filter can't
  // overwrite the board for the one typed since.
  let requestNo = 0;
  async function loadBoard() {
    const n = ++requestNo;
    loading = true;
    try {
      const result = await api.leaderboard(dept || undefined);
      if (n === requestNo) entries = result;
    } finally {
      if (n === requestNo) loading = false;
    }
  }

  // Typing in the filter waits for a short pause instead of a request per key.
  let filterTimer: ReturnType<typeof setTimeout> | undefined;
  function onFilterInput() {
    clearTimeout(filterTimer);
    filterTimer = setTimeout(loadBoard, 300);
  }
  onDestroy(() => clearTimeout(filterTimer));

  async function loadBadges() {
    try { badges = await api.myBadges(); } catch {}
  }

  const TONES = ['sky', 'lilac', 'mint', 'butter', 'peach'];
  // Podium order on screen: 2nd, 1st, 3rd.
  $: podium = entries.length >= 3 ? [entries[1], entries[0], entries[2]] : [];
  $: rest = entries.length >= 3 ? entries.slice(3) : entries;
  $: mine = entries.find((e) => e.user_id === $auth.user?.id) ?? null;
  const PLACE = { 0: 'second', 1: 'first', 2: 'third' } as Record<number, string>;
</script>

<svelte:head><title>Leaderboard — Champ LMS</title></svelte:head>

<div class="page">
  <header class="head">
    <div>
      <p class="eyebrow ui-rise">Who's leading the way</p>
      <h1 class="ui-rise" style="--i:1">
        Leaderboard
        <span class="title-mark" aria-hidden="true"><Icon name="trophy" size={24} /></span>
      </h1>
    </div>
    <label class="search ui-rise" style="--i:2">
      <Icon name="building" size={18} />
      <span class="sr">Filter by department</span>
      <input bind:value={dept} placeholder="Filter by department..." on:input={onFilterInput} />
    </label>
  </header>

  {#if mine}
    <div class="you ui-rise" style="--i:3">
      <span class="you-rank">#{mine.rank}</span>
      <span class="you-txt"><b>Your position</b><small>{mine.department ?? 'All departments'}</small></span>
      <span class="you-stat"><b use:countUp={mine.points}></b><small>points</small></span>
      <span class="you-stat"><b use:countUp={mine.streak_days}></b><small>day streak</small></span>
    </div>
  {/if}

  {#if badges.length}
    <section class="badges-row">
      <h3 class="ui-rise" style="--i:3">Your badges</h3>
      <div class="badges">
        {#each badges as b, n}
          <div class="badge-card ui-rise" style="--i:{4 + Math.min(n, 8)}" title={b.description ?? b.name}>
            <span class="b-ico {TONES[n % TONES.length]}">
              {#if b.icon_url}
                <img src={b.icon_url} alt={b.name} class="badge-icon" />
              {:else}
                <Icon name="award" size={18} />
              {/if}
            </span>
            <span>{b.name}</span>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  <!-- Skeleton only on first load, so typing in the filter doesn't flash it. -->
  {#if loading && entries.length === 0}
    <div class="podium sk">
      {#each Array(3) as _, n}<div class="ui-skeleton" style="height:{n === 1 ? 250 : 210}px;border-radius:28px"></div>{/each}
    </div>
    <div class="board">
      {#each Array(4) as _}<div class="ui-skeleton" style="height:70px;border-radius:22px"></div>{/each}
    </div>
  {:else if entries.length === 0 && !loading}
    <div class="empty ui-rise">
      <span class="empty-ico"><Icon name="users" size={26} /></span>
      <h2>No one here yet</h2>
      <p>{dept ? `Nobody matches “${dept}”. Try another department.` : 'Rankings appear as people earn points.'}</p>
    </div>
  {:else}
    {#if podium.length}
      <div class="podium">
        {#each podium as entry, i}
          <div class="step {PLACE[i]} ui-rise" style="--i:{i === 1 ? 2 : i === 0 ? 3 : 4}" class:me={entry.user_id === $auth.user?.id}>
            <div class="who">
              {#if i === 1}<span class="crown" aria-hidden="true"><Icon name="trophy" size={18} /></span>{/if}
              <Avatar src={entry.avatar_url} name={entry.full_name} size={i === 1 ? 72 : 60} ring={entry.user_id === $auth.user?.id} />
              <b class="p-name">{entry.full_name ?? 'Anonymous'}</b>
              {#if entry.department}<small class="p-dept">{entry.department}</small>{/if}
            </div>
            <div class="block">
              <span class="medal"><Icon name="medal" size={16} /> {entry.rank}</span>
              <b class="p-pts"><span use:countUp={entry.points}></span><small> pts</small></b>
              <span class="p-streak"><Icon name="flame" size={14} /> {entry.streak_days} day streak</span>
            </div>
          </div>
        {/each}
      </div>
    {/if}

    <div class="board">
      {#each rest as entry, n}
        <div class="entry ui-rise" style="--i:{Math.min(n, 10)}" class:me={entry.user_id === $auth.user?.id}>
          <span class="rank">#{entry.rank}</span>
          <Avatar
            src={entry.avatar_url}
            name={entry.full_name}
            size={42}
            ring={entry.user_id === $auth.user?.id}
          />
          <div class="user-info">
            <p class="name">
              {entry.full_name ?? 'Anonymous'}
              {#if entry.employee_code}
                <span class="code">{entry.employee_code}</span>
              {/if}
            </p>
            {#if entry.department}
              <p class="dept">{entry.department}</p>
            {/if}
          </div>
          <div class="stats">
            <span class="streak"><Icon name="flame" size={14} /> {entry.streak_days}</span>
            <span class="pts"><span use:countUp={entry.points}></span> pts</span>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .page { max-width: 920px; margin: 0 auto; }
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 1.5rem; flex-wrap: wrap; margin: 0 0 1.25rem; }
  .eyebrow { color: var(--muted); font-size: 0.95rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; display: flex; align-items: center; gap: 0.6rem; }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-butter); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }

  .search {
    display: flex; align-items: center; gap: 0.6rem; width: min(320px, 100%); height: 50px; padding: 0 1.1rem;
    background: var(--surface2); border-radius: 999px; color: var(--muted);
    transition: background-color var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out);
  }
  .search:focus-within { background: var(--surface); box-shadow: 0 0 0 2px var(--accent), var(--shadow); }
  .search input { flex: 1; min-width: 0; height: 100%; background: none; border: none; font-size: 0.92rem; color: var(--text); padding: 0; }
  .search input:focus { box-shadow: none; outline: none; }

  .mint { background: var(--tile-mint); } .butter { background: var(--tile-butter); } .sky { background: var(--tile-sky); }
  .lilac { background: var(--tile-lilac); } .peach { background: var(--tile-peach); }

  /* ---------- your position ---------- */
  .you {
    display: flex; align-items: center; gap: 1.1rem; flex-wrap: wrap;
    padding: 0.9rem 1.3rem; border-radius: 26px; margin-bottom: 1.75rem;
    background: var(--accent); color: var(--on-accent);
  }
  .you-rank { font-size: 1.8rem; font-weight: 700; letter-spacing: -0.03em; animation: pop 600ms var(--ease-out) 300ms backwards; }
  .you-txt { flex: 1; display: flex; flex-direction: column; min-width: 140px; }
  .you-txt small, .you-stat small { opacity: 0.65; font-size: 0.76rem; }
  .you-stat { display: flex; flex-direction: column; align-items: flex-end; }
  .you-stat b { font-size: 1.25rem; font-variant-numeric: tabular-nums; }

  /* ---------- badges ---------- */
  .badges-row { margin-bottom: 2rem; }
  h3 { font-size: 0.78rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin-bottom: 0.75rem; }
  .badges { display: flex; gap: 0.6rem; flex-wrap: wrap; }
  .badge-card {
    background: var(--surface); border-radius: 999px; padding: 0.35rem 0.95rem 0.35rem 0.35rem;
    display: flex; align-items: center; gap: 0.55rem; font-size: 0.84rem; font-weight: 600;
    box-shadow: var(--shadow-sm); transition: translate var(--dur-3) var(--ease-out);
  }
  .badge-card:hover { translate: 0 -2px; }
  .b-ico { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; color: var(--tile-ink); overflow: hidden; transition: rotate var(--dur-3) var(--ease-out); }
  .badge-card:hover .b-ico { rotate: -14deg; }
  .badge-icon { width: 24px; height: 24px; object-fit: contain; }

  /* ---------- podium ---------- */
  .podium { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; align-items: end; margin-bottom: 1.75rem; }
  .step { display: flex; flex-direction: column; align-items: center; gap: 0.8rem; }
  .who { position: relative; display: flex; flex-direction: column; align-items: center; gap: 0.3rem; text-align: center; transition: translate var(--dur-3) var(--ease-out); }
  .step:hover .who { translate: 0 -4px; }
  .crown {
    position: absolute; top: -26px; width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
    background: var(--tile-butter); color: var(--tile-ink); animation: float 3.5s var(--ease-in-out) infinite;
  }
  .p-name { font-size: 0.98rem; font-weight: 600; margin-top: 0.35rem; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .p-dept { font-size: 0.76rem; color: var(--muted); }
  .block {
    width: 100%; display: flex; flex-direction: column; align-items: center; gap: 0.3rem;
    padding: 1.1rem 0.8rem 1.2rem; border-radius: 26px 26px 18px 18px; color: var(--tile-ink);
    transform-origin: bottom; animation: lift 700ms var(--ease-out) 250ms backwards;
    transition: box-shadow var(--dur-3) var(--ease-out);
  }
  .step:hover .block { box-shadow: var(--shadow-md); }
  @keyframes lift { from { scale: 1 0.3; opacity: 0; } }
  .first .block { background: var(--tile-butter); min-height: 170px; }
  .second .block { background: var(--tile-sky); min-height: 135px; }
  .third .block { background: var(--tile-peach); min-height: 115px; }
  .step.me .block { box-shadow: 0 0 0 3px var(--accent); }
  .medal { display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.2rem 0.6rem; border-radius: 99px; background: var(--tile-inner); font-weight: 700; font-size: 0.85rem; }
  .p-pts { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.03em; font-variant-numeric: tabular-nums; }
  .first .p-pts { font-size: 2rem; }
  .p-pts small { font-size: 0.55em; opacity: 0.65; font-weight: 600; }
  .p-streak { display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.76rem; opacity: 0.75; }

  /* ---------- list ---------- */
  .board { display: flex; flex-direction: column; gap: 0.55rem; }
  .entry {
    display: flex; align-items: center; gap: 0.9rem;
    background: var(--surface); border-radius: 22px; box-shadow: var(--shadow-sm);
    padding: 0.7rem 1.1rem 0.7rem 0.8rem;
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .entry:hover { translate: 4px 0; box-shadow: var(--shadow); }
  .entry.me { background: var(--tile-lilac); color: var(--tile-ink); }
  .rank {
    min-width: 2.6rem; height: 2.6rem; border-radius: 50%; display: grid; place-items: center; flex-shrink: 0;
    background: var(--surface2); font-weight: 700; font-size: 0.85rem; font-variant-numeric: tabular-nums;
  }
  .entry.me .rank { background: var(--tile-inner); }
  .user-info { flex: 1; min-width: 0; }
  .name { font-weight: 600; display: flex; align-items: baseline; gap: 0.45rem; flex-wrap: wrap; }
  .code {
    font-size: 0.7rem; font-weight: 600; color: var(--muted);
    background: var(--surface2); border-radius: 999px; padding: 0.1rem 0.45rem; letter-spacing: 0.03em;
  }
  .dept { font-size: 0.78rem; color: var(--muted); }
  .entry.me .dept, .entry.me .code { color: color-mix(in srgb, var(--tile-ink) 70%, transparent); }
  .stats { display: flex; align-items: center; gap: 1rem; }
  .pts { font-weight: 700; font-variant-numeric: tabular-nums; }
  .streak { display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.84rem; color: var(--muted); }
  .entry:hover .streak :global(.icon) { animation: wiggle 500ms var(--ease-out); }

  .empty { display: flex; flex-direction: column; align-items: center; gap: 0.6rem; text-align: center; padding: 3rem 1rem; background: var(--surface); border-radius: 32px; }
  .empty-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }
  .empty h2 { font-size: 1.3rem; }
  .empty p { color: var(--muted); font-size: 0.9rem; }

  @media (max-width: 760px) {
    .podium { gap: 0.5rem; }
    .p-pts, .first .p-pts { font-size: 1.25rem; }
    .p-streak { display: none; }
    .search { width: 100%; }
    .stats { gap: 0.6rem; }
    .you-stat { align-items: flex-start; }
  }
</style>
