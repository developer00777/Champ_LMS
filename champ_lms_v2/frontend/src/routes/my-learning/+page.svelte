<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type ProgressEntry, type RequiredModule, type StreakData } from '$lib/api/client';
  import { auth } from '$lib/stores/auth';

  let progress: ProgressEntry[] = [];
  let streak: StreakData | null = null;
  // Modules an admin marked mandatory for this learner (their team, or them
  // specifically). Failing to load these must not break the page.
  let required: RequiredModule[] = [];
  let loading = true;

  onMount(async () => {
    try {
      [progress, streak, required] = await Promise.all([
        api.myProgress(),
        api.myStreak(),
        api.requiredModules().catch(() => [] as RequiredModule[]),
      ]);
    } finally {
      loading = false;
    }
  });

  $: completedCount = progress.filter(p => p.completed).length;
  $: inProgressCount = progress.filter(p => !p.completed && p.watched_seconds > 0).length;
</script>

<svelte:head><title>My Learning — Champ LMS</title></svelte:head>

<div class="page">
  <h1>My Learning</h1>

  {#if streak}
    <div class="stats-row">
      <div class="stat">
        <div class="stat-val">{streak.points}</div>
        <div class="stat-label">Total Points</div>
      </div>
      <div class="stat">
        <div class="stat-val">🔥 {streak.streak_days}</div>
        <div class="stat-label">Day Streak</div>
      </div>
      <div class="stat">
        <div class="stat-val">{completedCount}</div>
        <div class="stat-label">Completed</div>
      </div>
      <div class="stat">
        <div class="stat-val">{inProgressCount}</div>
        <div class="stat-label">In Progress</div>
      </div>
    </div>
  {/if}

  {#if !loading && required.length > 0}
    <section class="required">
      <h2>Required for you</h2>
      <p class="required-note">
        Assigned by your administrator — {required.length} module{required.length === 1 ? '' : 's'}.
      </p>
      <div class="required-list">
        {#each required as m (m.id)}
          <a class="required-item" href={`/module/${m.id}`}>
            <div class="required-title">{m.title}</div>
            {#if m.category}<div class="required-meta">{m.category}</div>{/if}
            <div class="required-meta">{m.total_episodes} episode{m.total_episodes === 1 ? '' : 's'}</div>
          </a>
        {/each}
      </div>
    </section>
  {/if}

  {#if loading}
    <div class="loading">Loading...</div>
  {:else if progress.length === 0}
    <div class="empty">
      <p>You haven't watched anything yet.</p>
      <a href="/" class="btn-primary">Start Learning</a>
    </div>
  {:else}
    <section>
      <h2>Watch History</h2>
      <div class="progress-list">
        {#each progress as p}
          <div class="progress-item">
            <div class="progress-ep">
              <span class="ep-id">Episode</span>
              <a href="/watch/{p.episode_id}" class="ep-link">Resume</a>
            </div>
            <div class="progress-bar-wrap">
              <div
                class="progress-bar-fill"
                style="width:{p.total_seconds ? Math.round(p.watched_seconds / p.total_seconds * 100) : 0}%"
                class:completed={p.completed}
              ></div>
            </div>
            <div class="meta">
              {#if p.completed}
                <span class="badge-done">✓ Complete</span>
              {:else}
                <span>{Math.round(p.watched_seconds / 60)}m watched</span>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    </section>
  {/if}
</div>

<style>
  .page { max-width: 800px; margin: 0 auto; }
  h1 { font-size: 1.8rem; font-weight: 800; margin-bottom: 1.5rem; }
  h2 { font-size: 1.1rem; font-weight: 700; margin: 2rem 0 1rem; }
  .stats-row {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem;
    margin-bottom: 2rem;
  }
  .stat {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.25rem; text-align: center;
  }
  .stat-val { font-size: 1.8rem; font-weight: 800; color: var(--gold); }
  .stat-label { font-size: 0.78rem; color: var(--muted); margin-top: 0.25rem; }
  .loading, .empty { text-align: center; padding: 3rem; color: var(--muted); }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 1rem; }
  .progress-list { display: flex; flex-direction: column; gap: 0.75rem; }
  .progress-item {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.85rem 1rem;
  }
  .progress-ep { display: flex; justify-content: space-between; margin-bottom: 0.5rem; font-size: 0.85rem; }
  .ep-link { color: var(--accent); font-weight: 600; }
  .progress-bar-wrap {
    height: 4px; background: var(--surface2); border-radius: 2px; margin-bottom: 0.4rem;
  }
  .progress-bar-fill {
    height: 100%; background: var(--accent); border-radius: 2px; transition: width 0.3s;
  }
  .progress-bar-fill.completed { background: var(--success); }
  .meta { font-size: 0.78rem; color: var(--muted); }
  .badge-done { color: var(--success); font-weight: 700; }
  .required { margin-bottom: 2rem; }
  .required-note { color: var(--muted); font-size: 0.82rem; margin: 0 0 0.75rem; }
  .required-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.75rem; }
  .required-item {
    display: block; padding: 0.85rem 1rem; border-radius: 8px;
    background: var(--surface); text-decoration: none; color: var(--text);
    border: 1px solid color-mix(in srgb, orange 45%, transparent);
  }
  .required-item:hover { border-color: var(--accent); }
  .required-title { font-weight: 600; margin-bottom: 0.25rem; }
  .required-meta { color: var(--muted); font-size: 0.75rem; }
</style>
