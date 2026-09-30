<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { api, type AdminCourse, type AdminVideoItem } from '$lib/api/client';
  import { fileFor } from '$lib/stores/course-uploads';
  import { clock, lineAt, segmentsToVtt } from '$lib/utils/transcribe';
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
  onDestroy(() => { hls?.destroy(); if (objectUrl) URL.revokeObjectURL(objectUrl); if (vttUrl) URL.revokeObjectURL(vttUrl); });

  // ---- captions in the preview ----------------------------------------------
  // The item's transcript is in clip time of its current trim; the preview
  // plays the whole video, so the lines move by that trim's start.
  let ccOn = false;
  let trackEl: HTMLTrackElement;
  const vttUrl = item.transcript_segments?.length
    ? URL.createObjectURL(new Blob([segmentsToVtt(item.transcript_segments, item.clip_start ?? 0)], { type: 'text/vtt' }))
    : '';
  // Drawn over the preview like the course player does; the browser's own
  // captions only in its full screen.
  let videoFs = false;
  const onFsChange = () => { videoFs = !!videoEl && document.fullscreenElement === videoEl; };
  onMount(() => document.addEventListener('fullscreenchange', onFsChange));
  onDestroy(() => { if (typeof document !== 'undefined') document.removeEventListener('fullscreenchange', onFsChange); });
  let trackMode: TextTrackMode = 'hidden';
  $: trackMode = ccOn && videoFs ? 'showing' : 'hidden';
  $: if (trackEl?.track) trackEl.track.mode = trackMode;
  $: caption = ccOn && !videoFs && item.transcript_segments?.length ? lineAt(item.transcript_segments, t - (item.clip_start ?? 0)) : '';

  // ---- preview: play it the way learners will get it -------------------------
  // A preview plays [from, to] and stops at `to`. "Preview result" plays part 1,
  // stops at its end (where a quiz or test can go), then continues with part 2
  // when asked, so every cut can be checked before saving.
  let playing: { from: number; to: number; label: string; seq: number | null } | null = null;
  let endCard: { text: string; next: number | null; replay: number | null } | null = null;

  function playRange(from: number, to: number, label: string, seq: number | null = null) {
    if (!videoEl) return;
    endCard = null;
    playing = { from, to, label, seq };
    videoEl.currentTime = from;
    videoEl.play().catch(() => {});
  }
  function previewAll() { playPart(0, true); }
  function playPart(i: number, seq = false) {
    const p = parts[i];
    if (p) playRange(p.from, p.to, parts.length > 1 ? `part ${i + 1}` : 'the kept video', seq ? i : null);
  }
  function playEnding(i: number) {
    const p = parts[i];
    if (p) playRange(Math.max(p.from, p.to - 5), p.to, `the end of ${parts.length > 1 ? `part ${i + 1}` : 'the video'}`);
  }
  function playCut(at: number) { playRange(Math.max(start, at - 4), Math.min(end, at + 4), `the split at ${clock(at)}`); }
  function stopPreview() { playing = null; endCard = null; }

  function onTime() {
    t = videoEl.currentTime;
    if (!playing || videoEl.seeking) return;
    if (t >= playing.to - 0.05) {
      videoEl.pause();
      const p = playing;
      playing = null;
      if (p.seq !== null) {
        const last = p.seq >= parts.length - 1;
        endCard = {
          text: last
            ? (parts.length > 1 ? `End of part ${p.seq + 1}, the last part.` : 'End of the video. This is where it stops for learners.')
            : `End of part ${p.seq + 1}. On the canvas, a quiz or test can go here before part ${p.seq + 2}.`,
          next: last ? null : p.seq + 1,
          replay: p.seq,
        };
      }
    }
  }

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
    stopPreview(); // the parts are changing under it
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
  function seekTo(e: MouseEvent) { stopPreview(); if (videoEl && length) videoEl.currentTime = timeAt(e.clientX); }
  function nudge(by: number) { stopPreview(); if (videoEl) videoEl.currentTime = Math.min(length, Math.max(0, videoEl.currentTime + by)); }

  async function save() {
    busy = true; error = '';
    stopPreview(); videoEl?.pause();
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
          Use <b>Preview result</b> to watch it the way learners will before you save.
          {#if item.part}This is part {item.part[0]} of {item.part[1]}; the timeline shows the whole video.{/if}
        </p>
      </div>
      <button class="icon-btn" on:click={onClose} aria-label="Close" disabled={busy}>{@html icons.x}</button>
    </header>

    <div class="preview">
      <!-- svelte-ignore a11y-media-has-caption -->
      <video bind:this={videoEl} controls preload="metadata" on:loadedmetadata={onMeta} on:timeupdate={onTime}>
        {#if vttUrl}<track bind:this={trackEl} kind="captions" srclang="en" label="Transcript" src={vttUrl}
          on:load={() => { if (trackEl?.track) trackEl.track.mode = trackMode; }} />{/if}
      </video>
      {#if caption && !endCard}<div class="caption" aria-hidden="true"><span>{caption}</span></div>{/if}
      <div class="ptools">
        {#if playing}<span class="now">{@html icons.play} Previewing {playing.label} · <span class="mono">{clock(Math.max(0, t - playing.from))} / {clock(playing.to - playing.from)}</span></span>{/if}
        <button class="ptool" class:on={ccOn} on:click={() => (ccOn = !ccOn)} disabled={!vttUrl}
          title={vttUrl ? (ccOn ? 'Captions on' : 'Captions off') : 'No transcript for this video yet'} aria-pressed={ccOn}>{@html icons.cc} CC</button>
      </div>
      {#if endCard}
        <div class="endcard" role="status">
          <p>{endCard.text}</p>
          <div class="row">
            {#if endCard.next !== null}<button class="btn sm primary" on:click={() => endCard && endCard.next !== null && playPart(endCard.next, true)}>{@html icons.play} Continue to part {endCard.next + 1}</button>{/if}
            {#if endCard.replay !== null}<button class="btn sm" on:click={() => endCard && endCard.replay !== null && playPart(endCard.replay, true)}>Replay{parts.length > 1 ? ` part ${endCard.replay + 1}` : ''}</button>{/if}
            <button class="btn sm ghost light" on:click={stopPreview}>Close</button>
          </div>
        </div>
      {/if}
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
        {#if playing}<div class="prange" style="left:{pct(playing.from)}%; width:{pct(playing.to) - pct(playing.from)}%"></div>{/if}
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
        <button class="btn sm primary" on:click={previewAll} disabled={!length || tooShort}
          title="Play it the way learners will get it: trimmed, and stopping at each split">{@html icons.play} Preview result</button>
        {#if playing || endCard}<button class="btn sm ghost" on:click={() => { stopPreview(); videoEl?.pause(); }}>Stop preview</button>{/if}
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
          <button class="btn sm ghost" on:click={() => playPart(i)} disabled={!length}>{@html icons.play} Play</button>
          <button class="btn sm ghost" on:click={() => playEnding(i)} disabled={!length} title="Play the last 5 seconds, to check where it stops">Play ending</button>
          {#if i > 0}<button class="btn sm ghost" on:click={() => playCut(p.from)} disabled={!length} title="Play 4 seconds either side of this split">Hear the cut</button>{/if}
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
  .ptools { position: absolute; top: 8px; left: 8px; right: 8px; display: flex; gap: 0.4rem; align-items: center; justify-content: flex-end; pointer-events: none; }
  .ptools > * { pointer-events: auto; }
  .now { margin-right: auto; display: inline-flex; gap: 0.35rem; align-items: center; height: 28px; padding: 0 0.6rem; border-radius: 7px; background: rgba(0, 0, 0, 0.65); color: #fff; font-size: 0.76rem; font-weight: 600; }
  .ptool { display: inline-flex; gap: 0.3rem; align-items: center; height: 28px; padding: 0 0.55rem; border-radius: 7px; color: #fff; background: rgba(0, 0, 0, 0.6); font-size: 0.74rem; font-weight: 700; border: 1px solid rgba(255, 255, 255, 0.15); }
  .ptool.on { background: #fff; color: #000; }
  .ptool:disabled { opacity: 0.5; cursor: not-allowed; }
  .endcard { position: absolute; inset: auto 0 0 0; padding: 0.9rem 1rem 3.4rem; background: linear-gradient(transparent, rgba(0, 0, 0, 0.88) 35%); color: #fff; display: grid; gap: 0.5rem; }
  .endcard p { font-size: 0.9rem; font-weight: 600; }
  .endcard .row { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .btn.light { color: #fff; border-color: rgba(255, 255, 255, 0.3); }
  .preview { container-type: inline-size; }
  .caption {
    position: absolute; left: 50%; bottom: 15%; transform: translateX(-50%);
    width: max-content; max-width: min(80%, 44em); text-align: center; pointer-events: none;
    font-size: clamp(0.72rem, 2.1cqw, 1.1rem); line-height: 1.45; font-weight: 500;
  }
  .caption span {
    color: #fff; background: rgba(8, 8, 12, 0.72); padding: 0.18em 0.6em; border-radius: 6px;
    box-decoration-break: clone; -webkit-box-decoration-break: clone; text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
  }
  .preview video::cue { background: rgba(8, 8, 12, 0.72); color: #fff; font-size: 70%; }
  .prange { position: absolute; top: 0; bottom: 0; background: rgba(245, 197, 24, 0.22); pointer-events: none; }
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
  .parts li { display: flex; flex-wrap: wrap; gap: 0.4rem 0.75rem; align-items: center; padding: 0.5rem 0.7rem; border: 1px solid var(--border); border-radius: 10px; font-size: 0.85rem; }
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
