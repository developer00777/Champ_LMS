<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api,
    type AdminChallengePool,
    type AdminChallengeRow,
    type ChallengeKind,
    type DailyChallengeInput,
  } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import Select from '$lib/components/Select.svelte';
  import { countUp } from '$lib/actions/motion';

  let pool: AdminChallengePool | null = null;
  let loading = true;
  let error = '';
  let busy = false;

  // --- create form ---------------------------------------------------------
  let showForm = false;
  let title = '';
  let description = '';
  let kind: ChallengeKind = 'self_report';
  let rewardXp = 20;
  let department = '';
  let alwaysOn = false;

  const KINDS: { value: ChallengeKind; label: string; hint: string }[] = [
    { value: 'watch_episode', label: 'Watch an episode',
      hint: 'Verified automatically from watch progress.' },
    { value: 'pass_quiz', label: 'Pass a module quiz',
      hint: 'Verified automatically from quiz attempts.' },
    { value: 'pass_test', label: 'Pass a test series',
      hint: 'Verified automatically from test attempts.' },
    { value: 'self_report', label: 'Self-reported',
      hint: 'The learner marks it done. Use for things the platform can’t see.' },
  ];

  onMount(load);

  async function load() {
    loading = true;
    try { pool = await api.adminDailyChallenges(); error = ''; }
    catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  async function create() {
    if (!title.trim() || busy) return;
    busy = true; error = '';
    try {
      const body: DailyChallengeInput = {
        title: title.trim(),
        description: description.trim() || null,
        kind,
        reward_xp: rewardXp,
        reward_points: rewardXp,
        department: department.trim() || null,
        always_on: alwaysOn,
      };
      await api.createDailyChallenge(body);
      title = ''; description = ''; department = ''; alwaysOn = false;
      showForm = false;
      await load();
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  async function toggleActive(row: AdminChallengeRow) {
    busy = true; error = '';
    try {
      await api.updateDailyChallenge(row.id, { active: !row.active });
      await load();
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  async function togglePin(row: AdminChallengeRow) {
    busy = true; error = '';
    try {
      await api.updateDailyChallenge(row.id, { always_on: !row.always_on });
      await load();
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  async function remove(row: AdminChallengeRow) {
    busy = true; error = '';
    try {
      const res = await api.deleteDailyChallenge(row.id);
      if (res.deactivated) {
        error = `"${row.title}" has ${res.completions} completion(s), so it was ` +
                `deactivated rather than deleted — removing it would erase that history.`;
      }
      await load();
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  const KIND_LABELS: Record<string, string> = {
    watch_episode: 'Watch', pass_quiz: 'Quiz',
    pass_test: 'Test', self_report: 'Self-reported',
  };

  $: liveCount = pool?.challenges.filter((c) => c.live_today).length ?? 0;
  $: rotatingCount = pool?.challenges.filter((c) => c.active && !c.always_on).length ?? 0;
  $: pinnedCount = pool?.challenges.filter((c) => c.active && c.always_on).length ?? 0;

  // Presentation only: an icon and tile colour per challenge type.
  const KIND_ICONS: Record<string, string> = {
    watch_episode: 'play', pass_quiz: 'checkCircle', pass_test: 'clipboard', self_report: 'flag',
  };
  const KIND_TONES: Record<string, string> = {
    watch_episode: 'sky', pass_quiz: 'mint', pass_test: 'lilac', self_report: 'butter',
  };
</script>

<svelte:head><title>Daily challenges · Admin</title></svelte:head>

<div class="page">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Daily Challenges' }]} />
  <header class="head">
    <div>
      <h1 class="ui-rise" style="--i:1">
        Daily challenges
        <span class="title-mark" aria-hidden="true"><Icon name="flame" size={24} /></span>
      </h1>
      <p class="sub ui-rise" style="--i:2">
        Write a pool once; {pool?.daily_count ?? 3} rotate into view each day. The
        rotation is driven by the date, so everyone sees the same set and every
        challenge gets its turn.
      </p>
    </div>
    <button class="btn primary ui-rise" style="--i:3" on:click={() => (showForm = !showForm)}>
      <span class="swap" class:turned={showForm}><Icon name="plus" size={16} /></span>
      {showForm ? 'Cancel' : 'New challenge'}
    </button>
  </header>

  {#if error}<p class="error pop-in"><Icon name="info" size={16} /> <span>{error}</span></p>{/if}

  {#if showForm}
    <div class="form-card pop-in">
      <div class="f-head">
        <span class="f-ico {KIND_TONES[kind] ?? 'butter'}"><Icon name={KIND_ICONS[kind] ?? 'flag'} size={20} /></span>
        <h2>New challenge</h2>
      </div>
      <label>Title<input bind:value={title} placeholder="Watch one episode today" /></label>
      <label>
        Description
        <input bind:value={description} placeholder="Shown under the title on the learner's card" />
      </label>
      <div class="row">
        <!-- svelte-ignore a11y-label-has-associated-control -->
        <label>
          Type
          <Select bind:value={kind} options={KINDS} />
        </label>
        <label>XP reward<input type="number" min="0" max="500" bind:value={rewardXp} /></label>
        <label>
          Department
          <input bind:value={department} placeholder="blank = everyone" />
        </label>
      </div>
      {#key kind}<p class="hint pop-in"><Icon name="info" size={14} /> {KINDS.find((k) => k.value === kind)?.hint}</p>{/key}
      <label class="check">
        <input type="checkbox" bind:checked={alwaysOn} />
        <span>
          Pin to every day
          <small>
            Skips the rotation and always appears. Pinned challenges take slots
            from the {pool?.daily_count ?? 3} shown, so use them sparingly.
          </small>
        </span>
      </label>
      <div>
        <button class="btn primary" disabled={!title.trim() || busy} on:click={create}>
          <Icon name="check" size={16} /> {busy ? 'Saving…' : 'Create challenge'}
        </button>
      </div>
    </div>
  {/if}

  {#if loading}
    <div class="kpis">{#each Array(4) as _}<div class="ui-skeleton" style="height:104px;border-radius:24px"></div>{/each}</div>
    <div class="rows">{#each Array(4) as _, i}<div class="ui-skeleton" style="height:86px;border-radius:24px;opacity:{1 - i * 0.15}"></div>{/each}</div>
  {:else if pool}
    <div class="kpis">
      <div class="kpi sky ui-rise" style="--i:3"><span class="k-ico"><Icon name="layers" size={18} /></span><b use:countUp={pool.active_count}></b><span>active in pool</span></div>
      <div class="kpi peach ui-rise" style="--i:4"><span class="k-ico flame"><Icon name="flame" size={18} /></span><b use:countUp={liveCount}></b><span>live today</span></div>
      <div class="kpi mint ui-rise" style="--i:5"><span class="k-ico spin-ico"><Icon name="refresh" size={18} /></span><b use:countUp={rotatingCount}></b><span>rotating</span></div>
      <div class="kpi butter ui-rise" style="--i:6"><span class="k-ico"><Icon name="flag" size={18} /></span><b use:countUp={pinnedCount}></b><span>pinned</span></div>
    </div>

    {#if rotatingCount > 0 && rotatingCount < pool.daily_count}
      <p class="warn ui-rise" style="--i:7">
        <Icon name="alert" size={17} />
        <span>
          Only {rotatingCount} rotating challenge{rotatingCount === 1 ? '' : 's'} in the
          pool, so the daily set can't fill {pool.daily_count} slots and will barely
          change day to day. Add a few more to make the rotation feel fresh.
        </span>
      </p>
    {/if}

    {#if pool.challenges.length === 0}
      <div class="empty ui-rise" style="--i:7">
        <span class="e-ico"><Icon name="flame" size={26} /></span>
        <p>No challenges yet. Create one above to start the rotation.</p>
      </div>
    {:else}
      <div class="rows">
        {#each pool.challenges as row, n (row.id)}
          <div class="row-card ui-rise" class:off={!row.active} class:live-card={row.live_today} style="--i:{Math.min(n + 7, 16)}">
            <span class="r-ico {KIND_TONES[row.kind] ?? 'butter'}" aria-hidden="true">
              <Icon name={KIND_ICONS[row.kind] ?? 'flag'} size={20} />
            </span>
            <div class="r-main">
              <div class="r-top">
                <b>{row.title}</b>
                <span class="tag" class:auto={row.auto_verified}>
                  {#if row.auto_verified}<Icon name="check" size={11} stroke={2.4} />{/if}
                  {KIND_LABELS[row.kind] ?? row.kind}
                </span>
                {#if row.live_today}<span class="tag live"><span class="dot"></span>Live today</span>{/if}
                {#if row.always_on}<span class="tag pin"><Icon name="flag" size={11} stroke={2.2} />Pinned</span>{/if}
                {#if row.department}<span class="tag">{row.department}</span>{/if}
                {#if !row.active}<span class="tag off-tag">Inactive</span>{/if}
              </div>
              {#if row.description}<p class="r-desc">{row.description}</p>{/if}
              <span class="meta">
                <span class="xp"><Icon name="zap" size={13} /> +{row.reward_xp} XP</span>
                <span class="sep"></span>{row.completion_count} completion{row.completion_count === 1 ? '' : 's'}
                {#if !row.auto_verified}<span class="sep"></span>honour system{/if}
              </span>
            </div>
            <div class="r-actions">
              <button class="btn small" disabled={busy} on:click={() => toggleActive(row)}>
                <Icon name={row.active ? 'pause' : 'play'} size={13} stroke={row.active ? 2 : 0} />
                {row.active ? 'Deactivate' : 'Activate'}
              </button>
              <button class="btn small" class:pinned={row.always_on} disabled={busy} on:click={() => togglePin(row)}>
                <Icon name="flag" size={13} /> {row.always_on ? 'Unpin' : 'Pin'}
              </button>
              <button class="btn small danger" disabled={busy} on:click={() => remove(row)}>
                <Icon name="trash" size={13} /> Delete
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1.25rem; flex-wrap: wrap; margin: 0 0 1.25rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.6rem; }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-peach); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .sub { color: var(--muted); font-size: 0.9rem; line-height: 1.55; max-width: 62ch; }
  .pop-in { animation: modal-in 380ms var(--ease-out) backwards; }
  .error { display: flex; align-items: flex-start; gap: 0.5rem; color: var(--text); background: color-mix(in srgb, var(--danger) 10%, transparent); border-radius: 16px; padding: 0.75rem 0.95rem; font-size: 0.85rem; margin-bottom: 1rem; line-height: 1.5; }
  .error :global(.icon) { color: var(--danger); flex: none; margin-top: 2px; }
  .warn { display: flex; gap: 0.55rem; align-items: flex-start; background: var(--tile-butter); color: var(--tile-ink); border-radius: 18px; padding: 0.8rem 1rem; font-size: 0.83rem; line-height: 1.55; margin-bottom: 1rem; }
  .warn :global(.icon) { flex: none; margin-top: 2px; color: var(--warn); }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 0.6rem; text-align: center; color: var(--muted); font-size: 0.88rem; padding: 3rem 1rem; border-radius: 28px; background: var(--surface); }
  .e-ico { width: 60px; height: 60px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-peach); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }

  /* ---------- kpis ---------- */
  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.85rem; margin-bottom: 1.4rem; }
  .kpi {
    border-radius: 24px; padding: 1rem 1.05rem; display: flex; flex-direction: column; color: var(--tile-ink);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .kpi:hover { translate: 0 -3px; box-shadow: var(--shadow); }
  .kpi b { font-size: clamp(1.5rem, 1.1rem + 1vw, 2rem); font-weight: 700; letter-spacing: -0.03em; margin-top: 0.5rem; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .kpi:hover b { animation: pop 420ms var(--ease-out); }
  .kpi > span:last-child { font-size: 0.78rem; opacity: 0.72; font-weight: 500; }
  .k-ico { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); transition: transform var(--dur-3) var(--ease-out); }
  .kpi:hover .k-ico { transform: rotate(-14deg) scale(1.1); }
  .kpi:hover .spin-ico { transform: rotate(180deg); transition-duration: 600ms; }
  .k-ico.flame { animation: flicker 2.4s var(--ease-in-out) infinite; }
  @keyframes flicker { 0%, 100% { scale: 1; } 45% { scale: 1.12; } 60% { scale: 0.96; } }
  .sky { background: var(--tile-sky); } .peach { background: var(--tile-peach); } .mint { background: var(--tile-mint); }
  .butter { background: var(--tile-butter); } .lilac { background: var(--tile-lilac); }

  /* ---------- form ---------- */
  .form-card { background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-sm); padding: 1.35rem 1.4rem; margin-bottom: 1.5rem; display: flex; flex-direction: column; gap: 0.8rem; }
  .f-head { display: flex; align-items: center; gap: 0.7rem; margin-bottom: 0.1rem; }
  .f-ico { width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center; color: var(--tile-ink); transition: background-color var(--dur-3); animation: pop 400ms var(--ease-out); }
  .form-card h2 { font-size: 1.15rem; font-weight: 700; letter-spacing: -0.015em; }
  .form-card label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }
  .form-card input {
    background: var(--surface2); border: 1px solid transparent; color: var(--text);
    border-radius: 14px; padding: 0.62rem 0.85rem; font-family: inherit;
    font-size: 0.88rem; font-weight: 400; width: 100%;
    transition: background-color var(--dur-2), border-color var(--dur-2), box-shadow var(--dur-2);
  }
  .form-card input:focus { outline: none; background: var(--surface); border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent); }
  .row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; }
  .hint { display: flex; align-items: center; gap: 0.4rem; font-size: 0.78rem; color: var(--muted); line-height: 1.5; }
  .check { flex-direction: row !important; align-items: flex-start; gap: 0.6rem; padding: 0.75rem 0.9rem; border-radius: 16px; background: var(--surface2); cursor: pointer; }
  .check input { width: auto; margin-top: 0.15rem; }
  .check span { display: flex; flex-direction: column; gap: 0.15rem; color: var(--text); }
  .check small { font-weight: 400; font-size: 0.75rem; color: var(--muted); line-height: 1.5; max-width: 56ch; }

  /* ---------- challenge rows ---------- */
  .rows { display: flex; flex-direction: column; gap: 0.6rem; }
  .row-card {
    display: flex; align-items: center; gap: 0.95rem; flex-wrap: wrap;
    background: var(--surface); border-radius: 24px; padding: 0.85rem 1rem 0.85rem 0.85rem; box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out), opacity var(--dur-3);
  }
  .row-card:hover { translate: 0 -2px; box-shadow: var(--shadow); }
  .row-card.live-card { box-shadow: var(--shadow-sm), inset 0 0 0 2px color-mix(in srgb, var(--brand) 35%, transparent); }
  .row-card.off { opacity: 0.6; }
  .row-card.off:hover { opacity: 0.85; }
  .r-ico { flex: none; width: 48px; height: 48px; border-radius: 16px; display: grid; place-items: center; color: var(--tile-ink); transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out); }
  .r-ico :global(svg[stroke-width="0"]) { fill: currentColor; }
  .row-card:hover .r-ico { rotate: -10deg; scale: 1.07; }
  .r-main { flex: 1; min-width: 220px; }
  .r-top { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.25rem; }
  .r-top b { font-size: 0.98rem; margin-right: 0.15rem; }
  .r-desc { font-size: 0.82rem; color: var(--muted); line-height: 1.5; margin-bottom: 0.3rem; }
  .tag {
    display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.02em;
    background: var(--surface2); color: var(--text-secondary); border-radius: 999px; padding: 0.16rem 0.55rem;
  }
  .tag.auto { background: var(--tile-mint); color: var(--tile-ink); }
  .tag.live { background: color-mix(in srgb, var(--brand) 13%, transparent); color: var(--brand); }
  .tag.live .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--brand); animation: pulse-ring 1.6s var(--ease-out) infinite; }
  .tag.pin { background: var(--tile-butter); color: var(--tile-ink); }
  .tag.off-tag { background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger); }
  .meta { display: inline-flex; align-items: center; gap: 0.45rem; flex-wrap: wrap; font-size: 0.76rem; color: var(--muted); }
  .xp { display: inline-flex; align-items: center; gap: 0.25rem; font-weight: 700; color: var(--text); }
  .sep { width: 3px; height: 3px; border-radius: 50%; background: currentColor; opacity: 0.6; }
  .r-actions { display: flex; gap: 0.35rem; flex-shrink: 0; flex-wrap: wrap; }

  .btn {
    display: inline-flex; align-items: center; gap: 0.4rem;
    background: var(--surface2); border: none; color: var(--text);
    border-radius: 999px; padding: 0.6rem 1.1rem; font-size: 0.85rem; font-weight: 600;
    cursor: pointer; font-family: inherit;
    transition: background-color var(--dur-2), color var(--dur-2), translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .btn:hover:not(:disabled) { background: var(--surface3); translate: 0 -1px; }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.primary { background: var(--accent); color: var(--on-accent); }
  .btn.primary:hover:not(:disabled) { background: var(--accent-hover); box-shadow: var(--shadow); }
  .btn.small { padding: 0.36rem 0.72rem; font-size: 0.76rem; gap: 0.3rem; }
  .btn.small :global(svg[stroke-width="0"]) { fill: currentColor; }
  .btn.pinned { background: var(--tile-butter); color: var(--tile-ink); }
  .btn.small.danger { color: var(--danger); background: color-mix(in srgb, var(--danger) 9%, transparent); }
  .btn.small.danger:hover:not(:disabled) { background: color-mix(in srgb, var(--danger) 16%, transparent); }
  .btn :global(.icon) { transition: transform var(--dur-3) var(--ease-out); }
  .btn:hover:not(:disabled) :global(.icon) { transform: rotate(-10deg) scale(1.1); }
  .swap { display: inline-flex; transition: rotate var(--dur-3) var(--ease-out); }
  .swap.turned { rotate: 45deg; }
  .btn:hover:not(:disabled) .swap :global(.icon) { transform: none; }

  @media (max-width: 720px) {
    .kpis { grid-template-columns: repeat(2, 1fr); }
    .row { grid-template-columns: 1fr; }
    .r-actions { width: 100%; }
    .r-actions .btn { flex: 1; justify-content: center; }
  }
</style>
