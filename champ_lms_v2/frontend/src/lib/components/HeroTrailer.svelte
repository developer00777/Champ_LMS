<script lang="ts">
  import type { Module } from '$lib/api/client';
  export let module: Module | null = null;
</script>

{#if module}
  <div
    class="hero"
    style="background-image: linear-gradient(to right, var(--bg) 30%, transparent 70%),
           url({module.thumbnail_url ?? ''});"
  >
    <div class="hero-content">
      {#if module.category}
        <span class="badge badge-category">{module.category}</span>
      {/if}
      <h1>{module.title}</h1>
      {#if module.description}
        <p class="desc">{module.description}</p>
      {/if}
      <div class="hero-actions">
        <a href="/module/{module.id}" class="btn-primary">▶ Play</a>
        <a href="/module/{module.id}" class="btn-ghost">More Info</a>
      </div>
    </div>
  </div>
{/if}

<style>
  .hero {
    width: 100%;
    min-height: 420px;
    background-size: cover;
    background-position: center right;
    display: flex;
    align-items: flex-end;
    margin-bottom: 2.5rem;
    border-radius: 12px;
    overflow: hidden;
  }
  .hero-content {
    padding: 3rem 2rem;
    max-width: 500px;
  }
  h1 {
    font-size: 2.2rem;
    font-weight: 800;
    line-height: 1.15;
    margin: 0.5rem 0;
    text-shadow: 0 2px 8px rgba(0,0,0,0.6);
  }
  .desc {
    color: var(--muted);
    font-size: 0.95rem;
    line-height: 1.5;
    margin-bottom: 1.2rem;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .hero-actions { display: flex; gap: 0.75rem; }
</style>
