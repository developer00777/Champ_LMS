<script lang="ts">
  // Canvas: how the picture sits in the 16:9 frame learners watch. What
  // fills the space around a picture that isn't 16:9 (black, a blurred copy
  // of itself, or a colour), turning and flipping it, and zoom and framing
  // all the way through.
  import type { Look } from '$lib/utils/video-edits';
  import { useStudio } from './studio';

  const st = useStudio();
  const { doc } = st;

  $: look = $doc.edits.look;
  const set = (patch: Partial<Look>, key?: string) => st.commit(d => { d.edits.look = { ...d.edits.look, ...patch }; }, key);

  const BGS: [Look['background'], string, string][] = [
    ['black', 'Black', 'Bars stay black.'],
    ['blur', 'Blur', 'A soft, blurred copy of the picture fills the bars.'],
    ['color', 'Colour', 'A flat colour fills the bars.'],
  ];
  const SWATCHES = ['#101014', '#ffffff', '#1f2a44', '#2e5bff', '#ff3b45', '#ffd23f', '#2ee6a6', '#7b5cff'];

  function turn(by: 90 | -90) {
    set({ rotate: (((look.rotate + by) % 360) + 360) % 360 as Look['rotate'] });
  }

  // Framing pad: click or drag where the zoom should centre.
  let pad: HTMLDivElement;
  let padDrag = false;
  function aim(e: PointerEvent) {
    const r = pad.getBoundingClientRect();
    set({
      focus_x: Math.round(Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100))),
      focus_y: Math.round(Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100))),
    }, 'focus');
  }
  $: vw = 100 / look.zoom;
  $: vx = look.focus_x - look.focus_x / look.zoom;
  $: vy = look.focus_y - look.focus_y / look.zoom;
</script>

<div class="p-sec">
  <h3 class="p-h">Background</h3>
  <p class="p-note">For a picture that doesn't fill the 16:9 frame: a 4:3 slide, a phone recording, a turned video.</p>
  <div class="bgs">
    {#each BGS as [v, l, about]}
      <button class="bg bg-{v}" class:on={look.background === v} on:click={() => set({ background: v })} aria-pressed={look.background === v} title={about}
        style={v === 'color' ? `--c:${look.bg_color}` : ''}>
        <span class="sw-demo"><i></i></span><b>{l}</b>
      </button>
    {/each}
  </div>
  {#if look.background === 'color'}
    <div class="swatches">
      {#each SWATCHES as c}<button class="sw" class:on={look.bg_color === c} style="background:{c}" on:click={() => set({ bg_color: c })} aria-label="Colour {c}"></button>{/each}
      <input type="color" value={look.bg_color} on:input={e => set({ bg_color: e.currentTarget.value }, 'bg')} aria-label="Any colour" />
    </div>
  {/if}
</div>

<div class="p-sec">
  <h3 class="p-h">Rotate and flip</h3>
  <div class="tools">
    <button class="tool" on:click={() => turn(-90)}><span>↺</span>Left</button>
    <button class="tool" on:click={() => turn(90)}><span>↻</span>Right</button>
    <button class="tool" class:on={look.flip_h} on:click={() => set({ flip_h: !look.flip_h })} aria-pressed={look.flip_h}><span>⇋</span>Mirror</button>
    <button class="tool" class:on={look.flip_v} on:click={() => set({ flip_v: !look.flip_v })} aria-pressed={look.flip_v}><span>⇵</span>Flip</button>
  </div>
  {#if look.rotate}<p class="p-note">Turned {look.rotate}°.{look.rotate % 180 ? ' A sideways picture shrinks to fit; Background fills around it.' : ''}</p>{/if}
</div>

<div class="p-sec">
  <h3 class="p-h">Zoom and framing</h3>
  <p class="p-note">Zoom in all the way through to drop black bars or keep a slide or speaker in frame. Click the picture where it should centre. For a zoom on one moment, use Effects.</p>
  <label class="slider">
    <span>Zoom<b class="mono">{look.zoom.toFixed(2)}×</b></span>
    <input type="range" min="1" max="2.5" step="0.05" value={look.zoom} on:input={e => set({ zoom: +e.currentTarget.value }, 'zoom')} />
  </label>
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="pad" bind:this={pad} class:off={look.zoom <= 1.001}
    on:pointerdown={e => { padDrag = true; e.currentTarget.setPointerCapture(e.pointerId); aim(e); }}
    on:pointermove={e => padDrag && aim(e)} on:pointerup={() => (padDrag = false)}>
    <div class="view" style="left:{vx}%; top:{vy}%; width:{vw}%; height:{vw}%"></div>
    <span class="dot" style="left:{look.focus_x}%; top:{look.focus_y}%"></span>
  </div>
</div>

<button class="btn sm ghost" on:click={() => set({ background: 'black', rotate: 0, flip_h: false, flip_v: false, zoom: 1, focus_x: 50, focus_y: 50 })}>Reset canvas</button>

<style>
  .bgs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.45rem; }
  .bg { display: grid; gap: 0.3rem; justify-items: center; padding: 0.45rem; border-radius: 10px; border: 1px solid var(--st-line); background: var(--st-raise); color: var(--st-text); font-size: 0.74rem; }
  .bg.on { border-color: var(--st-hot); box-shadow: 0 0 0 1px var(--st-hot); }
  .sw-demo { width: 100%; aspect-ratio: 16/9; border-radius: 6px; display: grid; place-items: center; overflow: hidden; }
  .sw-demo i { width: 56%; height: 100%; background: linear-gradient(135deg, #3a6ea5, #f3b562); display: block; }
  .bg-black .sw-demo { background: #000; }
  .bg-blur .sw-demo { background: linear-gradient(135deg, #3a6ea5, #f3b562); }
  .bg-blur .sw-demo i { box-shadow: 0 0 0 1px rgba(255,255,255,.35); }
  .bg-color .sw-demo { background: var(--c); }
  .swatches { display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; }
  .sw { width: 24px; height: 24px; border-radius: 50%; border: 2px solid var(--st-line); }
  .sw.on { border-color: #fff; box-shadow: 0 0 0 2px var(--st-hot); }
  .swatches input[type='color'] { width: 30px; height: 26px; padding: 0; border: 1px solid var(--st-line); border-radius: 6px; background: none; }
  .tools { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.4rem; }
  .tool { display: grid; justify-items: center; gap: 0.15rem; padding: 0.5rem 0.2rem; border-radius: 10px; background: var(--st-raise); border: 1px solid var(--st-line); color: var(--st-text); font-size: 0.7rem; font-weight: 600; }
  .tool span { font-size: 1.2rem; line-height: 1; }
  .tool.on { border-color: var(--st-hot); color: #fff; }
  .slider { display: grid; gap: 0.25rem; font-size: 0.76rem; }
  .slider span { display: flex; justify-content: space-between; color: var(--st-muted); }
  .slider b { color: var(--st-text); font-weight: 600; }
  .slider input { width: 100%; accent-color: var(--st-hot); }
  .pad { position: relative; aspect-ratio: 16/9; border-radius: 8px; overflow: hidden; cursor: crosshair; touch-action: none;
    background: linear-gradient(135deg, #3a4a5c, #1d2633 60%, #45392d); border: 1px solid var(--st-line); }
  .pad.off { opacity: 0.55; }
  .view { position: absolute; box-shadow: 0 0 0 999px rgba(0,0,0,.55); border: 1px solid #fff; border-radius: 3px; pointer-events: none; }
  .dot { position: absolute; width: 10px; height: 10px; border-radius: 50%; background: var(--st-hot); translate: -50% -50%; box-shadow: 0 0 0 2px #fff; pointer-events: none; }
</style>
