<script lang="ts">
  // Brand and fades: the fades at each part's ends, the Champions Group mark
  // and the progress bar. Colour is in Filter; zoom and framing in Canvas.
  import { BRAND_DEFAULTS, type Brand, type Look } from '$lib/utils/video-edits';
  import { useStudio } from './studio';

  const st = useStudio();
  const { doc } = st;

  $: look = $doc.edits.look;
  $: brand = $doc.edits.brand;
  const setLook = (patch: Partial<Look>, key?: string) => st.commit(d => { d.edits.look = { ...d.edits.look, ...patch }; }, key);
  const setBrand = (patch: Partial<Brand>, key?: string) => st.commit(d => { d.edits.brand = { ...d.edits.brand, ...patch }; }, key);

  const CORNERS = [['tl', 'Top left'], ['tr', 'Top right'], ['bl', 'Bottom left'], ['br', 'Bottom right']] as const;
</script>

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

<button class="btn sm ghost" on:click={() => st.commit(d => { d.edits.look = { ...d.edits.look, fade_in: false, fade_out: false }; d.edits.brand = { ...BRAND_DEFAULTS }; })}>Reset fades and brand</button>

<style>
  .slider { display: grid; gap: 0.25rem; font-size: 0.76rem; }
  .slider span { display: flex; justify-content: space-between; color: var(--st-muted); }
  .slider b { color: var(--st-text); font-weight: 600; }
  .slider input { width: 100%; accent-color: var(--st-hot); }
  .toggle { display: grid; grid-template-columns: auto 1fr; gap: 0.6rem; align-items: start; font-size: 0.8rem; cursor: pointer; }
  .toggle input { margin-top: 0.2rem; accent-color: var(--st-hot); }
  .toggle span { display: grid; gap: 0.15rem; }
  .toggle span span { color: var(--st-muted); font-size: 0.74rem; }
  .swatches { display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; }
  .sw { width: 24px; height: 24px; border-radius: 50%; border: 2px solid var(--st-line); }
  .sw.on { border-color: #fff; box-shadow: 0 0 0 2px var(--st-hot); }
  .swatches input[type='color'] { width: 30px; height: 26px; padding: 0; border: 1px solid var(--st-line); border-radius: 6px; background: none; }
</style>
