<script lang="ts">
  import { page } from '$app/stores';
  import { onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, ApiError, type StreamUrlResponse, type AssessmentData, type Episode } from '$lib/api/client';
  import VideoPlayer from '$lib/components/VideoPlayer.svelte';
  import QuizModal from '$lib/components/QuizModal.svelte';

  let streamData: StreamUrlResponse | null = null;
  let assessment: AssessmentData | null = null;
  let moduleEpisodes: Episode[] = [];
  let currentEpIndex = 0;
  let showQuiz = false;
  let loading = true;
  let processing = false;
  let error = '';

  let retryTimer: ReturnType<typeof setTimeout> | null = null;
  let retryDelayMs = 3000;
  const MAX_RETRY_DELAY_MS = 15000;
  let loadedEpisodeId = '';

  $: if ($page.params.id !== loadedEpisodeId) loadEpisode($page.params.id);

  onDestroy(() => { if (retryTimer) clearTimeout(retryTimer); });

  async function loadEpisode(episodeId: string) {
    loadedEpisodeId = episodeId;
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
    loading = true; processing = false; error = ''; streamData = null; showQuiz = false;
    retryDelayMs = 3000;
    await fetchStream(episodeId);
  }

  async function fetchStream(episodeId: string) {
    try {
      streamData = await api.streamUrl(episodeId);
      processing = false;
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 425) {
        processing = true;
        retryTimer = setTimeout(() => fetchStream(episodeId), retryDelayMs);
        retryDelayMs = Math.min(retryDelayMs * 1.5, MAX_RETRY_DELAY_MS);
      } else {
        error = e.message;
      }
    } finally {
      loading = false;
    }
  }

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
{:else if processing}
  <div class="processing">
    <div class="spinner"></div>
    <p>Video is still processing — this can take a few minutes for larger files.</p>
    <p class="hint">This page will update automatically once it's ready.</p>
  </div>
{:else if streamData}
  <div class="watch-page">
    <VideoPlayer
      episodeId={loadedEpisodeId}
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
  .loading, .error, .processing { text-align: center; padding: 4rem; color: var(--muted); }
  .error { color: var(--accent); display: flex; flex-direction: column; align-items: center; gap: 1rem; }
  .processing { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; }
  .processing .hint { font-size: 0.83rem; opacity: 0.75; }
  .spinner {
    width: 2.25rem; height: 2.25rem; border-radius: 50%;
    border: 3px solid var(--border); border-top-color: var(--accent);
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .watch-page { max-width: 960px; margin: 0 auto; }
</style>
