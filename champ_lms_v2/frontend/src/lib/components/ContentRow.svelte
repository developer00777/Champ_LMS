<script lang="ts">
  import VideoCard from './VideoCard.svelte';
  import Icon from './Icon.svelte';
  import { reveal } from '$lib/actions/motion';
  import type { Module } from '$lib/api/client';

  export let title: string;
  export let modules: Module[];
  export let progressMap: Record<string, number> = {};

  let rowEl: HTMLElement;
  let canScrollLeft = false;
  let canScrollRight = true;

  function updateScrollButtons() {
    if (!rowEl) return;
    canScrollLeft = rowEl.scrollLeft > 0;
    canScrollRight = rowEl.scrollLeft < (rowEl.scrollWidth - rowEl.clientWidth - 10);
  }

  function scrollByDir(dir: 1 | -1) {
    rowEl?.scrollBy({ left: dir * Math.max(300, rowEl.clientWidth * 0.8), behavior: 'smooth' });
    setTimeout(updateScrollButtons, 350);
  }
</script>

<section class="row" use:reveal>
  <div class="row-header">
    <h2 class="row-title">{title} <span class="count">{modules.length}</span></h2>
    <div class="scroll-btns">
      <button class="ui-round" on:click={() => scrollByDir(-1)} aria-label="Scroll left" disabled={!canScrollLeft}>
        <Icon name="chevronLeft" size={18} />
      </button>
      <button class="ui-round ink" on:click={() => scrollByDir(1)} aria-label="Scroll right" disabled={!canScrollRight}>
        <Icon name="chevronRight" size={18} />
      </button>
    </div>
  </div>
  <div class="cards" bind:this={rowEl} on:scroll={updateScrollButtons}>
    {#each modules as mod, i (mod.id)}
      <div class="slot ui-rise" style="--i:{Math.min(i, 8)}">
        <VideoCard module={mod} progress={progressMap[mod.id] ?? 0} />
      </div>
    {/each}
  </div>
</section>

<style>
  .row { margin: 0 0 2.75rem; }
  .row-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.9rem; }
  .row-title { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; display: flex; align-items: center; gap: 0.6rem; }
  .count {
    font-size: 0.75rem; font-weight: 700; padding: 0.15rem 0.55rem; border-radius: 99px;
    background: var(--surface2); color: var(--muted);
  }
  .scroll-btns { display: flex; gap: 0.45rem; }
  .scroll-btns button:disabled { opacity: 0.35; transform: none; }

  .cards {
    display: flex; align-items: stretch; gap: 1rem; overflow-x: auto;
    /* Room for the hover lift and shadow, which overflow would otherwise clip. */
    padding: 0.6rem 0.4rem 1.4rem; margin: -0.6rem -0.4rem -0.8rem;
    scrollbar-width: none; scroll-snap-type: x proximity;
  }
  .cards::-webkit-scrollbar { display: none; }
  /* Slots stretch to the tallest card so the whole row is one height. */
  .slot { scroll-snap-align: start; flex-shrink: 0; display: flex; }

  @media (max-width: 768px) {
    .row-title { font-size: 1.15rem; }
  }
</style>
