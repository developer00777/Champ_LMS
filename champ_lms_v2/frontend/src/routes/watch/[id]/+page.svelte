<script lang="ts">
  import { page } from '$app/stores';
  import { onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, ApiError, type StreamUrlResponse, type AssessmentData, type ModuleDetail, type ProgressEntry, type TranscriptSegment } from '$lib/api/client';
  import VideoPlayer from '$lib/components/VideoPlayer.svelte';
  import QuizModal from '$lib/components/QuizModal.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import Transcript from '$lib/components/course/Transcript.svelte';
  import WatchLayout from '$lib/components/watch/WatchLayout.svelte';
  import WatchTabs from '$lib/components/watch/WatchTabs.svelte';
  import WatchInfo from '$lib/components/watch/WatchInfo.svelte';
  import PlaylistItem from '$lib/components/watch/PlaylistItem.svelte';
  import StagePlaceholder from '$lib/components/watch/StagePlaceholder.svelte';
  import { clock, runtime } from '$lib/utils/transcribe';

  let streamData: StreamUrlResponse | null = null;
  let assessment: AssessmentData | null = null;
  let showQuiz = false;
  let processing = false;
  let error = '';
  let playerRef: VideoPlayer;
  let layoutRef: WatchLayout;
  let time = 0;
  let tab = 'transcript';

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
    processing = false; error = ''; streamData = null; showQuiz = false; time = 0;
    captions = [];
    // For the player's CC button and the Transcript tab; a video without a
    // transcript just has none.
    api.episodeCaptions(episodeId).then(c => { if (loadedEpisodeId === episodeId) captions = c.segments; }).catch(() => {});
    retryDelayMs = 3000;
    await fetchStream(episodeId);
  }

  async function fetchStream(episodeId: string) {
    try {
      const s = await api.streamUrl(episodeId);
      // The learner moved on to another episode while this was loading: a
      // late reply must not load (or redirect) the old one.
      if (episodeId !== loadedEpisodeId) return;
      streamData = s;
      processing = false;
      // Course episodes can be a trimmed or split part of their video, which
      // only the course player keeps to.
      if (streamData.course_id) {
        goto(`/course/${streamData.course_id}?ref=${episodeId}`, { replaceState: true });
        return;
      }
    } catch (e: any) {
      if (episodeId !== loadedEpisodeId) return;
      if (e instanceof ApiError && e.status === 425) {
        processing = true;
        retryTimer = setTimeout(() => fetchStream(episodeId), retryDelayMs);
        retryDelayMs = Math.min(retryDelayMs * 1.5, MAX_RETRY_DELAY_MS);
      } else {
        error = e.message;
      }
    }
  }

  // The stream API knows nothing of the episode's module, so callers pass
  // ?module= and the page loads the module for the title, breadcrumb and
  // episode list.
  let mod: ModuleDetail | null = null;
  let modFor = '';
  $: moduleId = $page.url.searchParams.get('module');
  $: if (moduleId && moduleId !== modFor) loadModule(moduleId);

  async function loadModule(id: string) {
    modFor = id; mod = null;
    try {
      const m = await api.module(id);
      if (modFor === id) mod = m;
    } catch { /* the page just falls back to generic labels */ }
  }

  // Watched/done marks for the episode list.
  // Reloaded when an episode finishes, so its tick appears straight away.
  let progress = new Map<string, ProgressEntry>();
  function loadProgress() {
    api.myProgress().then(list => {
      const m = new Map<string, ProgressEntry>();
      for (const p of list) if (!m.has(p.episode_id)) m.set(p.episode_id, p); // newest first
      progress = m;
    }).catch(() => { /* marks are optional */ });
  }
  loadProgress();

  $: episodes = mod ? [...mod.episodes].sort((a, b) => a.sequence_order - b.sequence_order) : [];
  $: idx = episodes.findIndex(e => e.id === loadedEpisodeId);
  $: episode = idx >= 0 ? episodes[idx] : null;
  $: prevEp = idx > 0 ? episodes[idx - 1] : null;
  $: nextEp = idx >= 0 && idx < episodes.length - 1 ? episodes[idx + 1] : null;
  $: doneCount = episodes.filter(e => progress.get(e.id)?.completed).length;
  $: totalSeconds = episodes.reduce((s, e) => s + (e.duration_seconds ?? 0), 0);

  $: crumbs = moduleId
    ? [
        { label: 'Home', href: '/' },
        { label: mod?.title ?? 'Course', href: `/module/${moduleId}` },
        { label: episode?.title ?? 'Video' },
      ]
    : [{ label: 'My Learning', href: '/my-learning' }, { label: 'Video' }];

  function open(id: string | undefined) {
    if (!id) return;
    goto(`/watch/${id}${moduleId ? `?module=${moduleId}` : ''}`);
  }

  function pct(id: string) {
    const p = progress.get(id);
    if (!p) return 0;
    if (p.completed) return 100;
    return p.total_seconds ? Math.round((p.watched_seconds / p.total_seconds) * 100) : 0;
  }

  function onEpisodeComplete() {
    loadProgress();
    if (assessment) { showQuiz = true; }
  }

  function onAutoAdvance() {
    if (nextEp && nextEp.status === 'ready') open(nextEp.id);
  }

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'transcript', label: 'Transcript' },
  ];
</script>

<svelte:head><title>{episode?.title ?? 'Watch'} — Champ LMS</title></svelte:head>

<Breadcrumbs items={crumbs} />

<WatchLayout bind:this={layoutRef}
  context={episode ? `Episode ${idx + 1} of ${episodes.length}` : ''}
  onPrev={mod ? () => open(prevEp?.id) : null}
  onNext={mod ? () => open(nextEp?.id) : null}
  prevDisabled={!prevEp || prevEp.status !== 'ready'}
  nextDisabled={!nextEp || nextEp.status !== 'ready'}
  side={!!mod}
  sideTitle={mod?.title ?? ''}
  sideProgress={episodes.length ? Math.round((doneCount / episodes.length) * 100) : null}
  sideMeta={episodes.length ? `${doneCount} of ${episodes.length} watched · ${runtime(totalSeconds)} of video` : ''}
>
  <svelte:fragment slot="stage">
    {#key loadedEpisodeId}
      {#if streamData && !streamData.course_id}
        <VideoPlayer
          bind:this={playerRef}
          episodeId={loadedEpisodeId}
          streamUrl={streamData.stream_url}
          embedUrl={streamData.embed_url}
          {captions}
          clipStart={streamData.clip_start ?? 0} clipEnd={streamData.clip_end ?? null}
          edits={streamData.edits ?? null}
          onFullscreen={() => layoutRef?.toggleTheater()}
          onTime={t => (time = t)}
          onComplete={onEpisodeComplete}
          onAutoAdvance={onAutoAdvance}
        />
      {:else if error}
        <StagePlaceholder busy={false} message="This video can't play right now" hint={error} />
      {:else if processing}
        <StagePlaceholder message="Still processing" hint="This can take a few minutes for larger files. The page updates on its own once it's ready." />
      {:else}
        <StagePlaceholder />
      {/if}
    {/key}
  </svelte:fragment>

  <WatchInfo
    title={episode?.title ?? 'Video'}
    eyebrow={episode ? `Episode ${idx + 1}${mod ? ` · ${mod.title}` : ''}` : ''}
    facts={episode?.duration_seconds ? [clock(episode.duration_seconds)] : []}
  />
  <WatchTabs {tabs} bind:active={tab} />
  {#if tab === 'transcript'}
    <Transcript segments={captions} {time} onSeek={t => playerRef?.seek(t)} />
  {:else}
    <div class="panel ui-panel">
      {#if episode?.description}<p>{episode.description}</p>{/if}
      {#if mod?.description}<p class="muted">{mod.description}</p>{/if}
      {#if !episode?.description && !mod?.description}<p class="muted">No description for this video yet.</p>{/if}
    </div>
  {/if}

  <svelte:fragment slot="side">
    {#each episodes as ep, i (ep.id)}
      <PlaylistItem
        title={ep.title}
        sub={ep.status === 'ready' ? `Episode ${i + 1}${progress.get(ep.id)?.completed ? ' · watched' : ''}` : 'Still processing'}
        thumb={ep.thumbnail_url}
        duration={ep.duration_seconds ? clock(ep.duration_seconds) : ''}
        current={ep.id === loadedEpisodeId}
        done={!!progress.get(ep.id)?.completed}
        progress={pct(ep.id)}
        locked={ep.status !== 'ready'}
        lockedHint="This video is still processing"
        on:click={() => ep.status === 'ready' && open(ep.id)}
      />
    {/each}
  </svelte:fragment>
</WatchLayout>

{#if showQuiz && assessment}
  <QuizModal
    assessmentId={assessment.id}
    questions={assessment.questions}
    on:close={() => { showQuiz = false; }}
    on:passed={() => { showQuiz = false; }}
  />
{/if}

<style>
  /* .ui-panel (app.css) gives the surface, radius and shadow. */
  .panel { display: grid; gap: 0.55rem; padding: 1.4rem 1.5rem; line-height: 1.55; }
  .muted { color: var(--muted); }
</style>
