<script lang="ts">
  import { BRAND_DEFAULTS, LOOK_DEFAULTS, type Brand, type Look } from '$lib/utils/video-edits';
  import { useStudio } from './studio';

  const st = useStudio();
  const { doc } = st;

  $: look = $doc.edits.look;
  $: brand = $doc.edits.brand;
  const setLook = (patch: Partial<Look>, key?: string) => st.commit(d => { d.edits.look = { ...d.edits.look, ...patch }; }, key);
  const setBrand = (patch: Partial<Brand>, key?: string) => st.commit(d => { d.edits.brand = { ...d.edits.brand, ...patch }; }, key);

  const PRESETS: { name: string; v: Partial<Look> }[] = [
    { name: 'Natural', v: { brightness: 100, contrast: 100, saturation: 100 } },
    { name: 'Brighter', v: { brightness: 112, contrast: 104, saturation: 105 } },
    { name: 'Vivid', v: { brightness: 103, contrast: 112, saturation: 130 } },
    { name: 'Soft', v: { brightness: 106, contrast: 90, saturation: 92 } },
    { name: 'Mono', v: { brightness: 102, contrast: 110, saturation: 0 } },
  ];
  const SLIDERS: { key: 'brightness' | 'contrast' | 'saturation'; label: string; min: number; max: number }[] = [
    { key: 'brightness', label: 'Brightness', min: 50, max: 150 },
    { key: 'contrast', label: 'Contrast', min: 50, max: 150 },
    { key: 'saturation', label: 'Saturation', min: 0, max: 200 },
  ];
  const CORNERS = [['tl', 'Top left'], ['tr', 'Top right'], ['bl', 'Bottom left'], ['br', 'Bottom right']] as const;

  // Framing pad: click or drag where the zoom should centre.
  let pad: HTMLDivElement;
  let padDrag = false;
  function aim(e: PointerEvent) {
    const r = pad.getBoundingClientRect();
    setLook({
      focus_x: Math.round(Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100))),
      focus_y: Math.round(Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100))),
    }, 'focus');
  }
  // The part of the picture that stays in view at this zoom, on the pad.
  $: vw = 100 / look.zoom;
  $: vx = look.focus_x - look.focus_x / look.zoom;
  $: vy = look.focus_y - look.focus_y / look.zoom;
</script>

<div class="p-sec">
  <h3 class="p-h">Colour</h3>
  <div class="chips">
    {#each PRESETS as p}
      <button class="chip" class:on={p.v.brightness === look.brightness && p.v.contrast === look.contrast && p.v.saturation === look.saturation}
        on:click={() => setLook(p.v)}>{p.name}</button>
    {/each}
  </div>
  {#each SLIDERS as s}
    <label class="slider">
      <span>{s.label}<b class="mono">{look[s.key]}%</b></span>
      <input type="range" min={s.min} max={s.max} value={look[s.key]} on:input={e => setLook({ [s.key]: +e.currentTarget.value }, s.key)} />
    </label>
  {/each}
</div>

<div class="p-sec">
  <h3 class="p-h">Zoom and framing</h3>
  <p class="p-note">Zoom in all the way through to drop black bars or keep a slide or speaker in frame. Click the picture where it should centre. For a zoom on one moment, use Effects.</p>
  <label class="slider">
    <span>Zoom<b class="mono">{look.zoom.toFixed(2)}×</b></span>
    <input type="range" min="1" max="2.5" step="0.05" value={look.zoom} on:input={e => setLook({ zoom: +e.currentTarget.value }, 'zoom')} />
  </label>
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="pad" bind:this={pad} class:off={look.zoom <= 1.001}
    on:pointerdown={e => { padDrag = true; (e.currentTarget).setPointerCapture(e.pointerId); aim(e); }}
    on:pointermove={e => padDrag && aim(e)} on:pointerup={() => (padDrag = false)}>
    <div class="view" style="left:{vx}%; top:{vy}%; width:{vw}%; height:{vw}%"></div>
    <span class="dot" style="left:{look.focus_x}%; top:{look.focus_y}%"></span>
  </div>
</div>

<div class="p-sec">
  <h3 class="p-h">Fades</h3>
  <label class="toggle"><input type="checkbox" checked={look.fade_in} on:change={e => setLook({ fade_in: e.currentTarget.checked })} />
    <span><b>Fade in from black</b><span>At the start of each part.</span></span></label>
  <label class="toggle"><input type="checkbox" checked={look.fade_out} on:change={e => setLook({ fade_out: e.currentTarget.checked })} />
    <span><b>Fade out to black</b><span>At the end of each part.</span></span></label>
</div>

<div class="p-sec">
  <h3 class="p-h">Brand mark</h3>
  <label class="toggle"><input type="checkbox" checked={brand.watermark} on:change={e => setBrand({ watermark: e.currentTarget.checked })} />
    <span><b>Show the Champions Group mark</b><span>A small logo in a corner, all the way through.</span></span></label>
  {#if brand.watermark}
    <div class="seg-ctl small" role="radiogroup" aria-label="Corner">
      {#each CORNERS as [v, l]}
        <button role="radio" aria-checked={brand.position === v} class:on={brand.position === v} on:click={() => setBrand({ position: v })}>{l}</button>
      {/each}
    </div>
    <label class="slider">
      <span>Opacity<b class="mono">{Math.round(brand.opacity * 100)}%</b></span>
      <input type="range" min="0.2" max="1" step="0.05" value={brand.opacity} on:input={e => setBrand({ opacity: +e.currentTarget.value }, 'opacity')} />
    </label>
  {/if}
</div>

<div class="p-sec">
  <h3 class="p-h">Progress bar</h3>
  <label class="toggle"><input type="checkbox" checked={brand.progress_bar} on:change={e => setBrand({ progress_bar: e.currentTarget.checked })} />
    <span><b>Show a progress bar</b><span>A thin bar along the top that fills as the part plays, so learners see how far along they are.</span></span></label>
  {#if brand.progress_bar}
    <div class="swatches">
      {#each ['#ff3b45', '#ffd23f', '#7ef0a8', '#6ea8ff', '#ffffff'] as c}
        <button class="sw" class:on={brand.progress_color === c} style="background:{c}" on:click={() => setBrand({ progress_color: c })} aria-label="Bar colour {c}"></button>
      {/each}
      <input type="color" value={brand.progress_color} on:input={e => setBrand({ progress_color: e.currentTarget.value }, 'bar-color')} aria-label="Any bar colour" />
    </div>
  {/if}
</div>

<button class="btn sm ghost" on:click={() => st.commit(d => { d.edits.look = { ...LOOK_DEFAULTS }; d.edits.brand = { ...BRAND_DEFAULTS }; })}>Reset look and brand</button>

<style>
  .chips { display: flex; flex-wrap: wrap; gap: 0.35rem; }
  .chip { height: 26px; padding: 0 0.7rem; border-radius: 99px; background: var(--st-raise); color: var(--st-text); font-size: 0.74rem; font-weight: 600; border: 1px solid var(--st-line); }
  .chip.on { border-color: var(--st-hot); }
  .slider { display: grid; gap: 0.25rem; font-size: 0.76rem; }
  .slider span { display: flex; justify-content: space-between; color: var(--st-muted); }
  .slider b { color: var(--st-text); font-weight: 600; }
  .slider input { width: 100%; accent-color: var(--st-hot); }
  .pad { position: relative; aspect-ratio: 16/9; border-radius: 8px; overflow: hidden; cursor: crosshair; touch-action: none;
    background: linear-gradient(135deg, #3a4a5c, #1d2633 60%, #45392d); border: 1px solid var(--st-line); }
  .pad.off { opacity: 0.55; }
  .view { position: absolute; box-shadow: 0 0 0 999px rgba(0,0,0,.55); border: 1px solid #fff; border-radius: 3px; pointer-events: none; }
  .dot { position: absolute; width: 10px; height: 10px; border-radius: 50%; background: var(--st-hot); translate: -50% -50%; box-shadow: 0 0 0 2px #fff; pointer-events: none; }
  .toggle { display: grid; grid-template-columns: auto 1fr; gap: 0.6rem; align-items: start; font-size: 0.8rem; cursor: pointer; }
  .toggle input { margin-top: 0.2rem; accent-color: var(--st-hot); }
  .toggle span { display: grid; gap: 0.15rem; }
  .toggle span span { color: var(--st-muted); font-size: 0.74rem; }
  .swatches { display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; }
  .sw { width: 24px; height: 24px; border-radius: 50%; border: 2px solid var(--st-line); }
  .sw.on { border-color: #fff; box-shadow: 0 0 0 2px var(--st-hot); }
  .swatches input[type='color'] { width: 30px; height: 26px; padding: 0; border: 1px solid var(--st-line); border-radius: 6px; background: none; }
</style>
