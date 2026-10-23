<script lang="ts">
  // The studio's timeline: the whole video, with a lane each for the kept
  // part (trim, splits, cuts), chapters, text overlays, effects and the
  // transcript.
  // Everything on it can be dragged; drags snap to the playhead, transcript
  // lines and other edits (hold Alt to place freely).
  import { onDestroy } from 'svelte';
  import { clock } from '$lib/utils/transcribe';
  import { EFFECT_NAMES, MIN_PART, round, useStudio, type Doc } from './studio';

  const st = useStudio();
  const { doc, parts, time, mark, selected, preview, playing, ep } = st;
  const L = st.length || 1;

  let scroller: HTMLDivElement;
  let inner: HTMLDivElement;
  let innerW = 1000;
  let zoom = 1;
  const MAX_ZOOM = Math.max(1, Math.min(80, L / 15));
  $: pps = innerW / L; // pixels per second
  const pct = (x: number) => (x / L) * 100;

  // Ruler: a tick step that leaves room for its label.
  const STEPS = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
  $: step = STEPS.find(s => s * pps >= 64) ?? 3600;
  $: ticks = Array.from({ length: Math.floor(L / step) + 1 }, (_, i) => i * step);

  $: segs = $doc.segments;
  $: sel = $selected;
  $: d = $doc;
  $: sortedSplits = [...d.splits].sort((a, b) => a - b);
  $: markLo = $mark.in !== null && $mark.out !== null ? Math.min($mark.in, $mark.out) : null;
  $: markHi = $mark.in !== null && $mark.out !== null ? Math.max($mark.in, $mark.out) : null;

  function timeAt(clientX: number) {
    const r = inner.getBoundingClientRect();
    return Math.min(L, Math.max(0, ((clientX - r.left) / r.width) * L));
  }

  // ---- snapping --------------------------------------------------------------
  function snapPoints(skip: (x: number) => boolean): number[] {
    const pts = [$time, d.start, d.end, ...d.splits];
    for (const s of segs) pts.push(s.start, s.end);
    for (const c of d.edits.cuts) pts.push(c.start, c.end);
    for (const c of d.edits.chapters) pts.push(c.start);
    for (const o of d.edits.overlays) pts.push(o.start, o.end);
    for (const e of d.edits.effects) pts.push(e.start, e.end);
    return pts.filter(x => !skip(x));
  }
  let snapAt: number | null = null;
  function snap(x: number, e: PointerEvent, skip: (x: number) => boolean = () => false): number {
    snapAt = null;
    if (e.altKey) return round(x);
    const tol = 7 / pps;
    let best = x, bestD = tol;
    for (const p of snapPoints(skip)) {
      const dd = Math.abs(p - x);
      if (dd < bestD) { best = p; bestD = dd; }
    }
    if (best !== x) snapAt = best;
    return round(best);
  }

  // ---- dragging ---------------------------------------------------------------
  type Drag =
    | { kind: 'scrub' }
    | { kind: 'select'; from: number }
    | { kind: 'start' }
    | { kind: 'end' }
    | { kind: 'split'; value: number }
    | { kind: 'cut-start' | 'cut-end' | 'cut-move'; index: number; grab: number; orig: { start: number; end: number } }
    | { kind: 'chapter'; index: number }
    | { kind: 'ov-start' | 'ov-end' | 'ov-move'; index: number; grab: number; orig: { start: number; end: number } }
    | { kind: 'ef-start' | 'ef-end' | 'ef-move'; index: number; grab: number; orig: { start: number; end: number } };
  let drag: Drag | null = null;
  let moved = false;

  function grab(e: PointerEvent, g: Drag) {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    drag = g;
    moved = false;
    if (g.kind !== 'scrub' && g.kind !== 'select') { st.begin(); st.stopPreview(); }
    if (g.kind === 'scrub') st.seek(timeAt(e.clientX));
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
  }

  function onMove(e: PointerEvent) {
    if (!drag) return;
    moved = true;
    const raw = timeAt(e.clientX);
    const g = drag;
    if (g.kind === 'scrub') { st.seek(raw); return; }
    if (g.kind === 'select') { mark.set({ in: g.from, out: snap(raw, e) }); return; }
    st.live((dd: Doc) => {
      if (g.kind === 'start') {
        dd.start = Math.max(0, Math.min(snap(raw, e, x => x === dd.start), dd.end - MIN_PART));
        dd.splits = dd.splits.filter(s => s > dd.start + 0.01);
      } else if (g.kind === 'end') {
        dd.end = Math.min(L, Math.max(snap(raw, e, x => x === dd.end), dd.start + MIN_PART));
        dd.splits = dd.splits.filter(s => s < dd.end - 0.01);
      } else if (g.kind === 'split') {
        const v = Math.min(dd.end - MIN_PART, Math.max(dd.start + MIN_PART, snap(raw, e, x => x === g.value)));
        dd.splits = dd.splits.map(s => (s === g.value ? v : s));
        drag = { kind: 'split', value: v };
      } else if (g.kind === 'chapter') {
        const c = dd.edits.chapters[g.index];
        if (c) c.start = snap(raw, e, x => x === c.start);
      } else if (g.kind === 'cut-start' || g.kind === 'cut-end' || g.kind === 'cut-move') {
        const c = dd.edits.cuts[g.index];
        if (!c) return;
        if (g.kind === 'cut-start') c.start = Math.min(snap(raw, e, x => x === c.start), c.end - 0.5);
        else if (g.kind === 'cut-end') c.end = Math.max(snap(raw, e, x => x === c.end), c.start + 0.5);
        else {
          const len = g.orig.end - g.orig.start;
          const s0 = Math.min(L - len, Math.max(0, snap(g.orig.start + raw - g.grab, e, x => x === c.start)));
          c.start = round(s0); c.end = round(s0 + len);
        }
      } else if (g.kind === 'ef-start' || g.kind === 'ef-end' || g.kind === 'ef-move') {
        const ef = dd.edits.effects[g.index];
        if (!ef) return;
        if (g.kind === 'ef-start') ef.start = Math.max(0, Math.min(snap(raw, e, x => x === ef.start), ef.end - 0.5));
        else if (g.kind === 'ef-end') ef.end = Math.min(L, Math.max(snap(raw, e, x => x === ef.end), ef.start + 0.5));
        else {
          const len = g.orig.end - g.orig.start;
          const s0 = Math.min(L - len, Math.max(0, snap(g.orig.start + raw - g.grab, e, x => x === ef.start)));
          ef.start = round(s0); ef.end = round(s0 + len);
        }
      } else {
        const o = dd.edits.overlays[g.index];
        if (!o) return;
        if (g.kind === 'ov-start') o.start = Math.max(0, Math.min(snap(raw, e, x => x === o.start), o.end - 0.5));
        else if (g.kind === 'ov-end') o.end = Math.min(L, Math.max(snap(raw, e, x => x === o.end), o.start + 0.5));
        else {
          const len = g.orig.end - g.orig.start;
          const s0 = Math.min(L - len, Math.max(0, snap(g.orig.start + raw - g.grab, e, x => x === o.start)));
          o.start = round(s0); o.end = round(s0 + len);
        }
      }
    });
  }

  function onUp() {
    window.removeEventListener('pointermove', onMove);
    const g = drag;
    drag = null;
    snapAt = null;
    if (!g) return;
    if (g.kind === 'select' && !moved) { mark.set({ in: null, out: null }); return; }
    if (g.kind !== 'scrub' && g.kind !== 'select') {
      // Keep the lists in time order once a drag settles.
      st.live(dd => {
        dd.edits.chapters.sort((a, b) => a.start - b.start);
        if (g.kind.startsWith('cut')) dd.edits.cuts.sort((a, b) => a.start - b.start);
        if (g.kind === 'ef-start' || g.kind === 'ef-end' || g.kind === 'ef-move') {
          // Keep the dragged effect selected once the list is back in order.
          const moving = dd.edits.effects[g.index];
          dd.edits.effects.sort((a, b) => a.start - b.start);
          selected.set({ kind: 'effect', index: dd.edits.effects.indexOf(moving) });
        }
      });
      st.end();
    }
  }
  onDestroy(() => window.removeEventListener('pointermove', onMove));

  function laneDown(e: PointerEvent) {
    if (e.button !== 0) return;
    selected.set(null);
    // Shift-drag marks a range; a plain press scrubs.
    if (e.shiftKey) grab(e, { kind: 'select', from: snap(timeAt(e.clientX), e) });
    else grab(e, { kind: 'scrub' });
  }

  function pick(kind: 'cut' | 'chapter' | 'overlay' | 'effect', index: number) {
    selected.set({ kind, index });
    if (kind !== 'cut') st.tab.set(kind === 'chapter' ? 'chapters' : kind === 'effect' ? 'effects' : 'text');
  }

  // ---- zoom and follow ----------------------------------------------------------
  function setZoom(z: number, anchorX?: number) {
    const before = anchorX !== undefined ? timeAt(anchorX) : $time;
    zoom = Math.min(MAX_ZOOM, Math.max(1, z));
    requestAnimationFrame(() => {
      if (!scroller || !inner) return;
      const r = scroller.getBoundingClientRect();
      const offset = anchorX !== undefined ? anchorX - r.left : r.width / 2;
      scroller.scrollLeft = (before / L) * inner.clientWidth - offset;
    });
  }
  function onWheel(e: WheelEvent) {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    setZoom(zoom * (e.deltaY < 0 ? 1.25 : 0.8), e.clientX);
  }
  export function zoomIn() { setZoom(zoom * 1.5); }
  export function zoomOut() { setZoom(zoom / 1.5); }
  export function fit() { setZoom(1); }

  $: if ($playing && scroller && zoom > 1 && !drag) {
    const x = ($time / L) * innerW;
    if (x < scroller.scrollLeft || x > scroller.scrollLeft + scroller.clientWidth - 40) {
      scroller.scrollLeft = x - scroller.clientWidth * 0.1;
    }
  }

  const inCut = (a: number, b: number) => d.edits.cuts.some(c => c.start <= a + 0.05 && c.end >= b - 0.05);
</script>

<div class="tl">
  <div class="tl-bar">
    <span class="hint">Drag the edges and markers. <kbd>Shift</kbd>-drag to mark a range, <kbd>Alt</kbd> to place without snapping, <kbd>Ctrl</kbd>+scroll to zoom.</span>
    <span class="zoom">
      <button class="z" on:click={zoomOut} disabled={zoom <= 1} aria-label="Zoom out">−</button>
      <input type="range" min="1" max={MAX_ZOOM} step="0.1" value={zoom} on:input={e => setZoom(+e.currentTarget.value)} aria-label="Timeline zoom" />
      <button class="z" on:click={zoomIn} disabled={zoom >= MAX_ZOOM} aria-label="Zoom in">+</button>
      <button class="z fit" on:click={fit} disabled={zoom <= 1}>Fit</button>
    </span>
  </div>
  <div class="tl-body">
    <div class="labels">
      <span class="lab ruler-lab"></span>
      <span class="lab">Video</span>
      <span class="lab">Chapters</span>
      <span class="lab">Text</span>
      <span class="lab">Effects</span>
      <span class="lab">Captions</span>
    </div>
    <div class="scroller" bind:this={scroller} on:wheel={onWheel}>
      <div class="inner" bind:this={inner} bind:clientWidth={innerW} style="width:{zoom * 100}%">
        <!-- ruler -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div class="ruler" on:pointerdown={e => grab(e, { kind: 'scrub' })}>
          {#each ticks as tk}
            <span class="tick" style="left:{pct(tk)}%"><span>{step < 1 ? tk.toFixed(1) : clock(tk)}</span></span>
          {/each}
        </div>

        <!-- video lane -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div class="lane video" on:pointerdown={laneDown}>
          <div class="kept" style="left:{pct(d.start)}%; width:{pct(d.end - d.start)}%"></div>
          {#each $parts as p, i}
            <span class="plabel" class:bad={p.played < MIN_PART} style="left:{pct(p.from)}%; width:{pct(p.len)}%">
              {$parts.length > 1 ? `Part ${i + 1} · ` : ''}{clock(p.played)}
            </span>
          {/each}
          {#each d.edits.cuts as c, i}
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div class="cut" class:sel={sel?.kind === 'cut' && sel.index === i} style="left:{pct(c.start)}%; width:{pct(c.end - c.start)}%"
              on:pointerdown={e => { pick('cut', i); grab(e, { kind: 'cut-move', index: i, grab: timeAt(e.clientX), orig: { ...c } }); }}
              title="Cut {clock(c.start)} – {clock(c.end)}: learners skip this">
              <span class="edge l" on:pointerdown={e => { pick('cut', i); grab(e, { kind: 'cut-start', index: i, grab: 0, orig: { ...c } }); }}></span>
              <span class="edge r" on:pointerdown={e => { pick('cut', i); grab(e, { kind: 'cut-end', index: i, grab: 0, orig: { ...c } }); }}></span>
            </div>
          {/each}
          {#each sortedSplits as sp (sp)}
            <button class="split" style="left:{pct(sp)}%" on:pointerdown={e => grab(e, { kind: 'split', value: sp })}
              aria-label="Split at {clock(sp)}; drag to move" title="Split at {clock(sp)}"></button>
          {/each}
          <button class="handle hs" style="left:{pct(d.start)}%" on:pointerdown={e => grab(e, { kind: 'start' })}
            aria-label="Start, {clock(d.start)}; drag to move" title="Starts at {clock(d.start)}"></button>
          <button class="handle he" style="left:{pct(d.end)}%" on:pointerdown={e => grab(e, { kind: 'end' })}
            aria-label="End, {clock(d.end)}; drag to move" title="Ends at {clock(d.end)}"></button>
        </div>

        <!-- chapters lane -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div class="lane chapters" on:pointerdown={laneDown}>
          {#each d.edits.chapters as c, i}
            <button class="flag" class:sel={sel?.kind === 'chapter' && sel.index === i} style="left:{pct(c.start)}%"
              on:pointerdown={e => { pick('chapter', i); grab(e, { kind: 'chapter', index: i }); }} title="{clock(c.start)} {c.title}">
              <span>{c.title}</span>
            </button>
          {/each}
        </div>

        <!-- text lane -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div class="lane text" on:pointerdown={laneDown}>
          {#each d.edits.overlays as o, i}
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div class="block st-{o.style}" class:sel={sel?.kind === 'overlay' && sel.index === i}
              style="left:{pct(o.start)}%; width:{pct(o.end - o.start)}%" title={o.text}
              on:pointerdown={e => { pick('overlay', i); grab(e, { kind: 'ov-move', index: i, grab: timeAt(e.clientX), orig: { ...o } }); }}>
              <span class="btxt">{o.text}</span>
              <span class="edge l" on:pointerdown={e => { pick('overlay', i); grab(e, { kind: 'ov-start', index: i, grab: 0, orig: { ...o } }); }}></span>
              <span class="edge r" on:pointerdown={e => { pick('overlay', i); grab(e, { kind: 'ov-end', index: i, grab: 0, orig: { ...o } }); }}></span>
            </div>
          {/each}
        </div>

        <!-- effects lane: zoom and blur on top, speed and mute below -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div class="lane effects" on:pointerdown={laneDown}>
          {#each d.edits.effects as ef, i}
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div class="fx k-{ef.kind}" class:low={ef.kind === 'speed' || ef.kind === 'mute'} class:sel={sel?.kind === 'effect' && sel.index === i}
              style="left:{pct(ef.start)}%; width:{pct(ef.end - ef.start)}%"
              title="{EFFECT_NAMES[ef.kind]} {clock(ef.start)} – {clock(ef.end)}"
              on:pointerdown={e => { pick('effect', i); grab(e, { kind: 'ef-move', index: i, grab: timeAt(e.clientX), orig: { ...ef } }); }}>
              <span class="btxt">{EFFECT_NAMES[ef.kind]}{ef.kind === 'speed' ? ` ${ef.rate}×` : ef.kind === 'zoom' ? ` ${(ef.scale ?? 1.4).toFixed(1)}×` : ''}</span>
              <span class="edge l" on:pointerdown={e => { pick('effect', i); grab(e, { kind: 'ef-start', index: i, grab: 0, orig: { ...ef } }); }}></span>
              <span class="edge r" on:pointerdown={e => { pick('effect', i); grab(e, { kind: 'ef-end', index: i, grab: 0, orig: { ...ef } }); }}></span>
            </div>
          {/each}
        </div>

        <!-- captions lane -->
        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <div class="lane caps" on:pointerdown={laneDown}>
          {#each segs as sgm}
            <span class="seg" class:gone={inCut(sgm.start, sgm.end)} class:out={sgm.end <= d.start || sgm.start >= d.end}
              style="left:{pct(sgm.start)}%; width:{pct(Math.max(0.4, sgm.end - sgm.start))}%" title={sgm.text}>{sgm.text}</span>
          {/each}
          {#if !segs.length}<span class="empty">No transcript yet: captions, AI and transcript cutting use it.</span>{/if}
        </div>

        <!-- overlays across every lane -->
        <div class="over">
          {#if markLo !== null && markHi !== null}
            <div class="markband" style="left:{pct(markLo)}%; width:{pct(markHi - markLo)}%"></div>
          {:else if $mark.in !== null}
            <div class="markpin" style="left:{pct($mark.in)}%"></div>
          {/if}
          {#if $preview}<div class="prange" style="left:{pct($preview.from)}%; width:{pct($preview.to - $preview.from)}%"></div>{/if}
          {#if snapAt !== null}<div class="snapline" style="left:{pct(snapAt)}%"></div>{/if}
          <div class="playhead" style="left:{pct($time)}%"><span class="ph-cap"></span></div>
        </div>
      </div>
    </div>
  </div>
</div>

<style>
  .tl { display: grid; gap: 0.35rem; user-select: none; }
  .tl-bar { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; }
  .hint { font-size: 0.72rem; color: var(--st-muted); }
  kbd { font: inherit; font-size: 0.68rem; padding: 0 0.3em; border: 1px solid var(--st-line); border-radius: 4px; background: var(--st-raise); }
  .zoom { display: inline-flex; align-items: center; gap: 0.35rem; }
  .zoom input { width: 120px; accent-color: var(--st-hot); }
  .z { min-width: 26px; height: 24px; border-radius: 6px; background: var(--st-raise); color: var(--st-text); font-weight: 700; font-size: 0.8rem; padding: 0 0.4rem; }
  .z:disabled { opacity: 0.4; }
  .z.fit { font-size: 0.7rem; }

  .tl-body { display: grid; grid-template-columns: 74px 1fr; border: 1px solid var(--st-line); border-radius: 10px; overflow: hidden; background: var(--st-deep); }
  .labels { display: grid; grid-template-rows: 22px 56px 30px 34px 36px 30px; border-right: 1px solid var(--st-line); }
  .lab { font-size: 0.66rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--st-muted); padding: 0 0.55rem; display: flex; align-items: center; border-top: 1px solid var(--st-line); }
  .ruler-lab { border-top: 0; }
  .scroller { overflow-x: auto; overflow-y: hidden; scrollbar-width: thin; }
  .inner { position: relative; display: grid; grid-template-rows: 22px 56px 30px 34px 36px 30px; min-width: 100%; }

  .ruler { position: relative; cursor: ew-resize; background: var(--st-panel); }
  .tick { position: absolute; top: 0; bottom: 0; border-left: 1px solid var(--st-line); }
  .tick span { position: absolute; left: 4px; top: 3px; font-size: 0.64rem; color: var(--st-muted); white-space: nowrap; font-variant-numeric: tabular-nums; }

  .lane { position: relative; border-top: 1px solid var(--st-line); cursor: text; touch-action: none; }
  .video { background: repeating-linear-gradient(135deg, rgba(255,255,255,.035) 0 7px, transparent 7px 14px); }
  .kept { position: absolute; top: 6px; bottom: 6px; border-radius: 6px; background: linear-gradient(180deg, #2f4f8a, #263f6e); box-shadow: inset 0 0 0 1px #6ea8ff; }
  .plabel { position: absolute; top: 50%; translate: 0 -50%; text-align: center; font-size: 0.7rem; font-weight: 700; color: #dbe7ff; pointer-events: none; white-space: nowrap; overflow: hidden; font-variant-numeric: tabular-nums; }
  .plabel.bad { color: #ff9196; }
  .cut { position: absolute; top: 6px; bottom: 6px; z-index: 2; border-radius: 4px; cursor: grab;
    background: repeating-linear-gradient(135deg, rgba(255,77,94,.55) 0 5px, rgba(80,10,20,.75) 5px 10px); box-shadow: inset 0 0 0 1px #ff4d5e; }
  .cut.sel { box-shadow: inset 0 0 0 2px #fff, 0 0 0 1px #ff4d5e; }
  .edge { position: absolute; top: 0; bottom: 0; width: 8px; cursor: ew-resize; }
  .edge.l { left: -4px; } .edge.r { right: -4px; }
  .split { position: absolute; top: 0; bottom: 0; width: 6px; translate: -50% 0; border-radius: 3px; background: #f5c518; cursor: ew-resize; z-index: 3; }
  .split::after { content: ''; position: absolute; left: 50%; top: -1px; translate: -50% 0; border: 5px solid transparent; border-top-color: #fff3b0; }
  .handle { position: absolute; top: 2px; bottom: 2px; width: 12px; translate: -50% 0; border-radius: 4px; background: #6ea8ff; cursor: ew-resize; z-index: 3; box-shadow: 0 0 0 2px var(--st-deep); }
  .handle::after { content: ''; position: absolute; inset: 35% 4px; border-left: 1px solid rgba(0,0,0,.45); border-right: 1px solid rgba(0,0,0,.45); }

  .flag { position: absolute; top: 4px; bottom: 4px; max-width: 160px; padding: 0 0.45rem 0 0.4rem; border-left: 2px solid #b48bff; border-radius: 0 6px 6px 0;
    background: rgba(180,139,255,.18); color: #e6dbff; font-size: 0.68rem; font-weight: 700; cursor: grab; display: flex; align-items: center; overflow: hidden; z-index: 2; }
  .flag span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .flag.sel { background: rgba(180,139,255,.45); color: #fff; }

  .block { position: absolute; top: 4px; bottom: 4px; border-radius: 6px; cursor: grab; display: flex; align-items: center; padding: 0 0.45rem; overflow: hidden; z-index: 2;
    background: rgba(255,210,63,.22); box-shadow: inset 0 0 0 1px #ffd23f; color: #fff1bf; }
  .block.st-title { background: rgba(255,255,255,.16); box-shadow: inset 0 0 0 1px #fff; color: #fff; }
  .block.st-label { background: rgba(229,9,20,.25); box-shadow: inset 0 0 0 1px #ff4d5e; color: #ffd5d8; }
  .block.st-quote { background: rgba(126,240,168,.2); box-shadow: inset 0 0 0 1px #7ef0a8; color: #d8ffe6; }
  .block.sel { box-shadow: inset 0 0 0 2px #fff; }
  .btxt { font-size: 0.68rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; pointer-events: none; }

  .fx { position: absolute; top: 3px; height: 14px; border-radius: 4px; cursor: grab; display: flex; align-items: center; padding: 0 0.35rem; overflow: hidden; z-index: 2;
    background: color-mix(in srgb, var(--k) 28%, transparent); box-shadow: inset 0 0 0 1px var(--k); color: #fff; }
  .fx.low { top: 19px; }
  .fx.sel { box-shadow: inset 0 0 0 2px #fff; }
  .fx .btxt { font-size: 0.6rem; }
  .fx.k-zoom { --k: #6ea8ff; } .fx.k-speed { --k: #ffb057; } .fx.k-mute { --k: #b48bff; } .fx.k-blur { --k: #7ef0a8; }
  .seg { position: absolute; top: 5px; bottom: 5px; border-radius: 3px; background: rgba(255,255,255,.1); color: var(--st-muted); font-size: 0.6rem; line-height: 20px; padding: 0 3px; overflow: hidden; white-space: nowrap; pointer-events: none; box-shadow: inset 1px 0 0 rgba(255,255,255,.25); }
  .seg.out { opacity: 0.4; }
  .seg.gone { text-decoration: line-through; background: rgba(255,77,94,.15); color: #ff9196; }
  .empty { position: absolute; left: 8px; top: 50%; translate: 0 -50%; font-size: 0.68rem; color: var(--st-muted); }

  .over { position: absolute; inset: 0; pointer-events: none; }
  .markband { position: absolute; top: 22px; bottom: 0; background: rgba(110,168,255,.16); border-left: 1px solid #6ea8ff; border-right: 1px solid #6ea8ff; }
  .markpin { position: absolute; top: 22px; bottom: 0; border-left: 1px dashed #6ea8ff; }
  .prange { position: absolute; top: 0; height: 22px; background: rgba(245,197,24,.35); }
  .snapline { position: absolute; top: 0; bottom: 0; border-left: 1px solid #7ef0a8; }
  .playhead { position: absolute; top: 0; bottom: 0; width: 2px; translate: -50% 0; background: var(--st-hot); z-index: 5; }
  .ph-cap { position: absolute; top: 0; left: 50%; translate: -50% 0; width: 12px; height: 12px; background: var(--st-hot); clip-path: polygon(0 0, 100% 0, 100% 55%, 50% 100%, 0 55%); }
</style>
