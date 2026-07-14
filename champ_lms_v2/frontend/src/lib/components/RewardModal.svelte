<script lang="ts">
  import { rewardQueue, hasLevelUp } from '$lib/stores/gamification';
  import { onDestroy } from 'svelte';
  import { fade, scale } from 'svelte/transition';

  $: current = $rewardQueue[0] ?? null;
  $: show = Boolean(current || $hasLevelUp);

  let confetti: boolean[] = [];
  $: if ($hasLevelUp) {
    confetti = Array.from({ length: 24 });
  } else {
    confetti = [];
  }

  function dismiss() {
    rewardQueue.shift();
  }

  function closeOnKey(e: KeyboardEvent) {
    if (e.key === 'Escape') dismiss();
  }

  onDestroy(() => {
    rewardQueue.clear();
  });
</script>

{#if show}
  <!-- svelte-ignore a11y-no-noninteractive-tabindex -->
  <div
    class="overlay"
    role="dialog"
    aria-modal="true"
    aria-labelledby="reward-title"
    tabindex="0"
    on:click|self={dismiss}
    on:keydown={closeOnKey}
    transition:fade={{ duration: 180 }}
  >
    {#if confetti.length}
      <div class="confetti">
        {#each confetti as _, i}
          <span style="left: {Math.random() * 100}%; animation-delay: {Math.random() * 0.6}s" />
        {/each}
      </div>
    {/if}

    <div class="modal" transition:scale={{ duration: 220, start: 0.9 }}>
      {#if current?.level_up}
        <div class="level-up-banner">⭐ Level {current.new_level ?? '?'}!</div>
        <h2 id="reward-title">Level Up</h2>
        <p class="subtitle">You just reached a new level. Keep going!</p>
      {:else if current}
        <div class="icon">
          {#if current.badge}
            🏅
          {:else if current.module_completion || current.module_mastery}
            🏆
          {:else if current.first_to_complete}
            🥇
          {:else if current.perfect_quiz}
            💯
          {:else}
            ⚡
          {/if}
        </div>
        <h2 id="reward-title">Reward Earned</h2>
      {:else}
        <div class="icon">⭐</div>
        <h2 id="reward-title">Level Up</h2>
      {/if}

      {#if current}
        <ul class="rewards">
          {#if current.total_points}
            <li class="points"><span>⭐</span> +{current.total_points} points</li>
          {/if}
          {#if current.total_xp}
            <li class="xp"><span>✨</span> +{current.total_xp} XP</li>
          {/if}
          {#if current.badge}
            <li class="badge"><span>🏅</span> Badge: {current.badge.name}</li>
          {/if}
        </ul>
      {/if}

      <button class="btn-primary" on:click={dismiss}>Awesome</button>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.72);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 2rem 2.5rem;
    max-width: 420px;
    width: 90%;
    text-align: center;
    box-shadow: var(--shadow-lg);
  }
  .icon {
    font-size: 3.5rem;
    margin-bottom: 0.5rem;
  }
  .level-up-banner {
    background: linear-gradient(90deg, var(--gold), #ff8c00);
    color: #1a1200;
    font-weight: 900;
    padding: 0.5rem 1rem;
    border-radius: 999px;
    margin-bottom: 1rem;
    display: inline-block;
  }
  h2 {
    font-size: 1.5rem;
    font-weight: 800;
    margin-bottom: 0.25rem;
  }
  .subtitle {
    color: var(--muted);
    margin-bottom: 1.25rem;
  }
  .rewards {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    margin: 1.25rem 0;
  }
  .rewards li {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.65rem 0.9rem;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    font-weight: 700;
  }
  .points { color: var(--gold); }
  .xp { color: #c084fc; }
  .badge { color: var(--success); }
  .btn-primary {
    width: 100%;
    margin-top: 0.5rem;
  }
  .confetti {
    position: fixed;
    inset: 0;
    pointer-events: none;
    overflow: hidden;
    z-index: 1001;
  }
  .confetti span {
    position: absolute;
    top: -12px;
    width: 8px;
    height: 12px;
    background: var(--gold);
    animation: fall 1.4s ease-in forwards;
    border-radius: 2px;
  }
  @keyframes fall {
    to {
      transform: translateY(100vh) rotate(720deg);
      opacity: 0;
    }
  }
</style>
