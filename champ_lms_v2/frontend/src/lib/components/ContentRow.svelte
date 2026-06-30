<script lang="ts">
  import VideoCard from './VideoCard.svelte';
  import type { Module } from '$lib/api/client';

  export let title: string;
  export let modules: Module[];
  export let progressMap: Record<string, number> = {};

  let rowEl: HTMLElement;

  function scrollLeft() { rowEl?.scrollBy({ left: -700, behavior: 'smooth' }); }
  function scrollRight() { rowEl?.scrollBy({ left: 700, behavior: 'smooth' }); }
</script>

<section class="row">
  <div class="row-header">
    <h2 class="row-title">{title}</h2>
    <div class="scroll-btns">
      <button on:click={scrollLeft} aria-label="Scroll left">‹</button>
      <button on:click={scrollRight} aria-label="Scroll right">›</button>
    </div>
  </div>
  <div class="cards" bind:this={rowEl}>
    {#each modules as mod}
      <VideoCard module={mod} progress={progressMap[mod.id] ?? 0} />
    {/each}
  </div>
</section>

<style>
  .row { margin: 0 0 2.5rem; }
  .row-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 0.75rem;
  }
  .row-title {
    font-size: 1.1rem; font-weight: 700;
    color: var(--text);
  }
  .scroll-btns { display: flex; gap: 0.4rem; }
  .scroll-btns button {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    width: 2rem; height: 2rem;
    border-radius: 50%;
    font-size: 1.1rem;
    display: flex; align-items: center; justify-content: center;
    transition: background 0.15s;
  }
  .scroll-btns button:hover { background: var(--surface); }
  .cards {
    display: flex;
    gap: 0.75rem;
    overflow-x: auto;
    padding-bottom: 0.5rem;
    scrollbar-width: none;
  }
  .cards::-webkit-scrollbar { display: none; }
</style>
