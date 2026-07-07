<script lang="ts">
  import VideoCard from './VideoCard.svelte';
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

  function scrollLeft() { 
    rowEl?.scrollBy({ left: -800, behavior: 'smooth' }); 
    setTimeout(updateScrollButtons, 300);
  }
  
  function scrollRight() { 
    rowEl?.scrollBy({ left: 800, behavior: 'smooth' }); 
    setTimeout(updateScrollButtons, 300);
  }
</script>

<section class="row">
  <div class="row-header">
    <h2 class="row-title">{title}</h2>
    <div class="scroll-btns">
      <button 
        on:click={scrollLeft} 
        aria-label="Scroll left"
        class:disabled={!canScrollLeft}
      >‹</button>
      <button 
        on:click={scrollRight} 
        aria-label="Scroll right"
        class:disabled={!canScrollRight}
      >›</button>
    </div>
  </div>
  <div class="cards-wrapper">
    <div class="cards" bind:this={rowEl} on:scroll={updateScrollButtons}>
      {#each modules as mod}
        <VideoCard module={mod} progress={progressMap[mod.id] ?? 0} />
      {/each}
    </div>
  </div>
</section>

<style>
  .row { 
    margin: 0 0 3rem;
  }
  
  .row-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
    padding: 0 0.2rem;
  }
  
  .row-title {
    font-size: 1.25rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.01em;
  }
  
  .scroll-btns { 
    display: flex; 
    gap: 0.5rem; 
  }
  
  .scroll-btns button {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 50%;
    font-size: 1.3rem;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    cursor: pointer;
  }
  
  .scroll-btns button:hover:not(.disabled) { 
    background: var(--surface2);
    border-color: var(--muted);
    transform: scale(1.05);
  }
  
  .scroll-btns button.disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }
  
  .cards-wrapper {
    position: relative;
    margin: 0 -2rem;
    padding: 0 2rem;
  }
  
  .cards {
    display: flex;
    gap: 1rem;
    overflow-x: auto;
    padding: 0.5rem 0.2rem 1rem;
    scrollbar-width: none;
    scroll-snap-type: x mandatory;
  }
  
  .cards::-webkit-scrollbar { 
    display: none; 
  }
  
  .cards > :global(*) {
    scroll-snap-align: start;
  }
  
  @media (max-width: 768px) {
    .row-title {
      font-size: 1.1rem;
    }
    
    .cards-wrapper {
      margin: 0 -1rem;
      padding: 0 1rem;
    }
  }
</style>
