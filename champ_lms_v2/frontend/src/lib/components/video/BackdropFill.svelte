<script lang="ts">
  // The canvas's blurred background: the playing frame, drawn small and
  // blurred behind the video, so a picture that isn't 16:9 (a 4:3 slide, a
  // phone recording, a rotated video) sits on a soft copy of itself instead
  // of black bars. Only drawn while shown; the video stays the video.
  import { onDestroy } from 'svelte';

  export let video: HTMLVideoElement | null = null;
  export let active = false;

  let canvas: HTMLCanvasElement;
  let raf = 0;
  let last = 0;
  let bound: HTMLVideoElement | null = null;

  function draw() {
    const ctx = canvas?.getContext('2d');
    if (!ctx || !video || !video.videoWidth) return;
    const vw = video.videoWidth, vh = video.videoHeight;
    const cw = canvas.width, ch = canvas.height;
    // Cover: fill the canvas, cropping whatever overflows.
    const s = Math.max(cw / vw, ch / vh);
    const w = vw * s, h = vh * s;
    try { ctx.drawImage(video, (cw - w) / 2, (ch - h) / 2, w, h); } catch { /* not ready yet */ }
  }

  // About 15 frames a second is plenty for a blur.
  function loop(now: number) {
    raf = 0;
    if (!active || !video || video.paused) return;
    if (now - last > 66) { draw(); last = now; }
    raf = requestAnimationFrame(loop);
  }
  function start() { if (!raf && active) raf = requestAnimationFrame(loop); }
  function once() { if (active) draw(); }

  function bind(v: HTMLVideoElement | null) {
    if (bound === v) return;
    if (bound) {
      bound.removeEventListener('play', start);
      bound.removeEventListener('seeked', once);
      bound.removeEventListener('loadeddata', once);
    }
    bound = v;
    if (v) {
      v.addEventListener('play', start);
      v.addEventListener('seeked', once);
      v.addEventListener('loadeddata', once);
    }
  }
  $: bind(video);
  $: if (active && canvas) { once(); start(); }

  onDestroy(() => { if (raf) cancelAnimationFrame(raf); bind(null); });
</script>

{#if active}<canvas bind:this={canvas} class="fill" width="64" height="36" aria-hidden="true"></canvas>{/if}

<style>
  .fill { position: absolute; inset: -8%; width: 116%; height: 116%; filter: blur(22px) brightness(0.72) saturate(1.25); pointer-events: none; }
</style>
