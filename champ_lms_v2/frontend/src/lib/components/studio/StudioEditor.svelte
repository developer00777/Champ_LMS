<script lang="ts">
  // The studio's editor, once VideoStudio has loaded the episode, laid out
  // like a phone video editor (InShot): the preview on top, the timeline
  // with its playhead fixed in the middle, and a strip of tools along the
  // bottom. A tool opens its sheet beside the preview (or over the timeline
  // on a narrow screen). It owns the shared state (studio.ts) that the
  // stage, timeline and sheets work on.
  import { onDestroy, onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { api, type StudioEpisode } from '$lib/api/client';
  import { clock, lineAt } from '$lib/utils/transcribe';
  import { cutAt, frameStyle, freezeAt, lookFilter, mutedAt, speedAt, type Effect, type Overlay } from '$lib/utils/video-edits';
  import EditedLayer from '$lib/components/video/EditedLayer.svelte';
  import BackdropFill from '$lib/components/video/BackdropFill.svelte';
  import { icons } from '$lib/components/course/icons';
  import {
    MIN_PART, addEffect, createStudio, cutMarked, provideStudio, removeSelected, round, splitAt, trimEnd, trimStart,
    type Tab,
  } from './studio';
  import StageBox from './StageBox.svelte';
  import Timeline from './Timeline.svelte';
  import AiPanel from './AiPanel.svelte';
  import TrimPanel from './TrimPanel.svelte';
  import CutsPanel from './CutsPanel.svelte';
  import CanvasPanel from './CanvasPanel.svelte';
  import FilterPanel from './FilterPanel.svelte';
  import EffectsPanel from './EffectsPanel.svelte';
  import SpeedPanel from './SpeedPanel.svelte';
  import TransitionPanel from './TransitionPanel.svelte';
  import MusicPanel from './MusicPanel.svelte';
  import VoicePanel from './VoicePanel.svelte';
  import TextPanel from './TextPanel.svelte';
  import StickerPanel from './StickerPanel.svelte';
  import CaptionsPanel from './CaptionsPanel.svelte';
  import ChaptersPanel from './ChaptersPanel.svelte';
  import LookPanel from './LookPanel.svelte';
  import DetailsPanel from './DetailsPanel.svelte';
  import ThumbPanel from './ThumbPanel.svelte';

  export let initial: StudioEpisode;
  export let localFile: File | null = null;
  export let onClose: () => void;
  export let onSaved: (ep: StudioEpisode) => void = () => {};

  const st = createStudio(initial);
  provideStudio(st);
  const { doc, time, playing, tab, preview, notice, canUndo, canRedo, ep, mark, ccOn, parts, selected, quiet } = st;
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
      st.source.set({ file: localFile, stream: null });
      objectUrl = URL.createObjectURL(localFile);
      videoEl.src = objectUrl;
      videoEl.addEventListener('loadedmetadata', () => { videoEl.currentTime = startAt; }, { once: true });
      return;
    }
    try {
      const sres = await api.streamUrl(episodeId);
      st.source.set({ file: null, stream: sres.stream_url });
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
    if (holdTimer) clearTimeout(holdTimer);
    st.mixer.destroy();
  });

  // Frame loop while playing: smooth playhead, cuts skipped, freezes held,
  // speed, mute and the mixed-in audio applied as learners get them, and a
  // preview run stopped at its end (with an end card between parts).
  let raf = 0;
  let endCard: { text: string; next: number | null; replay: number | null } | null = null;
  let holding = false;
  let holdTimer: ReturnType<typeof setTimeout> | null = null;
  const frozen = new Set<Effect>();
  function mix(now: number, isPlaying: boolean) {
    const p = $parts.find(x => now >= x.from - 0.05 && now <= x.to + 0.05);
    st.mixer.sync($doc.edits, now, { playing: isPlaying, rate, master: 1, end: p?.to ?? $doc.end });
  }
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
        const fz = freezeAt($doc.edits.effects, now);
        if (fz && !frozen.has(fz)) { hold(fz); return; }
        const want = rate * speedAt($doc.edits.effects, now);
        if (Math.abs(videoEl.playbackRate - want) > 0.001) videoEl.playbackRate = want;
        const mute = mutedAt($doc.edits.effects, now) || $quiet;
        if (videoEl.muted !== mute) videoEl.muted = mute;
        const vol = $doc.edits.audio.volume / 100;
        if (Math.abs(videoEl.volume - vol) > 0.001) videoEl.volume = vol;
        mix(now, true);
      }
      raf = requestAnimationFrame(frame);
    }
  }
  // A freeze holds the frame: pause for its hold, then play on, as learners see it.
  function hold(fz: Effect) {
    frozen.add(fz);
    holding = true;
    videoEl.pause();
    holdTimer = setTimeout(() => {
      holding = false;
      holdTimer = null;
      videoEl?.play().catch(() => {});
    }, ((fz.hold ?? 2) * 1000) / rate);
  }
  function onPlay() { playing.set(true); endCard = null; if (!raf) raf = requestAnimationFrame(frame); }
  function onPause() {
    if (holding) return;
    playing.set(false);
    st.mixer.pauseAll();
  }
  function onSeeking() {
    if (holding) { holding = false; if (holdTimer) clearTimeout(holdTimer); holdTimer = null; }
    for (const f of frozen) if (f.start > videoEl.currentTime) frozen.delete(f);
  }
  function onTimeUpdate() {
    if (videoEl.paused && !holding) { time.set(videoEl.currentTime); mix(videoEl.currentTime, false); }
  }

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
      ...d.edits.effects.flatMap(e => [e.start, e.end]), ...d.edits.audio.tracks.map(x => x.start)].sort((a, b) => a - b);
    const target = dir > 0 ? pts.find(p => p > t + 0.05) : [...pts].reverse().find(p => p < t - 0.05);
    if (target !== undefined) st.seek(target);
  }

  // ---- stage state ---------------------------------------------------------------
  $: look = $doc.edits.look;
  $: selIndex = $selected?.kind === 'effect' ? $selected.index : -1;
  $: selEffect = selIndex >= 0 ? $doc.edits.effects[selIndex] ?? null : null;
  $: selOverlay = $selected?.kind === 'overlay' ? $selected.index : -1;
  // Aiming a zoom, paused: show the whole picture, with the zoom's frame on it.
  $: aiming = !!selEffect && selEffect.kind === 'zoom' && !$playing;
  $: shownEffects = aiming ? $doc.edits.effects.filter(e => e !== selEffect) : $doc.edits.effects;
  $: videoStyle = [lookFilter(look) && `filter: ${lookFilter(look)};`, frameStyle(look, shownEffects, t, $doc.edits.cuts)].filter(Boolean).join(' ');
  $: picture = frameStyle(look, $doc.edits.effects, t, $doc.edits.cuts);
  $: partNow = $parts.find(p => t >= p.from - 0.05 && t <= p.to + 0.05) ?? null;
  $: outside = t < $doc.start - 0.05 || t > $doc.end + 0.05;
  $: inCut = !$playing && !!cutAt($doc.edits.cuts, t);
  $: segs = $doc.segments;
  $: frameBg = look.background === 'color' ? `background:${look.bg_color}` : '';

  // Text and stickers dragged on the picture: one undo step per drag.
  function moveOverlay(i: number, x: number, y: number, phase: 'start' | 'move' | 'end') {
    if (phase === 'start') { st.begin(); st.tab.set($doc.edits.overlays[i]?.style === 'sticker' ? 'sticker' : 'text'); return; }
    if (phase === 'end') { st.end(); return; }
    st.live(d => { const o = d.edits.overlays[i]; if (o) { o.position = 'free'; o.x = x; o.y = y; } });
  }

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

  // ---- tools ----------------------------------------------------------------------
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
  function freezeHere() {
    if ($doc.edits.effects.some(e => e.kind === 'freeze' && Math.abs(e.start - t) < 0.5)) { tab.set('speed'); return; }
    addEffect(st, 'freeze');
    tab.set('speed');
    st.say(`The frame at ${clock(t)} holds for 2 seconds.`);
  }

  const ic = (d: string, extra = '') =>
    `<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"${extra}>${d}</svg>`;
  // The bottom strip, in InShot's order: cutting first, then the picture,
  // then what goes over it, then sound, then the rest. `run` tools act
  // straight away; the others open their sheet.
  const TOOLS: { id: Tab; label: string; icon: string; run?: () => void }[] = [
    { id: 'trim', label: 'Trim', icon: ic('<path d="M7 4v16M17 4v16M4 8h3M17 8h3M4 16h3M17 16h3"/>') },
    { id: 'trim', label: 'Split', icon: ic('<path d="M12 3v18M5 7h4M15 7h4M5 17h4M15 17h4"/><path d="M9 7l-2 5 2 5M15 7l2 5-2 5"/>'), run: () => { splitAt(st, t); tab.set('trim'); } },
    { id: 'cuts', label: 'Cut', icon: ic('<circle cx="6" cy="7" r="2.5"/><circle cx="6" cy="17" r="2.5"/><path d="M8 8.5l12 8M8 15.5l12-8"/>') },
    { id: 'speed', label: 'Speed', icon: ic('<path d="M4 16a8 8 0 1116 0"/><path d="M12 16l4-5"/>') },
    { id: 'speed', label: 'Freeze', icon: ic('<path d="M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9M9.5 4.5L12 7l2.5-2.5M9.5 19.5L12 17l2.5 2.5"/>'), run: freezeHere },
    { id: 'canvas', label: 'Canvas', icon: ic('<rect x="3" y="5" width="18" height="14" rx="2"/><rect x="7.5" y="8" width="9" height="8" rx="1"/>') },
    { id: 'filter', label: 'Filter', icon: ic('<circle cx="9" cy="10" r="5"/><circle cx="15" cy="10" r="5"/><circle cx="12" cy="15" r="5"/>') },
    { id: 'effects', label: 'Effects', icon: ic('<path d="M4 20l9-9M14 4v3M14 13v3M10 8H7M21 8h-3M17.5 4.5l-2 2M12.5 11.5l-2-2"/>') },
    { id: 'transition', label: 'Transition', icon: ic('<rect x="3" y="6" width="9" height="12" rx="1.5"/><rect x="12" y="6" width="9" height="12" rx="1.5"/><path d="M10 12h4M12.5 10.5L14 12l-1.5 1.5"/>') },
    { id: 'text', label: 'Text', icon: ic('<path d="M5 6V4.5h14V6M12 4.5V19.5M9 19.5h6"/>') },
    { id: 'sticker', label: 'Sticker', icon: ic('<circle cx="12" cy="12" r="8.5"/><path d="M8.5 14.5a4.5 4.5 0 007 0"/><path d="M9.5 9.5h.01M14.5 9.5h.01" stroke-width="2.6"/>') },
    { id: 'music', label: 'Music', icon: ic('<path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>') },
    { id: 'voice', label: 'Record', icon: ic('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0013 0M12 17.5V21"/>') },
    { id: 'captions', label: 'Captions', icon: icons.cc },
    { id: 'ai', label: 'AI', icon: icons.sparkle },
    { id: 'chapters', label: 'Chapters', icon: ic('<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>') },
    { id: 'look', label: 'Brand', icon: ic('<path d="M12 3s6 6.2 6 10.5A6 6 0 016 13.5C6 9.2 12 3 12 3z"/>') },
    { id: 'details', label: 'Details', icon: ic('<path d="M5 6h14M5 11h14M5 16h9"/>') },
    { id: 'thumb', label: 'Thumbnail', icon: ic('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/><circle cx="15.5" cy="9.5" r="1.5"/>') },
  ];
  const NAMES: Record<Tab, string> = {
    ai: 'AI editor', trim: 'Trim and split', cuts: 'Cut', canvas: 'Canvas', filter: 'Filter', effects: 'Effects', speed: 'Speed and freeze',
    transition: 'Transition', music: 'Music', voice: 'Voice-over', text: 'Text', sticker: 'Stickers', captions: 'Captions',
    chapters: 'Chapters', look: 'Brand and fades', details: 'Details', thumb: 'Thumbnail',
  };
  function useTool(tl: (typeof TOOLS)[number]) {
    if (tl.run) { tl.run(); return; }
    tab.update(cur => (cur === tl.id ? null : tl.id));
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
    else if (k === 'f') freezeHere();
    else if (k === 'z') { tab.set('effects'); addEffect(st, 'zoom'); }
    else if (k === 'b') { tab.set('effects'); addEffect(st, 'blur'); }
    else if (k === 'Delete' || k === 'Backspace') { if (removeSelected(st)) e.preventDefault(); }
    else if (k === '?') help = !help;
    else if (k === 'Escape') {
      if (help) help = false;
      else if (get(st.selected) || get(st.mark).in !== null) { st.selected.set(null); st.mark.set({ in: null, out: null }); }
      else if (get(tab)) tab.set(null);
      else close();
    }
  }

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
      <button class="icon help-btn" on:click={() => (help = !help)} aria-label="Keyboard shortcuts" title="Shortcuts (?)">?</button>
      <button class="btn sm" on:click={() => playPart(0)} disabled={tooShort}
        title="Play it the way learners will get it: trimmed, cut, and stopping at each split">{@html icons.play} <span class="hide-sm">Preview as learner</span></button>
      <button class="btn save" on:click={save} disabled={busy || !dirty || tooShort} title="Save (Ctrl+S)">
        {busy ? 'Saving…' : $parts.length > 1 ? `Save · ${$parts.length} parts` : dirty ? 'Save' : 'Saved'}
      </button>
    </div>
  </header>

  <div class="work" class:open={!!$tab}>
    <section class="stage-col">
      <div class="stage">
        <!-- The learner's player is 16:9, so the preview is too: text and
             boxes land where learners will see them. -->
        <div class="frame" style={frameBg}>
          <BackdropFill video={videoEl ?? null} active={look.background === 'blur'} />
          <!-- svelte-ignore a11y-media-has-caption a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
          <video bind:this={videoEl} preload="metadata" playsinline style={videoStyle}
            on:play={onPlay} on:pause={onPause} on:seeking={onSeeking} on:timeupdate={onTimeUpdate} on:click={() => st.toggle()}></video>
          <EditedLayer edits={$doc.edits} {t} from={partNow?.from ?? $doc.start} to={partNow?.to ?? $doc.end}
            captions={segs} ccOn={$ccOn} editable={!$playing} selected={selOverlay}
            onPick={i => selected.set({ kind: 'overlay', index: i })} onMove={moveOverlay} />
          {#if selEffect && (selEffect.kind === 'blur' || selEffect.kind === 'zoom') && !$playing}
            <StageBox effect={selEffect} index={selIndex} {picture} />
          {/if}
        </div>
        <div class="badges">
          {#if $preview}<span class="badge play">{@html icons.play} Previewing {$preview.label} · <span class="mono">{clock(Math.max(0, t - $preview.from))} / {clock($preview.to - $preview.from)}</span></span>
          {:else if holding}<span class="badge">❄ Frozen frame</span>
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
        <span class="tc mono">{clock(t)}<small>.{Math.floor((t % 1) * 10)}</small> <span class="muted">/ {clock(st.length)}</span></span>
        <div class="tgrp mid">
          <button class="tb" on:click={() => boundary(-1)} aria-label="Previous edit point" title="Previous edit point">⏮</button>
          <button class="tb" on:click={() => nudge(-5)} title="Back 5 s (Shift+←)">−5</button>
          <button class="tb play" on:click={() => st.toggle()} aria-label={$playing ? 'Pause' : 'Play'} title="Play/pause (Space)">
            {#if $playing}<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>
            {:else}<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M8 5.5v13l10.5-6.5z"/></svg>{/if}
          </button>
          <button class="tb" on:click={() => nudge(5)} title="Forward 5 s (Shift+→)">+5</button>
          <button class="tb" on:click={() => boundary(1)} aria-label="Next edit point" title="Next edit point">⏭</button>
        </div>
        <div class="tgrp right">
          <span class="rt" title="How long learners watch, after trimming, cuts, speed and freezes">Plays <b class="mono">{clock(runtime)}</b>{$parts.length > 1 ? ` · ${$parts.length} parts` : ''}</span>
          <button class="tb" class:on={$mark.in !== null} on:click={() => mark.update(m => ({ ...m, in: t }))} title="Mark in (I)">I</button>
          <button class="tb" class:on={$mark.out !== null} on:click={() => mark.update(m => ({ ...m, out: t }))} title="Mark out (O)">O</button>
          <button class="tb" on:click={() => cutMarked(st)} title="Cut the marked range (C)">✂</button>
          <button class="tb" class:on={$ccOn} on:click={() => ccOn.update(v => !v)} disabled={!segs.length} title="Captions in the preview">CC</button>
          <select class="rate" value={rate} on:change={e => setRate(+e.currentTarget.value)} aria-label="Preview speed">
            {#each [0.5, 0.75, 1, 1.25, 1.5, 2] as r}<option value={r}>{r}×</option>{/each}
          </select>
        </div>
      </div>
    </section>

    {#if $tab}
      <aside class="sheet" aria-label={NAMES[$tab]}>
        <div class="sheet-head">
          <b>{NAMES[$tab]}</b>
          <button class="done" on:click={() => tab.set(null)} aria-label="Close {NAMES[$tab]}" title="Done (Esc)">✓</button>
        </div>
        <div class="sheet-body">
          {#if $tab === 'ai'}<AiPanel />
          {:else if $tab === 'trim'}<TrimPanel {dirty} onJoined={() => onSaved(get(ep))} />
          {:else if $tab === 'cuts'}<CutsPanel />
          {:else if $tab === 'canvas'}<CanvasPanel />
          {:else if $tab === 'filter'}<FilterPanel />
          {:else if $tab === 'effects'}<EffectsPanel />
          {:else if $tab === 'speed'}<SpeedPanel />
          {:else if $tab === 'transition'}<TransitionPanel />
          {:else if $tab === 'music'}<MusicPanel />
          {:else if $tab === 'voice'}<VoicePanel />
          {:else if $tab === 'text'}<TextPanel />
          {:else if $tab === 'sticker'}<StickerPanel />
          {:else if $tab === 'captions'}<CaptionsPanel {localFile} />
          {:else if $tab === 'chapters'}<ChaptersPanel />
          {:else if $tab === 'look'}<LookPanel />
          {:else if $tab === 'details'}<DetailsPanel />
          {:else}<ThumbPanel />{/if}
        </div>
      </aside>
    {/if}
  </div>

  <div class="tl-wrap"><Timeline /></div>

  <nav class="toolbar" aria-label="Studio tools">
    {#each TOOLS as tl}
      <button class="tool" class:on={!tl.run && $tab === tl.id} on:click={() => useTool(tl)} aria-pressed={!tl.run && $tab === tl.id}>
        <span class="ti">{@html tl.icon}</span><span class="tlabel">{tl.label}</span>
      </button>
    {/each}
  </nav>

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
          <dt>F</dt><dd>Freeze the frame at the playhead</dd>
          <dt>Z / B</dt><dd>Zoom / blur at the playhead (or the marked range)</dd>
          <dt>Delete</dt><dd>Remove the selected cut, chapter, text or effect</dd>
          <dt>Ctrl+Z / Ctrl+Shift+Z</dt><dd>Undo / redo</dd>
          <dt>Ctrl+S</dt><dd>Save</dd>
          <dt>Drag the timeline</dt><dd>Move through the video</dd>
          <dt>Shift-drag</dt><dd>Mark a range on the timeline</dd>
          <dt>Alt-drag</dt><dd>Move without snapping</dd>
          <dt>Ctrl+scroll</dt><dd>Zoom the timeline</dd>
          <dt>Esc</dt><dd>Close the open tool</dd>
        </dl>
        <button class="btn sm" on:click={() => (help = false)}>Close</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .studio {
    --st-bg: #0d0d10; --st-panel: #16161b; --st-deep: #0a0a0d; --st-raise: #212128; --st-line: #2b2b33;
    --st-text: #f1f1f4; --st-muted: #9b9ba6; --st-hot: #ff3b45; --st-mint: #2ee6a6;
    position: fixed; inset: 0; z-index: 1000; background: var(--st-bg); color: var(--st-text);
    display: grid; grid-template-rows: auto minmax(0, 1fr) auto auto; font-size: 0.86rem; color-scheme: dark;
  }
  .studio :global(*) { scrollbar-width: thin; scrollbar-color: #3a3c48 transparent; }

  .top { display: flex; align-items: center; gap: 0.8rem; padding: 0.5rem 0.9rem; border-bottom: 1px solid var(--st-line); }
  .ttl { min-width: 0; flex: 1; }
  .eyebrow { font-size: 0.64rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--st-muted); }
  .ttl h2 { font-size: 0.98rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .part { color: var(--st-muted); font-weight: 500; }
  .hbtns { display: flex; align-items: center; gap: 0.4rem; flex: none; }
  .icon { width: 32px; height: 32px; border-radius: 99px; display: grid; place-items: center; color: var(--st-text); font-size: 1rem; }
  .icon:hover:not(:disabled) { background: var(--st-raise); }
  .icon:disabled { opacity: 0.35; }
  .studio :global(.btn.save) { height: 34px; padding: 0 1.2rem; border-radius: 99px; background: var(--st-mint); border-color: var(--st-mint); color: #04261b; font-weight: 800; }
  .studio :global(.btn.save:hover:not(:disabled)) { background: #5af0bd; }

  .work { display: grid; grid-template-columns: minmax(0, 1fr); min-height: 0; }
  .work.open { grid-template-columns: minmax(0, 1fr) 380px; }
  .stage-col { display: grid; grid-template-rows: minmax(0, 1fr) auto; min-height: 0; min-width: 0; padding: 0.7rem 0.9rem 0.4rem; gap: 0.5rem; }
  .stage { position: relative; background: #000; border-radius: 14px; overflow: hidden; min-height: 0; container-type: size; display: grid; place-items: center; }
  .frame { position: relative; width: min(100cqw, calc(100cqh * 16 / 9)); aspect-ratio: 16 / 9; overflow: hidden; container-type: inline-size; background: #000; }
  /* Positioned, so it paints over the canvas's blurred fill behind it. */
  .frame video { position: relative; width: 100%; height: 100%; object-fit: contain; display: block; cursor: pointer; transition: filter 150ms; }
  .badges { position: absolute; top: 8px; left: 8px; right: 8px; display: flex; pointer-events: none; z-index: 6; }
  .badge { display: inline-flex; gap: 0.35rem; align-items: center; height: 26px; padding: 0 0.6rem; border-radius: 7px; background: rgba(0,0,0,.7); font-size: 0.74rem; font-weight: 600; }
  .badge.warn { background: rgba(245,197,24,.9); color: #111; }
  .badge.bad { background: rgba(255,59,69,.9); color: #fff; }
  .endcard { position: absolute; inset: auto 0 0 0; padding: 1rem; background: linear-gradient(transparent, rgba(0,0,0,.9) 35%); display: grid; gap: 0.5rem; z-index: 7; }
  .endcard p { font-weight: 600; }
  .perr { position: absolute; inset: auto 0 0 0; padding: 0.5rem 0.8rem; font-size: 0.8rem; background: rgba(0,0,0,.75); z-index: 7; }
  .notice { position: absolute; left: 50%; bottom: 14px; translate: -50% 0; max-width: 90%; padding: 0.5rem 0.9rem; border-radius: 99px; font-size: 0.8rem; font-weight: 600; z-index: 8; box-shadow: 0 8px 24px rgba(0,0,0,.4); animation: pop-in 220ms ease-out; }
  .notice.ok { background: #e6fff5; color: #04392a; }
  .notice.bad { background: #ffe1e3; color: #6a0710; }
  @keyframes pop-in { from { opacity: 0; translate: -50% 8px; } }

  .transport { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 0.8rem; }
  .tgrp { display: flex; gap: 0.25rem; align-items: center; }
  .tgrp.right { justify-content: flex-end; flex-wrap: wrap; }
  .tb { min-width: 32px; height: 30px; padding: 0 0.45rem; border-radius: 8px; background: var(--st-raise); color: var(--st-text); font-size: 0.78rem; font-weight: 700; }
  .tb:hover:not(:disabled) { background: #2c2c35; }
  .tb.on { background: #2f4f8a; }
  .tb:disabled { opacity: 0.4; }
  .tb.play { width: 44px; height: 38px; background: #fff; color: #000; border-radius: 99px; display: grid; place-items: center; }
  .tc { font-size: 0.95rem; font-weight: 700; }
  .tc small { font-size: 0.7rem; color: var(--st-muted); }
  .rt { font-size: 0.74rem; color: var(--st-muted); margin-right: 0.3rem; }
  .rt b { color: var(--st-text); }
  .rate { height: 30px; border-radius: 8px; background: var(--st-raise); color: var(--st-text); border: 0; font-size: 0.76rem; padding: 0 0.3rem; }

  .sheet { display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 0; border-left: 1px solid var(--st-line); background: var(--st-bg); animation: sheet-in 200ms ease-out; }
  @keyframes sheet-in { from { opacity: 0; translate: 16px 0; } }
  .sheet-head { display: flex; align-items: center; justify-content: space-between; padding: 0.6rem 0.8rem; border-bottom: 1px solid var(--st-line); }
  .sheet-head b { font-size: 0.92rem; }
  .done { width: 32px; height: 32px; border-radius: 99px; background: var(--st-mint); color: #04261b; font-weight: 900; font-size: 1rem; display: grid; place-items: center; }
  .sheet-body { overflow-y: auto; padding: 0.8rem; display: grid; align-content: start; gap: 0.7rem; }

  .tl-wrap { padding: 0.4rem 0.9rem 0.5rem; border-top: 1px solid var(--st-line); background: var(--st-panel); }

  .toolbar { display: flex; gap: 0.15rem; overflow-x: auto; padding: 0.45rem 0.6rem 0.55rem; border-top: 1px solid var(--st-line); background: var(--st-panel); scrollbar-width: none; }
  .toolbar::-webkit-scrollbar { display: none; }
  .tool { flex: none; display: grid; justify-items: center; gap: 0.25rem; min-width: 62px; padding: 0.3rem 0.2rem; border-radius: 12px; color: var(--st-muted); font-size: 0.66rem; font-weight: 600; }
  .ti { width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; font-size: 1.25rem; background: var(--st-raise); color: var(--st-text); transition: background 120ms, color 120ms, transform 120ms; }
  .tool:hover .ti { background: #2c2c35; transform: translateY(-1px); }
  .tool:hover { color: var(--st-text); }
  .tool.on .ti { background: #fff; color: #000; }
  .tool.on { color: #fff; }

  .help { position: absolute; inset: 0; background: rgba(0,0,0,.55); display: grid; place-items: center; z-index: 20; }
  .help-in { background: var(--st-panel); border: 1px solid var(--st-line); border-radius: 14px; padding: 1.2rem 1.4rem; display: grid; gap: 0.8rem; min-width: 320px; max-height: 90vh; overflow: auto; }
  .help dl { display: grid; grid-template-columns: auto 1fr; gap: 0.35rem 1.2rem; font-size: 0.82rem; }
  .help dt { font-family: ui-monospace, Consolas, monospace; color: #fff; }
  .help dd { margin: 0; color: var(--st-muted); }

  @media (max-width: 1200px) {
    .work.open { grid-template-columns: minmax(0, 1fr) 330px; }
  }
  /* Narrow screens: the phone layout. The sheet slides up over the timeline. */
  @media (max-width: 900px) {
    .work.open { grid-template-columns: minmax(0, 1fr); }
    .sheet { position: fixed; left: 0; right: 0; bottom: 0; max-height: 62vh; z-index: 12; border-left: 0; border-top: 1px solid var(--st-line);
      border-radius: 18px 18px 0 0; box-shadow: 0 -18px 40px rgba(0,0,0,.5); animation: sheet-up 220ms ease-out; }
    @keyframes sheet-up { from { translate: 0 30px; opacity: 0; } }
    .transport { grid-template-columns: auto 1fr; }
    .tgrp.mid { justify-content: flex-end; }
    .tgrp.right { grid-column: 1 / -1; justify-content: flex-start; }
    .hide-sm { display: none; }
  }
  @media (max-width: 600px) {
    .top { gap: 0.4rem; padding: 0.45rem 0.6rem; }
    .eyebrow, .help-btn { display: none; }
    .ttl h2 { font-size: 0.9rem; }
  }

  /* ---- shared by every panel ---- */
  .studio :global(.p-sec) { display: grid; gap: 0.55rem; padding: 0.75rem; border: 1px solid var(--st-line); border-radius: 14px; background: var(--st-panel); }
  .studio :global(.p-h) { font-size: 0.84rem; font-weight: 700; }
  .studio :global(.p-note) { font-size: 0.75rem; color: var(--st-muted); line-height: 1.45; }
  .studio :global(.p-bad) { font-size: 0.76rem; color: #ff9196; line-height: 1.45; }
  .studio :global(.row) { display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center; }
  .studio :global(.row.tight) { gap: 0.25rem; }
  .studio :global(.muted) { color: var(--st-muted); }
  .studio :global(.mono) { font-family: ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; }
  .studio :global(kbd) { font: inherit; font-size: 0.66rem; padding: 0 0.3em; border: 1px solid rgba(255,255,255,.25); border-radius: 4px; margin-left: 0.2rem; opacity: 0.8; }
  .studio :global(.btn) { display: inline-flex; align-items: center; gap: 0.35rem; height: 34px; padding: 0 0.9rem; border-radius: 9px; border: 1px solid var(--st-line); background: var(--st-raise); color: var(--st-text); font-weight: 600; font-size: 0.82rem; white-space: nowrap; }
  .studio :global(.btn:hover:not(:disabled)) { background: #2c2c35; }
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
    font: inherit; font-size: 0.82rem; color: var(--st-text); background: var(--st-deep); border: 1px solid var(--st-line); border-radius: 8px; padding: 0.35rem 0.55rem; min-width: 0;
  }
  .studio :global(input[type='text']:focus), .studio :global(input[type='search']:focus), .studio :global(select:focus) { outline: none; border-color: #6ea8ff; }
  .studio :global(.field.sm input) { width: 110px; font-variant-numeric: tabular-nums; }
  .studio :global(.seg-ctl) { display: inline-flex; padding: 2px; border-radius: 9px; background: var(--st-deep); border: 1px solid var(--st-line); flex-wrap: wrap; }
  .studio :global(.seg-ctl button) { height: 26px; padding: 0 0.65rem; border-radius: 7px; color: var(--st-muted); font-size: 0.74rem; font-weight: 600; }
  .studio :global(.seg-ctl.small button) { padding: 0 0.5rem; font-size: 0.7rem; }
  .studio :global(.seg-ctl button.on) { background: var(--st-raise); color: #fff; }
  .studio :global(.seg-ctl button:disabled) { opacity: 0.4; }
  .studio :global(.list) { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.35rem; }
  .studio :global(.list li) { display: grid; gap: 0.35rem; padding: 0.45rem 0.55rem; border: 1px solid var(--st-line); border-radius: 10px; background: var(--st-raise); font-size: 0.8rem; }
  .studio :global(.list li.cur) { border-color: #6ea8ff; }
  .studio :global(.list li.bad) { border-color: #ff4d5e; }
  .studio :global(.li-main) { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: baseline; }
</style>
