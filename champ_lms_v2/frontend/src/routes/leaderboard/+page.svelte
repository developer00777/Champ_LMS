<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type LeaderboardEntry, type Badge } from '$lib/api/client';
  import { auth } from '$lib/stores/auth';

  let entries: LeaderboardEntry[] = [];
  let badges: Badge[] = [];
  let loading = true;
  let dept = '';

  onMount(async () => {
    await Promise.all([loadBoard(), loadBadges()]);
  });

  async function loadBoard() {
    loading = true;
    try {
      entries = await api.leaderboard(dept || undefined);
    } finally {
      loading = false;
    }
  }

  async function loadBadges() {
    try { badges = await api.myBadges(); } catch {}
  }

  const MEDALS = ['🥇', '🥈', '🥉'];
</script>

<svelte:head><title>Leaderboard — Champ LMS</title></svelte:head>

<div class="page">
  <div class="header">
    <h1>Leaderboard</h1>
    <div class="filter">
      <input bind:value={dept} placeholder="Filter by department..." on:input={() => loadBoard()} />
    </div>
  </div>

  {#if badges.length}
    <section class="badges-row">
      <h3>Your Badges</h3>
      <div class="badges">
        {#each badges as b}
          <div class="badge-card" title={b.description ?? b.name}>
            {#if b.icon_url}
              <img src={b.icon_url} alt={b.name} class="badge-icon" />
            {:else}
              <div class="badge-emoji">🏆</div>
            {/if}
            <span>{b.name}</span>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  {#if loading}
    <div class="loading">Loading...</div>
  {:else}
    <div class="board">
      {#each entries as entry, i}
        <div class="entry" class:me={entry.user_id === $auth.user?.id}>
          <span class="rank">{MEDALS[i] ?? `#${entry.rank}`}</span>
          <div class="user-info">
            <p class="name">{entry.full_name ?? 'Anonymous'}</p>
            {#if entry.department}
              <p class="dept">{entry.department}</p>
            {/if}
          </div>
          <div class="stats">
            <span class="pts">{entry.points} pts</span>
            <span class="streak">🔥 {entry.streak_days}</span>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { max-width: 700px; margin: 0 auto; }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2rem; }
  h1 { font-size: 1.8rem; font-weight: 800; }
  .filter input {
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text); border-radius: 6px; padding: 0.5rem 0.8rem; font-size: 0.85rem;
  }
  .badges-row { margin-bottom: 2rem; }
  h3 { font-size: 0.95rem; color: var(--muted); margin-bottom: 0.75rem; }
  .badges { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .badge-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.6rem 0.9rem;
    display: flex; align-items: center; gap: 0.4rem;
    font-size: 0.8rem;
  }
  .badge-icon, .badge-emoji { width: 24px; height: 24px; object-fit: contain; }
  .board { display: flex; flex-direction: column; gap: 0.5rem; }
  .entry {
    display: flex; align-items: center; gap: 1rem;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.85rem 1rem;
    transition: background 0.15s;
  }
  .entry.me { border-color: var(--accent); background: rgba(229,9,20,0.07); }
  .rank { font-size: 1.3rem; min-width: 2rem; text-align: center; }
  .user-info { flex: 1; }
  .name { font-weight: 600; }
  .dept { font-size: 0.78rem; color: var(--muted); }
  .stats { display: flex; align-items: center; gap: 1rem; }
  .pts { font-weight: 700; color: var(--gold); }
  .streak { font-size: 0.85rem; color: var(--muted); }
  .loading { text-align: center; padding: 3rem; color: var(--muted); }
</style>
