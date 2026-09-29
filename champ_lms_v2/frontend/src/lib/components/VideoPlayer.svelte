<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { player } from '$lib/stores/player';
  import { api } from '$lib/api/client';

  export let episodeId: string;
  export let embedUrl: string = '';   // Bunny iframe embed fallback
  export let streamUrl: string = '';  // Bunny token-auth HLS URL

  let videoEl: HTMLVideoElement;
  let container: HTMLElement;
  let hls: any = null;
  let autoAdvanceTimer: ReturnType<typeof setTimeout> | null = null;
  let showAutoAdvance = false;
  let countdown = 5;

  // * Playback-path selection. The native <video> + hls.js path is the ONLY one
  // * that emits timeupdate/ended, so it is the only path that records watch
  // * progress. The Bunny iframe embed cannot report progress at all.
  // * Previously the template tested `{#if embedUrl}` first and the backend
  // * always supplied an embedUrl, so the native path was unreachable and every
  // * learner's progress was posted as 0 seconds forever.
  // * Now: prefer streamUrl, and fall back to the iframe only if HLS actually
  // * fails (e.g. the token is rejected), so a broken token degrades to
  // * playback-without-tracking instead of a black screen.
  let hlsFailed = false;
  $: useNative = !!streamUrl && !hlsFailed;

  function fallbackToEmbed(reason: string) {
    if (!embedUrl) return; // nothing to fall back to; leave the error visible
    console.warn(`[VideoPlayer] HLS failed (${reason}) — falling back to embed; progress tracking disabled`);
    hls?.destroy();
    hls = null;
    hlsFailed = true;
  }

  export let onComplete: (() => void) | undefined = undefined;
  export let onAutoAdvance: (() => void) | undefined = undefined;
  // Reports the playhead so a synced transcript can follow along.
  export let onTime: ((seconds: number) => void) | undefined = undefined;
  // Where to start, e.g. to resume an episode part-way through.
  export let startAt = 0;
  // Course videos: how far past the furthest point reached a learner may jump
  // ahead in one go, in seconds. null = seek freely (classic modules, finished
  // episodes, admins). The server holds recorded progress to the same limit.
  export let skipLimitSeconds: number | null = null;
  // The furthest point already recorded for this learner, so the limit
  // carries over from an earlier session.
  export let furthestStart = 0;

  let furthest = 0;
  let skipNotice = '';
  let noticeTimer: ReturnType<typeof setTimeout> | null = null;
  let reportedStart = false;
  // The furthest point as it stood when the current seek began. The browser
  // fires a time update just before "seeked", which already moves `furthest`,
  // so the end of a seek compares against this instead.
  let furthestAtSeek: number | null = null;

  function showSkipNotice() {
    const mins = Math.round((skipLimitSeconds ?? 0) / 60);
    skipNotice = `You can skip ahead up to ${mins} minute${mins === 1 ? '' : 's'} at a time.`;
    if (noticeTimer) clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => (skipNotice = ''), 3500);
  }

  // Every seek comes through here: the scrub bar, the keyboard, a transcript
  // line. A jump further than the limit past the furthest point reached is
  // held at the limit. Going back, and returning to where you were, is free.
  function onSeeking() {
    if (!videoEl) return;
    if (furthestAtSeek === null) furthestAtSeek = furthest;
    if (skipLimitSeconds == null) return;
    const limit = furthestAtSeek + skipLimitSeconds;
    if (videoEl.currentTime > limit + 0.5) {
      videoEl.currentTime = limit;
      showSkipNotice();
    }
  }

  // After a skip past the furthest point, report it straight away so each skip
  // reaches the server on its own rather than several at once.
  function onSeeked() {
    if (!videoEl) return;
    const before = furthestAtSeek ?? furthest;
    furthestAtSeek = null;
    if (videoEl.currentTime > before + 1) {
      furthest = Math.max(furthest, videoEl.currentTime);
      if (skipLimitSeconds != null) {
        player.updateTime(Math.floor(videoEl.currentTime), Math.floor(videoEl.duration || 0));
        player.sync();
      }
    }
  }

  // The first report marks when watching began, which the server's limit
  // counts real playback time from.
  function onPlaying() {
    if (reportedStart || skipLimitSeconds == null || !videoEl) return;
    reportedStart = true;
    player.updateTime(Math.floor(videoEl.currentTime), Math.floor(videoEl.duration || 0));
    player.sync();
  }

  /** Jump to a point in the video (a transcript line was clicked). */
  export function seek(seconds: number) {
    if (!videoEl) return;
    videoEl.currentTime = seconds;
    videoEl.play().catch(() => {});
  }

  function applyStart() {
    if (startAt > 0 && videoEl && videoEl.duration && startAt < videoEl.duration - 5) {
      videoEl.currentTime = startAt;
    }
  }

  onMount(async () => {
    player.startTracking(episodeId);
    furthest = Math.max(furthestStart, startAt);

    if (!streamUrl) return;

    // Dynamically import HLS.js — works with Bunny Stream HLS URLs
    const { default: Hls } = await import('hls.js/dist/hls.min.js');

    if (Hls.isSupported()) {
      hls = new Hls({
        enableWorker: true,
        lowLatencyMode: false,
        backBufferLength: 90,
      });
      // Surface fatal errors instead of leaving a silent black player — a
      // rejected token is the likely cause and the iframe still works.
      hls.on(Hls.Events.ERROR, (_e: unknown, data: any) => {
        if (data?.fatal) fallbackToEmbed(data?.details ?? 'fatal');
      });
      hls.loadSource(streamUrl);
      hls.attachMedia(videoEl);
      hls.on(Hls.Events.MANIFEST_PARSED, () => videoEl.play().catch(() => {}));
      videoEl.addEventListener('loadedmetadata', applyStart, { once: true });
    } else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari native HLS
      videoEl.src = streamUrl;
      videoEl.addEventListener('loadedmetadata', applyStart, { once: true });
      videoEl.addEventListener('error', () => fallbackToEmbed('safari-native'));
      videoEl.play();
    } else {
      fallbackToEmbed('hls-unsupported');
    }
  });

  onDestroy(() => {
    hls?.destroy();
    player.stopTracking();
    if (autoAdvanceTimer) clearTimeout(autoAdvanceTimer);
    if (noticeTimer) clearTimeout(noticeTimer);
  });

  function onTimeUpdate() {
    if (!videoEl) return;
    player.updateTime(Math.floor(videoEl.currentTime), Math.floor(videoEl.duration || 0));
    if (!videoEl.seeking) furthest = Math.max(furthest, videoEl.currentTime);
    onTime?.(videoEl.currentTime);
  }

  async function onEnded() {
    await player.complete();
    onComplete?.();
    // Auto-advance
    showAutoAdvance = true;
    countdown = 5;
    const tick = setInterval(() => {
      countdown--;
      if (countdown <= 0) {
        clearInterval(tick);
        showAutoAdvance = false;
        onAutoAdvance?.();
      }
    }, 1000);
    autoAdvanceTimer = setTimeout(() => {
      showAutoAdvance = false;
      onAutoAdvance?.();
    }, 5100);
  }

  function cancelAutoAdvance() {
    showAutoAdvance = false;
    if (autoAdvanceTimer) clearTimeout(autoAdvanceTimer);
  }
</script>

<div bind:this={container} class="player-wrap">
  {#if useNative}
    <!-- Preferred: token-authenticated HLS in a native player. This is the ONLY
         path that fires timeupdate/ended, so it is the only one that records
         watch progress. -->
    <video
      bind:this={videoEl}
      class="video"
      controls
      preload="metadata"
      on:timeupdate={onTimeUpdate}
      on:seeking={onSeeking}
      on:seeked={onSeeked}
      on:playing={onPlaying}
      on:ended={onEnded}
    ></video>
  {:else if embedUrl}
    <!-- Fallback: Bunny's iframe embed. Plays reliably but reports NO progress,
         so a learner watching here will not have completion recorded. -->
    <iframe
      src={embedUrl}
      class="bunny-embed"
      title="Video player"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen
    ></iframe>
  {:else}
    <div class="placeholder">Loading video...</div>
  {/if}

  {#if skipNotice}
    <div class="skip-notice" role="status">{skipNotice}</div>
  {/if}

  {#if showAutoAdvance}
    <div class="auto-advance">
      <p>Next episode in <strong>{countdown}s</strong></p>
      <button class="btn-ghost" on:click={cancelAutoAdvance}>Cancel</button>
    </div>
  {/if}
</div>

<style>
  .player-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 16/9;
    background: #000;
    border-radius: 8px;
    overflow: hidden;
  }
  .video, .bunny-embed {
    width: 100%; height: 100%; border: none;
  }
  .placeholder {
    display: flex; align-items: center; justify-content: center;
    height: 100%; color: var(--muted);
  }
  .skip-notice {
    position: absolute; left: 50%; top: 1.25rem; transform: translateX(-50%);
    max-width: calc(100% - 2rem); text-align: center;
    background: rgba(0,0,0,0.82); color: #fff;
    border: 1px solid var(--border);
    border-radius: 8px; padding: 0.55rem 0.9rem; font-size: 0.88rem;
    pointer-events: none;
  }
  .auto-advance {
    position: absolute; bottom: 1.5rem; right: 1.5rem;
    background: rgba(0,0,0,0.85);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 0.75rem 1rem;
    display: flex; align-items: center; gap: 1rem;
    font-size: 0.9rem;
  }
  .btn-ghost {
    background: rgba(255,255,255,0.12);
    color: #fff;
    padding: 0.3rem 0.8rem;
    border-radius: 4px;
    font-size: 0.8rem;
  }
</style>
