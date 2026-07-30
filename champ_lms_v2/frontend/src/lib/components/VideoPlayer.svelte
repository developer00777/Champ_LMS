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

  onMount(async () => {
    player.startTracking(episodeId);

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
      hls.on(Hls.Events.MANIFEST_PARSED, () => videoEl.play());
    } else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari native HLS
      videoEl.src = streamUrl;
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
  });

  function onTimeUpdate() {
    if (!videoEl) return;
    player.updateTime(Math.floor(videoEl.currentTime), Math.floor(videoEl.duration || 0));
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
