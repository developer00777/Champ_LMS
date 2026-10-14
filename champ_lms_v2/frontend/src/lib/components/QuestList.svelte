<script lang="ts">
  /** Quests as the reference's pastel "event" cards: one colour per scope. */
  import type { Quest } from '$lib/api/client';
  import Icon from './Icon.svelte';
  import { reveal } from '$lib/actions/motion';

  export let quests: Quest[] = [];
  export let maxShown = 4;

  $: visible = quests.slice(0, maxShown);

  const SCOPE: Record<string, { label: string; tone: string; icon: string }> = {
    daily: { label: 'Daily quest', tone: 'sky', icon: 'zap' },
    weekly: { label: 'Weekly quest', tone: 'lilac', icon: 'calendar' },
    monthly: { label: 'Monthly quest', tone: 'butter', icon: 'target' },
  };
</script>

{#if visible.length}
  <div class="list">
    {#each visible as q, i (q.quest_id)}
      {@const s = SCOPE[q.scope] ?? SCOPE.daily}
      {@const pct = q.target > 0 ? Math.min(100, (q.progress / q.target) * 100) : 0}
      <article class="quest {s.tone}" class:completed={q.completed} use:reveal={{ delay: i * 80 }}>
        <header>
          <span class="kind"><Icon name={s.icon} size={17} /> {s.label}</span>
          {#if q.reward_points || q.reward_xp}
            <span class="reward">
              {#if q.reward_points}+{q.reward_points} pts{/if}{#if q.reward_points && q.reward_xp} · {/if}{#if q.reward_xp}+{q.reward_xp} XP{/if}
            </span>
          {/if}
        </header>
        <div class="inner">
          <p class="name">{q.title}</p>
          {#if q.description}<p class="desc">{q.description}</p>{/if}
        </div>
        <footer>
          {#if q.completed}
            <span class="done"><Icon name="check" size={16} /> Completed</span>
          {:else}
            <span class="bar" aria-hidden="true"><span style="--p:{pct}%"></span></span>
            <span class="count">{q.progress}/{q.target}</span>
          {/if}
        </footer>
      </article>
    {/each}
  </div>
{:else}
  <div class="empty">
    <Icon name="target" size={22} />
    <p>No quests right now. New ones arrive daily.</p>
  </div>
{/if}

<style>
  /* One row height for every quest card. */
  .list { display: grid; grid-auto-rows: 1fr; gap: 0.75rem; }
  .quest {
    display: flex; flex-direction: column;
    border-radius: 26px; padding: 0.9rem 0.9rem 0.8rem;
    color: var(--tile-ink);
    transition: transform var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out), rotate var(--dur-3) var(--ease-out);
  }
  .quest:hover { transform: translateY(-3px); rotate: -0.6deg; box-shadow: var(--shadow); }
  .sky { background: var(--tile-sky); }
  .lilac { background: var(--tile-lilac); }
  .butter { background: var(--tile-butter); }

  header { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; padding: 0.15rem 0.35rem 0.55rem; }
  .kind { display: inline-flex; align-items: center; gap: 0.45rem; font-weight: 600; font-size: 0.9rem; white-space: nowrap; }
  .quest:hover .kind :global(.icon) { animation: pop 420ms var(--ease-out); }
  .reward { font-size: 0.78rem; opacity: 0.7; white-space: nowrap; }

  .inner { flex: 1; background: var(--tile-inner); border-radius: 18px; padding: 0.65rem 0.9rem; }
  .name {
    font-size: 0.95rem; font-weight: 500; line-height: 1.4;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .desc {
    font-size: 0.82rem; opacity: 0.72; margin-top: 0.25rem; line-height: 1.45;
    display: -webkit-box; -webkit-line-clamp: 1; line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden;
  }
  .completed .name { text-decoration: line-through; text-decoration-thickness: 1.5px; opacity: 0.7; }

  footer { display: flex; align-items: center; gap: 0.7rem; min-height: 2.2rem; padding: 0.5rem 0.35rem 0; }
  .bar { flex: 1; height: 6px; border-radius: 99px; background: color-mix(in srgb, var(--tile-ink) 12%, transparent); overflow: hidden; }
  .bar span {
    display: block; height: 100%; width: var(--p); border-radius: inherit; background: var(--tile-ink);
    transform-origin: left; animation: grow 1s var(--ease-out) 300ms backwards;
  }
  @keyframes grow { from { transform: scaleX(0); } }
  .count { font-size: 0.8rem; font-weight: 700; font-variant-numeric: tabular-nums; }
  .done {
    display: inline-flex; align-items: center; gap: 0.4rem; margin: 0 auto;
    background: var(--surface); color: var(--text);
    padding: 0.35rem 0.9rem; border-radius: 99px; font-size: 0.82rem; font-weight: 600;
  }
  .done :global(.icon) { animation: pop 500ms var(--ease-out); }

  .empty {
    display: flex; flex-direction: column; align-items: center; gap: 0.5rem; text-align: center;
    padding: 1.75rem 1rem; border: 2px dashed var(--surface3); border-radius: 24px; color: var(--muted); font-size: 0.88rem;
  }
</style>
