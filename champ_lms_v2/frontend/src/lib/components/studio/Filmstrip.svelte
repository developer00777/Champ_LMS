<script lang="ts">
  // The video lane's filmstrip: frames of the video along the timeline, as
  // in a phone editor. Frames come from a hidden second copy of the video
  // (its lowest quality, for a stream), seeked from one tile to the next.
  // Only the tiles in view are drawn, nearest the playhead first, and each
  // frame is kept once taken.
  import { onDestroy } from 'svelte';
  import type { Source } from './studio';

  export let source: Source;
  export let length: number;
  // Pixels per second of the timeline, and the stretch in view (seconds).
  export let pps: number;
  export let from: number;
  export let to: number;
  export let around = 0;
  export let height = 48;

  const TW = Math.round((height * 16) / 9);
  $: span = TW / pps;
  $: first = Math.max(0, Math.floor(from / span) - 1);
  $: last = Math.min(Math.ceil(length / span) - 1, Math.ceil(to / span) + 1);
  $: keys = last >= first ? Array.from({ length: last - first + 1 }, (_, n) => first + n) : [];

  const frames = new Map<number, HTMLCanvasElement>(); // tenths of a second -> frame
  let version = 0;
  let vid: HTMLVideoElement;
  let hls: any = null;
  let objectUrl: string | null = null;
  let ready = false;
  let busy = false;
  let dead = false;
  let queue: number[] = [];

  function nearest(t: number, within: number): HTMLCanvasElement | null {
    let best: HTMLCanvasElement | null = null, bd = within;
    for (const [k, c] of frames) {
      const d = Math.abs(k / 10 - t);
      if (d <= bd) { bd = d; best = c; }
    }
    return best;
  }

  // Whenever the view moves: queue the tiles without a frame, nearest the playhead first.
  $: if (ready) {
    queue = keys.map(k => (k + 0.5) * span).filter(t => t < length && !nearest(t, span / 2))
      .sort((a, b) => Math.abs(a - around) - Math.abs(b - around));
    pump();
  }

  function seek(t: number): Promise<void> {
    return new Promise(res => {
      const done = () => { vid.removeEventListener('seeked', done); clearTimeout(timer); res(); };
      const timer = setTimeout(done, 5000);
      vid.addEventListener('seeked', done);
      vid.currentTime = Math.min(length - 0.1, Math.max(0, t));
    });
  }

  async function pump() {
    if (busy || !ready) return;
    busy = true;
    while (queue.length && !dead) {
      const t = queue.shift()!;
      if (nearest(t, span / 2)) continue;
      await seek(t);
      if (dead) break;
      const c = document.createElement('canvas');
      c.width = 160; c.height = 90;
      try { cover(c, vid); } catch { /* no frame */ }
      frames.set(Math.round(t * 10), c);
      version++;
    }
    busy = false;
  }

  function cover(c: HTMLCanvasElement, src: CanvasImageSource & { videoWidth?: number; videoHeight?: number; width?: number; height?: number }) {
    const ctx = c.getContext('2d');
    if (!ctx) return;
    const w = (src.videoWidth || src.width || c.width) as number, h = (src.videoHeight || src.height || c.height) as number;
    const s = Math.max(c.width / w, c.height / h);
    ctx.drawImage(src, (c.width - w * s) / 2, (c.height - h * s) / 2, w * s, h * s);
  }

  // A tile draws the nearest frame it has, and again as better ones arrive.
  function tile(node: HTMLCanvasElement, arg: [number, number]) {
    const draw = ([t]: [number, number]) => {
      const f = nearest(t, span * 3);
      if (f) node.getContext('2d')?.drawImage(f, 0, 0, node.width, node.height);
    };
    draw(arg);
    return { update: draw };
  }

  // The stream's address arrives after the studio opens, so start once it's known.
  let started = false;
  $: if (vid && !started && (source.file || source.stream)) { started = true; start(); }
  async function start() {
    if (source.file) {
      objectUrl = URL.createObjectURL(source.file);
      vid.src = objectUrl;
    } else if (source.stream) {
      try {
        const { default: Hls } = await import('hls.js/dist/hls.min.js');
        if (Hls.isSupported()) {
          // The smallest picture there is: a tile is a thumbnail.
          hls = new Hls({ startLevel: 0, capLevelToPlayerSize: true, maxBufferLength: 2, maxMaxBufferLength: 4, autoStartLoad: true });
          hls.on(Hls.Events.MANIFEST_PARSED, () => { hls.currentLevel = 0; });
          hls.loadSource(source.stream);
          hls.attachMedia(vid);
        } else vid.src = source.stream;
      } catch { return; }
    } else return;
    vid.addEventListener('loadeddata', () => { ready = true; }, { once: true });
  }
  onDestroy(() => {
    dead = true;
    hls?.destroy();
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  });
</script>

<!-- svelte-ignore a11y-media-has-caption -->
<video bind:this={vid} class="src" muted playsinline preload="auto" width="160" height="90" aria-hidden="true"></video>
<div class="strip" aria-hidden="true">
  {#each keys as k (k)}
    <canvas class="tile" width="96" height="54" style="left:{k * TW}px; width:{TW}px" use:tile={[(k + 0.5) * span, version]}></canvas>
  {/each}
</div>

<style>
  .src { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
  .strip { position: absolute; inset: 0; overflow: hidden; pointer-events: none; }
  .tile { position: absolute; top: 0; height: 100%; display: block; border-right: 1px solid rgba(0,0,0,.45); background: #15161c; }
</style>
