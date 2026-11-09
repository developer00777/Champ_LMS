<script lang="ts">
  // The video resizer: pick a new shape for a video, frame it, trim it, and
  // render the result in this browser. The preview canvas is drawn by the
  // same drawFrame the export uses, so the output matches it exactly.
  import { createEventDispatcher, onDestroy, tick } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import {
    SIZE_PRESETS, clock, drawFrame, grabPoster, nearestPreset, ratioLabel, readVideoMeta,
    recordingFormat, renderResized, RenderCancelled,
    type Backdrop, type FitMode, type RenderResult, type ResizeOptions, type VideoMeta,
  } from '$lib/utils/resize-video';

  export let file: File | null = null;
  /** Preset to start on (a key of SIZE_PRESETS). */
  export let preset = '9:16';
  /** Longest output allowed, in seconds (shorts: 180). null = any. */
  export let maxSeconds: number | null = null;
  /** Label of the main button. */
  export let actionLabel = 'Render video';

  const dispatch = createEventDispatcher<{ rendered: RenderResult & { poster: Blob | null; name: string }; cancel: void }>();

  let meta: VideoMeta | null = null;
  let srcUrl = '';
  let video: HTMLVideoElement;
  let canvas: HTMLCanvasElement;
  let error = '';
  let hot = false;

  // Output
  let presetKey = preset;
  let customW = 1080, customH = 1920;
  let quality: 'full' | 'hd' = 'full';
  let fit: FitMode = 'contain';
  let backdrop: Backdrop = 'blur';
  let color = '#101014';
  let zoom = 1;
  let x = 50, y = 50;
  let start = 0, end = 0;

  $: base = presetKey === 'custom'
    ? { width: clampDim(customW), height: clampDim(customH) }
    : SIZE_PRESETS.find(p => p.key === presetKey) ?? SIZE_PRESETS[0];
  // 720p: the short edge at 720, keeping the shape.
  $: k = quality === 'hd' ? 720 / Math.min(base.width, base.height) : 1;
  $: outW = Math.round((base.width * Math.min(1, k)) / 2) * 2;
  $: outH = Math.round((base.height * Math.min(1, k)) / 2) * 2;
  $: opts = { width: outW, height: outH, fit, backdrop, color, zoom, x, y, start, end } satisfies ResizeOptions;
  $: length = Math.max(0, end - start);
  $: tooLong = maxSeconds != null && length > maxSeconds + 0.5;
  $: format = typeof window !== 'undefined' ? recordingFormat() : null;

  function clampDim(n: number) { return Math.min(3840, Math.max(64, Math.round(+n || 0))); }

  // ---- loading a file ----------------------------------------------------
  let loadedFile: File | null = null;
  $: if (file !== loadedFile) load(file);

  async function load(f: File | null) {
    loadedFile = f;
    error = ''; meta = null; playing = false;
    if (srcUrl) URL.revokeObjectURL(srcUrl);
    srcUrl = '';
    if (!f) return;
    try {
      meta = await readVideoMeta(f);
    } catch (e: any) {
      error = e.message; return;
    }
    srcUrl = URL.createObjectURL(f);
    start = 0;
    end = maxSeconds != null ? Math.min(meta.duration, maxSeconds) : meta.duration;
    // A picture already this shape fills the frame; anything else starts
    // whole, on a blurred copy of itself.
    const same = nearestPreset(meta.width, meta.height).key === presetKey
      && Math.abs(meta.width / meta.height - base.width / base.height) < 0.02;
    fit = same ? 'cover' : 'contain';
    zoom = 1; x = 50; y = 50;
    await tick();
  }

  function pick(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) file = f;
  }

  // ---- preview -----------------------------------------------------------
  let playing = false;
  let now = 0;
  let raf = 0;
  function paint() {
    const ctx = canvas?.getContext('2d');
    if (ctx && video?.videoWidth) drawFrame(ctx, video, canvas.width, canvas.height, opts);
  }
  function loop() {
    raf = 0;
    if (!video) return;
    now = video.currentTime;
    if (video.currentTime >= end - 0.03) { video.currentTime = start; }
    paint();
    if (playing) raf = requestAnimationFrame(loop);
  }
  // Repaint whenever a setting or the size changes.
  $: if (canvas && opts) { canvas.width = outW; canvas.height = outH; paint(); }

  function togglePlay() {
    if (!video) return;
    if (video.paused) {
      if (video.currentTime < start || video.currentTime >= end - 0.05) video.currentTime = start;
      video.play().then(() => { playing = true; loop(); }).catch(() => {});
    } else { video.pause(); playing = false; }
  }
  function seekTo(t: number) {
    if (!video) return;
    video.currentTime = Math.min(Math.max(t, 0), meta?.duration ?? t);
    now = video.currentTime;
  }
  function setStart(v: number) { start = Math.min(Math.max(0, v), end - 0.5); seekTo(start); }
  function setEnd(v: number) { end = Math.max(Math.min(meta?.duration ?? v, v), start + 0.5); seekTo(Math.max(start, end - 1)); }

  // Drag the picture to frame it. Moving the pointer by d output pixels moves
  // the picture by d, whichever way it overflows.
  let drag: { px: number; py: number; x: number; y: number } | null = null;
  function down(e: PointerEvent) {
    drag = { px: e.clientX, py: e.clientY, x, y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }
  function move(e: PointerEvent) {
    if (!drag || !video?.videoWidth || !canvas) return;
    const r = canvas.getBoundingClientRect();
    const scaleOut = outW / r.width;
    const vw = video.videoWidth, vh = video.videoHeight;
    const s = (fit === 'cover' ? Math.max(outW / vw, outH / vh) : Math.min(outW / vw, outH / vh)) * zoom;
    const roomX = outW - vw * s, roomY = outH - vh * s;
    if (Math.abs(roomX) > 1) x = clampPct(drag.x + ((e.clientX - drag.px) * scaleOut * 100) / roomX);
    if (Math.abs(roomY) > 1) y = clampPct(drag.y + ((e.clientY - drag.py) * scaleOut * 100) / roomY);
  }
  function up() { drag = null; }
  const clampPct = (n: number) => Math.round(Math.min(100, Math.max(0, n)) * 10) / 10;

  // ---- export ------------------------------------------------------------
  let rendering = false;
  let progress = 0;
  let note = '';
  let abort: AbortController | null = null;
  let startedAt = 0;
  $: eta = rendering && progress > 0.03 ? ((Date.now() - startedAt) / progress) * (1 - progress) / 1000 : null;

  async function render() {
    if (!file || !meta || tooLong) return;
    if (video && !video.paused) { video.pause(); playing = false; }
    rendering = true; progress = 0; note = ''; error = '';
    abort = new AbortController();
    startedAt = Date.now();
    try {
      const result = await renderResized(file, opts, (p, n) => { progress = p; note = n ?? ''; }, abort.signal);
      // The poster: the first frame of the output, framed the same way.
      seekTo(start + Math.min(0.5, length / 3));
      await new Promise(r => video.addEventListener('seeked', r, { once: true }));
      const poster = await grabPoster(video, opts);
      const stem = file.name.replace(/\.[^.]+$/, '');
      dispatch('rendered', { ...result, poster, name: `${stem}-${outW}x${outH}.${result.ext}` });
    } catch (e: any) {
      if (!(e instanceof RenderCancelled)) error = e?.message ?? 'Rendering failed';
    } finally {
      rendering = false; abort = null;
    }
  }
  function cancel() { abort?.abort(); }

  onDestroy(() => {
    if (raf) cancelAnimationFrame(raf);
    abort?.abort();
    if (srcUrl) URL.revokeObjectURL(srcUrl);
  });

  const SWATCHES = ['#101014', '#ffffff', '#1f2a44', '#e50914', '#ffd23f', '#2ee6a6', '#7b5cff'];
  // Ratio of a preset card's little shape icon.
  const shapeStyle = (w: number, h: number) => {
    const m = Math.max(w, h);
    return `width:${(w / m) * 26}px;height:${(h / m) * 26}px`;
  };
</script>

<div class="rz">
  {#if !file}
    <label class="drop" class:hot on:dragenter={() => (hot = true)} on:dragleave={() => (hot = false)} on:drop={() => (hot = false)}>
      <input type="file" accept="video/*" on:change={pick} aria-label="Video to resize" />
      <span class="d-ico"><Icon name="crop" size={26} /></span>
      <b>Drop a video to resize, or click to choose</b>
      <span>MP4, MOV or WebM. It stays on this computer until you publish or download it.</span>
    </label>
  {:else}
    <div class="work">
      <!-- ---------- preview ---------- -->
      <div class="stage-col">
        <div class="stage" style="--ar:{outW}/{outH}">
          <!-- svelte-ignore a11y-no-static-element-interactions -->
          <canvas bind:this={canvas} class="out" class:grab={!!drag}
            on:pointerdown={down} on:pointermove={move} on:pointerup={up} on:pointercancel={up}
            title="Drag to move the picture"></canvas>
          <span class="size-tag">{outW} × {outH}</span>
        </div>
        {#if srcUrl}
          <!-- svelte-ignore a11y-media-has-caption -->
          <video bind:this={video} src={srcUrl} class="src" playsinline preload="auto"
            on:loadeddata={() => { seekTo(start); paint(); }} on:seeked={paint}
            on:pause={() => (playing = false)}></video>
        {/if}
        <div class="transport">
          <button class="ui-round ink" on:click={togglePlay} aria-label={playing ? 'Pause preview' : 'Play preview'} disabled={rendering}>
            <Icon name={playing ? 'pause' : 'play'} size={16} stroke={playing ? 1.75 : 0} />
          </button>
          <input class="scrub" type="range" min="0" max={meta?.duration ?? 0} step="0.05" value={now}
            on:input={e => seekTo(+e.currentTarget.value)} aria-label="Preview position" disabled={rendering}
            style="--a:{meta ? (start / meta.duration) * 100 : 0}%; --b:{meta ? (end / meta.duration) * 100 : 100}%" />
          <span class="mono">{clock(now)}</span>
        </div>
        <p class="src-meta">
          <Icon name="film" size={14} /> {file.name}
          {#if meta}· {meta.width}×{meta.height} ({ratioLabel(meta.width, meta.height)}) · {clock(meta.duration)}{/if}
          <button class="link" on:click={() => (file = null)} disabled={rendering}>Change</button>
        </p>
      </div>

      <!-- ---------- settings ---------- -->
      <div class="panel">
        <section>
          <h3>Size</h3>
          <div class="presets">
            {#each SIZE_PRESETS as p}
              <button class="preset" class:on={presetKey === p.key} on:click={() => (presetKey = p.key)} aria-pressed={presetKey === p.key}>
                <span class="shape"><i style={shapeStyle(p.width, p.height)}></i></span>
                <b>{p.label} <em>{p.ratio}</em></b>
                <small>{p.use}</small>
              </button>
            {/each}
            <button class="preset" class:on={presetKey === 'custom'} on:click={() => (presetKey = 'custom')} aria-pressed={presetKey === 'custom'}>
              <span class="shape"><i style={shapeStyle(clampDim(customW), clampDim(customH))}></i></span>
              <b>Custom</b>
              <small>Any width and height</small>
            </button>
          </div>
          {#if presetKey === 'custom'}
            <div class="row dims">
              <label>Width <input type="number" min="64" max="3840" step="2" bind:value={customW} /></label>
              <span class="x">×</span>
              <label>Height <input type="number" min="64" max="3840" step="2" bind:value={customH} /></label>
            </div>
          {/if}
          <div class="seg two" role="radiogroup" aria-label="Quality">
            <button role="radio" aria-checked={quality === 'full'} class:on={quality === 'full'} on:click={() => (quality = 'full')}>Full HD</button>
            <button role="radio" aria-checked={quality === 'hd'} class:on={quality === 'hd'} on:click={() => (quality = 'hd')}>720p · smaller file</button>
          </div>
        </section>

        <section>
          <h3>Framing</h3>
          <div class="seg two" role="radiogroup" aria-label="Fit">
            <button role="radio" aria-checked={fit === 'cover'} class:on={fit === 'cover'} on:click={() => (fit = 'cover')}>Fill · crop to fit</button>
            <button role="radio" aria-checked={fit === 'contain'} class:on={fit === 'contain'} on:click={() => (fit = 'contain')}>Fit · whole picture</button>
          </div>
          {#if fit === 'contain'}
            <div class="seg three" role="radiogroup" aria-label="Background">
              <button role="radio" aria-checked={backdrop === 'blur'} class:on={backdrop === 'blur'} on:click={() => (backdrop = 'blur')}>Blur</button>
              <button role="radio" aria-checked={backdrop === 'color'} class:on={backdrop === 'color'} on:click={() => (backdrop = 'color')}>Colour</button>
              <button role="radio" aria-checked={backdrop === 'black'} class:on={backdrop === 'black'} on:click={() => (backdrop = 'black')}>Black</button>
            </div>
            {#if backdrop === 'color'}
              <div class="swatches">
                {#each SWATCHES as c}<button class="sw" class:on={color === c} style="background:{c}" on:click={() => (color = c)} aria-label="Colour {c}"></button>{/each}
                <input type="color" bind:value={color} aria-label="Any colour" />
              </div>
            {/if}
          {/if}
          <label class="slider">
            <span>Zoom <b class="mono">{Math.round(zoom * 100)}%</b></span>
            <input type="range" min="1" max="3" step="0.01" bind:value={zoom} />
          </label>
          <div class="row">
            <label class="slider half"><span>Left – right</span><input type="range" min="0" max="100" step="0.5" bind:value={x} /></label>
            <label class="slider half"><span>Up – down</span><input type="range" min="0" max="100" step="0.5" bind:value={y} /></label>
          </div>
          <p class="hint"><Icon name="info" size={14} /> Drag the picture in the preview to move it.
            <button class="link" on:click={() => { x = 50; y = 50; zoom = 1; }}>Centre it</button></p>
        </section>

        <section>
          <h3>Trim <span class="len" class:bad={tooLong}>{clock(length)}{#if maxSeconds} of {clock(maxSeconds)} max{/if}</span></h3>
          <div class="row">
            <label class="slider half"><span>Start <b class="mono">{clock(start)}</b></span>
              <input type="range" min="0" max={meta?.duration ?? 0} step="0.1" value={start} on:input={e => setStart(+e.currentTarget.value)} /></label>
            <label class="slider half"><span>End <b class="mono">{clock(end)}</b></span>
              <input type="range" min="0" max={meta?.duration ?? 0} step="0.1" value={end} on:input={e => setEnd(+e.currentTarget.value)} /></label>
          </div>
          {#if tooLong}<p class="msg bad"><Icon name="alert" size={15} /> Shorts can be up to {clock(maxSeconds)}. Move the end in to trim it.</p>{/if}
        </section>

        {#if rendering}
          <div class="progress" aria-live="polite">
            <div class="bar"><span style="width:{Math.round(progress * 100)}%"></span></div>
            <p><b>Rendering {Math.round(progress * 100)}%</b>{#if eta != null} · about {clock(eta)} left{/if}</p>
            <p class="hint">{note || 'It plays through once in real time. Keep this tab open and visible.'}</p>
            <button class="btn-ghost" on:click={cancel}>Cancel</button>
          </div>
        {:else}
          {#if error}<p class="msg bad"><Icon name="alert" size={15} /> {error}</p>{/if}
          {#if !format}<p class="msg bad"><Icon name="alert" size={15} /> This browser can't record video. Use Chrome, Edge, Firefox or Safari.</p>{/if}
          <div class="actions">
            <slot name="extra-actions" />
            <button class="btn-primary" on:click={render} disabled={!meta || tooLong || !format}>
              <Icon name="crop" size={17} /> {actionLabel}
            </button>
          </div>
          {#if format}<p class="hint">Saves as {format.ext.toUpperCase()} at {outW}×{outH}. Takes about {clock(length)} to render.</p>{/if}
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .rz { display: flex; flex-direction: column; gap: 1rem; }
  .drop {
    position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.4rem;
    min-height: 260px; padding: 2rem; border-radius: 28px; text-align: center; cursor: pointer;
    background: var(--surface2); border: 2px dashed var(--border-hover); color: var(--muted); font-size: 0.86rem;
    transition: background-color var(--dur-2) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .drop b { color: var(--text); font-size: 1rem; }
  .drop:hover { background: var(--surface3); }
  .drop.hot { background: var(--tile-sky); scale: 1.01; }
  .drop input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  .d-ico { width: 58px; height: 58px; border-radius: 50%; display: grid; place-items: center; background: var(--surface); color: var(--text); margin-bottom: 0.3rem; pointer-events: none; }
  .drop b, .drop span { pointer-events: none; }

  .work { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 1.25rem; align-items: start; }
  .stage-col { display: flex; flex-direction: column; gap: 0.75rem; min-width: 0; position: sticky; top: 1rem; }
  /* A checked floor, so the output's edges read against the page. */
  .stage {
    position: relative; display: flex; align-items: center; justify-content: center; height: min(66vh, 640px); padding: 1rem;
    border-radius: 28px; background: #0b0b0d;
    background-image: radial-gradient(rgba(255,255,255,.07) 1px, transparent 1px); background-size: 14px 14px;
  }
  .out {
    /* Replaced element: auto size within max bounds keeps the shape. */
    display: block; max-width: 100%; max-height: 100%; width: auto; height: auto;
    border-radius: 14px; box-shadow: 0 0 0 1px rgba(255,255,255,.18), 0 20px 50px -20px #000;
    cursor: grab; touch-action: none; object-fit: contain;
  }
  .out.grab { cursor: grabbing; }
  .size-tag {
    position: absolute; left: 1rem; top: 1rem; padding: 0.25rem 0.6rem; border-radius: 99px;
    background: rgba(255,255,255,.12); color: #fff; font-size: 0.74rem; font-weight: 700; font-variant-numeric: tabular-nums;
  }
  .src { position: absolute; width: 1px; height: 1px; opacity: 0; pointer-events: none; }
  .transport { display: flex; align-items: center; gap: 0.75rem; }
  .scrub {
    flex: 1; height: 6px; appearance: none; border-radius: 6px; cursor: pointer;
    background: linear-gradient(to right, var(--surface3) var(--a), var(--accent) var(--a), var(--accent) var(--b), var(--surface3) var(--b));
  }
  .scrub::-webkit-slider-thumb { appearance: none; width: 16px; height: 16px; border-radius: 50%; background: var(--surface); border: 2px solid var(--accent); }
  .scrub::-moz-range-thumb { width: 14px; height: 14px; border-radius: 50%; background: var(--surface); border: 2px solid var(--accent); }
  .mono { font-variant-numeric: tabular-nums; font-size: 0.82rem; color: var(--text-secondary); }
  .src-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; font-size: 0.8rem; color: var(--muted); overflow-wrap: anywhere; }

  .panel { display: flex; flex-direction: column; gap: 1rem; background: var(--surface); border-radius: 28px; padding: 1.25rem; box-shadow: var(--shadow-sm); }
  section { display: flex; flex-direction: column; gap: 0.65rem; padding-bottom: 1rem; border-bottom: 1px solid var(--border); }
  h3 { font-size: 0.98rem; font-weight: 700; display: flex; align-items: baseline; justify-content: space-between; }
  .len { font-size: 0.8rem; font-weight: 600; color: var(--muted); font-variant-numeric: tabular-nums; }
  .len.bad { color: var(--danger); }
  .presets { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
  .preset {
    display: grid; grid-template-columns: 34px 1fr; grid-template-rows: auto auto; column-gap: 0.55rem; align-items: center;
    padding: 0.6rem 0.65rem; border-radius: 16px; text-align: left; background: var(--surface2); border: 1px solid transparent;
    transition: background-color var(--dur-2) var(--ease-out), border-color var(--dur-2) var(--ease-out);
  }
  .preset:hover { background: var(--surface3); }
  .preset.on { border-color: var(--accent); background: var(--surface); box-shadow: var(--shadow-sm); }
  .shape { grid-row: 1 / 3; width: 34px; height: 34px; display: grid; place-items: center; }
  .shape i { display: block; border-radius: 4px; border: 2px solid currentColor; }
  .preset.on .shape i { background: var(--tile-sky); }
  .preset b { font-size: 0.84rem; font-weight: 700; }
  .preset b em { font-style: normal; font-weight: 600; color: var(--muted); margin-left: 0.2rem; }
  .preset small { font-size: 0.72rem; color: var(--muted); line-height: 1.3; }
  .row { display: flex; gap: 0.6rem; align-items: flex-end; }
  .dims label { display: flex; flex-direction: column; gap: 0.3rem; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); flex: 1; }
  .dims input { background: var(--surface2); border: 1px solid transparent; border-radius: 12px; padding: 0.55rem 0.7rem; color: var(--text); font-size: 0.92rem; width: 100%; }
  .dims input:focus { outline: none; border-color: var(--accent); }
  .x { padding-bottom: 0.6rem; color: var(--muted); }
  .seg { display: grid; gap: 0.25rem; padding: 0.25rem; border-radius: 999px; background: var(--surface2); }
  .seg.two { grid-template-columns: 1fr 1fr; }
  .seg.three { grid-template-columns: 1fr 1fr 1fr; }
  .seg button { min-height: 36px; border-radius: 999px; font-size: 0.8rem; font-weight: 600; color: var(--muted); padding: 0 0.5rem; }
  .seg button:hover { color: var(--text); }
  .seg button.on { background: var(--accent); color: var(--on-accent); }
  .swatches { display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; }
  .sw { width: 28px; height: 28px; border-radius: 50%; border: 2px solid var(--border-hover); }
  .sw.on { outline: 2px solid var(--accent); outline-offset: 2px; }
  .swatches input { width: 34px; height: 30px; border: none; background: none; padding: 0; }
  .slider { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }
  .slider span { display: flex; justify-content: space-between; }
  .slider.half { flex: 1; min-width: 0; }
  .slider input { width: 100%; accent-color: var(--accent); }
  .hint { display: flex; flex-wrap: wrap; align-items: center; gap: 0.35rem; font-size: 0.76rem; color: var(--muted); }
  .link { font-size: inherit; font-weight: 700; color: var(--text); text-decoration: underline; text-underline-offset: 3px; }
  .msg { display: flex; gap: 0.45rem; align-items: center; font-size: 0.83rem; font-weight: 500; }
  .msg.bad { color: var(--danger); }
  .actions { display: flex; flex-wrap: wrap; gap: 0.6rem; justify-content: flex-end; }
  .progress { display: flex; flex-direction: column; gap: 0.5rem; align-items: flex-start; }
  .progress p { font-size: 0.86rem; }
  .bar { width: 100%; height: 10px; border-radius: 99px; background: var(--surface2); overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); border-radius: 99px; transition: width 200ms linear; }

  @media (max-width: 1020px) {
    .work { grid-template-columns: 1fr; }
    .stage-col { position: static; }
    .stage { height: min(56vh, 520px); }
  }
</style>
