<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { api, type AdminCourse, type AdminVideoItem } from '$lib/api/client';
  import { fileFor } from '$lib/stores/course-uploads';
  import { clock } from '$lib/utils/transcribe';
  import { icons } from '../icons';

  export let courseId: string;
  export let item: AdminVideoItem;
  export let onClose: () => void;
  export let onSaved: (course: AdminCourse) => void;

  // Keep in step with backend services/clips.py MIN_CLIP_SECONDS.
  const MIN_PART = 10;

  let videoEl: HTMLVideoElement;
  let track: HTMLDivElement;
  let hls: any = null;
  let objectUrl: string | null = null;
  let previewError = '';
  let length = item.source_duration_seconds ?? 0;
  let start = item.clip_start ?? 0;
  let end = item.clip_end ?? length;
  let splits: number[] = [];
  let t = start;
  let busy = false;
  let error = '';
  let startText = clock(start);
  let endText = clock(end);

  onMount(async () => {
    // The file itself when this session uploaded it: instant, and no stream needed.
    const file = fileFor(item.id);
    if (file) {
      objectUrl = URL.createObjectURL(file);
      videoEl.src = objectUrl;
      return;
    }
    try {
      const s = await api.streamUrl(item.ref_id);
      const { default: Hls } = await import('hls.js/dist/hls.min.js');
      if (Hls.isSupported()) {
        hls = new Hls({ startPosition: start });
        hls.on(Hls.Events.ERROR, (_e: unknown, d: any) => {
          if (d?.fatal) previewError = "The preview couldn't load. You can still type the times.";
        });
        hls.loadSource(s.stream_url);
        hls.attachMedia(videoEl);
      } else {
        videoEl.src = s.stream_url;
      }
    } catch {
      previewError = "The preview couldn't load. You can still type the times.";
    }
  });
  onDestroy(() => { hls?.destroy(); if (objectUrl) URL.revokeObjectURL(objectUrl); });

  function onMeta() {
    if (!length && videoEl.duration) { length = videoEl.duration; if (!end) end = length; endText = clock(end); }
    if (start > 0) videoEl.currentTime = start;
  }

  $: sorted = [...splits].sort((a, b) => a - b);
  $: points = [start, ...sorted, end];
  $: parts = points.slice(1).map((b, i) => ({ from: points[i], to: b, len: b - points[i] }));
  $: tooShort = parts.some(p => p.len < MIN_PART);
  $: changed = start !== (item.clip_start ?? 0) || end !== (item.clip_end ?? length) || splits.length > 0;
  $: pct = (x: number) => (length ? (x / length) * 100 : 0);

  const round = (x: number) => Math.round(x * 10) / 10;
  function setStart(x: number) { start = round(Math.max(0, Math.min(x, end - MIN_PART))); startText = clock(start); splits = splits.filter(s => s > start); }
  function setEnd(x: number) { end = round(Math.min(length, Math.max(x, start + MIN_PART))); endText = clock(end); splits = splits.filter(s => s < end); }
  function addSplit(x: number) {
    x = round(x);
    if (x <= start + MIN_PART - 0.01 || x >= end - MIN_PART + 0.01) { error = `A split needs at least ${MIN_PART} seconds on each side.`; return; }
    if (splits.some(s => Math.abs(s - x) < MIN_PART)) { error = 'There is already a split right there.'; return; }
    error = '';
    splits = [...splits, x];
  }
  function removeSplit(x: number) { splits = splits.filter(s => s !== x); }

  function parseTime(text: string): number | null {
    const parts = text.trim().split(':').map(Number);
    if (!parts.length || parts.some(n => Number.isNaN(n) || n < 0)) return null;
    return parts.reduce((acc, n) => acc * 60 + n, 0);
  }

  // Dragging a handle or a split marker along the timeline.
  let dragging: { kind: 'start' | 'end' | 'split'; value?: number } | null = null;
  const timeAt = (clientX: number) => {
    const r = track.getBoundingClientRect();
    return Math.min(length, Math.max(0, ((clientX - r.left) / r.width) * length));
  };
  function grab(e: PointerEvent, kind: 'start' | 'end' | 'split', value?: number) {
    e.stopPropagation();
    dragging = { kind, value };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }
  function move(e: PointerEvent) {
    if (!dragging) return;
    const x = timeAt(e.clientX);
    if (dragging.kind === 'start') setStart(x);
    else if (dragging.kind === 'end') setEnd(x);
    else {
      const old = dragging.value!;
      const clamped = round(Math.min(end - MIN_PART, Math.max(start + MIN_PART, x)));
      splits = splits.map(s => (s === old ? clamped : s));
      dragging = { kind: 'split', value: clamped };
    }
  }
  function drop() { dragging = null; }
  function seekTo(e: MouseEvent) { if (videoEl && length) videoEl.currentTime = timeAt(e.clientX); }
  function nudge(by: number) { if (videoEl) videoEl.currentTime = Math.min(length, Math.max(0, videoEl.currentTime + by)); }
  function playPart() { if (videoEl) { videoEl.currentTime = start; videoEl.play().catch(() => {}); } }

  async function save() {
    busy = true; error = '';
    try { onSaved(await api.setClip(courseId, item.id, { start, end, split_at: sorted })); }
    catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape' && !busy) onClose();
  }
</script>

<svelte:window on:keydown={onKey} on:pointermove={move} on:pointerup={drop} />

<div class="scrim" role="presentation" on:click|self={() => !busy && onClose()}>
  <div class="editor" role="dialog" aria-modal="true" aria-labelledby="ve-title">
    <header>
      <div>
        <span class="eyebrow">Trim and split</span>
        <h2 id="ve-title">{item.title}</h2>
        <p class="hint">
          The video on Bunny isn't changed: this sets which part plays. Split it to put a quiz or test between the parts.
          {#if item.part}This is part {item.part[0]} of {item.part[1]}; the timeline shows the whole video.{/if}
        </p>
      </div>
      <button class="icon-btn" on:click={onClose} aria-label="Close" disabled={busy}>{@html icons.x}</button>
    </header>

    <div class="preview">
      <!-- svelte-ignore a11y-media-has-caption -->
      <video bind:this={videoEl} controls preload="metadata" on:loadedmetadata={onMeta} on:timeupdate={() => (t = videoEl.currentTime)}></video>
      {#if previewError}<p class="perr">{previewError}</p>{/if}
    </div>

    <div class="timeline">
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div class="track" bind:this={track} on:click={seekTo}>
        <div class="kept" style="left:{pct(start)}%; width:{pct(end) - pct(start)}%"></div>
        {#each parts as p, i}
          <span class="plabel" style="left:{pct(p.from)}%; width:{pct(p.to) - pct(p.from)}%" class:bad={p.len < MIN_PART}>{parts.length > 1 ? `Part ${i + 1}` : ''}</span>
        {/each}
        {#each sorted as s (s)}
          <button class="split" style="left:{pct(s)}%" on:pointerdown={e => grab(e, 'split', s)} on:click|stopPropagation aria-label="Split at {clock(s)}; drag to move"></button>
        {/each}
        <button class="handle hstart" style="left:{pct(start)}%" on:pointerdown={e => grab(e, 'start')} on:click|stopPropagation aria-label="Start, {clock(start)}; drag to move"></button>
        <button class="handle hend" style="left:{pct(end)}%" on:pointerdown={e => grab(e, 'end')} on:click|stopPropagation aria-label="End, {clock(end)}; drag to move"></button>
        <div class="playhead" style="left:{pct(t)}%"></div>
      </div>
      <div class="scale mono"><span>0:00</span><span>Playhead {clock(t)}</span><span>{clock(length)}</span></div>
    </div>

    <div class="tools">
      <div class="group">
        <button class="btn sm" on:click={() => nudge(-5)}>−5 s</button>
        <button class="btn sm" on:click={() => nudge(-1)}>−1 s</button>
        <button class="btn sm" on:click={() => nudge(1)}>+1 s</button>
        <button class="btn sm" on:click={() => nudge(5)}>+5 s</button>
      </div>
      <div class="group">
        <button class="btn sm" on:click={() => setStart(t)}>Start here</button>
        <button class="btn sm" on:click={() => setEnd(t)}>End here</button>
        <button class="btn sm primary" on:click={() => addSplit(t)}>{@html icons.plus} Split here</button>
      </div>
      <div class="group">
        <button class="btn sm ghost" on:click={playPart}>{@html icons.play} Play from start</button>
        <button class="btn sm ghost" on:click={() => { setStart(0); setEnd(length); splits = []; }}>Use whole video</button>
      </div>
    </div>

    <div class="fields">
      <label>Starts at
        <input type="text" bind:value={startText} on:change={() => { const v = parseTime(startText); if (v !== null) setStart(v); else startText = clock(start); }} />
      </label>
      <label>Ends at
        <input type="text" bind:value={endText} on:change={() => { const v = parseTime(endText); if (v !== null) setEnd(v); else endText = clock(end); }} />
      </label>
      <span class="hint">Type times as m:ss or h:mm:ss.</span>
    </div>

    <ol class="parts">
      {#each parts as p, i}
        <li class:bad={p.len < MIN_PART}>
          <b>{parts.length > 1 ? `Part ${i + 1}` : 'Plays'}</b>
          <span class="mono">{clock(p.from)} – {clock(p.to)}</span>
          <span class="muted">{clock(p.len)}{i === 0 ? ' · stays this episode' : ' · new episode after it'}</span>
          {#if i > 0}<button class="icon-btn" on:click={() => removeSplit(p.from)} aria-label="Remove the split at {clock(p.from)}">{@html icons.x}</button>{/if}
        </li>
      {/each}
    </ol>
    {#if tooShort}<p class="error">Each part needs to be at least {MIN_PART} seconds long.</p>{/if}
    {#if error}<p class="error">{error}</p>{/if}

    <footer>
      <button class="btn" on:click={onClose} disabled={busy}>Cancel</button>
      <button class="btn primary" on:click={save} disabled={busy || tooShort || !changed || !length}>
        {busy ? 'Saving…' : parts.length > 1 ? `Save and make ${parts.length} parts` : 'Save'}
      </button>
    </footer>
  </div>
</div>

<style>
  .scrim { position: fixed; inset: 0; z-index: 350; background: rgba(4, 4, 10, 0.65); display: grid; place-items: center; padding: 1rem; }
  .editor {
    width: min(920px, 100%); max-height: calc(100vh - 2rem); overflow: auto;
    background: var(--surface); border: 1px solid var(--border-hover); border-radius: 16px; box-shadow: var(--shadow-lg);
    padding: 1.2rem; display: grid; gap: 0.9rem;
  }
  header { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; }
  .eyebrow { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  h2 { font-size: 1.15rem; font-weight: 700; margin: 0.15rem 0 0.3rem; }
  .preview { position: relative; background: #000; border-radius: 10px; overflow: hidden; aspect-ratio: 16/9; max-height: 46vh; }
  .preview video { width: 100%; height: 100%; }
  .perr { position: absolute; inset: auto 0 0 0; padding: 0.5rem 0.8rem; font-size: 0.82rem; color: #fff; background: rgba(0, 0, 0, 0.7); }
  .timeline { display: grid; gap: 0.3rem; }
  .track { position: relative; height: 54px; border-radius: 8px; background: repeating-linear-gradient(135deg, var(--surface2) 0 8px, var(--surface3) 8px 16px); cursor: pointer; touch-action: none; }
  .kept { position: absolute; top: 0; bottom: 0; background: rgba(110, 168, 255, 0.28); border-top: 2px solid #6ea8ff; border-bottom: 2px solid #6ea8ff; }
  .plabel { position: absolute; top: 50%; transform: translateY(-50%); text-align: center; font-size: 0.72rem; font-weight: 700; color: #cfe0ff; pointer-events: none; white-space: nowrap; overflow: hidden; }
  .plabel.bad { color: #ff8a8f; }
  .handle, .split { position: absolute; top: -4px; bottom: -4px; transform: translateX(-50%); cursor: ew-resize; touch-action: none; }
  .handle { width: 14px; border-radius: 5px; background: #6ea8ff; box-shadow: 0 0 0 2px var(--surface); }
  .split { width: 6px; border-radius: 3px; background: #f5c518; }
  .split::after { content: ''; position: absolute; left: 50%; top: -6px; transform: translateX(-50%); border: 5px solid transparent; border-top-color: #f5c518; }
  .playhead { position: absolute; top: -6px; bottom: -6px; width: 2px; background: var(--accent); pointer-events: none; transform: translateX(-50%); }
  .scale { display: flex; justify-content: space-between; font-size: 0.72rem; color: var(--muted); }
  .mono { font-family: ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; }
  .tools { display: flex; gap: 0.75rem; flex-wrap: wrap; justify-content: space-between; }
  .group { display: flex; gap: 0.35rem; flex-wrap: wrap; }
  .fields { display: flex; gap: 0.8rem; align-items: flex-end; flex-wrap: wrap; }
  .fields label { display: grid; gap: 0.25rem; font-size: 0.76rem; font-weight: 600; color: var(--text-secondary); }
  .fields input { width: 110px; font: inherit; font-size: 0.88rem; color: var(--text); background: var(--bg); border: 1px solid var(--border-hover); border-radius: 8px; padding: 0.4rem 0.6rem; font-variant-numeric: tabular-nums; }
  .parts { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.35rem; }
  .parts li { display: flex; gap: 0.75rem; align-items: center; padding: 0.5rem 0.7rem; border: 1px solid var(--border); border-radius: 10px; font-size: 0.85rem; }
  .parts li.bad { border-color: #ff6b70; }
  .parts .muted { color: var(--muted); flex: 1; }
  .hint { font-size: 0.8rem; color: var(--muted); line-height: 1.45; }
  .error { font-size: 0.82rem; color: #ff6b70; }
  footer { display: flex; gap: 0.5rem; justify-content: flex-end; }
  .btn { display: inline-flex; align-items: center; gap: 0.35rem; height: 34px; padding: 0 0.9rem; border-radius: 8px; border: 1px solid var(--border-hover); background: var(--surface2); color: var(--text); font-weight: 600; font-size: 0.82rem; }
  .btn:hover:not(:disabled) { background: var(--surface3); }
  .btn.sm { height: 28px; padding: 0 0.6rem; font-size: 0.76rem; }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn.ghost { background: transparent; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .icon-btn { display: inline-grid; place-items: center; width: 28px; height: 28px; border-radius: 7px; color: var(--muted); }
  .icon-btn:hover { background: var(--surface2); color: var(--text); }
</style>
