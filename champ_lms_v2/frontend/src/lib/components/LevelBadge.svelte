<script lang="ts">
  export let level = 1;
  export let xp = 0;
  export let xpToNextLevel: number | undefined = undefined;
  export let compact = false;
  export let size = 40;

  $: nextXp = xpToNextLevel ?? 100;
  $: pct = nextXp > 0 ? Math.max(0, Math.min(100, (xp / nextXp) * 100)) : 100;
  $: radius = (size - 4) / 2;
  $: circumference = 2 * Math.PI * radius;
  $: dashoffset = circumference - (pct / 100) * circumference;
</script>

<div class="level-badge" class:compact style="--size:{size}px">
  <svg class="ring" width={size} height={size} viewBox="0 0 {size} {size}">
    <circle class="track" cx={size / 2} cy={size / 2} r={radius} />
    <circle
      class="progress"
      cx={size / 2}
      cy={size / 2}
      r={radius}
      style="stroke-dasharray: {circumference}; stroke-dashoffset: {dashoffset};"
    />
  </svg>
  <span class="level">{level}</span>
  {#if !compact && typeof xpToNextLevel === 'number'}
    <span class="label">{xp}/{nextXp} XP</span>
  {/if}
</div>

<style>
  .level-badge {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--size);
    height: var(--size);
  }
  .level-badge.compact {
    width: var(--size);
    height: var(--size);
  }
  .ring {
    position: absolute;
    inset: 0;
    transform: rotate(-90deg);
  }
  .track {
    fill: transparent;
    stroke: var(--surface2);
    stroke-width: 3;
  }
  .progress {
    fill: transparent;
    stroke: var(--gold);
    stroke-width: 3;
    stroke-linecap: round;
    transition: stroke-dashoffset 0.6s ease;
  }
  .level {
    position: relative;
    z-index: 1;
    font-size: calc(var(--size) * 0.4);
    font-weight: 800;
    color: var(--text);
  }
  .label {
    position: absolute;
    bottom: -1.1rem;
    left: 50%;
    transform: translateX(-50%);
    font-size: 0.65rem;
    white-space: nowrap;
    color: var(--muted);
  }
</style>
