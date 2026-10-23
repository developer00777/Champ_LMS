<script lang="ts">
  // Handles on the preview for the selected blur or zoom effect: drag a blur
  // box to move it and its corner to size it; drag a zoom's frame to aim it.
  // While a zoom is selected and paused, the preview shows the whole picture
  // so the frame can be seen against it (StudioEditor leaves that zoom out).
  import type { Effect } from '$lib/utils/video-edits';
  import { useStudio } from './studio';

  export let effect: Effect;
  export let index: number;
  // The picture's framing (CSS transform) a blur box sits in.
  export let picture = '';

  const st = useStudio();
  let box: HTMLDivElement;

  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  const r1 = (v: number) => Math.round(v * 10) / 10;

  type Grab = { mode: 'move' | 'size'; x0: number; y0: number; orig: Effect };
  let grab: Grab | null = null;

  function down(e: PointerEvent, mode: Grab['mode']) {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    const r = box.getBoundingClientRect();
    grab = { mode, x0: ((e.clientX - r.left) / r.width) * 100, y0: ((e.clientY - r.top) / r.height) * 100, orig: { ...effect } };
    st.begin();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }

  function move(e: PointerEvent) {
    if (!grab) return;
    const r = box.getBoundingClientRect();
    const dx = ((e.clientX - r.left) / r.width) * 100 - grab.x0;
    const dy = ((e.clientY - r.top) / r.height) * 100 - grab.y0;
    const o = grab.orig;
    st.live(d => {
      const ef = d.edits.effects[index];
      if (!ef) return;
      if (ef.kind === 'zoom') {
        // The frame's left edge is x(1 - 1/scale): move the edge, solve for x.
        const k = 1 - 1 / (o.scale ?? 1.4);
        const left = clamp((o.x ?? 50) * k + dx, 0, 100 * k);
        const top = clamp((o.y ?? 50) * k + dy, 0, 100 * k);
        ef.x = r1(k ? left / k : 50);
        ef.y = r1(k ? top / k : 50);
      } else if (grab!.mode === 'move') {
        ef.x = r1(clamp((o.x ?? 0) + dx, 0, 100 - (o.w ?? 20)));
        ef.y = r1(clamp((o.y ?? 0) + dy, 0, 100 - (o.h ?? 20)));
      } else {
        ef.w = r1(clamp((o.w ?? 20) + dx, 2, 100 - (o.x ?? 0)));
        ef.h = r1(clamp((o.h ?? 20) + dy, 2, 100 - (o.y ?? 0)));
      }
    });
  }

  function up() {
    if (!grab) return;
    grab = null;
    st.end();
  }

  $: zoomW = 100 / (effect.scale ?? 1.4);
  $: zoomL = (effect.x ?? 50) * (1 - 1 / (effect.scale ?? 1.4));
  $: zoomT = (effect.y ?? 50) * (1 - 1 / (effect.scale ?? 1.4));
</script>

<div class="space" bind:this={box} style={effect.kind === 'blur' ? picture : ''}>
  {#if effect.kind === 'blur'}
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="bx blur" style="left:{effect.x ?? 0}%; top:{effect.y ?? 0}%; width:{effect.w ?? 20}%; height:{effect.h ?? 20}%"
      on:pointerdown={e => down(e, 'move')} on:pointermove={move} on:pointerup={up} on:pointercancel={up}>
      <span class="tag">Blur · drag to move</span>
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <span class="corner" on:pointerdown={e => down(e, 'size')} on:pointermove={move} on:pointerup={up} on:pointercancel={up}></span>
    </div>
  {:else}
    <div class="dim" style="--l:{zoomL}%; --t:{zoomT}%; --w:{zoomW}%"></div>
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="bx zoom" style="left:{zoomL}%; top:{zoomT}%; width:{zoomW}%; height:{zoomW}%"
      on:pointerdown={e => down(e, 'move')} on:pointermove={move} on:pointerup={up} on:pointercancel={up}>
      <span class="tag">Zoom {(effect.scale ?? 1.4).toFixed(2)}× · drag to aim</span>
    </div>
  {/if}
</div>

<style>
  .space { position: absolute; inset: 0; z-index: 9; pointer-events: none; }
  .bx { position: absolute; pointer-events: auto; cursor: move; touch-action: none; border-radius: 4px; }
  .bx.blur { outline: 2px dashed #fff; box-shadow: 0 0 0 1px rgba(0,0,0,.6); }
  .bx.zoom { outline: 2px solid #6ea8ff; box-shadow: 0 0 0 1px rgba(0,0,0,.5); }
  .dim { position: absolute; inset: 0; pointer-events: none;
    background: rgba(0,0,0,.45);
    clip-path: polygon(0 0, 100% 0, 100% 100%, 0 100%, 0 0,
      var(--l) var(--t), var(--l) calc(var(--t) + var(--w)), calc(var(--l) + var(--w)) calc(var(--t) + var(--w)), calc(var(--l) + var(--w)) var(--t), var(--l) var(--t)); }
  .tag { position: absolute; left: 0; top: -22px; white-space: nowrap; font-size: 0.68rem; font-weight: 700; padding: 2px 6px; border-radius: 5px; background: rgba(0,0,0,.75); color: #fff; pointer-events: none; }
  .corner { position: absolute; right: -6px; bottom: -6px; width: 14px; height: 14px; border-radius: 3px; background: #fff; box-shadow: 0 0 0 1px #000; cursor: nwse-resize; }
</style>
