<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type FeedRow, type ProgressEntry } from '$lib/api/client';
  import { gamification } from '$lib/stores/gamification';
  import ContentRow from '$lib/components/ContentRow.svelte';
  import HeroTrailer from '$lib/components/HeroTrailer.svelte';
  import UpskillingTrack from '$lib/components/UpskillingTrack.svelte';
  import QuestList from '$lib/components/QuestList.svelte';

  let rows: FeedRow[] = [];
  let progressMap: Record<string, number> = {};
  let loading = true;
  let error = '';

  onMount(async () => {
    try {
      const [feedData, progressData] = await Promise.all([
        api.feed(),
        api.myProgress().catch(() => [] as ProgressEntry[]),
      ]);
      rows = feedData;

      // Build progress % per module from episode progress
      for (const p of progressData) {
        if (p.total_seconds > 0) {
          progressMap[p.episode_id] = Math.round(p.watched_seconds / p.total_seconds * 100);
        }
      }
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  });

  $: heroModule = rows[0]?.modules?.[0] ?? null;
</script>

<svelte:head><title>Champ LMS — Home</title></svelte:head>

{#if loading}
  <!-- Skeleton loading state -->
  <div class="hero-skeleton">
    <div class="skeleton-content">
      <div class="skeleton-badge"></div>
      <div class="skeleton-title"></div>
      <div class="skeleton-desc"></div>
      <div class="skeleton-buttons">
        <div class="skeleton-btn"></div>
        <div class="skeleton-btn ghost"></div>
      </div>
    </div>
  </div>
  
  {#each [1, 2, 3] as _}
    <div class="row-skeleton">
      <div class="skeleton-row-title"></div>
      <div class="skeleton-cards">
        {#each [1, 2, 3, 4, 5] as __}
          <div class="skeleton-card">
            <div class="skeleton-thumb"></div>
            <div class="skeleton-text"></div>
          </div>
        {/each}
      </div>
    </div>
  {/each}
{:else if error}
  <div class="error-state">
    <div class="error-icon">⚠️</div>
    <h2>Something went wrong</h2>
    <p>{error}</p>
    <button class="btn-primary" on:click={() => window.location.reload()}>Retry</button>
  </div>
{:else}
  <div class="home-grid">
    <div class="home-main">
      <HeroTrailer module={heroModule} />
      {#each rows as row}
        <ContentRow
          title={row.row_title}
          modules={row.modules}
          {progressMap}
        />
      {/each}
    </div>
    <aside class="home-sidebar">
      <UpskillingTrack track={$gamification.upselling} />
      <QuestList quests={$gamification.quests} title="Quests" />
    </aside>
  </div>

  {#if rows.length === 0}
    <div class="empty-state">
      <div class="empty-icon">🎬</div>
      <h2>No content yet</h2>
      <p>Upload your first video to get started.</p>
      <a href="/admin/upload" class="btn-primary">Upload First Video</a>
    </div>
  {/if}
{/if}

<style>
  /* Skeleton loading animations */
  @keyframes shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }
  
  .hero-skeleton {
    width: 100%;
    min-height: 450px;
    border-radius: 16px;
    background: var(--surface);
    margin-bottom: 3rem;
    display: flex;
    align-items: flex-end;
    overflow: hidden;
  }
  
  .skeleton-content {
    padding: 3rem 2.5rem;
    width: 100%;
    max-width: 600px;
  }
  
  .skeleton-badge {
    width: 80px;
    height: 20px;
    background: linear-gradient(90deg, var(--surface2) 25%, var(--surface) 50%, var(--surface2) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
    margin-bottom: 1rem;
  }

  .skeleton-title {
    width: 70%;
    height: 40px;
    background: linear-gradient(90deg, var(--surface2) 25%, var(--surface) 50%, var(--surface2) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
    margin-bottom: 1rem;
  }

  .skeleton-desc {
    width: 90%;
    height: 60px;
    background: linear-gradient(90deg, var(--surface2) 25%, var(--surface) 50%, var(--surface2) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
    margin-bottom: 1.5rem;
  }

  .skeleton-buttons {
    display: flex;
    gap: 1rem;
  }

  .skeleton-btn {
    width: 120px;
    height: 40px;
    background: linear-gradient(90deg, var(--surface2) 25%, var(--surface) 50%, var(--surface2) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 8px;
  }

  .skeleton-btn.ghost {
    width: 100px;
    opacity: 0.5;
  }

  .row-skeleton {
    margin-bottom: 2.5rem;
  }

  .skeleton-row-title {
    width: 200px;
    height: 24px;
    background: linear-gradient(90deg, var(--surface2) 25%, var(--surface) 50%, var(--surface2) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
    margin-bottom: 0.75rem;
  }

  .skeleton-cards {
    display: flex;
    gap: 0.75rem;
    overflow: hidden;
  }

  .skeleton-card {
    width: 240px;
    flex-shrink: 0;
  }

  .skeleton-thumb {
    aspect-ratio: 16/9;
    background: linear-gradient(90deg, var(--surface2) 25%, var(--surface) 50%, var(--surface2) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 8px;
    margin-bottom: 0.5rem;
  }

  .skeleton-text {
    width: 80%;
    height: 16px;
    background: linear-gradient(90deg, var(--surface2) 25%, var(--surface) 50%, var(--surface2) 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: 4px;
  }
  
  /* Error state */
  .error-state {
    text-align: center;
    padding: 6rem 2rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
  }
  
  .error-icon {
    font-size: 3rem;
    margin-bottom: 0.5rem;
  }
  
  .error-state h2 {
    font-size: 1.5rem;
    font-weight: 700;
  }
  
  .error-state p {
    color: var(--muted);
    margin-bottom: 1rem;
  }
  
  /* Empty state */
  .empty-state {
    text-align: center;
    padding: 6rem 2rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
  }
  
  .empty-icon {
    font-size: 4rem;
    margin-bottom: 0.5rem;
  }
  
  .empty-state h2 {
    font-size: 1.5rem;
    font-weight: 700;
  }
  
  .empty-state p {
    color: var(--muted);
    margin-bottom: 1rem;
  }
  
  .home-grid {
    display: grid;
    grid-template-columns: 1fr 320px;
    gap: 2rem;
    align-items: start;
  }
  .home-main {
    min-width: 0;
  }
  .home-sidebar {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
    position: sticky;
    top: 80px;
  }

  @media (max-width: 1024px) {
    .home-grid {
      grid-template-columns: 1fr;
    }
    .home-sidebar {
      position: static;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }
    @media (max-width: 640px) {
      .home-sidebar {
        grid-template-columns: 1fr;
      }
    }
  }

  @media (max-width: 768px) {
    .hero-skeleton {
      min-height: 350px;
    }
    
    .skeleton-content {
      padding: 2rem 1.5rem;
    }
    
    .skeleton-card {
      width: 160px;
    }
  }
</style>
