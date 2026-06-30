<script lang="ts">
  import type { Module } from '$lib/api/client';
  export let module: Module;
  export let progress: number = 0; // 0-100

  // Bunny Optimizer: thumbnail served with WebP + resize via CDN URL params
  // The thumbnail_url already contains ?width=480&height=270&format=webp
  $: thumbSrc = module.thumbnail_url ?? '/placeholder-thumb.svg';
</script>

<a href="/module/{module.id}" class="card">
  <div class="thumb-wrap">
    <img src={thumbSrc} alt={module.title} class="thumb" loading="lazy" />
    {#if progress > 0}
      <div class="progress-bar" style="width:{progress}%"></div>
    {/if}
    {#if module.total_episodes > 1}
      <span class="ep-count">{module.total_episodes} episodes</span>
    {/if}
  </div>
  <div class="info">
    {#if module.category}
      <span class="badge badge-category">{module.category}</span>
    {/if}
    <p class="title">{module.title}</p>
  </div>
</a>

<style>
  .card {
    display: block;
    width: 220px;
    flex-shrink: 0;
    transition: transform 0.2s;
  }
  .card:hover { transform: scale(1.04); }

  .thumb-wrap {
    position: relative;
    aspect-ratio: 16/9;
    border-radius: 6px;
    overflow: hidden;
    background: var(--surface2);
  }
  .thumb { width: 100%; height: 100%; object-fit: cover; }

  .progress-bar {
    position: absolute; bottom: 0; left: 0;
    height: 3px;
    background: var(--accent);
    border-radius: 0 2px 0 0;
    transition: width 0.3s;
  }
  .ep-count {
    position: absolute; bottom: 6px; right: 6px;
    background: rgba(0,0,0,0.75);
    font-size: 0.65rem;
    padding: 0.15rem 0.4rem;
    border-radius: 3px;
    font-weight: 600;
  }
  .info { padding: 0.5rem 0 0; }
  .title {
    font-size: 0.85rem;
    font-weight: 500;
    margin-top: 0.25rem;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .badge { font-size: 0.6rem; }
</style>
