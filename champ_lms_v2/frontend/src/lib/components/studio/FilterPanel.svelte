<script lang="ts">
  // Filter: a preset look with a strength, previewed on the frame under the
  // playhead, then fine adjustments. All of it is CSS on the playing video,
  // so learners get it without the file on Bunny changing.
  import { onDestroy, tick } from 'svelte';
  import { FILTERS, LOOK_DEFAULTS, lookFilter, tintsOf, vignetteOf, type FilterId, type Look } from '$lib/utils/video-edits';
  import { useStudio } from './studio';

  const st = useStudio();
  const { doc, time, playing } = st;

  $: look = $doc.edits.look;
  const set = (patch: Partial<Look>, key?: string) => st.commit(d => { d.edits.look = { ...d.edits.look, ...patch }; }, key);
  const IDS = Object.keys(FILTERS) as FilterId[];

  const SLIDERS: { key: 'brightness' | 'contrast' | 'saturation' | 'warmth' | 'hue' | 'vignette'; label: string; min: number; max: number; unit: string; zero: number }[] = [
    { key: 'brightness', label: 'Brightness', min: 50, max: 150, unit: '%', zero: 100 },
    { key: 'contrast', label: 'Contrast', min: 50, max: 150, unit: '%', zero: 100 },
    { key: 'saturation', label: 'Saturation', min: 0, max: 200, unit: '%', zero: 100 },
    { key: 'warmth', label: 'Warmth', min: -100, max: 100, unit: '', zero: 0 },
    { key: 'hue', label: 'Hue', min: -180, max: 180, unit: '°', zero: 0 },
    { key: 'vignette', label: 'Vignette', min: 0, max: 100, unit: '', zero: 0 },
  ];

  // Each preset's tile shows the current frame through that preset. Drawn
  // straight from the video into each tile: nothing is read back, so it works
  // whatever the browser thinks of the video's origin.
  const tiles: Record<string, HTMLCanvasElement> = {};
  function paint() {
    const v = st.video();
    if (!v || !v.videoWidth) return;
    for (const id of IDS) {
      const c = tiles[id];
      const ctx = c?.getContext('2d');
      if (!ctx) continue;
      const s = Math.max(c.width / v.videoWidth, c.height / v.videoHeight);
      const w = v.videoWidth * s, h = v.videoHeight * s;
      try { ctx.drawImage(v, (c.width - w) / 2, (c.height - h) / 2, w, h); } catch { /* no frame yet */ }
    }
  }
  let timer: ReturnType<typeof setTimeout> | null = null;
  $: if (!$playing) { $time; if (timer) clearTimeout(timer); timer = setTimeout(paint, 120); }
  tick().then(paint);
  onDestroy(() => { if (timer) clearTimeout(timer); });

  const preview = (id: FilterId) => {
    const l: Look = { ...LOOK_DEFAULTS, filter: id, filter_strength: 100 };
    return { filter: lookFilter(l), tints: tintsOf(l), vignette: vignetteOf(l) };
  };
</script>

<div class="p-sec">
  <h3 class="p-h">Filters</h3>
  <div class="grid">
    {#each IDS as id}
      {@const p = preview(id)}
      <button class="tile" class:on={look.filter === id} on:click={() => set({ filter: id })} aria-pressed={look.filter === id}>
        <span class="img">
          <canvas bind:this={tiles[id]} width="128" height="72" style={p.filter ? `filter:${p.filter}` : ''}></canvas>
          {#each p.tints as w}<i class="tint" style="background:{w.color}; mix-blend-mode:{w.blend}; opacity:{w.opacity}"></i>{/each}
          {#if p.vignette}<i class="vig" style="--v:{p.vignette}"></i>{/if}
        </span>
        <b>{FILTERS[id].label}</b>
      </button>
    {/each}
  </div>
  {#if look.filter !== 'none'}
    <label class="slider">
      <span>Strength<b class="mono">{look.filter_strength}%</b></span>
      <input type="range" min="0" max="100" value={look.filter_strength} on:input={e => set({ filter_strength: +e.currentTarget.value }, 'strength')} />
    </label>
  {/if}
</div>

<div class="p-sec">
  <div class="p-hrow"><h3 class="p-h">Adjust</h3>
    <button class="btn xs ghost" on:click={() => set({ brightness: 100, contrast: 100, saturation: 100, warmth: 0, hue: 0, vignette: 0 })}>Reset</button></div>
  {#each SLIDERS as s}
    <label class="slider">
      <span>{s.label}<b class="mono">{look[s.key] > s.zero && s.zero === 0 && s.key !== 'vignette' ? '+' : ''}{look[s.key]}{s.unit}</b></span>
      <input type="range" min={s.min} max={s.max} value={look[s.key]} on:input={e => set({ [s.key]: +e.currentTarget.value }, s.key)}
        on:dblclick={() => set({ [s.key]: s.zero })} title="Double-click to reset" />
    </label>
  {/each}
</div>

<style>
  .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.4rem; }
  .tile { display: grid; gap: 0.25rem; padding: 0; background: none; color: var(--st-muted); font-size: 0.66rem; font-weight: 600; text-align: center; }
  .img { position: relative; display: block; aspect-ratio: 16/9; border-radius: 7px; overflow: hidden; background: linear-gradient(135deg, #3a6ea5, #f3b562); border: 2px solid transparent; isolation: isolate; }
  .tile.on .img { border-color: var(--st-hot); }
  .tile.on { color: #fff; }
  .img canvas { width: 100%; height: 100%; display: block; }
  .tint, .vig { position: absolute; inset: 0; pointer-events: none; }
  .vig { background: radial-gradient(ellipse at center, transparent 45%, rgba(0,0,0,calc(var(--v) * 0.85)) 100%); }
  .p-hrow { display: flex; align-items: center; justify-content: space-between; }
  .slider { display: grid; gap: 0.25rem; font-size: 0.76rem; }
  .slider span { display: flex; justify-content: space-between; color: var(--st-muted); }
  .slider b { color: var(--st-text); font-weight: 600; }
  .slider input { width: 100%; accent-color: var(--st-hot); }
</style>
