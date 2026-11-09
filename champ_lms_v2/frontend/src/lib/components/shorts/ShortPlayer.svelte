<script lang="ts">
  // One short in the feed. It loads its stream only while it is on screen or
  // next to it (`warm`), plays while `active`, loops like YouTube Shorts, and
  // starts over when you come back to it. Tap to pause, double-tap to like.
  import { createEventDispatcher, onDestroy } from 'svelte';
  import { api, ApiError, type ShortItem } from '$lib/api/client';

  export let short: ShortItem;
  export let active = false;
  export let warm = false;
  export let muted = false;

  const dispatch = createEventDispatcher<{ autoplaymuted: void; doubletap: void; paused: boolean }>();

  let video: HTMLVideoElement;
  let hls: any = null;
  let loading = false;
  let loaded = false;
  let error = '';
  let paused = true;
  let buffering = false;
  let t = 0;
  let duration = short.duration_seconds ?? 0;

  $: fit = short.aspect === '9:16' ? 'cover' : short.fit;
  $: showBackdrop = fit === 'contain' && short.aspect !== '9:16' && !!short.poster_url;
  $: if (video) video.muted = muted;
  $: (warm || active) ? load() : unload();
  $: if (loaded && video) active ? start() : stop();

  async function load() {
    if (loaded || loading) return;
    loading = true; error = '';
    try {
      const { stream_url } = await api.shortStream(short.id);
      if (!warm && !active) return;
      const { default: Hls } = await import('hls.js/dist/hls.min.js');
      if (!video) return;
      if (Hls.isSupported()) {
        hls = new Hls({ enableWorker: true, maxBufferLength: active ? 30 : 8, startPosition: 0 });
        hls.on(Hls.Events.ERROR, (_e: unknown, d: any) => {
          if (!d?.fatal) return;
          if (d.type === Hls.ErrorTypes.NETWORK_ERROR && d.response?.code === 403) error = 'This video is blocked by the video host (403).';
          else if (d.type === Hls.ErrorTypes.MEDIA_ERROR) { hls.recoverMediaError(); return; }
          else error = 'This short could not load. Try again in a moment.';
        });
        hls.loadSource(stream_url);
        hls.attachMedia(video);
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = stream_url;
      } else {
        error = "This browser can't play these videos.";
        return;
      }
      loaded = true;
    } catch (e) {
      error = e instanceof ApiError && e.status === 425 ? 'Still processing. Check back in a minute.' : 'This short could not load.';
    } finally {
      loading = false;
    }
  }

  function unload() {
    if (!loaded) return;
    hls?.destroy(); hls = null;
    if (video) { video.removeAttribute('src'); video.load(); }
    loaded = false; paused = true; t = 0;
  }

  async function start() {
    if (!video) return;
    hls?.config && (hls.config.maxBufferLength = 30);
    try {
      await video.play();
    } catch (e: any) {
      // No sound without a tap first (a link opened in a fresh tab): play
      // muted and let the page offer the unmute button.
      if (e?.name === 'NotAllowedError' && !video.muted) {
        video.muted = true;
        dispatch('autoplaymuted');
        video.play().catch(() => {});
      }
    }
  }
  function stop() {
    if (!video) return;
    video.pause();
    if (video.currentTime > 0) video.currentTime = 0;
    t = 0; watched = 0; reported = false; looped = false;
  }

  // ---- views: one after a few seconds, completed after a full loop -------
  let watched = 0;
  let lastT = 0;
  let reported = false;
  let looped = false;
  function onTime() {
    const now = video.currentTime;
    const d = now - lastT;
    if (d > 0 && d < 1.5) watched += d;
    if (now + 0.5 < lastT && lastT > duration - 1.5 && !looped) {
      looped = true;
      api.viewShort(short.id, duration, true).catch(() => {});
    }
    lastT = now; t = now;
    if (!reported && watched >= Math.min(3, (duration || 6) / 2)) {
      reported = true;
      api.viewShort(short.id, watched, false).then(r => (short.view_count = r.view_count)).catch(() => {});
    }
  }

  // ---- tap / double tap ---------------------------------------------------
  let tapTimer: ReturnType<typeof setTimeout> | null = null;
  let flash: 'play' | 'pause' | null = null;
  let flashTimer: ReturnType<typeof setTimeout>;
  let hearts: { id: number; x: number; y: number }[] = [];
  let heartId = 0;
  function onTap(e: MouseEvent) {
    if (tapTimer) {
      clearTimeout(tapTimer); tapTimer = null;
      const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
      const h = { id: ++heartId, x: e.clientX - r.left, y: e.clientY - r.top };
      hearts = [...hearts, h];
      setTimeout(() => (hearts = hearts.filter(x => x.id !== h.id)), 900);
      dispatch('doubletap');
      return;
    }
    tapTimer = setTimeout(() => { tapTimer = null; toggle(); }, 240);
  }
  export function toggle() {
    if (!video || !loaded) return;
    if (video.paused) { video.play().catch(() => {}); showFlash('play'); }
    else { video.pause(); showFlash('pause'); }
  }
  function showFlash(k: 'play' | 'pause') {
    flash = k; clearTimeout(flashTimer);
    flashTimer = setTimeout(() => (flash = null), 650);
  }

  // ---- scrub bar ----------------------------------------------------------
  let scrubbing = false;
  function seekFrom(e: PointerEvent) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const p = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    if (video && duration) { video.currentTime = p * duration; t = video.currentTime; }
  }
  function scrubDown(e: PointerEvent) {
    scrubbing = true; (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); seekFrom(e);
  }

  onDestroy(() => { hls?.destroy(); if (tapTimer) clearTimeout(tapTimer); clearTimeout(flashTimer); });
</script>

<div class="sp">
  {#if showBackdrop}<img class="bg" src={short.poster_url} alt="" aria-hidden="true" />{/if}
  <!-- svelte-ignore a11y-media-has-caption -->
  <video
    bind:this={video}
    class="v"
    style="object-fit:{fit}; object-position:{short.focus_x}% 50%"
    poster={short.poster_url ?? undefined}
    playsinline loop preload="none"
    on:timeupdate={onTime}
    on:loadedmetadata={() => (duration = video.duration || duration)}
    on:play={() => { paused = false; dispatch('paused', false); }}
    on:pause={() => { paused = true; dispatch('paused', true); }}
    on:waiting={() => (buffering = true)}
    on:playing={() => (buffering = false)}
  ></video>

  <!-- The tap area sits under the overlays, so their buttons keep working. -->
  <button class="tap" on:click={onTap} aria-label={paused ? 'Play' : 'Pause'} tabindex="-1"></button>

  {#if (buffering || loading) && active && !error}<span class="ring" aria-hidden="true"></span>{/if}
  {#if flash}
    <span class="flash" aria-hidden="true">
      {#if flash === 'pause'}<svg viewBox="0 0 24 24" width="34" height="34" fill="currentColor"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>
      {:else}<svg viewBox="0 0 24 24" width="34" height="34" fill="currentColor"><path d="M8 5.5v13l10.5-6.5z"/></svg>{/if}
    </span>
  {/if}
  {#each hearts as h (h.id)}
    <span class="heart" style="left:{h.x}px; top:{h.y}px" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="84" height="84" fill="currentColor"><path d="M7 10v11H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zM7 10l4-7.5a2.3 2.3 0 0 1 3 2.4L13.4 9H19a2 2 0 0 1 2 2.3l-1.3 7.6A2.5 2.5 0 0 1 17.3 21H7z"/></svg>
    </span>
  {/each}
  {#if error}<p class="err">{error}</p>{/if}

  <slot {paused} {toggle} />

  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="scrub" class:on={scrubbing}
    on:pointerdown={scrubDown} on:pointermove={e => scrubbing && seekFrom(e)}
    on:pointerup={() => (scrubbing = false)} on:pointercancel={() => (scrubbing = false)}
    role="slider" aria-label="Seek" aria-valuemin={0} aria-valuemax={Math.round(duration)} aria-valuenow={Math.round(t)} tabindex="-1">
    <span class="fill" style="width:{duration ? (t / duration) * 100 : 0}%"></span>
  </div>
</div>

<style>
  .sp { position: absolute; inset: 0; overflow: hidden; background: #000; }
  .bg { position: absolute; inset: -12%; width: 124%; height: 124%; object-fit: cover; filter: blur(30px) brightness(0.55) saturate(1.2); }
  .v { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  .tap { position: absolute; inset: 0; z-index: 1; background: transparent; cursor: pointer; border-radius: 0; }
  .ring {
    position: absolute; left: 50%; top: 50%; z-index: 2; width: 46px; height: 46px; margin: -23px; border-radius: 50%;
    border: 3px solid rgba(255,255,255,.2); border-top-color: #fff; animation: spin 0.9s linear infinite; pointer-events: none;
  }
  @keyframes spin { to { rotate: 360deg; } }
  .flash {
    position: absolute; left: 50%; top: 50%; z-index: 2; width: 76px; height: 76px; margin: -38px; border-radius: 50%;
    display: grid; place-items: center; background: rgba(0,0,0,.5); color: #fff; pointer-events: none;
    animation: flash 650ms var(--ease-out) forwards;
  }
  @keyframes flash { 0% { opacity: 0; scale: .7; } 25% { opacity: 1; scale: 1; } 100% { opacity: 0; scale: 1.25; } }
  .heart {
    position: absolute; z-index: 3; translate: -50% -50%; color: #fff; pointer-events: none;
    filter: drop-shadow(0 4px 14px rgba(0,0,0,.45)); animation: heart 900ms var(--ease-out) forwards;
  }
  @keyframes heart {
    0% { opacity: 0; scale: .3; rotate: -14deg; }
    25% { opacity: 1; scale: 1.15; rotate: 0deg; }
    45% { scale: 1; }
    100% { opacity: 0; scale: 1.1; translate: -50% -130%; }
  }
  .err {
    position: absolute; left: 1rem; right: 1rem; top: 50%; z-index: 2; translate: 0 -50%; text-align: center;
    padding: 0.7rem 0.9rem; border-radius: 14px; background: rgba(0,0,0,.7); color: #fff; font-size: 0.86rem; pointer-events: none;
  }
  .scrub { position: absolute; left: 0; right: 0; bottom: 0; z-index: 4; height: 14px; display: flex; align-items: flex-end; cursor: pointer; touch-action: none; }
  .scrub::before { content: ''; position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: rgba(255,255,255,.28); transition: height var(--dur-1); }
  .fill { position: relative; height: 3px; background: var(--brand); transition: height var(--dur-1); }
  .scrub:hover::before, .scrub.on::before, .scrub:hover .fill, .scrub.on .fill { height: 6px; }
  .fill::after { content: ''; position: absolute; right: -6px; bottom: -3px; width: 12px; height: 12px; border-radius: 50%; background: var(--brand); opacity: 0; transition: opacity var(--dur-1); }
  .scrub:hover .fill::after, .scrub.on .fill::after { opacity: 1; }
</style>
