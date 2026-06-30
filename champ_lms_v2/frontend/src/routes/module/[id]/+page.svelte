<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, type ModuleDetail } from '$lib/api/client';

  let module: ModuleDetail | null = null;
  let loading = true;
  let error = '';

  $: id = $page.params.id;

  onMount(async () => {
    try {
      module = await api.module(id);
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  });

  function formatDuration(secs: number | null) {
    if (!secs) return '';
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  }
</script>

<svelte:head>
  <title>{module?.title ?? 'Module'} — Champ LMS</title>
</svelte:head>

{#if loading}
  <div class="loading">Loading...</div>
{:else if error}
  <div class="error">{error}</div>
{:else if module}
  <div class="module-page">
    <div class="hero-thumb" style="background-image: url({module.thumbnail_url ?? ''})">
      <div class="hero-overlay">
        <div class="hero-info">
          {#if module.category}
            <span class="badge badge-category">{module.category}</span>
          {/if}
          <h1>{module.title}</h1>
          {#if module.description}
            <p class="desc">{module.description}</p>
          {/if}
          {#if module.tags?.length}
            <div class="tags">
              {#each module.tags as tag}
                <span class="tag">{tag}</span>
              {/each}
            </div>
          {/if}
          {#if module.episodes.length}
            <a href="/watch/{module.episodes[0].id}" class="btn-primary">▶ Play Episode 1</a>
          {/if}
        </div>
      </div>
    </div>

    <section class="episodes">
      <h2>Episodes <span class="count">{module.episodes.length}</span></h2>
      <div class="episode-list">
        {#each module.episodes as ep}
          <a href="/watch/{ep.id}" class="ep-card" class:disabled={ep.status !== 'ready'}>
            <div class="ep-thumb">
              {#if ep.thumbnail_url}
                <img src={ep.thumbnail_url} alt={ep.title} />
              {:else}
                <div class="ep-thumb-placeholder">{ep.sequence_order}</div>
              {/if}
              {#if ep.status === 'processing'}
                <span class="status-badge">Processing...</span>
              {/if}
            </div>
            <div class="ep-info">
              <span class="ep-num">Episode {ep.sequence_order}</span>
              <p class="ep-title">{ep.title}</p>
              {#if ep.description}
                <p class="ep-desc">{ep.description}</p>
              {/if}
            </div>
            {#if ep.duration_seconds}
              <span class="ep-dur">{formatDuration(ep.duration_seconds)}</span>
            {/if}
          </a>
        {/each}
      </div>
    </section>
  </div>
{/if}

<style>
  .loading, .error { text-align: center; padding: 4rem; color: var(--muted); }
  .error { color: var(--accent); }

  .hero-thumb {
    width: 100%; min-height: 360px;
    background-size: cover; background-position: center;
    border-radius: 12px; overflow: hidden;
    margin-bottom: 2rem;
  }
  .hero-overlay {
    min-height: 360px;
    background: linear-gradient(to right, var(--bg) 35%, transparent 70%);
    display: flex; align-items: flex-end;
    padding: 2.5rem;
  }
  .hero-info { max-width: 460px; }
  h1 { font-size: 2rem; font-weight: 800; margin: 0.4rem 0; }
  .desc { color: var(--muted); font-size: 0.95rem; line-height: 1.5; margin-bottom: 0.75rem; }
  .tags { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1rem; }
  .tag {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 4px; padding: 0.15rem 0.5rem;
    font-size: 0.75rem; color: var(--muted);
  }
  .episodes h2 { font-size: 1.2rem; margin-bottom: 1rem; }
  .count {
    background: var(--surface2); border-radius: 4px;
    padding: 0.1rem 0.4rem; font-size: 0.8rem; margin-left: 0.4rem;
  }
  .episode-list { display: flex; flex-direction: column; gap: 0.75rem; }
  .ep-card {
    display: flex; align-items: center; gap: 1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem;
    transition: background 0.15s, border-color 0.15s;
    cursor: pointer;
  }
  .ep-card:hover { background: var(--surface2); border-color: rgba(255,255,255,0.15); }
  .ep-card.disabled { opacity: 0.5; pointer-events: none; }
  .ep-thumb {
    width: 140px; flex-shrink: 0;
    aspect-ratio: 16/9;
    border-radius: 5px; overflow: hidden;
    background: var(--surface2);
    position: relative;
  }
  .ep-thumb img { width: 100%; height: 100%; object-fit: cover; }
  .ep-thumb-placeholder {
    width: 100%; height: 100%; display: flex;
    align-items: center; justify-content: center;
    font-size: 1.5rem; font-weight: 800; color: var(--muted);
  }
  .status-badge {
    position: absolute; bottom: 4px; left: 4px;
    background: rgba(0,0,0,0.8); font-size: 0.65rem;
    padding: 0.15rem 0.35rem; border-radius: 3px;
  }
  .ep-info { flex: 1; }
  .ep-num { font-size: 0.75rem; color: var(--muted); font-weight: 600; text-transform: uppercase; }
  .ep-title { font-weight: 600; margin: 0.2rem 0; }
  .ep-desc {
    font-size: 0.82rem; color: var(--muted);
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .ep-dur { font-size: 0.82rem; color: var(--muted); flex-shrink: 0; }
</style>
