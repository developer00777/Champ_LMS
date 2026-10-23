<script lang="ts">
  // The studio's timeline, InShot style: the playhead stays in the middle and
  // the video scrolls under it. Drag the background (or scroll) to move
  // through the video; Ctrl+scroll or the slider zooms. A lane each for the
  // video (a filmstrip with the kept part, splits and cuts), chapters, text
  // and stickers, effects, music and voice, and the transcript.
  // Everything on it can be dragged; drags snap to the playhead, transcript
  // lines and other edits (hold Alt to place freely).
  import { onDestroy } from 'svelte';
  import { clock } from '$lib/utils/transcribe';
  import { playedLength, type AudioTrack } from '$lib/utils/video-edits';
  import { EFFECT_NAMES, MIN_PART, round, useStudio, type Doc } from './studio';
  import Filmstrip from './Filmstrip.svelte';

  const st = useStudio();
  const { doc, parts, time, mark, selected, preview, source } = st;
  const L = st.length || 1;

  let scroller: HTMLDivElement;
  let inner: HTMLDivElement;
  let viewW = 1000;
  // Start close in, about a minute and a half across, like a phone editor.
  const MAX_ZOOM = Math.max(1, Math.min(400, L / 8));
  let zoom = Math.min(MAX_ZOOM, Math.max(1, L / 90));
  $: innerW = Math.max(1, viewW * zoom);
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

  // ---- the centre playhead: scroll position is time -------------------------
  // Half a view of padding either side, so 0 and the end can reach the middle.
  let lastSet = -1;
  let viewLeft = 0;
  function follow(t: number, perSecond: number) {
    if (!scroller || drag?.kind === 'pan') return;
    const x = t * perSecond;
    if (Math.abs(scroller.scrollLeft - x) > 0.5) {
      scroller.scrollLeft = x;
      lastSet = scroller.scrollLeft;
    }
    viewLeft = scroller.scrollLeft;
  }
  $: follow($time, pps);
  function onScroll() {
    viewLeft = scroller.scrollLeft;
    if (Math.abs(viewLeft - lastSet) <= 1) return; // our own follow()
    lastSet = viewLeft;
    st.pause();
    st.seek(viewLeft / pps);
  }
  // What's in view, in seconds, for the filmstrip.
  $: viewFrom = Math.max(0, (viewLeft - viewW / 2) / pps);
  $: viewTo = Math.min(L, (viewLeft + viewW / 2) / pps);

  // ---- snapping --------------------------------------------------------------
  function snapPoints(skip: (x: number) => boolean): number[] {
    const pts = [$time, d.start, d.end, ...d.splits];
    for (const s of segs) pts.push(s.start, s.end);
    for (const c of d.edits.cuts) pts.push(c.start, c.end);
    for (const c of d.edits.chapters) pts.push(c.start);
    for (const o of d.edits.overlays) pts.push(o.start, o.end);
    for (const e of d.edits.effects) pts.push(e.start, e.end);
    for (const tr of d.edits.audio.tracks) pts.push(tr.start);
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
  type Range = { start: number; end: number };
  type Drag =
    | { kind: 'pan'; x0: number; left0: number; at: number }
    | { kind: 'select'; from: number }
    | { kind: 'start' }
    | { kind: 'end' }
    | { kind: 'split'; value: number }
    | { kind: 'cut-start' | 'cut-end' | 'cut-move'; index: number; grab: number; orig: Range }
    | { kind: 'chapter'; index: number }
    | { kind: 'ov-start' | 'ov-end' | 'ov-move'; index: number; grab: number; orig: Range }
    | { kind: 'ef-start' | 'ef-end' | 'ef-move'; index: number; grab: number; orig: Range }
    | { kind: 'au-move'; index: number; grab: number; orig: { start: number } };
  let drag: Drag | null = null;
  let moved = false;

  function grab(e: PointerEvent, g: Drag) {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    drag = g;
    moved = false;
    if (g.kind !== 'pan' && g.kind !== 'select') { st.begin(); st.stopPreview(); }
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
  }

  function onMove(e: PointerEvent) {
    if (!drag) return;
    const g = drag;
    if (g.kind === 'pan') {
      // Drag the video under the playhead, like a phone editor.
      if (!moved && Math.abs(e.clientX - g.x0) < 3) return;
      moved = true;
      scroller.scrollLeft = g.left0 - (e.clientX - g.x0);
      return;
    }
    moved = true;
    const raw = timeAt(e.clientX);
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
      } else if (g.kind === 'au-move') {
        const tr = dd.edits.audio.tracks[g.index];
        if (tr) tr.start = Math.max(0, Math.min(L - 0.5, snap(g.orig.start + raw - g.grab, e, x => x === tr.start)));
      } else {
        const list: Range[] = g.kind.startsWith('cut') ? dd.edits.cuts : g.kind.startsWith('ef') ? dd.edits.effects : dd.edits.overlays;
        const r = list[g.index];
        if (!r) return;
        const min = g.kind.startsWith('cut') ? -Infinity : 0, max = g.kind.startsWith('cut') ? Infinity : L;
        if (g.kind.endsWith('start')) r.start = Math.max(min, Math.min(snap(raw, e, x => x === r.start), r.end - 0.5));
        else if (g.kind.endsWith('end')) r.end = Math.min(max, Math.max(snap(raw, e, x => x === r.end), r.start + 0.5));
        else {
          const len = g.orig.end - g.orig.start;
          const s0 = Math.min(L - len, Math.max(0, snap(g.orig.start + raw - g.grab, e, x => x === r.start)));
          r.start = round(s0); r.end = round(s0 + len);
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
    if (g.kind === 'pan') {
      // A tap, not a drag: go to where it landed.
      if (!moved) st.seek(g.at);
      return;
    }
    if (g.kind === 'select') { if (!moved) mark.set({ in: null, out: null }); return; }
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
  onDestroy(() => window.removeEventListener('pointermove', onMove));

  function laneDown(e: PointerEvent) {
    if (e.button !== 0) return;
    selected.set(null);
    // Shift-drag marks a range; a plain press pans (or, as a tap, jumps there).
    if (e.shiftKey) grab(e, { kind: 'select', from: snap(timeAt(e.clientX), e) });
    else grab(e, { kind: 'pan', x0: e.clientX, left0: scroller.scrollLeft, at: timeAt(e.clientX) });
  }

  function pick(kind: 'cut' | 'chapter' | 'overlay' | 'effect', index: number) {
    selected.set({ kind, index });
    if (kind === 'chapter') st.tab.set('chapters');
    else if (kind === 'overlay') st.tab.set(d.edits.overlays[index]?.style === 'sticker' ? 'sticker' : 'text');
    else if (kind === 'effect') {
      const k = d.edits.effects[index]?.kind;
      st.tab.set(k === 'speed' || k === 'freeze' ? 'speed' : 'effects');
    }
  }

  // ---- zoom ---------------------------------------------------------------------
  // The playhead stays put in the middle; follow() recentres at the new scale.
  function setZoom(z: number) { zoom = Math.min(MAX_ZOOM, Math.max(1, z)); }
  function onWheel(e: WheelEvent) {
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) setZoom(zoom * (e.deltaY < 0 ? 1.2 : 1 / 1.2));
    else scroller.scrollLeft += Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
  }

  // Where a track stops on the timeline: it runs in watch time, so cuts and
  // speed changes stretch or shrink it here.
  function trackEnd(tr: AudioTrack): number {
    if (tr.loop) return Math.max(tr.start + 0.5, d.end);
    let lo = tr.start, hi = L;
    if (playedLength(d.edits, tr.start, hi) < tr.duration) return hi;
    for (let n = 0; n < 24; n++) {
      const mid = (lo + hi) / 2;
      if (playedLength(d.edits, tr.start, mid) < tr.duration) lo = mid; else hi = mid;
    }
    return hi;
  }

  // Text and stickers that overlap in time stack in two rows, so neither hides the other.
  $: ovRow = (() => {
    const ends = [-Infinity, -Infinity];
    const rows: number[] = [];
    d.edits.overlays.map((o, i) => ({ o, i })).sort((a, b) => a.o.start - b.o.start).forEach(({ o, i }) => {
      const r = ends[0] <= o.start + 0.01 ? 0 : ends[1] <= o.start + 0.01 ? 1 : ends[0] <= ends[1] ? 0 : 1;
      rows[i] = r;
      ends[r] = Math.max(ends[r], o.end);
    });
    return rows;
  })();
  $: ovStacked = ovRow.some(r => r === 1);

  const inCut = (a: number, b: number) => d.edits.cuts.some(c => c.start <= a + 0.05 && c.end >= b - 0.05);
  const FX_NAMES: Record<string, string> = { shake: 'Shake', glitch: 'Glitch', analog: 'Analog', dizzy: 'Dizzy', flash: 'Flash', defocus: 'Defocus', pulse: 'Pulse' };
</script>

<div class="tl">
  <div class="tl-bar">
    <span class="hint">Drag the timeline to move through the video. Drag edges and blocks to edit. <kbd>Shift</kbd>-drag marks a range, <kbd>Alt</kbd> places without snapping, <kbd>Ctrl</kbd>+scroll zooms.</span>
    <span class="zoom">
      <button class="z" on:click={() => setZoom(zoom / 1.5)} disabled={zoom <= 1} aria-label="Zoom out">−</button>
      <input type="range" min="0" max="1" step="0.001" value={Math.log(zoom) / Math.log(MAX_ZOOM || 1) || 0}
        on:input={e => setZoom(Math.pow(MAX_ZOOM, +e.currentTarget.value))} aria-label="Timeline zoom" />
      <button class="z" on:click={() => setZoom(zoom * 1.5)} disabled={zoom >= MAX_ZOOM} aria-label="Zoom in">+</button>
      <button class="z fit" on:click={() => setZoom(1)} disabled={zoom <= 1}>Whole video</button>
    </span>
  </div>
  <div class="tl-body">
    <div class="labels">
      <span class="lab ruler-lab"></span>
      <span class="lab">Video</span>
      <span class="lab">Chapters</span>
      <span class="lab">Text</span>
      <span class="lab">Effects</span>
      <span class="lab">Audio</span>
      <span class="lab">Captions</span>
    </div>
    <div class="view" bind:clientWidth={viewW}>
      <div class="scroller" bind:this={scroller} on:wheel={onWheel} on:scroll={onScroll}>
        <div class="track" style="padding: 0 {viewW / 2}px">
          <div class="inner" bind:this={inner} style="width:{innerW}px">
            <!-- ruler -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div class="ruler" on:pointerdown={laneDown}>
              {#each ticks as tk}
                <span class="tick" style="left:{pct(tk)}%"><span>{step < 1 ? tk.toFixed(1) : clock(tk)}</span></span>
              {/each}
            </div>

            <!-- video lane: the filmstrip, with what learners don't see dimmed -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div class="lane video" on:pointerdown={laneDown}>
              <Filmstrip source={$source} length={L} {pps} from={viewFrom} to={viewTo} around={$time} height={56} />
              <div class="dim" style="left:0; width:{pct(d.start)}%"></div>
              <div class="dim" style="left:{pct(d.end)}%; right:0"></div>
              <div class="kept" style="left:{pct(d.start)}%; width:{pct(d.end - d.start)}%"></div>
              {#each $parts as p, i}
                <span class="plabel" class:bad={p.played < MIN_PART} style="left:{pct(p.from)}%; width:{pct(p.len)}%">
                  <span>{$parts.length > 1 ? `Part ${i + 1} · ` : ''}{clock(p.played)}</span>
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

            <!-- text and stickers lane -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div class="lane text" on:pointerdown={laneDown}>
              {#each d.edits.overlays as o, i}
                <!-- svelte-ignore a11y-no-static-element-interactions -->
                <div class="block st-{o.style}" class:sel={sel?.kind === 'overlay' && sel.index === i} class:half={ovStacked} class:r1={ovRow[i] === 1}
                  style="left:{pct(o.start)}%; width:{pct(o.end - o.start)}%" title={o.text}
                  on:pointerdown={e => { pick('overlay', i); grab(e, { kind: 'ov-move', index: i, grab: timeAt(e.clientX), orig: { ...o } }); }}>
                  <span class="btxt">{o.text}</span>
                  <span class="edge l" on:pointerdown={e => { pick('overlay', i); grab(e, { kind: 'ov-start', index: i, grab: 0, orig: { ...o } }); }}></span>
                  <span class="edge r" on:pointerdown={e => { pick('overlay', i); grab(e, { kind: 'ov-end', index: i, grab: 0, orig: { ...o } }); }}></span>
                </div>
              {/each}
            </div>

            <!-- effects lane: what changes the picture on top, timing and sound below -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div class="lane effects" on:pointerdown={laneDown}>
              {#each d.edits.effects as ef, i}
                {#if ef.kind === 'freeze'}
                  <!-- svelte-ignore a11y-no-static-element-interactions -->
                  <div class="frz" class:sel={sel?.kind === 'effect' && sel.index === i} style="left:{pct(ef.start)}%"
                    title="Freeze at {clock(ef.start)} for {ef.hold ?? 2} s"
                    on:pointerdown={e => { pick('effect', i); grab(e, { kind: 'ef-move', index: i, grab: timeAt(e.clientX), orig: { ...ef } }); }}>
                    <span>❄ {ef.hold ?? 2}s</span>
                  </div>
                {:else}
                  <!-- svelte-ignore a11y-no-static-element-interactions -->
                  <div class="fx k-{ef.kind}" class:low={ef.kind === 'speed' || ef.kind === 'mute'} class:sel={sel?.kind === 'effect' && sel.index === i}
                    style="left:{pct(ef.start)}%; width:{pct(ef.end - ef.start)}%"
                    title="{EFFECT_NAMES[ef.kind]} {clock(ef.start)} – {clock(ef.end)}"
                    on:pointerdown={e => { pick('effect', i); grab(e, { kind: 'ef-move', index: i, grab: timeAt(e.clientX), orig: { ...ef } }); }}>
                    <span class="btxt">{ef.kind === 'fx' ? FX_NAMES[ef.style ?? 'shake'] : EFFECT_NAMES[ef.kind]}{ef.kind === 'speed' ? ` ${ef.rate}×` : ef.kind === 'zoom' ? ` ${(ef.scale ?? 1.4).toFixed(1)}×` : ''}</span>
                    <span class="edge l" on:pointerdown={e => { pick('effect', i); grab(e, { kind: 'ef-start', index: i, grab: 0, orig: { ...ef } }); }}></span>
                    <span class="edge r" on:pointerdown={e => { pick('effect', i); grab(e, { kind: 'ef-end', index: i, grab: 0, orig: { ...ef } }); }}></span>
                  </div>
                {/if}
              {/each}
            </div>

            <!-- audio lane: music and voice-overs -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div class="lane audio" on:pointerdown={laneDown}>
              {#each d.edits.audio.tracks as tr, i (tr.id)}
                <!-- svelte-ignore a11y-no-static-element-interactions -->
                <div class="au k-{tr.kind}" style="left:{pct(tr.start)}%; width:{pct(trackEnd(tr) - tr.start)}%"
                  title="{tr.name} from {clock(tr.start)}"
                  on:pointerdown={e => { st.tab.set(tr.kind === 'music' ? 'music' : 'voice'); grab(e, { kind: 'au-move', index: i, grab: timeAt(e.clientX), orig: { start: tr.start } }); }}>
                  <span class="btxt">{tr.kind === 'music' ? '♪' : '🎙'} {tr.name}</span>
                </div>
              {/each}
            </div>

            <!-- captions lane -->
            <!-- svelte-ignore a11y-no-static-element-interactions -->
            <div class="lane caps" on:pointerdown={laneDown}>
              {#each segs as sgm}
                <span class="seg" class:gone={inCut(sgm.start, sgm.end)} class:out={sgm.end <= d.start || sgm.start >= d.end}
                  style="left:{pct(sgm.start)}%; width:{pct(Math.max(0.4, sgm.end - sgm.start))}%" title={sgm.text}>{(sgm.end - sgm.start) * pps >= 44 ? sgm.text : ''}</span>
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
            </div>
          </div>
        </div>
      </div>
      <!-- Always in the middle: the video moves, not the playhead. -->
      <div class="playhead"><span class="ph-cap"></span><span class="ph-time mono">{clock($time)}</span></div>
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

  .tl-body { display: grid; grid-template-columns: 74px 1fr; border: 1px solid var(--st-line); border-radius: 12px; overflow: hidden; background: var(--st-deep); }
  .labels { display: grid; grid-template-rows: 22px 58px 28px 32px 36px 30px 28px; border-right: 1px solid var(--st-line); }
  .lab { font-size: 0.64rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--st-muted); padding: 0 0.55rem; display: flex; align-items: center; border-top: 1px solid var(--st-line); }
  .ruler-lab { border-top: 0; }
  .view { position: relative; min-width: 0; }
  .scroller { overflow-x: auto; overflow-y: hidden; scrollbar-width: none; }
  .scroller::-webkit-scrollbar { display: none; }
  .track { width: max-content; }
  .inner { position: relative; display: grid; grid-template-rows: 22px 58px 28px 32px 36px 30px 28px; }

  .ruler { position: relative; cursor: grab; background: var(--st-panel); touch-action: none; }
  .tick { position: absolute; top: 0; bottom: 0; border-left: 1px solid var(--st-line); }
  .tick span { position: absolute; left: 4px; top: 3px; font-size: 0.64rem; color: var(--st-muted); white-space: nowrap; font-variant-numeric: tabular-nums; }

  .lane { position: relative; border-top: 1px solid var(--st-line); cursor: grab; touch-action: none; }
  .lane:active { cursor: grabbing; }
  .video { background: #15161c; overflow: hidden; }
  .dim { position: absolute; top: 0; bottom: 0; background: rgba(0,0,0,.62); z-index: 1; pointer-events: none;
    background-image: repeating-linear-gradient(135deg, rgba(255,255,255,.05) 0 7px, transparent 7px 14px); }
  .kept { position: absolute; top: 2px; bottom: 2px; border-radius: 8px; box-shadow: inset 0 0 0 2px #fff; z-index: 1; pointer-events: none; }
  .plabel { position: absolute; bottom: 4px; display: flex; justify-content: center; pointer-events: none; z-index: 2; overflow: hidden; }
  .plabel span { font-size: 0.66rem; font-weight: 700; color: #fff; background: rgba(0,0,0,.6); padding: 0 6px; border-radius: 5px; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .plabel.bad span { color: #ff9196; }
  .cut { position: absolute; top: 2px; bottom: 2px; z-index: 2; border-radius: 4px; cursor: grab;
    background: repeating-linear-gradient(135deg, rgba(255,77,94,.6) 0 5px, rgba(80,10,20,.82) 5px 10px); box-shadow: inset 0 0 0 1px #ff4d5e; }
  .cut.sel { box-shadow: inset 0 0 0 2px #fff, 0 0 0 1px #ff4d5e; }
  .edge { position: absolute; top: 0; bottom: 0; width: 10px; cursor: ew-resize; }
  .edge.l { left: -5px; } .edge.r { right: -5px; }
  .split { position: absolute; top: 0; bottom: 0; width: 6px; translate: -50% 0; border-radius: 3px; background: #f5c518; cursor: ew-resize; z-index: 3; }
  .split::after { content: ''; position: absolute; left: 50%; top: -1px; translate: -50% 0; border: 5px solid transparent; border-top-color: #fff3b0; }
  .handle { position: absolute; top: 2px; bottom: 2px; width: 14px; translate: -50% 0; border-radius: 5px; background: #fff; cursor: ew-resize; z-index: 3; box-shadow: 0 0 0 2px var(--st-deep); }
  .handle::after { content: ''; position: absolute; inset: 35% 5px; border-left: 1px solid rgba(0,0,0,.45); border-right: 1px solid rgba(0,0,0,.45); }

  .flag { position: absolute; top: 4px; bottom: 4px; max-width: 160px; padding: 0 0.45rem 0 0.4rem; border-left: 2px solid #b48bff; border-radius: 0 6px 6px 0;
    background: rgba(180,139,255,.18); color: #e6dbff; font-size: 0.68rem; font-weight: 700; cursor: grab; display: flex; align-items: center; overflow: hidden; z-index: 2; }
  .flag span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .flag.sel { background: rgba(180,139,255,.45); color: #fff; }

  .block { position: absolute; top: 4px; bottom: 4px; border-radius: 6px; cursor: grab; display: flex; align-items: center; padding: 0 0.45rem; overflow: hidden; z-index: 2;
    background: rgba(255,210,63,.22); box-shadow: inset 0 0 0 1px #ffd23f; color: #fff1bf; }
  .block.st-title { background: rgba(255,255,255,.16); box-shadow: inset 0 0 0 1px #fff; color: #fff; }
  .block.st-label { background: rgba(229,9,20,.25); box-shadow: inset 0 0 0 1px #ff4d5e; color: #ffd5d8; }
  .block.st-quote { background: rgba(126,240,168,.2); box-shadow: inset 0 0 0 1px #7ef0a8; color: #d8ffe6; }
  .block.st-sticker { background: rgba(255,143,177,.18); box-shadow: inset 0 0 0 1px #ff8fb1; }
  .block.st-sticker .btxt { font-size: 0.9rem; }
  .block.sel { box-shadow: inset 0 0 0 2px #fff; }
  .block.half { top: 2px; bottom: auto; height: 13px; border-radius: 4px; }
  .block.half.r1 { top: 16px; }
  .block.half .btxt { font-size: 0.6rem; }
  .block.half.st-sticker .btxt { font-size: 0.7rem; }
  .btxt { font-size: 0.68rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; pointer-events: none; }

  .fx { position: absolute; top: 3px; height: 14px; border-radius: 4px; cursor: grab; display: flex; align-items: center; padding: 0 0.35rem; overflow: hidden; z-index: 2;
    background: color-mix(in srgb, var(--k) 28%, transparent); box-shadow: inset 0 0 0 1px var(--k); color: #fff; }
  .fx.low { top: 19px; }
  .fx.sel { box-shadow: inset 0 0 0 2px #fff; }
  .fx .btxt { font-size: 0.6rem; }
  .fx.k-zoom { --k: #6ea8ff; } .fx.k-speed { --k: #ffb057; } .fx.k-mute { --k: #b48bff; } .fx.k-blur { --k: #7ef0a8; } .fx.k-fx { --k: #ff7ad9; }
  .frz { position: absolute; top: 3px; bottom: 3px; translate: -2px 0; border-left: 2px solid #9be7ff; padding-left: 4px; cursor: grab; z-index: 3; display: flex; align-items: center; }
  .frz span { font-size: 0.62rem; font-weight: 800; color: #9be7ff; background: rgba(155,231,255,.14); padding: 1px 5px; border-radius: 5px; white-space: nowrap; }
  .frz.sel span { background: #9be7ff; color: #000; }

  .au { position: absolute; top: 4px; bottom: 4px; border-radius: 6px; cursor: grab; display: flex; align-items: center; padding: 0 0.45rem; overflow: hidden; z-index: 2;
    background: repeating-linear-gradient(90deg, color-mix(in srgb, var(--k) 40%, transparent) 0 2px, color-mix(in srgb, var(--k) 18%, transparent) 2px 5px);
    box-shadow: inset 0 0 0 1px var(--k); color: #fff; }
  .au.k-music { --k: #2ee6a6; } .au.k-voice { --k: #ff8fb1; }

  .seg { position: absolute; top: 4px; bottom: 4px; border-radius: 3px; background: rgba(255,255,255,.1); color: var(--st-muted); font-size: 0.6rem; line-height: 19px; padding: 0 3px; overflow: hidden; white-space: nowrap; pointer-events: none; box-shadow: inset 1px 0 0 rgba(255,255,255,.25); }
  .seg.out { opacity: 0.4; }
  .seg.gone { text-decoration: line-through; background: rgba(255,77,94,.15); color: #ff9196; }
  .empty { position: absolute; left: 8px; top: 50%; translate: 0 -50%; font-size: 0.68rem; color: var(--st-muted); white-space: nowrap; }

  .over { position: absolute; inset: 0; pointer-events: none; }
  .markband { position: absolute; top: 22px; bottom: 0; background: rgba(110,168,255,.16); border-left: 1px solid #6ea8ff; border-right: 1px solid #6ea8ff; }
  .markpin { position: absolute; top: 22px; bottom: 0; border-left: 1px dashed #6ea8ff; }
  .prange { position: absolute; top: 0; height: 22px; background: rgba(245,197,24,.35); }
  .snapline { position: absolute; top: 0; bottom: 0; border-left: 1px solid #7ef0a8; z-index: 4; }
  .playhead { position: absolute; top: 0; bottom: 0; left: 50%; width: 2px; translate: -50% 0; background: #fff; z-index: 5; pointer-events: none; box-shadow: 0 0 0 1px rgba(0,0,0,.35); }
  .ph-cap { position: absolute; top: 0; left: 50%; translate: -50% 0; width: 12px; height: 12px; background: #fff; clip-path: polygon(0 0, 100% 0, 100% 55%, 50% 100%, 0 55%); }
  .ph-time { position: absolute; bottom: 3px; left: 6px; font-size: 0.62rem; font-weight: 700; background: #fff; color: #000; padding: 0 4px; border-radius: 4px; }
</style>
