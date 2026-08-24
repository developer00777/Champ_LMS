<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api,
    type AdminChallengePool,
    type AdminChallengeRow,
    type ChallengeKind,
    type DailyChallengeInput,
  } from '$lib/api/client';

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
</script>

<svelte:head><title>Daily challenges · Admin</title></svelte:head>

<div class="page">
  <header class="head">
    <div>
      <h1>Daily challenges</h1>
      <p class="sub">
        Write a pool once; {pool?.daily_count ?? 3} rotate into view each day. The
        rotation is driven by the date, so everyone sees the same set and every
        challenge gets its turn.
      </p>
    </div>
    <button class="btn primary" on:click={() => (showForm = !showForm)}>
      {showForm ? 'Cancel' : 'New challenge'}
    </button>
  </header>

  {#if error}<p class="error">{error}</p>{/if}

  {#if showForm}
    <div class="form-card">
      <h2>New challenge</h2>
      <label>Title<input bind:value={title} placeholder="Watch one episode today" /></label>
      <label>
        Description
        <input bind:value={description} placeholder="Shown under the title on the learner's card" />
      </label>
      <div class="row">
        <label>
          Type
          <select bind:value={kind}>
            {#each KINDS as k}<option value={k.value}>{k.label}</option>{/each}
          </select>
        </label>
        <label>XP reward<input type="number" min="0" max="500" bind:value={rewardXp} /></label>
        <label>
          Department
          <input bind:value={department} placeholder="blank = everyone" />
        </label>
      </div>
      <p class="hint">{KINDS.find((k) => k.value === kind)?.hint}</p>
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
      <button class="btn primary" disabled={!title.trim() || busy} on:click={create}>
        {busy ? 'Saving…' : 'Create challenge'}
      </button>
    </div>
  {/if}

  {#if loading}
    <div class="skeleton big"></div>
  {:else if pool}
    <div class="kpis">
      <div class="kpi"><b>{pool.active_count}</b><span>active in pool</span></div>
      <div class="kpi"><b>{liveCount}</b><span>live today</span></div>
      <div class="kpi"><b>{rotatingCount}</b><span>rotating</span></div>
      <div class="kpi"><b>{pinnedCount}</b><span>pinned</span></div>
    </div>

    {#if rotatingCount > 0 && rotatingCount < pool.daily_count}
      <p class="warn">
        Only {rotatingCount} rotating challenge{rotatingCount === 1 ? '' : 's'} in the
        pool, so the daily set can't fill {pool.daily_count} slots and will barely
        change day to day. Add a few more to make the rotation feel fresh.
      </p>
    {/if}

    {#if pool.challenges.length === 0}
      <p class="empty">No challenges yet. Create one above to start the rotation.</p>
    {:else}
      <div class="rows">
        {#each pool.challenges as row (row.id)}
          <div class="row-card" class:off={!row.active}>
            <div class="r-main">
              <div class="r-top">
                <b>{row.title}</b>
                <span class="tag" class:auto={row.auto_verified}>
                  {KIND_LABELS[row.kind] ?? row.kind}
                </span>
                {#if row.live_today}<span class="tag live">Live today</span>{/if}
                {#if row.always_on}<span class="tag pin">Pinned</span>{/if}
                {#if row.department}<span class="tag">{row.department}</span>{/if}
                {#if !row.active}<span class="tag off-tag">Inactive</span>{/if}
              </div>
              {#if row.description}<p class="r-desc">{row.description}</p>{/if}
              <span class="muted tiny">
                +{row.reward_xp} XP · {row.completion_count} completion{row.completion_count === 1 ? '' : 's'}
                {#if !row.auto_verified}· honour system{/if}
              </span>
            </div>
            <div class="r-actions">
              <button class="btn small" disabled={busy} on:click={() => toggleActive(row)}>
                {row.active ? 'Deactivate' : 'Activate'}
              </button>
              <button class="btn small" disabled={busy} on:click={() => togglePin(row)}>
                {row.always_on ? 'Unpin' : 'Pin'}
              </button>
              <button class="btn small danger" disabled={busy} on:click={() => remove(row)}>
                Delete
              </button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .page { max-width: 900px; margin: 0 auto; padding-bottom: 4rem; }
  .head { display: flex; justify-content: space-between; align-items: flex-start;
          gap: 1rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
  h1 { font-size: 1.5rem; font-weight: 800; margin-bottom: 0.2rem; }
  .sub { color: var(--muted); font-size: 0.82rem; line-height: 1.55; max-width: 62ch; }
  .error { color: #e05260; font-size: 0.84rem; margin-bottom: 0.8rem; line-height: 1.5; }
  .warn { background: color-mix(in srgb, #e0a852 12%, var(--surface));
          border: 1px solid #e0a852; border-radius: 8px; padding: 0.7rem 0.9rem;
          font-size: 0.79rem; line-height: 1.55; margin-bottom: 1rem; }
  .empty { color: var(--muted); font-size: 0.85rem; padding: 1.5rem 0; }

  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.7rem; margin-bottom: 1.25rem; }
  .kpi { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
         padding: 0.85rem 1rem; display: flex; flex-direction: column; }
  .kpi b { font-size: 1.35rem; font-weight: 800; font-variant-numeric: tabular-nums; }
  .kpi span { font-size: 0.71rem; color: var(--muted); }

  .form-card { background: var(--surface); border: 1px solid var(--border);
               border-radius: 12px; padding: 1.25rem 1.35rem; margin-bottom: 1.5rem;
               display: flex; flex-direction: column; gap: 0.7rem; }
  .form-card h2 { font-size: 1rem; font-weight: 800; margin-bottom: 0.2rem; }
  .form-card label { display: flex; flex-direction: column; gap: 0.3rem;
                     font-size: 0.77rem; font-weight: 600; }
  .form-card input, .form-card select {
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    border-radius: 7px; padding: 0.55rem 0.7rem; font-family: inherit;
    font-size: 0.85rem; font-weight: 400; width: 100%; }
  .form-card input:focus, .form-card select:focus { outline: none; border-color: var(--accent); }
  .row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.7rem; }
  .hint { font-size: 0.74rem; color: var(--muted); line-height: 1.5; }
  .check { flex-direction: row; align-items: flex-start; gap: 0.55rem; }
  .check input { width: auto; margin-top: 0.15rem; }
  .check span { display: flex; flex-direction: column; gap: 0.15rem; }
  .check small { font-weight: 400; font-size: 0.72rem; color: var(--muted);
                 line-height: 1.5; max-width: 52ch; }

  .rows { display: flex; flex-direction: column; gap: 0.6rem; }
  .row-card { display: flex; justify-content: space-between; align-items: center;
              gap: 1rem; background: var(--surface); border: 1px solid var(--border);
              border-radius: 10px; padding: 0.9rem 1.1rem; flex-wrap: wrap; }
  .row-card.off { opacity: 0.6; }
  .r-main { flex: 1; min-width: 0; }
  .r-top { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.2rem; }
  .r-top b { font-size: 0.9rem; }
  .r-desc { font-size: 0.78rem; color: var(--muted); line-height: 1.5; margin-bottom: 0.2rem; }
  .tag { font-size: 0.63rem; font-weight: 800; text-transform: uppercase;
         letter-spacing: 0.04em; border: 1px solid var(--border); color: var(--muted);
         border-radius: 999px; padding: 0.08rem 0.42rem; }
  .tag.auto { color: var(--success); border-color: var(--success); }
  .tag.live { color: var(--accent); border-color: var(--accent); }
  .tag.pin { color: #e0a852; border-color: #e0a852; }
  .tag.off-tag { color: #e05260; border-color: #e05260; }
  .r-actions { display: flex; gap: 0.4rem; flex-shrink: 0; flex-wrap: wrap; }
  .muted { color: var(--muted); }
  .tiny { font-size: 0.71rem; }

  .btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 7px; padding: 0.5rem 1rem; font-size: 0.82rem; font-weight: 700;
         cursor: pointer; font-family: inherit; }
  .btn:hover:not(:disabled) { border-color: var(--accent); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn.small { padding: 0.32rem 0.7rem; font-size: 0.74rem; }
  .btn.small.danger { color: #e05260; }
  .btn.small.danger:hover:not(:disabled) { border-color: #e05260; }

  .skeleton { border-radius: 12px; background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
              background-size: 200% 100%; animation: shimmer 1.4s infinite; }
  .skeleton.big { height: 340px; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

  @media (max-width: 720px) {
    .kpis { grid-template-columns: repeat(2, 1fr); }
    .row { grid-template-columns: 1fr; }
  }
</style>
