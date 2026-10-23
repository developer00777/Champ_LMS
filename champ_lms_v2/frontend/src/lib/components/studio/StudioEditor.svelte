<script lang="ts">
  // The studio's editor, once VideoStudio has loaded the episode. It owns the
  // shared state (studio.ts) that the stage, timeline and panels work on.
  import { onDestroy, onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { api, type StudioEpisode } from '$lib/api/client';
  import { clock, lineAt } from '$lib/utils/transcribe';
  import { cutAt, frameStyle, lookFilter, mutedAt, speedAt, type Overlay } from '$lib/utils/video-edits';
  import EditedLayer from '$lib/components/video/EditedLayer.svelte';
  import { icons } from '$lib/components/course/icons';
  import {
    MIN_PART, addEffect, createStudio, cutMarked, provideStudio, removeSelected, round, splitAt, trimEnd, trimStart,
    type Tab,
  } from './studio';
  import StageBox from './StageBox.svelte';
  import EffectsPanel from './EffectsPanel.svelte';
  import DetailsPanel from './DetailsPanel.svelte';
  import Timeline from './Timeline.svelte';
  import AiPanel from './AiPanel.svelte';
  import TrimPanel from './TrimPanel.svelte';
  import CutsPanel from './CutsPanel.svelte';
  import CaptionsPanel from './CaptionsPanel.svelte';
  import TextPanel from './TextPanel.svelte';
  import ChaptersPanel from './ChaptersPanel.svelte';
  import LookPanel from './LookPanel.svelte';
  import ThumbPanel from './ThumbPanel.svelte';

  export let initial: StudioEpisode;
  export let localFile: File | null = null;
  export let onClose: () => void;
  export let onSaved: (ep: StudioEpisode) => void = () => {};

  const st = createStudio(initial);
  provideStudio(st);
  const { doc, time, playing, tab, preview, notice, canUndo, canRedo, ep, mark, ccOn, parts, selected } = st;
  const isDirty = st.dirty;
  const episodeId = initial.id;

  $: t = $time;
  $: dirty = $isDirty;
  $: tooShort = $parts.some(p => p.played < MIN_PART);
  $: runtime = $parts.reduce((a, p) => a + p.played, 0);

  // ---- the preview video ------------------------------------------------------
  let videoEl: HTMLVideoElement;
  let hls: any = null;
  let objectUrl: string | null = null;
  let previewError = '';
  let rate = 1;

  onMount(async () => {
    st.attach(videoEl);
    const startAt = $doc.start;
    if (localFile) {
      objectUrl = URL.createObjectURL(localFile);
      videoEl.src = objectUrl;
      videoEl.addEventListener('loadedmetadata', () => { videoEl.currentTime = startAt; }, { once: true });
      return;
    }
    try {
      const sres = await api.streamUrl(episodeId);
      const { default: Hls } = await import('hls.js/dist/hls.min.js');
      if (Hls.isSupported()) {
        hls = new Hls({ startPosition: startAt });
        hls.on(Hls.Events.ERROR, (_e: unknown, d: any) => {
          if (d?.fatal) previewError = "The preview couldn't load. You can still edit on the timeline and type times.";
        });
        hls.loadSource(sres.stream_url);
        hls.attachMedia(videoEl);
      } else {
        videoEl.src = sres.stream_url;
        videoEl.addEventListener('loadedmetadata', () => { videoEl.currentTime = startAt; }, { once: true });
      }
    } catch {
      previewError = "The preview couldn't load. You can still edit on the timeline and type times.";
    }
  });
  onDestroy(() => {
    hls?.destroy();
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    if (raf) cancelAnimationFrame(raf);
  });

  // Frame loop while playing: smooth playhead, cuts skipped, a preview run
  // stopped at its end (with an end card between parts).
  let raf = 0;
  let endCard: { text: string; next: number | null; replay: number | null } | null = null;
  function frame() {
    raf = 0;
    if (!videoEl) return;
    const now = videoEl.currentTime;
    st.time.set(now);
    if (!videoEl.paused) {
      const run = get(st.preview);
      const cut = !videoEl.seeking && cutAt($doc.edits.cuts, now);
      if (run && now >= run.to - 0.05) {
        videoEl.pause();
        st.preview.set(null);
        if (run.seq !== null) {
          const last = run.seq >= $parts.length - 1;
          endCard = {
            text: last
              ? ($parts.length > 1 ? `End of part ${run.seq + 1}, the last part.` : 'End of the video. This is where it stops for learners.')
              : `End of part ${run.seq + 1}. ${$ep.layout === 'canvas' ? 'On the canvas, a quiz or test can go here' : 'The next episode starts'} before part ${run.seq + 2}.`,
            next: last ? null : run.seq + 1,
            replay: run.seq,
          };
        }
      } else if (cut) {
        videoEl.currentTime = cut.end;
      } else {
        // Speed and mute effects, as the learner's player applies them.
        const want = rate * speedAt($doc.edits.effects, now);
        if (Math.abs(videoEl.playbackRate - want) > 0.001) videoEl.playbackRate = want;
        const mute = mutedAt($doc.edits.effects, now);
        if (videoEl.muted !== mute) videoEl.muted = mute;
      }
      raf = requestAnimationFrame(frame);
    }
  }
  function onPlay() { playing.set(true); endCard = null; if (!raf) raf = requestAnimationFrame(frame); }
  function onPause() { playing.set(false); }
  function onTimeUpdate() { if (videoEl.paused) time.set(videoEl.currentTime); }

  function playPart(i: number) {
    const p = $parts[i];
    if (p) st.playRange(p.from, p.to, $parts.length > 1 ? `part ${i + 1}` : 'the result', i);
  }
  function setRate(r: number) { rate = r; if (videoEl) videoEl.playbackRate = r * speedAt($doc.edits.effects, t); }
  function nudge(by: number) { st.seek(t + by); }
  function boundary(dir: 1 | -1) {
    const d = $doc;
    const pts = [d.start, d.end, ...d.splits, ...d.edits.cuts.flatMap(c => [c.start, c.end]),
      ...d.edits.chapters.map(c => c.start), ...d.edits.overlays.map(o => o.start),
      ...d.edits.effects.flatMap(e => [e.start, e.end])].sort((a, b) => a - b);
    const target = dir > 0 ? pts.find(p => p > t + 0.05) : [...pts].reverse().find(p => p < t - 0.05);
    if (target !== undefined) st.seek(target);
  }

  // ---- stage state ---------------------------------------------------------------
  $: look = $doc.edits.look;
  $: selIndex = $selected?.kind === 'effect' ? $selected.index : -1;
  $: selEffect = selIndex >= 0 ? $doc.edits.effects[selIndex] ?? null : null;
  // Aiming a zoom, paused: show the whole picture, with the zoom's frame on it.
  $: aiming = !!selEffect && selEffect.kind === 'zoom' && !$playing;
  $: shownEffects = aiming ? $doc.edits.effects.filter(e => e !== selEffect) : $doc.edits.effects;
  $: videoStyle = [lookFilter(look) && `filter: ${lookFilter(look)};`, frameStyle(look, shownEffects, t)].filter(Boolean).join(' ');
  $: picture = frameStyle(look, $doc.edits.effects, t);
  $: partNow = $parts.find(p => t >= p.from - 0.05 && t <= p.to + 0.05) ?? null;
  $: outside = t < $doc.start - 0.05 || t > $doc.end + 0.05;
  $: inCut = !$playing && !!cutAt($doc.edits.cuts, t);
  $: segs = $doc.segments;

  // ---- save and close -------------------------------------------------------------
  let busy = false;
  async function save() {
    busy = true;
    st.pause();
    const d = $doc;
    const made = $parts.length;
    try {
      // Caption words fixed here are the transcript's, saved first so the
      // studio comes back with them.
      if (d.segments.length && JSON.stringify(d.segments) !== JSON.stringify(get(ep).transcript_segments)) {
        await api.saveTranscript(episodeId, d.segments, 'manual', 'source');
      }
      const res = await api.saveStudio(episodeId, {
        start: d.start, end: d.end, split_at: [...d.splits].sort((a, b) => a - b), edits: d.edits,
      });
      st.reset(res);
      st.say(made > 1 ? `Saved. The video is now ${made} episodes; this is part 1.` : 'Saved. Learners get the edited video now.');
      onSaved(res);
    } catch (e: any) { st.say(e.message, 'bad'); }
    finally { busy = false; }
  }
  function close() {
    if (busy) return;
    if (dirty && !confirm('Close the studio without saving your changes?')) return;
    onClose();
  }

  // ---- keyboard -------------------------------------------------------------------
  let help = false;
  function onKey(e: KeyboardEvent) {
    const el = e.target as HTMLElement;
    const typing = el.closest('input, textarea, select, [contenteditable="true"]');
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === 'z' && !typing) { e.preventDefault(); e.shiftKey ? st.redo() : st.undo(); return; }
    if (mod && e.key.toLowerCase() === 'y' && !typing) { e.preventDefault(); st.redo(); return; }
    if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); if (dirty && !tooShort) save(); return; }
    if (typing) { if (e.key === 'Escape') (el as HTMLElement).blur(); return; }
    const k = e.key;
    if (k === ' ' || k === 'k') { e.preventDefault(); st.toggle(); }
    else if (k === 'ArrowLeft') { e.preventDefault(); nudge(e.shiftKey ? -5 : -1); }
    else if (k === 'ArrowRight') { e.preventDefault(); nudge(e.shiftKey ? 5 : 1); }
    else if (k === ',') nudge(-1 / 30);
    else if (k === '.') nudge(1 / 30);
    else if (k === 'j') nudge(-10);
    else if (k === 'l') nudge(10);
    else if (k === 'i') st.mark.update(m => ({ ...m, in: t }));
    else if (k === 'o') st.mark.update(m => ({ ...m, out: t }));
    else if (k === 'c') cutMarked(st);
    else if (k === 's') splitAt(st, t);
    else if (k === '[') trimStart(st, t);
    else if (k === ']') trimEnd(st, t);
    else if (k === 'Home') st.seek($doc.start);
    else if (k === 'End') st.seek($doc.end);
    else if (k === 't') addText();
    else if (k === 'm') addChapter();
    else if (k === 'z') { tab.set('effects'); addEffect(st, 'zoom'); }
    else if (k === 'b') { tab.set('effects'); addEffect(st, 'blur'); }
    else if (k === 'Delete' || k === 'Backspace') { if (removeSelected(st)) e.preventDefault(); }
    else if (k === '?') help = !help;
    else if (k === 'Escape') {
      if (help) help = false;
      else if (get(st.selected) || get(st.mark).in !== null) { st.selected.set(null); st.mark.set({ in: null, out: null }); }
      else close();
    }
  }

  function addText() {
    const start = round(t);
    const o: Overlay = {
      start, end: round(Math.min(st.length, start + 4)), text: 'Key point', subtext: null, position: 'top', style: 'callout',
      size: 'm', anim: 'rise', color: null,
    };
    let index = 0;
    st.commit(d => { d.edits.overlays = [...d.edits.overlays, o].sort((a, b) => a.start - b.start); index = d.edits.overlays.indexOf(o); });
    tab.set('text');
    selected.set({ kind: 'overlay', index });
  }
  function addChapter() {
    const at = round(t);
    if ($doc.edits.chapters.some(c => Math.abs(c.start - at) < 1)) { st.say('There is already a chapter here.', 'bad'); return; }
    const said = lineAt($doc.segments, at).split(/\s+/).slice(0, 5).join(' ');
    let index = 0;
    st.commit(d => {
      const c = { start: at, title: said || `Chapter ${d.edits.chapters.length + 1}` };
      d.edits.chapters = [...d.edits.chapters, c].sort((a, b) => a.start - b.start);
      index = d.edits.chapters.indexOf(c);
    });
    tab.set('chapters');
    selected.set({ kind: 'chapter', index });
  }

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: 'ai', label: 'AI', icon: icons.sparkle },
    { id: 'trim', label: 'Trim', icon: '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M7 4v16M17 4v16M4 8h3M17 8h3M4 16h3M17 16h3"/></svg>' },
    { id: 'cuts', label: 'Cuts', icon: '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="6" cy="7" r="2.5"/><circle cx="6" cy="17" r="2.5"/><path d="M8 8.5l12 8M8 15.5l12-8"/></svg>' },
    { id: 'captions', label: 'Captions', icon: icons.cc },
    { id: 'text', label: 'Text', icon: '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M5 6V4.5h14V6M12 4.5V19.5M9 19.5h6"/></svg>' },
    { id: 'effects', label: 'Effects', icon: '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20l9-9M14 4v3M14 13v3M10 8H7M21 8h-3M17.5 4.5l-2 2M12.5 11.5l-2-2"/></svg>' },
    { id: 'chapters', label: 'Chapters', icon: '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M5 21V4M5 4h11l-2 4 2 4H5"/></svg>' },
    { id: 'look', label: 'Look', icon: '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="8"/><path d="M12 4a8 8 0 000 16z" fill="currentColor"/></svg>' },
    { id: 'details', label: 'Details', icon: '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M5 6h14M5 11h14M5 16h9"/></svg>' },
    { id: 'thumb', label: 'Thumbnail', icon: '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/><circle cx="15.5" cy="9.5" r="1.5"/></svg>' },
  ];

  // The studio opens from inside sticky side panels and the course canvas,
  // which trap z-index; on the body it always sits above the page. The page
  // underneath is held still while it's open, so nothing drifts behind it.
  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    const html = document.documentElement;
    const before = [html.style.overflow, document.body.style.overflow];
    html.style.overflow = document.body.style.overflow = 'hidden';
    return {
      destroy() {
        node.remove();
        [html.style.overflow, document.body.style.overflow] = before;
      },
    };
  }
</script>

<svelte:window on:keydown={onKey} />

<div class="studio" role="dialog" aria-modal="true" aria-label="Video studio" use:portal>
    <header class="top">
      <button class="icon" on:click={close} aria-label="Close the studio" title="Close (Esc)">{@html icons.x}</button>
      <div class="ttl">
        <span class="eyebrow">Video studio · {$ep.layout === 'canvas' ? 'Course' : 'Module'}: {$ep.module_title}</span>
        <h2>{$ep.title}{#if $ep.part}<span class="part"> · part {$ep.part[0]} of {$ep.part[1]}</span>{/if}</h2>
      </div>
      <div class="hbtns">
        <button class="icon" on:click={() => st.undo()} disabled={!$canUndo} aria-label="Undo" title="Undo (Ctrl+Z)">↶</button>
        <button class="icon" on:click={() => st.redo()} disabled={!$canRedo} aria-label="Redo" title="Redo (Ctrl+Shift+Z)">↷</button>
        <button class="icon" on:click={() => (help = !help)} aria-label="Keyboard shortcuts" title="Shortcuts (?)">?</button>
        <button class="btn sm" on:click={() => playPart(0)} disabled={tooShort}
          title="Play it the way learners will get it: trimmed, cut, and stopping at each split">{@html icons.play} Preview as learner</button>
        <button class="btn hot" on:click={save} disabled={busy || !dirty || tooShort} title="Save (Ctrl+S)">
          {busy ? 'Saving…' : $parts.length > 1 ? `Save · make ${$parts.length} parts` : dirty ? 'Save' : 'Saved'}
        </button>
      </div>
    </header>

    <div class="main">
      <nav class="rail" aria-label="Studio tools">
        {#each TABS as tb}
          <button class:on={$tab === tb.id} on:click={() => tab.set(tb.id)} aria-pressed={$tab === tb.id}>
            <span class="ri">{@html tb.icon}</span><span>{tb.label}</span>
          </button>
        {/each}
      </nav>

      <aside class="panel">
        {#if $tab === 'ai'}<AiPanel />
        {:else if $tab === 'trim'}<TrimPanel {dirty} onJoined={() => onSaved(get(ep))} />
        {:else if $tab === 'cuts'}<CutsPanel />
        {:else if $tab === 'captions'}<CaptionsPanel {localFile} />
        {:else if $tab === 'text'}<TextPanel />
        {:else if $tab === 'effects'}<EffectsPanel />
        {:else if $tab === 'chapters'}<ChaptersPanel />
        {:else if $tab === 'look'}<LookPanel />
        {:else if $tab === 'details'}<DetailsPanel />
        {:else}<ThumbPanel />{/if}
      </aside>

      <section class="stage-col">
        <div class="stage">
          <!-- The learner's player is 16:9, so the preview is too: text and
               boxes land where learners will see them. -->
          <div class="frame">
            <!-- svelte-ignore a11y-media-has-caption a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
            <video bind:this={videoEl} preload="metadata" playsinline style={videoStyle}
              on:play={onPlay} on:pause={onPause} on:timeupdate={onTimeUpdate} on:click={() => st.toggle()}></video>
            <EditedLayer edits={$doc.edits} {t} from={partNow?.from ?? $doc.start} to={partNow?.to ?? $doc.end}
              captions={segs} ccOn={$ccOn} />
            {#if selEffect && (selEffect.kind === 'blur' || selEffect.kind === 'zoom') && !$playing}
              <StageBox effect={selEffect} index={selIndex} {picture} />
            {/if}
          </div>
          <div class="badges">
            {#if $preview}<span class="badge play">{@html icons.play} Previewing {$preview.label} · <span class="mono">{clock(Math.max(0, t - $preview.from))} / {clock($preview.to - $preview.from)}</span></span>
            {:else if outside}<span class="badge warn">Outside the kept part: learners don't see this</span>
            {:else if inCut}<span class="badge bad">In a cut: learners skip this</span>{/if}
          </div>
          {#if endCard}
            <div class="endcard" role="status">
              <p>{endCard.text}</p>
              <div class="row">
                {#if endCard.next !== null}<button class="btn sm hot" on:click={() => endCard?.next != null && playPart(endCard.next)}>{@html icons.play} Continue to part {endCard.next + 1}</button>{/if}
                {#if endCard.replay !== null}<button class="btn sm" on:click={() => endCard?.replay != null && playPart(endCard.replay)}>Replay</button>{/if}
                <button class="btn sm ghost" on:click={() => (endCard = null)}>Close</button>
              </div>
            </div>
          {/if}
          {#if previewError}<p class="perr">{previewError}</p>{/if}
          {#if $notice}<div class="notice {$notice.tone}" role="status">{$notice.text}</div>{/if}
        </div>

        <div class="transport">
          <div class="tgrp">
            <button class="tb" on:click={() => boundary(-1)} aria-label="Previous edit point" title="Previous edit point">⏮</button>
            <button class="tb" on:click={() => nudge(-5)} title="Back 5 s (Shift+←)">−5</button>
            <button class="tb play" on:click={() => st.toggle()} aria-label={$playing ? 'Pause' : 'Play'} title="Play/pause (Space)">
              {#if $playing}<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>
              {:else}<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M8 5.5v13l10.5-6.5z"/></svg>{/if}
            </button>
            <button class="tb" on:click={() => nudge(5)} title="Forward 5 s (Shift+→)">+5</button>
            <button class="tb" on:click={() => boundary(1)} aria-label="Next edit point" title="Next edit point">⏭</button>
          </div>
          <span class="tc mono">{clock(t)}<small>.{Math.floor((t % 1) * 10)}</small> <span class="muted">/ {clock(st.length)}</span></span>
          <span class="rt" title="How long learners watch, after trimming and cuts">Learners watch <b class="mono">{clock(runtime)}</b>{$parts.length > 1 ? ` in ${$parts.length} parts` : ''}</span>
          <div class="tgrp right">
            <button class="tb" class:on={$mark.in !== null} on:click={() => mark.update(m => ({ ...m, in: t }))} title="Mark in (I)">I</button>
            <button class="tb" class:on={$mark.out !== null} on:click={() => mark.update(m => ({ ...m, out: t }))} title="Mark out (O)">O</button>
            <button class="tb" on:click={() => cutMarked(st)} title="Cut the marked range (C)">✂</button>
            <button class="tb" on:click={() => splitAt(st, t)} title="Split at the playhead (S)">⟊</button>
            <button class="tb" class:on={$ccOn} on:click={() => ccOn.update(v => !v)} disabled={!segs.length} title="Captions in the preview">CC</button>
            <select class="rate" value={rate} on:change={e => setRate(+e.currentTarget.value)} aria-label="Preview speed">
              {#each [0.5, 0.75, 1, 1.25, 1.5, 2] as r}<option value={r}>{r}×</option>{/each}
            </select>
          </div>
        </div>
      </section>
    </div>

    <div class="tl-wrap"><Timeline /></div>

    {#if help}
      <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
      <div class="help" on:click|self={() => (help = false)}>
        <div class="help-in">
          <h3>Keyboard shortcuts</h3>
          <dl>
            <dt>Space / K</dt><dd>Play or pause</dd>
            <dt>← →</dt><dd>1 second (Shift: 5)</dd>
            <dt>J / L</dt><dd>10 seconds back / on</dd>
            <dt>, .</dt><dd>One frame</dd>
            <dt>I / O</dt><dd>Mark in / out</dd>
            <dt>C</dt><dd>Cut the marked range</dd>
            <dt>S</dt><dd>Split at the playhead</dd>
            <dt>[ / ]</dt><dd>Trim start / end to the playhead</dd>
            <dt>T</dt><dd>Add text at the playhead</dd>
            <dt>M</dt><dd>Add a chapter at the playhead</dd>
            <dt>Z / B</dt><dd>Zoom / blur at the playhead (or the marked range)</dd>
            <dt>Delete</dt><dd>Remove the selected cut, chapter, text or effect</dd>
            <dt>Ctrl+Z / Ctrl+Shift+Z</dt><dd>Undo / redo</dd>
            <dt>Ctrl+S</dt><dd>Save</dd>
            <dt>Shift-drag</dt><dd>Mark a range on the timeline</dd>
            <dt>Alt-drag</dt><dd>Move without snapping</dd>
            <dt>Ctrl+scroll</dt><dd>Zoom the timeline</dd>
          </dl>
          <button class="btn sm" on:click={() => (help = false)}>Close</button>
        </div>
      </div>
    {/if}
</div>

<style>
  .studio {
    --st-bg: #0e0f13; --st-panel: #15161c; --st-deep: #0a0b0e; --st-raise: #1e2028; --st-line: #2a2c36;
    --st-text: #ececf1; --st-muted: #9a9ba8; --st-hot: #ff3b45;
    position: fixed; inset: 0; z-index: 1000; background: var(--st-bg); color: var(--st-text);
    display: grid; grid-template-rows: auto 1fr auto; font-size: 0.86rem; color-scheme: dark;
  }

  .top { display: flex; align-items: center; gap: 0.8rem; padding: 0.55rem 0.9rem; border-bottom: 1px solid var(--st-line); background: var(--st-panel); }
  .ttl { min-width: 0; flex: 1; }
  .eyebrow { font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--st-muted); }
  .ttl h2 { font-size: 1rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .part { color: var(--st-muted); font-weight: 500; }
  .hbtns { display: flex; align-items: center; gap: 0.4rem; }
  .icon { width: 32px; height: 32px; border-radius: 8px; display: grid; place-items: center; color: var(--st-text); font-size: 1rem; }
  .icon:hover:not(:disabled) { background: var(--st-raise); }
  .icon:disabled { opacity: 0.35; }

  .main { display: grid; grid-template-columns: 76px 360px 1fr; min-height: 0; }
  .rail { display: grid; align-content: start; gap: 2px; padding: 0.5rem 0.35rem; border-right: 1px solid var(--st-line); background: var(--st-panel); overflow-y: auto; scrollbar-width: none; }
  .rail::-webkit-scrollbar { display: none; }
  .studio :global(*) { scrollbar-width: thin; scrollbar-color: #3a3c48 transparent; }
  .rail button { display: grid; justify-items: center; gap: 0.2rem; padding: 0.5rem 0.2rem; border-radius: 9px; color: var(--st-muted); font-size: 0.66rem; font-weight: 600; }
  .rail button:hover { color: var(--st-text); background: var(--st-raise); }
  .rail button.on { color: #fff; background: var(--st-raise); box-shadow: inset 2px 0 0 var(--st-hot); }
  .ri { font-size: 1.25rem; display: grid; }
  .panel { overflow-y: auto; padding: 0.8rem; display: grid; align-content: start; gap: 0.7rem; border-right: 1px solid var(--st-line); background: var(--st-bg); }

  .stage-col { display: grid; grid-template-rows: 1fr auto; min-height: 0; min-width: 0; padding: 0.8rem; gap: 0.6rem; }
  .stage { position: relative; background: #000; border-radius: 10px; overflow: hidden; min-height: 0; container-type: size; display: grid; place-items: center; }
  .frame { position: relative; width: min(100cqw, calc(100cqh * 16 / 9)); aspect-ratio: 16 / 9; overflow: hidden; container-type: inline-size; background: #000; }
  .frame video { width: 100%; height: 100%; object-fit: contain; display: block; cursor: pointer; transition: filter 150ms; }
  .badges { position: absolute; top: 8px; left: 8px; right: 8px; display: flex; pointer-events: none; z-index: 6; }
  .badge { display: inline-flex; gap: 0.35rem; align-items: center; height: 26px; padding: 0 0.6rem; border-radius: 7px; background: rgba(0,0,0,.7); font-size: 0.74rem; font-weight: 600; }
  .badge.warn { background: rgba(245,197,24,.9); color: #111; }
  .badge.bad { background: rgba(255,59,69,.9); color: #fff; }
  .endcard { position: absolute; inset: auto 0 0 0; padding: 1rem; background: linear-gradient(transparent, rgba(0,0,0,.9) 35%); display: grid; gap: 0.5rem; z-index: 7; }
  .endcard p { font-weight: 600; }
  .perr { position: absolute; inset: auto 0 0 0; padding: 0.5rem 0.8rem; font-size: 0.8rem; background: rgba(0,0,0,.75); z-index: 7; }
  .notice { position: absolute; left: 50%; bottom: 14px; translate: -50% 0; max-width: 90%; padding: 0.5rem 0.9rem; border-radius: 9px; font-size: 0.8rem; font-weight: 600; z-index: 8; box-shadow: 0 8px 24px rgba(0,0,0,.4); animation: pop-in 220ms ease-out; }
  .notice.ok { background: #e9fbe9; color: #0b3d16; }
  .notice.bad { background: #ffe1e3; color: #6a0710; }
  @keyframes pop-in { from { opacity: 0; translate: -50% 8px; } }

  .transport { display: flex; align-items: center; gap: 0.9rem; flex-wrap: wrap; }
  .tgrp { display: flex; gap: 0.25rem; align-items: center; }
  .tgrp.right { margin-left: auto; }
  .tb { min-width: 32px; height: 30px; padding: 0 0.45rem; border-radius: 7px; background: var(--st-raise); color: var(--st-text); font-size: 0.78rem; font-weight: 700; }
  .tb:hover:not(:disabled) { background: #2a2d38; }
  .tb.on { background: #2f4f8a; }
  .tb:disabled { opacity: 0.4; }
  .tb.play { width: 40px; height: 34px; background: #fff; color: #000; border-radius: 99px; display: grid; place-items: center; }
  .tc { font-size: 0.95rem; font-weight: 700; }
  .tc small { font-size: 0.7rem; color: var(--st-muted); }
  .rt { font-size: 0.76rem; color: var(--st-muted); }
  .rt b { color: var(--st-text); }
  .rate { height: 30px; border-radius: 7px; background: var(--st-raise); color: var(--st-text); border: 0; font-size: 0.76rem; padding: 0 0.3rem; }
  .tl-wrap { padding: 0.5rem 0.9rem 0.8rem; border-top: 1px solid var(--st-line); background: var(--st-panel); }

  .help { position: absolute; inset: 0; background: rgba(0,0,0,.55); display: grid; place-items: center; z-index: 20; }
  .help-in { background: var(--st-panel); border: 1px solid var(--st-line); border-radius: 14px; padding: 1.2rem 1.4rem; display: grid; gap: 0.8rem; min-width: 320px; }
  .help dl { display: grid; grid-template-columns: auto 1fr; gap: 0.35rem 1.2rem; font-size: 0.82rem; }
  .help dt { font-family: ui-monospace, Consolas, monospace; color: #fff; }
  .help dd { margin: 0; color: var(--st-muted); }

  /* Short screens: a tighter rail, so every tool fits without scrolling. */
  @media (max-height: 860px) {
    .rail button { padding: 0.3rem 0.2rem; gap: 0.1rem; font-size: 0.62rem; }
    .ri { font-size: 1.05rem; }
  }
  @media (max-width: 1100px) {
    .main { grid-template-columns: 64px 300px 1fr; }
  }
  @media (max-width: 820px) {
    .studio { overflow-y: auto; grid-template-rows: auto auto auto; }
    .main { grid-template-columns: 1fr; }
    .rail { grid-auto-flow: column; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--st-line); }
    .stage-col { order: -1; }
    .stage { aspect-ratio: 16/9; }
    .panel { border-right: 0; max-height: none; }
  }

  /* ---- shared by every panel ---- */
  .studio :global(.p-sec) { display: grid; gap: 0.55rem; padding: 0.75rem; border: 1px solid var(--st-line); border-radius: 12px; background: var(--st-panel); }
  .studio :global(.p-h) { font-size: 0.84rem; font-weight: 700; }
  .studio :global(.p-note) { font-size: 0.75rem; color: var(--st-muted); line-height: 1.45; }
  .studio :global(.p-bad) { font-size: 0.76rem; color: #ff9196; line-height: 1.45; }
  .studio :global(.row) { display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center; }
  .studio :global(.row.tight) { gap: 0.25rem; }
  .studio :global(.muted) { color: var(--st-muted); }
  .studio :global(.mono) { font-family: ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; }
  .studio :global(kbd) { font: inherit; font-size: 0.66rem; padding: 0 0.3em; border: 1px solid rgba(255,255,255,.25); border-radius: 4px; margin-left: 0.2rem; opacity: 0.8; }
  .studio :global(.btn) { display: inline-flex; align-items: center; gap: 0.35rem; height: 34px; padding: 0 0.9rem; border-radius: 8px; border: 1px solid var(--st-line); background: var(--st-raise); color: var(--st-text); font-weight: 600; font-size: 0.82rem; white-space: nowrap; }
  .studio :global(.btn:hover:not(:disabled)) { background: #2a2d38; }
  .studio :global(.btn.sm) { height: 30px; padding: 0 0.7rem; font-size: 0.76rem; }
  .studio :global(.btn.xs) { height: 24px; padding: 0 0.5rem; font-size: 0.7rem; border-radius: 6px; }
  .studio :global(.btn.hot) { background: var(--st-hot); border-color: var(--st-hot); color: #fff; }
  .studio :global(.btn.hot:hover:not(:disabled)) { background: #ff5960; }
  .studio :global(.btn.ai) { background: linear-gradient(135deg, #7b5cff, #4f7dff); border-color: transparent; color: #fff; }
  .studio :global(.btn.ghost) { background: transparent; }
  .studio :global(.btn.danger:hover:not(:disabled)) { background: rgba(255,59,69,.2); color: #fff; }
  .studio :global(.btn:disabled) { opacity: 0.45; cursor: not-allowed; }
  .studio :global(.btn svg) { font-size: 0.95em; }
  .studio :global(.field) { display: grid; gap: 0.25rem; font-size: 0.74rem; font-weight: 600; color: var(--st-muted); }
  .studio :global(input[type='text']), .studio :global(input[type='search']), .studio :global(select) {
    font: inherit; font-size: 0.82rem; color: var(--st-text); background: var(--st-deep); border: 1px solid var(--st-line); border-radius: 7px; padding: 0.35rem 0.55rem; min-width: 0;
  }
  .studio :global(input[type='text']:focus), .studio :global(input[type='search']:focus), .studio :global(select:focus) { outline: none; border-color: #6ea8ff; }
  .studio :global(.field.sm input) { width: 110px; font-variant-numeric: tabular-nums; }
  .studio :global(.seg-ctl) { display: inline-flex; padding: 2px; border-radius: 8px; background: var(--st-deep); border: 1px solid var(--st-line); flex-wrap: wrap; }
  .studio :global(.seg-ctl button) { height: 26px; padding: 0 0.65rem; border-radius: 6px; color: var(--st-muted); font-size: 0.74rem; font-weight: 600; }
  .studio :global(.seg-ctl.small button) { padding: 0 0.5rem; font-size: 0.7rem; }
  .studio :global(.seg-ctl button.on) { background: var(--st-raise); color: #fff; }
  .studio :global(.list) { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.35rem; }
  .studio :global(.list li) { display: grid; gap: 0.35rem; padding: 0.45rem 0.55rem; border: 1px solid var(--st-line); border-radius: 9px; background: var(--st-raise); font-size: 0.8rem; }
  .studio :global(.list li.cur) { border-color: #6ea8ff; }
  .studio :global(.list li.bad) { border-color: #ff4d5e; }
  .studio :global(.li-main) { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: baseline; }
</style>
