<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type AnalyticsData } from '$lib/api/client';

  let analytics: AnalyticsData | null = null;
  let loading = true;

  onMount(async () => {
    try { analytics = await api.analytics(); }
    finally { loading = false; }
  });
</script>

<svelte:head><title>Admin Dashboard — Champ LMS</title></svelte:head>

<div class="page">
  <h1>Admin Dashboard</h1>

  {#if loading}
    <div class="loading">Loading...</div>
  {:else if analytics}
    <div class="stats-grid">
      <div class="stat-card">
        <div class="num">{analytics.total_users}</div>
        <div class="lbl">Total Users</div>
      </div>
      <div class="stat-card">
        <div class="num">{analytics.published_modules}</div>
        <div class="lbl">Published Modules</div>
      </div>
      <div class="stat-card">
        <div class="num">{analytics.episode_completions}</div>
        <div class="lbl">Episode Completions</div>
      </div>
      <div class="stat-card">
        <div class="num">{analytics.total_enrollments}</div>
        <div class="lbl">Total Enrollments</div>
      </div>
    </div>
  {/if}

  <div class="quick-links">
    <a href="/admin/upload" class="link-card">
      <div class="icon">📤</div>
      <h3>Upload Video</h3>
      <p>Upload to Bunny Stream — auto-transcodes to HLS</p>
    </a>
    <a href="/admin/zoom" class="link-card">
      <div class="icon">🎥</div>
      <h3>Zoom → Module Builder</h3>
      <p>Convert Zoom recordings into AI-structured modules</p>
    </a>
    <a href="/leaderboard" class="link-card">
      <div class="icon">🏆</div>
      <h3>Leaderboard</h3>
      <p>View rankings and gamification data</p>
    </a>
  </div>
</div>

<style>
  .page { max-width: 960px; margin: 0 auto; }
  h1 { font-size: 1.8rem; font-weight: 800; margin-bottom: 2rem; }
  .stats-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2.5rem;
  }
  .stat-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.5rem; text-align: center;
  }
  .num { font-size: 2.2rem; font-weight: 800; color: var(--gold); }
  .lbl { font-size: 0.8rem; color: var(--muted); margin-top: 0.25rem; }
  .quick-links { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }
  .link-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.5rem;
    transition: border-color 0.15s, transform 0.15s;
  }
  .link-card:hover { border-color: var(--accent); transform: translateY(-2px); }
  .icon { font-size: 2rem; margin-bottom: 0.75rem; }
  h3 { font-size: 1rem; font-weight: 700; margin-bottom: 0.4rem; }
  p { font-size: 0.83rem; color: var(--muted); line-height: 1.4; }
  .loading { color: var(--muted); padding: 3rem; text-align: center; }
</style>
