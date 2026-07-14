<script lang="ts">
  import type { UpskillingTrack } from '$lib/api/client';

  export let track: UpskillingTrack | null = null;

  const statusEmoji: Record<string, string> = {
    not_started: '⚪',
    in_progress: '🔵',
    completed: '🟢',
    mastered: '⭐',
  };
</script>

{#if track}
  <section class="track-card">
    <div class="header">
      <div>
        <p class="eyebrow">UpSkill Track</p>
        <h2>{track.track}</h2>
      </div>
      <span class="rank">#{track.rank_in_department} in {track.track}</span>
    </div>

    <div class="summary">
      <div class="metric">
        <span class="value">{track.mastered_modules}/{track.total_modules}</span>
        <span class="label">Mastered</span>
      </div>
      <div class="metric">
        <span class="value">{track.mastery_percentage}%</span>
        <span class="label">Mastery</span>
      </div>
    </div>

    <div class="progress-wrap">
      <div class="big-bar">
        <div class="big-fill" style="width: {track.mastery_percentage}%" />
      </div>
    </div>

    <ul class="modules">
      {#each track.modules as m}
        <li class="module-row">
          <span class="status">{statusEmoji[m.status] ?? '⚪'}</span>
          <span class="title">{m.title}</span>
          <div class="mini-bar">
            <div class="mini-fill" style="width: {m.progress}%" />
          </div>
        </li>
      {/each}
    </ul>
  </section>
{/if}

<style>
  .track-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1.5rem;
  }
  .header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 1.25rem;
  }
  .eyebrow {
    font-size: 0.75rem;
    color: var(--accent);
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.25rem;
  }
  h2 {
    font-size: 1.25rem;
    font-weight: 800;
    text-transform: capitalize;
  }
  .rank {
    background: var(--surface2);
    border: 1px solid var(--border);
    padding: 0.35rem 0.7rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--gold);
  }
  .summary {
    display: flex;
    gap: 2rem;
    margin-bottom: 0.75rem;
  }
  .metric {
    display: flex;
    flex-direction: column;
  }
  .value {
    font-size: 1.5rem;
    font-weight: 800;
  }
  .label {
    font-size: 0.75rem;
    color: var(--muted);
  }
  .progress-wrap {
    margin-bottom: 1.25rem;
  }
  .big-bar {
    height: 10px;
    background: var(--surface2);
    border-radius: 999px;
    overflow: hidden;
  }
  .big-fill {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent-hover));
    border-radius: 999px;
    transition: width 0.5s ease;
  }
  .modules {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .module-row {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
  }
  .module-row:last-child {
    border-bottom: none;
  }
  .status {
    font-size: 0.9rem;
  }
  .title {
    font-size: 0.88rem;
  }
  .mini-bar {
    width: 80px;
    height: 5px;
    background: var(--surface2);
    border-radius: 999px;
    overflow: hidden;
  }
  .mini-fill {
    height: 100%;
    background: var(--success);
    border-radius: 999px;
  }
</style>
