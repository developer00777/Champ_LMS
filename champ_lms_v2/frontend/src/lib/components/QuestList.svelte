<script lang="ts">
  import type { Quest } from '$lib/api/client';

  export let quests: Quest[] = [];
  export let title = 'Quests';
  export let maxShown = 3;

  $: visible = quests.slice(0, maxShown);

  const scopeEmoji: Record<string, string> = {
    daily: '📅',
    weekly: '🗓️',
    monthly: '📆',
  };
</script>

{#if visible.length}
  <section class="quests">
    <h3>{title}</h3>
    <div class="list">
      {#each visible as q}
        {@const pct = q.target > 0 ? Math.min(100, (q.progress / q.target) * 100) : 0}
        <div class="quest" class:completed={q.completed}>
          <div class="row">
            <span class="scope">{scopeEmoji[q.scope] ?? '🎯'}</span>
            <div class="info">
              <p class="name">{q.title}</p>
              <p class="meta">{q.progress}/{q.target} · +{q.points_reward} pts / +{q.xp_reward} XP</p>
            </div>
          </div>
          <div class="bar">
            <div class="fill" style="width: {pct}%" />
          </div>
        </div>
      {/each}
    </div>
  </section>
{/if}

<style>
  .quests {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1.25rem;
  }
  h3 {
    font-size: 0.95rem;
    color: var(--muted);
    margin-bottom: 1rem;
  }
  .list {
    display: flex;
    flex-direction: column;
    gap: 0.85rem;
  }
  .quest {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }
  .scope {
    font-size: 1.1rem;
  }
  .info {
    flex: 1;
  }
  .name {
    font-size: 0.92rem;
    font-weight: 600;
  }
  .meta {
    font-size: 0.75rem;
    color: var(--muted);
  }
  .bar {
    height: 5px;
    background: var(--surface2);
    border-radius: 999px;
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--gold);
    border-radius: 999px;
    transition: width 0.4s ease;
  }
  .completed .fill {
    background: var(--success);
  }
  .completed .name {
    text-decoration: line-through;
    color: var(--muted);
  }
</style>
