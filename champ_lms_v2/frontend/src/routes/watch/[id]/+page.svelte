<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, type StreamUrlResponse, type AssessmentData, type Episode } from '$lib/api/client';
  import VideoPlayer from '$lib/components/VideoPlayer.svelte';
  import QuizModal from '$lib/components/QuizModal.svelte';

  let streamData: StreamUrlResponse | null = null;
  let assessment: AssessmentData | null = null;
  let moduleEpisodes: Episode[] = [];
  let currentEpIndex = 0;
  let showQuiz = false;
  let loading = true;
  let error = '';

  $: episodeId = $page.params.id;

  onMount(() => loadEpisode());

  async function loadEpisode() {
    loading = true; error = ''; streamData = null; showQuiz = false;
    try {
      streamData = await api.streamUrl(episodeId);
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  $: if (episodeId) loadEpisode();

  function onEpisodeComplete() {
    if (assessment) { showQuiz = true; }
  }

  function onAutoAdvance() {
    if (moduleEpisodes.length && currentEpIndex < moduleEpisodes.length - 1) {
      const next = moduleEpisodes[currentEpIndex + 1];
      goto(`/watch/${next.id}`);
    }
  }
</script>

<svelte:head><title>Watch — Champ LMS</title></svelte:head>

{#if loading}
  <div class="loading">Loading video...</div>
{:else if error}
  <div class="error">
    <p>{error}</p>
    <a href="/" class="btn-ghost">Back to Home</a>
  </div>
{:else if streamData}
  <div class="watch-page">
    <VideoPlayer
      {episodeId}
      streamUrl={streamData.stream_url}
      embedUrl={streamData.embed_url}
      onComplete={onEpisodeComplete}
      onAutoAdvance={onAutoAdvance}
    />
  </div>
{/if}

{#if showQuiz && assessment}
  <QuizModal
    assessmentId={assessment.id}
    questions={assessment.questions}
    on:close={() => { showQuiz = false; }}
    on:passed={() => { showQuiz = false; }}
  />
{/if}

<style>
  .loading, .error { text-align: center; padding: 4rem; color: var(--muted); }
  .error { color: var(--accent); display: flex; flex-direction: column; align-items: center; gap: 1rem; }
  .watch-page { max-width: 960px; margin: 0 auto; }
</style>
