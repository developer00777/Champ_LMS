<script lang="ts">
  import { page } from '$app/stores';
  import { onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, ApiError, type StreamUrlResponse, type AssessmentData, type Episode, type ModuleDetail, type TranscriptSegment } from '$lib/api/client';
  import VideoPlayer from '$lib/components/VideoPlayer.svelte';
  import QuizModal from '$lib/components/QuizModal.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';

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
  let captions: TranscriptSegment[] = [];

  $: if ($page.params.id !== loadedEpisodeId) loadEpisode($page.params.id);

  onDestroy(() => { if (retryTimer) clearTimeout(retryTimer); });

  async function loadEpisode(episodeId: string) {
    loadedEpisodeId = episodeId;
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
    loading = true; processing = false; error = ''; streamData = null; showQuiz = false;
    captions = [];
    // For the player's CC button; a video without a transcript just has none.
    api.episodeCaptions(episodeId).then(c => { if (loadedEpisodeId === episodeId) captions = c.segments; }).catch(() => {});
    retryDelayMs = 3000;
    await fetchStream(episodeId);
  }

  async function fetchStream(episodeId: string) {
    try {
      streamData = await api.streamUrl(episodeId);
      processing = false;
      // Course episodes can be a trimmed or split part of their video, which
      // only the course player keeps to.
      if (streamData.course_id) {
        goto(`/course/${streamData.course_id}?ref=${episodeId}`, { replaceState: true });
        return;
      }
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

  // The stream API knows nothing of the episode's module, so callers pass
  // ?module= and the breadcrumb names the course and episode from it.
  let crumbModule: ModuleDetail | null = null;
  let crumbFor = '';
  $: moduleId = $page.url.searchParams.get('module');
  $: if (moduleId && moduleId !== crumbFor) loadCrumb(moduleId);

  async function loadCrumb(id: string) {
    crumbFor = id; crumbModule = null;
    try {
      const m = await api.module(id);
      if (crumbFor === id) crumbModule = m;
    } catch { /* the trail just falls back to generic labels */ }
  }

  $: episodeTitle = crumbModule?.episodes.find((e) => e.id === loadedEpisodeId)?.title ?? null;
  $: crumbs = moduleId
    ? [
        { label: 'Home', href: '/' },
        { label: crumbModule?.title ?? 'Course', href: `/module/${moduleId}` },
        { label: episodeTitle ?? 'Video' },
      ]
    : [{ label: 'My Learning', href: '/my-learning' }, { label: 'Video' }];

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

<svelte:head><title>{episodeTitle ?? 'Watch'} — Champ LMS</title></svelte:head>

{#if loading}
  <div class="watch-page">
    <div class="ui-skeleton sk-player"></div>
    <div class="ui-skeleton" style="height:20px;width:40%;border-radius:8px;margin-top:1rem"></div>
  </div>
{:else if error}
  <div class="state ui-rise">
    <span class="state-ico danger"><Icon name="alert" size={28} /></span>
    <h2>This video can't play right now</h2>
    <p>{error}</p>
    <a href="/" class="btn-ghost"><Icon name="arrowLeft" size={16} /> Back to home</a>
  </div>
{:else if processing}
  <div class="state ui-rise">
    <span class="state-ico proc"><span class="spinner"></span><Icon name="film" size={24} /></span>
    <h2>Still processing</h2>
    <p>Video is still processing — this can take a few minutes for larger files.</p>
    <p class="hint"><span class="live-dot"></span> This page will update automatically once it's ready.</p>
  </div>
{:else if streamData}
  <div class="watch-page ui-rise">
    <Breadcrumbs items={crumbs} />
    <VideoPlayer
      episodeId={loadedEpisodeId}
      streamUrl={streamData.stream_url}
      embedUrl={streamData.embed_url}
      {captions}
      clipStart={streamData.clip_start ?? 0} clipEnd={streamData.clip_end ?? null}
      edits={streamData.edits ?? null}
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
  .watch-page { max-width: 1040px; margin: 0 auto; }
  .sk-player { aspect-ratio: 16 / 9; border-radius: 28px; }
  .state {
    max-width: 640px; margin: 2rem auto 0;
    display: flex; flex-direction: column; align-items: center; gap: 0.75rem; text-align: center;
    padding: 3rem 1.5rem; border-radius: 32px; background: var(--surface); box-shadow: var(--shadow-sm);
  }
  .state h2 { font-size: 1.35rem; }
  .state p { color: var(--muted); }
  .state .hint { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.83rem; margin-bottom: 0.25rem; }
  .state-ico {
    position: relative; width: 68px; height: 68px; border-radius: 50%; display: grid; place-items: center;
    animation: pop 520ms var(--ease-out);
  }
  .state-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }
  .state-ico.proc { background: var(--tile-sky); color: var(--tile-ink); }
  .spinner {
    position: absolute; inset: -5px; border-radius: 50%;
    border: 3px solid transparent; border-top-color: var(--accent);
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin { to { rotate: 360deg; } }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--brand); animation: pulse-ring 1.6s var(--ease-out) infinite; }
</style>
