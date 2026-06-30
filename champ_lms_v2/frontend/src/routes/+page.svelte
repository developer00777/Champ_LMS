<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type FeedRow, type ProgressEntry } from '$lib/api/client';
  import ContentRow from '$lib/components/ContentRow.svelte';
  import HeroTrailer from '$lib/components/HeroTrailer.svelte';

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
  <div class="loading">Loading your feed...</div>
{:else if error}
  <div class="error">{error}</div>
{:else}
  <HeroTrailer module={heroModule} />

  {#each rows as row}
    <ContentRow
      title={row.row_title}
      modules={row.modules}
      {progressMap}
    />
  {/each}

  {#if rows.length === 0}
    <div class="empty">
      <p>No content yet.</p>
      <a href="/admin/upload" class="btn-primary">Upload First Video</a>
    </div>
  {/if}
{/if}

<style>
  .loading, .error, .empty {
    text-align: center; padding: 4rem; color: var(--muted);
  }
  .error { color: var(--accent); }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 1.5rem; }
</style>
