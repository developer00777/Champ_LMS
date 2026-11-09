<script lang="ts">
  // The studio's editor, once VideoStudio has loaded the episode, laid out
  // like a desktop video editor: a top bar (where you are, save state,
  // undo, preview, save), the preview with its transport and a floating dock
  // of tools under it, a properties panel on the right (the open tool, or an
  // overview of the edit when none is open), and the timeline across the
  // bottom. On a phone the dock is a strip you swipe and the panel a sheet. It owns the shared state (studio.ts) that the
  // stage, timeline and panels work on.
  import { onDestroy, onMount, tick } from 'svelte';
  import { get } from 'svelte/store';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { isAdmin } from '$lib/stores/auth';
  import { pendingRequests } from '$lib/stores/test-requests';
  import { NAV } from '$lib/nav';
  import Icon from '$lib/components/Icon.svelte';
  import { api, type StudioEpisode } from '$lib/api/client';
  import { clock, lineAt } from '$lib/utils/transcribe';
  import { cutAt, frameStyle, freezeAt, lookFilter, mutedAt, speedAt, type Effect, type Overlay } from '$lib/utils/video-edits';
  import EditedLayer from '$lib/components/video/EditedLayer.svelte';
  import BackdropFill from '$lib/components/video/BackdropFill.svelte';
  import { icons } from '$lib/components/course/icons';
  import { theme } from '$lib/stores/theme';
  import { confirmDialog, openDialog } from '$lib/stores/dialog';
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
  import StudioTour from './StudioTour.svelte';
  import FloatingDock from './FloatingDock.svelte';
  import type { Result } from './tour';

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
        // A dropped connection or a decode hiccup is often only that: try
        // again a few times before giving up on the preview.
        let retries = 0;
        hls.on(Hls.Events.ERROR, (_e: unknown, d: any) => {
          if (!d?.fatal) return;
          if (retries < 3 && d.type === Hls.ErrorTypes.MEDIA_ERROR) { retries++; hls.recoverMediaError(); return; }
          const code = d.response?.code ?? d.networkDetails?.status;
          const refused = code === 401 || code === 403 || code === 404;
          if (retries < 3 && d.type === Hls.ErrorTypes.NETWORK_ERROR && !refused) {
            retries++;
            setTimeout(() => hls?.startLoad(), 1000 * retries);
            return;
          }
          previewError = previewProblem(d.details, code);
        });
        hls.loadSource(sres.stream_url);
        hls.attachMedia(videoEl);
      } else {
        videoEl.src = sres.stream_url;
        videoEl.addEventListener('loadedmetadata', () => { videoEl.currentTime = startAt; }, { once: true });
      }
    } catch (e: any) {
      previewError = `The preview couldn't load: ${e?.message ?? 'the video stream was unavailable'}. You can still edit on the timeline and type times.`;
    }
  });

  /** Why the preview failed, in words an admin can act on. */
  function previewProblem(details: string | undefined, code: number | undefined): string {
    const tail = ' You can still edit on the timeline and type times.';
    if (code === 401 || code === 403) {
      return `The preview couldn't load: Bunny refused the video stream (${code}). Bunny's token authentication is blocking the direct stream the studio needs; learners still get Bunny's own player.` + tail;
    }
    if (code === 404) return "The preview couldn't load: Bunny says the video isn't there (404). It may still be processing, or have been deleted." + tail;
    if (code === 0 || details?.includes('Timeout')) return "The preview couldn't load: Bunny didn't answer. Check the connection (or a network filter blocking Bunny's CDN), then reopen the studio." + tail;
    return `The preview couldn't load (${details ?? 'stream error'}${code ? `, HTTP ${code}` : ''}).` + tail;
  }
  function onVideoError() {
    // A file picked in this session that the browser can't decode (MKV, HEVC...).
    if (localFile && !previewError) previewError = `This browser can't play ${localFile.name} in the preview. You can still edit on the timeline and type times.`;
  }

  // ---- layout: properties panel, timeline height ----------------------------------
  // Remembered between visits, so an admin who wants a big preview keeps it.
  const UI_KEY = 'champ_studio_layout';
  let propsOpen = true;
  let tlH = 0; // timeline lanes' height in px; 0 = their natural height
  try {
    const s = JSON.parse(localStorage.getItem(UI_KEY) ?? '{}');
    propsOpen = s.propsOpen ?? true; tlH = +s.tlH || 0;
  } catch { /* storage blocked */ }
  function saveLayout() { try { localStorage.setItem(UI_KEY, JSON.stringify({ propsOpen, tlH })); } catch { /* storage blocked */ } }
  let winW = 1600; // the dock uses smaller icons below 1360px
  // Opening a tool always shows the panel, even when it's been hidden.
  $: showProps = propsOpen || !!$tab;
  let tlWrapEl: HTMLElement;
  function resizeTimeline(e: PointerEvent) {
    const body = tlWrapEl?.querySelector('.tl-body') as HTMLElement | null;
    if (!body) return;
    e.preventDefault();
    const startY = e.clientY, startH = body.getBoundingClientRect().height;
    const natural = body.scrollHeight;
    const move = (ev: PointerEvent) => {
      const h = Math.round(startH + (startY - ev.clientY));
      tlH = Math.max(96, Math.min(natural, h, Math.round(window.innerHeight * 0.55)));
    };
    const up = () => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up);
      if (tlH >= natural - 2) tlH = 0;
      saveLayout();
    };
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up);
  }

  // ---- the tour and the feature check ---------------------------------------------
  const TOUR_KEY = 'champ_studio_tour_offered';
  let studioEl: HTMLElement;
  let tourMode: 'tour' | 'check' | null = null;
  let tourResults: Record<string, Result> = {};
  let tourSnapshot: string | null = null;
  let tourOffer = false;
  try { tourOffer = !localStorage.getItem(TOUR_KEY); } catch { /* storage blocked */ }
  function openTour(m: 'tour' | 'check') {
    tourOffer = false;
    try { localStorage.setItem(TOUR_KEY, '1'); } catch { /* storage blocked */ }
    tourMode = m;
  }
  // Leaving the tour with its sample edits still on the video: ask what to do with them first.
  function closeTour() {
    if (tourSnapshot && tourMode === 'tour') { tourMode = 'check'; return; }
    tourMode = null;
  }
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
  /** True once saved. */
  async function save(): Promise<boolean> {
    if (busy) return false;
    if (tourSnapshot && !(await confirmDialog({
      title: "Save the tour's sample edits too?",
      message: "The tour's sample edits (a sticker, a chime, a cut…) are still on this video.\n\nTo save without them, go back and use Undo the tour's edits in the feature check.",
      confirm: 'Save them too', cancel: 'Go back', icon: 'alert',
    }))) return false;
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
      tourSnapshot = null;
      st.say(made > 1 ? `Saved. The video is now ${made} episodes; this is part 1.` : 'Saved. Learners get the edited video now.');
      onSaved(res);
      return true;
    } catch (e: any) { st.say(e.message, 'bad'); return false; }
    finally { busy = false; }
  }
  let closing = false;
  /** Leaves the studio, asking about unsaved edits first. False if it stayed open. */
  async function close(): Promise<boolean> {
    if (busy || closing) return false;
    if (dirty) {
      closing = true;
      const choice = await openDialog({
        title: 'Save your changes before closing?',
        message: tooShort
          ? `You have edits that aren't saved yet. They can't be saved as they are: every part must play at least ${MIN_PART} seconds.`
          : "You have edits that aren't saved yet. Learners only see them once they're saved.",
        icon: 'unsaved', tone: 'warn',
        actions: [
          { id: 'keep', label: 'Keep editing', kind: 'ghost' },
          { id: 'discard', label: 'Discard changes', kind: 'danger' },
          { id: 'save', label: 'Save and close', kind: 'primary', disabled: tooShort },
        ],
        focus: tooShort ? 'keep' : 'save',
      });
      closing = false;
      if (choice === 'save') { if (!(await save())) return false; }
      else if (choice !== 'discard') return false;
    }
    onClose();
    return true;
  }

  // ---- app menu -------------------------------------------------------------------
  // The studio covers the app's top bar, so its own bar carries the main
  // navigation. Going somewhere closes the studio first (same unsaved-edits
  // question as ✕), and only then navigates.
  let appMenu = false;
  let appMenuBtn: HTMLButtonElement;
  let appMenuEl: HTMLElement;
  $: navItems = NAV.filter(i => !i.admin || $isAdmin);
  async function toggleAppMenu() {
    appMenu = !appMenu;
    if (appMenu) { await tick(); appMenuEl?.querySelector<HTMLElement>('a')?.focus(); }
  }
  async function goTo(href: string) {
    // Focus the menu button before its link goes, so "Keep editing" in the
    // unsaved-edits question hands focus back there, not to the page body.
    appMenuBtn?.focus();
    appMenu = false;
    if (await close()) goto(href);
  }
  /** Tabbing out of the menu closes it. */
  function menuFocusOut(e: FocusEvent) {
    const next = e.relatedTarget as Node | null;
    if (next && !(e.currentTarget as HTMLElement).contains(next)) appMenu = false;
  }
  function clickAway(node: HTMLElement) {
    const handler = (e: MouseEvent) => { if (!node.contains(e.target as Node)) appMenu = false; };
    document.addEventListener('click', handler, true);
    return { destroy: () => document.removeEventListener('click', handler, true) };
  }
  function menuKeys(e: KeyboardEvent) {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    e.stopPropagation();
    const links = [...appMenuEl.querySelectorAll<HTMLElement>('a')];
    const i = links.indexOf(document.activeElement as HTMLElement);
    links[(i + (e.key === 'ArrowDown' ? 1 : -1) + links.length) % links.length]?.focus();
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
  // The tools, in groups (dividers on the dock). `label` is also the tour's handle
  // (data-tool), so it stays as is. `run` tools act at the playhead straight
  // away; the others open their panel on the right. `key` is the shortcut.
  type Tool = { id: Tab; label: string; icon: string; desc: string; key?: string; run?: () => void };
  const GROUPS: { name: string; tools: Tool[] }[] = [
    { name: 'Assist', tools: [
      { id: 'ai', label: 'AI', icon: icons.sparkle, desc: 'Let AI suggest edits from the transcript' },
    ] },
    { name: 'Edit', tools: [
      { id: 'trim', label: 'Trim', icon: ic('<path d="M7 4v16M17 4v16M4 8h3M17 8h3M4 16h3M17 16h3"/>'), desc: 'Set where the video starts and ends' },
      { id: 'trim', label: 'Split', icon: ic('<path d="M12 3v18M5 7h4M15 7h4M5 17h4M15 17h4"/><path d="M9 7l-2 5 2 5M15 7l2 5-2 5"/>'), desc: 'Split into parts at the playhead', key: 'S', run: () => { splitAt(st, t); tab.set('trim'); } },
      { id: 'cuts', label: 'Cut', icon: ic('<circle cx="6" cy="7" r="2.5"/><circle cx="6" cy="17" r="2.5"/><path d="M8 8.5l12 8M8 15.5l12-8"/>'), desc: 'Remove stretches learners should skip', key: 'C' },
      { id: 'speed', label: 'Speed', icon: ic('<path d="M4 16a8 8 0 1116 0"/><path d="M12 16l4-5"/>'), desc: 'Speed up or slow down a stretch' },
      { id: 'speed', label: 'Freeze', icon: ic('<path d="M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9M9.5 4.5L12 7l2.5-2.5M9.5 19.5L12 17l2.5 2.5"/>'), desc: 'Hold the frame at the playhead', key: 'F', run: freezeHere },
    ] },
    { name: 'Picture', tools: [
      { id: 'canvas', label: 'Canvas', icon: ic('<rect x="3" y="5" width="18" height="14" rx="2"/><rect x="7.5" y="8" width="9" height="8" rx="1"/>'), desc: 'Frame, fit and background' },
      { id: 'filter', label: 'Filter', icon: ic('<circle cx="9" cy="10" r="5"/><circle cx="15" cy="10" r="5"/><circle cx="12" cy="15" r="5"/>'), desc: 'Colour presets and adjustments' },
      { id: 'effects', label: 'Effects', icon: ic('<path d="M4 20l9-9M14 4v3M14 13v3M10 8H7M21 8h-3M17.5 4.5l-2 2M12.5 11.5l-2-2"/>'), desc: 'Zoom, blur and visual effects', key: 'Z' },
      { id: 'transition', label: 'Transition', icon: ic('<rect x="3" y="6" width="9" height="12" rx="1.5"/><rect x="12" y="6" width="9" height="12" rx="1.5"/><path d="M10 12h4M12.5 10.5L14 12l-1.5 1.5"/>'), desc: 'How parts and cuts blend together' },
    ] },
    { name: 'Text & graphics', tools: [
      { id: 'text', label: 'Text', icon: ic('<path d="M5 6V4.5h14V6M12 4.5V19.5M9 19.5h6"/>'), desc: 'Titles, callouts and labels', key: 'T' },
      { id: 'sticker', label: 'Sticker', icon: ic('<circle cx="12" cy="12" r="8.5"/><path d="M8.5 14.5a4.5 4.5 0 007 0"/><path d="M9.5 9.5h.01M14.5 9.5h.01" stroke-width="2.6"/>'), desc: 'Emoji and stickers on the picture' },
      { id: 'captions', label: 'Captions', icon: icons.cc, desc: 'Show and style the transcript' },
    ] },
    { name: 'Audio', tools: [
      { id: 'music', label: 'Music', icon: ic('<path d="M9 18V6l11-2v12"/><circle cx="6.5" cy="18" r="2.5"/><circle cx="17.5" cy="16" r="2.5"/>'), desc: 'Background music and volume' },
      { id: 'voice', label: 'Record', icon: ic('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0013 0M12 17.5V21"/>'), desc: 'Record a voice-over' },
    ] },
    { name: 'Publish', tools: [
      { id: 'chapters', label: 'Chapters', icon: ic('<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>'), desc: 'Sections learners can jump to', key: 'M' },
      { id: 'look', label: 'Brand', icon: ic('<path d="M12 3s6 6.2 6 10.5A6 6 0 016 13.5C6 9.2 12 3 12 3z"/>'), desc: 'Logo, brand and fades' },
      { id: 'details', label: 'Details', icon: ic('<path d="M5 6h14M5 11h14M5 16h9"/>'), desc: 'Title and description learners see' },
      { id: 'thumb', label: 'Thumbnail', icon: ic('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/><circle cx="15.5" cy="9.5" r="1.5"/>'), desc: 'The picture before it plays' },
    ] },
  ];
  const TOOLS = GROUPS.flatMap(g => g.tools);
  const NAMES: Record<Tab, string> = {
    ai: 'AI editor', trim: 'Trim and split', cuts: 'Cut', canvas: 'Canvas', filter: 'Filter', effects: 'Effects', speed: 'Speed and freeze',
    transition: 'Transition', music: 'Music', voice: 'Voice-over', text: 'Text', sticker: 'Stickers', captions: 'Captions',
    chapters: 'Chapters', look: 'Brand and fades', details: 'Details', thumb: 'Thumbnail',
  };
  // One line under the panel's title: what the tool is for.
  const ABOUT: Record<Tab, string> = {
    ai: 'Ask AI to suggest cuts, chapters and highlights from the transcript, then review each one.',
    trim: 'Choose where the video starts and ends, and split it into parts (a quiz or test can sit between parts on a course).',
    cuts: 'Remove stretches learners should skip. Mark a range with I and O, or cut by transcript.',
    canvas: 'How the picture sits in the 16:9 frame: size, position and the background around it.',
    filter: 'Colour presets and fine adjustments for the whole video.',
    effects: 'Zooms, blurs and visual effects on a stretch of the video.',
    speed: 'Speed up, slow down or mute a stretch, or hold a frame for a moment.',
    transition: 'How the video blends across parts and cuts.',
    music: 'Add background music under the video and balance it with the voice.',
    voice: 'Record a voice-over at the playhead, straight from your microphone.',
    text: 'Titles, callouts, labels and quotes over the picture. Drag them on the preview to place them.',
    sticker: 'Emoji and stickers you can drag anywhere on the picture.',
    captions: 'Captions from the transcript: turn them on for learners, fix words and choose a style.',
    chapters: 'Named sections shown on the learner’s seek bar, so they can jump straight to a topic.',
    look: 'Your logo on the video, plus fade in and fade out.',
    details: 'The title and description learners see beside the video.',
    thumb: 'The picture learners see before the video starts.',
  };
  function useTool(tl: { id: string; run?: () => void }) {
    if (tl.run) { tl.run(); return; }
    const id = tl.id as Tab;
    tab.update(cur => (cur === id ? null : id));
  }
  $: activeTool = $tab ? TOOLS.find(x => x.id === $tab && !x.run) ?? null : null;

  // ---- the overview (properties panel with no tool open) ------------------------
  $: d = $doc;
  $: textCount = d.edits.overlays.filter(o => o.style !== 'sticker').length;
  $: stickerCount = d.edits.overlays.length - textCount;
  $: musicCount = d.edits.audio.tracks.filter(x => x.kind === 'music').length;
  $: voiceCount = d.edits.audio.tracks.length - musicCount;
  $: speedCount = d.edits.effects.filter(e => e.kind === 'speed' || e.kind === 'mute' || e.kind === 'freeze').length;
  $: fxCount = d.edits.effects.length - speedCount;
  $: editRows = [
    { tab: 'cuts' as Tab, label: 'Cuts', n: d.edits.cuts.length, hint: 'skipped by learners' },
    { tab: 'trim' as Tab, label: 'Splits', n: d.splits.length, hint: d.splits.length ? `${$parts.length} parts` : 'one part' },
    { tab: 'text' as Tab, label: 'Text', n: textCount, hint: 'titles and callouts' },
    { tab: 'sticker' as Tab, label: 'Stickers', n: stickerCount, hint: 'on the picture' },
    { tab: 'effects' as Tab, label: 'Effects', n: fxCount, hint: 'zoom, blur, visual' },
    { tab: 'speed' as Tab, label: 'Speed and freeze', n: speedCount, hint: 'timing changes' },
    { tab: 'chapters' as Tab, label: 'Chapters', n: d.edits.chapters.length, hint: 'on the seek bar' },
    { tab: 'music' as Tab, label: 'Music', n: musicCount, hint: 'background tracks' },
    { tab: 'voice' as Tab, label: 'Voice-overs', n: voiceCount, hint: 'recorded' },
  ];
  // The selected timeline item, named, with the tool that edits it.
  const SEL_NAMES = { cut: 'Cut', chapter: 'Chapter', overlay: 'Text', effect: 'Effect' } as const;
  $: sel = $selected;
  let selTab: Tab | null = null;
  $: selTab = !sel ? null
    : sel.kind === 'cut' ? 'cuts'
    : sel.kind === 'chapter' ? 'chapters'
    : sel.kind === 'overlay' ? (d.edits.overlays[sel.index]?.style === 'sticker' ? 'sticker' : 'text')
    : ['speed', 'mute', 'freeze'].includes(d.edits.effects[sel.index]?.kind ?? '') ? 'speed' : 'effects';
  $: selLabel = !sel ? ''
    : sel.kind === 'overlay' ? (d.edits.overlays[sel.index]?.style === 'sticker' ? 'Sticker' : 'Text')
    : sel.kind === 'chapter' ? `Chapter: ${d.edits.chapters[sel.index]?.title ?? ''}`
    : SEL_NAMES[sel.kind];
  $: selRange = !sel ? ''
    : sel.kind === 'cut' ? `${clock(d.edits.cuts[sel.index]?.start ?? 0)} – ${clock(d.edits.cuts[sel.index]?.end ?? 0)}`
    : sel.kind === 'chapter' ? `at ${clock(d.edits.chapters[sel.index]?.start ?? 0)}`
    : sel.kind === 'overlay' ? `${clock(d.edits.overlays[sel.index]?.start ?? 0)} – ${clock(d.edits.overlays[sel.index]?.end ?? 0)}`
    : `${clock(d.edits.effects[sel.index]?.start ?? 0)} – ${clock(d.edits.effects[sel.index]?.end ?? 0)}`;

  // Save state shown in the top bar.
  $: status = busy ? { tone: 'busy', text: 'Saving…' }
    : tooShort ? { tone: 'bad', text: `A part is under ${MIN_PART} s` }
    : dirty ? { tone: 'warn', text: 'Unsaved changes' }
    : { tone: 'ok', text: 'All changes saved' };

  // ---- keyboard -------------------------------------------------------------------
  let help = false;
  function onKey(e: KeyboardEvent) {
    const el = e.target as HTMLElement;
    // Keys typed in another modal on top (the admin's test-request pop-up)
    // are that modal's, not the editor's.
    const modal = el.closest?.('[aria-modal="true"]');
    if (modal && !studioEl?.contains(modal)) return;
    // While the app menu is open, keys belong to it, not the editor.
    if (appMenu) {
      if (e.key === 'Escape') { appMenu = false; appMenuBtn?.focus(); }
      return;
    }
    const typing = el.closest('input, textarea, select, [contenteditable="true"]');
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === 'z' && !typing) { e.preventDefault(); e.shiftKey ? st.redo() : st.undo(); return; }
    if (mod && e.key.toLowerCase() === 'y' && !typing) { e.preventDefault(); st.redo(); return; }
    if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); if (dirty && !tooShort && !busy) save(); return; }
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
      if (tourMode) closeTour();
      else if (help) help = false;
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

<svelte:window on:keydown={onKey} bind:innerWidth={winW} />

<div class="studio" class:no-props={!showProps} role="dialog" aria-modal="true" aria-label="Video studio"
  style="--tl-max:{tlH ? `${tlH}px` : 'none'}" use:portal bind:this={studioEl}>
  <!-- ============ top bar ============ -->
  <header class="top" class:raised={appMenu}>
    <div class="tl-left">
      <button class="icon" on:click={close} aria-label="Close the studio" title="Close (Esc)">{@html icons.x}</button>
      <div class="appnav" use:clickAway on:focusout={menuFocusOut}>
        <button class="icon" class:pressed={appMenu} bind:this={appMenuBtn} on:click={toggleAppMenu}
          aria-haspopup="menu" aria-expanded={appMenu} aria-label="Main menu: go to another part of Champ LMS" title="Main menu">
          <svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true"><circle cx="5.5" cy="5.5" r="1.9"/><circle cx="12" cy="5.5" r="1.9"/><circle cx="18.5" cy="5.5" r="1.9"/><circle cx="5.5" cy="12" r="1.9"/><circle cx="12" cy="12" r="1.9"/><circle cx="18.5" cy="12" r="1.9"/><circle cx="5.5" cy="18.5" r="1.9"/><circle cx="12" cy="18.5" r="1.9"/><circle cx="18.5" cy="18.5" r="1.9"/></svg>
          {#if $isAdmin && $pendingRequests.length}<span class="am-dot" aria-hidden="true"></span>{/if}
        </button>
        {#if appMenu}
          <div class="appmenu" role="menu" tabindex="-1" aria-label="Main menu" bind:this={appMenuEl} on:keydown={menuKeys}>
            <div class="am-head"><span class="am-logo">Champ<span>LMS</span></span><em>Leaving closes the studio</em></div>
            {#each navItems as item}
              {@const active = item.match($page.url.pathname)}
              <a role="menuitem" href={item.href} class:active aria-current={active ? 'page' : undefined}
                on:click|preventDefault={() => goTo(item.href)}>
                <Icon name={item.icon} size={18} /> {item.label}
                {#if item.admin && $pendingRequests.length}
                  <span class="am-count" title="Test requests waiting">{$pendingRequests.length}</span>
                {/if}
              </a>
            {/each}
            <a role="menuitem" href="/settings" on:click|preventDefault={() => goTo('/settings')}>
              <Icon name="settings" size={18} /> Settings
            </a>
          </div>
        {/if}
      </div>
      <div class="ttl">
        <nav class="crumbs" aria-label="Where you are">
          <span class="app">Video studio</span><span class="sep">›</span>
          <span class="crumb">{$ep.layout === 'canvas' ? 'Course' : 'Module'}: {$ep.module_title}</span>
        </nav>
        <h2>
          <span class="title">{$ep.title}</span>
          {#if $ep.part}<span class="chip">Part {$ep.part[0]} of {$ep.part[1]}</span>{/if}
        </h2>
      </div>
    </div>

    <span class="status st-{status.tone}" role="status" title={status.tone === 'bad' ? `Every part must play at least ${MIN_PART} seconds before you can save` : ''}>
      <i aria-hidden="true"></i>{status.text}
    </span>

    <div class="hbtns">
      <span class="grp" aria-label="History">
        <button class="icon" on:click={() => st.undo()} disabled={!$canUndo} aria-label="Undo" title="Undo (Ctrl+Z)">↶</button>
        <button class="icon" on:click={() => st.redo()} disabled={!$canRedo} aria-label="Redo" title="Redo (Ctrl+Shift+Z)">↷</button>
      </span>
      <span class="vsep" aria-hidden="true"></span>
      <span class="grp" aria-label="View">
        <button class="icon" class:pressed={showProps} on:click={() => { if ($tab) { tab.set(null); propsOpen = false; } else propsOpen = !propsOpen; saveLayout(); }}
          aria-pressed={showProps} aria-label={showProps ? 'Hide the properties panel' : 'Show the properties panel'}
          title={showProps ? 'Hide the properties panel (bigger preview)' : 'Show the properties panel'}>
          <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>{#if showProps}<path d="M16.5 8h3M16.5 11h3M16.5 14h3" stroke-linecap="round"/>{/if}</svg>
        </button>
        <button class="icon" on:click={() => theme.toggle()} aria-label={$theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          title={$theme === 'dark' ? 'Light theme' : 'Dark theme'}>
          {#if $theme === 'dark'}
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4"/></svg>
          {:else}
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z"/></svg>
          {/if}
        </button>
      </span>
      <button class="icon help-btn" on:click={() => (help = !help)} aria-label="Keyboard shortcuts" title="Keyboard shortcuts (?)">⌨</button>
      <button class="btn sm ghost tour-btn" class:on={!!tourMode} on:click={() => (tourMode ? closeTour() : openTour('tour'))}
        title="A guided tour of every tool, checking each one works on this video">🎓 <span class="hide-sm">Tour</span></button>
      <button class="btn sm" data-tour="preview" on:click={() => playPart(0)} disabled={tooShort}
        title="Play it the way learners will get it: trimmed, cut, and stopping at each split">{@html icons.play} <span class="hide-sm">Preview as learner</span></button>
      <button class="btn save" on:click={save} disabled={busy || !dirty || tooShort} title="Save (Ctrl+S)">
        {busy ? 'Saving…' : $parts.length > 1 ? `Save · ${$parts.length} parts` : dirty ? 'Save changes' : 'Saved'}
      </button>
    </div>
  </header>

  <!-- ============ preview + transport ============ -->
  <section class="stage-col" aria-label="Preview">
    <div class="stage">
      <!-- The learner's player is 16:9, so the preview is too: text and
           boxes land where learners will see them. -->
      <div class="frame" style={frameBg}>
        <BackdropFill video={videoEl ?? null} active={look.background === 'blur'} />
        <!-- svelte-ignore a11y-media-has-caption a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
        <video bind:this={videoEl} preload="metadata" playsinline style={videoStyle}
          on:play={onPlay} on:pause={onPause} on:seeking={onSeeking} on:timeupdate={onTimeUpdate} on:error={onVideoError} on:click={() => st.toggle()}></video>
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
      <div class="tc-box">
        <span class="tc mono">{clock(t)}<small>.{Math.floor((t % 1) * 10)}</small></span>
        <span class="tc-sub">of {clock(st.length)} · plays <b class="mono">{clock(runtime)}</b>{$parts.length > 1 ? ` in ${$parts.length} parts` : ''}</span>
      </div>
      <div class="tgrp mid" aria-label="Transport">
        <button class="tb" on:click={() => boundary(-1)} aria-label="Previous edit point" title="Previous edit point">⏮</button>
        <button class="tb" on:click={() => nudge(-5)} title="Back 5 s (Shift+←)">−5s</button>
        <button class="tb play" on:click={() => st.toggle()} aria-label={$playing ? 'Pause' : 'Play'} title="Play/pause (Space)">
          {#if $playing}<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>
          {:else}<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M8 5.5v13l10.5-6.5z"/></svg>{/if}
        </button>
        <button class="tb" on:click={() => nudge(5)} title="Forward 5 s (Shift+→)">+5s</button>
        <button class="tb" on:click={() => boundary(1)} aria-label="Next edit point" title="Next edit point">⏭</button>
      </div>
      <div class="tgrp right">
        <span class="tgroup" aria-label="Mark a range">
          <span class="tglabel">Range</span>
          <button class="tb" class:on={$mark.in !== null} on:click={() => mark.update(m => ({ ...m, in: t }))} title="Mark in at the playhead (I)">In</button>
          <button class="tb" class:on={$mark.out !== null} on:click={() => mark.update(m => ({ ...m, out: t }))} title="Mark out at the playhead (O)">Out</button>
          <button class="tb" on:click={() => cutMarked(st)} title="Cut the marked range (C)">✂ Cut</button>
        </span>
        <span class="tgroup" aria-label="Preview options">
          <span class="tglabel">View</span>
          <button class="tb" class:on={$ccOn} on:click={() => ccOn.update(v => !v)} disabled={!segs.length} title={segs.length ? 'Captions in the preview' : 'No transcript yet'}>CC</button>
          <select class="rate" value={rate} on:change={e => setRate(+e.currentTarget.value)} aria-label="Preview speed" title="Preview speed">
            {#each [0.5, 0.75, 1, 1.25, 1.5, 2] as r}<option value={r}>{r}×</option>{/each}
          </select>
        </span>
      </div>
    </div>
  </section>

  <!-- ============ properties panel ============ -->
  <aside class="props" class:sheet={!!$tab} aria-label={$tab ? NAMES[$tab] : 'Overview'}>
    {#if $tab}
      <div class="props-head">
        <span class="ph-ico">{@html activeTool?.icon ?? ''}</span>
        <div class="ph-txt">
          <b>{NAMES[$tab]}</b>
          <span>{ABOUT[$tab]}</span>
        </div>
        <button class="done" on:click={() => tab.set(null)} aria-label="Close {NAMES[$tab]}" title="Done (Esc)">Done</button>
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
    {:else}
      <div class="props-head">
        <div class="ph-txt">
          <b>Overview</b>
          <span>Pick a tool from the dock below to edit, or select something on the timeline.</span>
        </div>
      </div>
      <div class="sheet-body ov">
        {#if sel}
          <section class="p-sec selcard">
            <span class="kick">Selected</span>
            <div class="selrow">
              <b class="selname">{selLabel}</b>
              <span class="mono muted">{selRange}</span>
            </div>
            <div class="row">
              <button class="btn sm" on:click={() => selTab && tab.set(selTab)}>Edit</button>
              <button class="btn sm ghost danger" on:click={() => removeSelected(st)} title="Delete">Delete</button>
              <button class="btn sm ghost" on:click={() => selected.set(null)}>Deselect</button>
            </div>
          </section>
        {/if}

        <section class="p-sec">
          <span class="kick">This video</span>
          <dl class="stats">
            <div><dt>Source</dt><dd class="mono">{clock(st.length)}</dd></div>
            <div><dt>Kept</dt><dd class="mono">{clock(Math.max(0, d.end - d.start))}</dd></div>
            <div><dt>Learners watch</dt><dd class="mono strong">{clock(runtime)}</dd></div>
            <div><dt>Parts</dt><dd>{$parts.length}{#if tooShort}<span class="warnt"> · one is under {MIN_PART} s</span>{/if}</dd></div>
          </dl>
          <p class="p-note">Kept is the trimmed range; learners watch it minus cuts, adjusted for speed and freezes.</p>
        </section>

        <section class="p-sec">
          <span class="kick">Edits on this video</span>
          <ul class="edits">
            {#each editRows as r}
              <li>
                <button class="editrow" class:zero={!r.n} on:click={() => tab.set(r.tab)}>
                  <span class="er-n mono">{r.n}</span>
                  <span class="er-l">{r.label}<small>{r.hint}</small></span>
                  <span class="er-go" aria-hidden="true">›</span>
                </button>
              </li>
            {/each}
            <li>
              <button class="editrow" class:zero={!segs.length} on:click={() => tab.set('captions')}>
                <span class="er-n mono">{segs.length ? 'On' : '—'}</span>
                <span class="er-l">Captions<small>{segs.length ? `${segs.length} transcript lines` : 'no transcript yet'}</small></span>
                <span class="er-go" aria-hidden="true">›</span>
              </button>
            </li>
          </ul>
        </section>

        <section class="p-sec">
          <span class="kick">At the playhead · <span class="mono">{clock(t)}</span></span>
          <div class="quick">
            <button class="btn sm" on:click={() => { splitAt(st, t); tab.set('trim'); }}>Split here <kbd>S</kbd></button>
            <button class="btn sm" on:click={addText}>Add text <kbd>T</kbd></button>
            <button class="btn sm" on:click={addChapter}>Add chapter <kbd>M</kbd></button>
            <button class="btn sm" on:click={freezeHere}>Freeze frame <kbd>F</kbd></button>
          </div>
          <button class="linkbtn" on:click={() => (help = true)}>All keyboard shortcuts</button>
        </section>
      </div>
    {/if}
  </aside>

  <!-- ============ timeline ============ -->
  <div class="tl-wrap" bind:this={tlWrapEl}>
    <!-- Drag to make the timeline shorter (bigger preview) or taller. -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="tl-grip" on:pointerdown={resizeTimeline} on:dblclick={() => { tlH = 0; saveLayout(); }}
      title="Drag to resize the timeline · double-click to reset"><span></span></div>
    <Timeline>
      <svelte:fragment slot="bar">
        <span class="tl-head">
          <b>Timeline</b>
          <span class="legend" aria-label="Track colours">
            <span><i class="lg-kept"></i>Kept</span>
            <span><i class="lg-cut"></i>Cut</span>
            <span><i class="lg-split"></i>Split</span>
            <span><i class="lg-text"></i>Text</span>
            <span><i class="lg-ch"></i>Chapter</span>
          </span>
          <button class="linkbtn" on:click={() => (help = true)} title="Drag to move · Shift-drag marks a range · Alt places without snapping · Ctrl+scroll zooms">How to use</button>
        </span>
      </svelte:fragment>
    </Timeline>
  </div>

  <!-- ============ tools: a floating dock along the bottom ============ -->
  <div class="dock-row">
    <FloatingDock groups={GROUPS} active={$tab} small={winW <= 1360} on:use={e => useTool(e.detail)} />
  </div>

  {#if tourMode && studioEl}
    <StudioTour root={studioEl} bind:mode={tourMode} bind:results={tourResults} bind:snapshot={tourSnapshot} onClose={closeTour} />
  {:else if tourOffer}
    <div class="offer" role="dialog" aria-label="Studio tour">
      <b>New to the studio?</b>
      <span>Take the 2-minute tour: each step shows a tool and checks it works on this video. Or run every check at once.</span>
      <div class="row">
        <button class="btn sm save" on:click={() => openTour('tour')}>Start the tour</button>
        <button class="btn sm" on:click={() => openTour('check')}>Feature check</button>
        <button class="btn sm ghost" on:click={() => { tourOffer = false; try { localStorage.setItem(TOUR_KEY, '1'); } catch { /* storage blocked */ } }}>No thanks</button>
      </div>
    </div>
  {/if}

  {#if help}
    <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
    <div class="help" on:click|self={() => (help = false)}>
      <div class="help-in" role="dialog" aria-label="Keyboard shortcuts">
        <div class="help-h">
          <h3>Keyboard shortcuts</h3>
          <button class="icon" on:click={() => (help = false)} aria-label="Close">{@html icons.x}</button>
        </div>
        <div class="help-cols">
          <section>
            <h4>Playback</h4>
            <dl>
              <dt>Space / K</dt><dd>Play or pause</dd>
              <dt>← →</dt><dd>1 second (Shift: 5)</dd>
              <dt>J / L</dt><dd>10 seconds back / on</dd>
              <dt>, .</dt><dd>One frame</dd>
              <dt>Home / End</dt><dd>Start / end of the kept part</dd>
            </dl>
          </section>
          <section>
            <h4>Editing at the playhead</h4>
            <dl>
              <dt>I / O</dt><dd>Mark in / out</dd>
              <dt>C</dt><dd>Cut the marked range</dd>
              <dt>S</dt><dd>Split</dd>
              <dt>[ / ]</dt><dd>Trim start / end here</dd>
              <dt>T</dt><dd>Add text</dd>
              <dt>M</dt><dd>Add a chapter</dd>
              <dt>F</dt><dd>Freeze the frame</dd>
              <dt>Z / B</dt><dd>Zoom / blur (or the marked range)</dd>
              <dt>Delete</dt><dd>Remove the selected item</dd>
            </dl>
          </section>
          <section>
            <h4>Timeline</h4>
            <dl>
              <dt>Drag</dt><dd>Move through the video</dd>
              <dt>Shift-drag</dt><dd>Mark a range</dd>
              <dt>Alt-drag</dt><dd>Move without snapping</dd>
              <dt>Ctrl+scroll</dt><dd>Zoom</dd>
            </dl>
          </section>
          <section>
            <h4>General</h4>
            <dl>
              <dt>Ctrl+Z / Ctrl+Shift+Z</dt><dd>Undo / redo</dd>
              <dt>Ctrl+S</dt><dd>Save</dd>
              <dt>?</dt><dd>This list</dd>
              <dt>Esc</dt><dd>Close the open tool</dd>
            </dl>
          </section>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  /* Follows the app's theme: light by default, dark under [data-theme='dark'].
     The preview stage stays black in both (it's the video). The brand red
     marks what's active. Every colour below is a token, so the panels,
     timeline and shared controls switch with it. */
  .studio {
    --st-bg: #f4f4f1; --st-panel: #fdfdfb; --st-deep: #efefeb; --st-raise: #ebebe6; --st-hover: #e1e1db; --st-line: #dcdcd5;
    --st-text: #121214; --st-muted: #62626a; --st-hot: #e50914; --st-mint: #16803c; --st-focus: #1f63c4;
    --st-ink: #141416; --st-on-ink: #fdfdfb; --st-sel: #dbe6fb; --st-on-sel: #123a7a;
    --st-ok-text: #16803c; --st-warn-text: #8a5a00; --st-bad-text: #c7232c;
    --tl-lane: #e9e9e4; --st-shadow: 0 20px 50px rgba(18, 18, 20, 0.18);
    --props-w: 340px; --tl-h: 230px;
    position: fixed; inset: 0; z-index: 1000; background: var(--st-bg); color: var(--st-text);
    display: grid; font-size: 0.86rem; color-scheme: light;
    grid-template-columns: minmax(0, 1fr) var(--props-w);
    grid-template-rows: auto minmax(0, 1fr) auto auto;
    grid-template-areas: 'top top' 'stage props' 'tl tl' 'dock dock';
  }
  :global([data-theme='dark']) .studio {
    --st-bg: #0e0e12; --st-panel: #15151b; --st-deep: #0a0a0d; --st-raise: #1f1f27; --st-hover: #282832; --st-line: #2a2a34;
    --st-text: #f1f1f4; --st-muted: #9b9ba6; --st-hot: #ff3b45; --st-mint: #2ee6a6; --st-focus: #6ea8ff;
    --st-ink: #f4f4f6; --st-on-ink: #121214; --st-sel: #2f4f8a; --st-on-sel: #ffffff;
    --st-ok-text: #7fe3b8; --st-warn-text: #ffd166; --st-bad-text: #ff8a92;
    --tl-lane: #15161c; --st-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
    color-scheme: dark;
  }
  .studio :global(*) { scrollbar-width: thin; scrollbar-color: color-mix(in srgb, var(--st-text) 25%, transparent) transparent; }

  /* ---- top bar ---- */
  .top {
    grid-area: top; display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 1rem;
    padding: 0.3rem 0.7rem; border-bottom: 1px solid var(--st-line); background: var(--st-panel);
  }
  /* Over the stage, panels and timeline while the app menu hangs below it. */
  .top.raised { position: relative; z-index: 40; }
  .tl-left { display: flex; align-items: center; gap: 0.6rem; min-width: 0; }

  /* ---- app menu (the main navigation the studio covers) ---- */
  .appnav { position: relative; flex: none; margin-left: -0.3rem; }
  .appnav > .icon { position: relative; }
  .am-dot { position: absolute; top: 3px; right: 3px; width: 7px; height: 7px; border-radius: 50%; background: var(--st-hot); box-shadow: 0 0 0 2px var(--st-panel); }
  .appmenu {
    position: absolute; top: calc(100% + 8px); left: 0; z-index: 40;
    width: 240px; padding: 0.4rem; display: grid; gap: 1px;
    background: var(--st-panel); color: var(--st-text);
    border: 1px solid var(--st-line); border-radius: 14px; box-shadow: var(--st-shadow);
    transform-origin: top left; animation: am-in 180ms ease-out;
  }
  @keyframes am-in { from { opacity: 0; transform: translateY(-4px) scale(0.97); } to { opacity: 1; transform: none; } }
  .am-head { display: grid; gap: 2px; padding: 0.45rem 0.6rem 0.55rem; margin-bottom: 0.25rem; border-bottom: 1px solid var(--st-line); }
  .am-logo { font-size: 1rem; font-weight: 900; letter-spacing: -0.04em; display: inline-flex; align-items: baseline; gap: 0.15rem; }
  .am-logo span { font-size: 0.58rem; font-weight: 700; letter-spacing: 0.08em; color: #fff; background: #e50914; padding: 0.08rem 0.32rem; border-radius: 5px; transform: translateY(-0.25rem); }
  .am-head em { font-style: normal; font-size: 0.7rem; color: var(--st-muted); }
  .appmenu a {
    display: flex; align-items: center; gap: 0.6rem; min-height: 36px; padding: 0 0.6rem;
    border-radius: 9px; font-size: 0.84rem; font-weight: 500; color: var(--st-text);
  }
  .appmenu a:hover, .appmenu a:focus-visible { background: var(--st-hover); outline: none; }
  .appmenu a:focus-visible { box-shadow: inset 0 0 0 2px var(--st-focus); }
  .appmenu a.active { color: var(--st-hot); font-weight: 700; }
  .am-count { margin-left: auto; min-width: 18px; height: 18px; padding: 0 5px; border-radius: 999px; background: var(--st-hot); color: #fff; font-size: 0.68rem; font-weight: 700; line-height: 18px; text-align: center; }
  .ttl { min-width: 0; display: grid; gap: 1px; }
  .crumbs { display: flex; gap: 0.35rem; align-items: center; font-size: 0.62rem; font-weight: 600; color: var(--st-muted); min-width: 0; }
  .crumbs .app { color: var(--st-hot); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 800; flex: none; }
  .crumbs .sep { opacity: 0.6; }
  .crumbs .crumb { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ttl h2 { display: flex; align-items: center; gap: 0.45rem; font-size: 0.9rem; font-weight: 700; min-width: 0; letter-spacing: -0.01em; }
  .ttl .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chip { flex: none; font-size: 0.68rem; font-weight: 700; padding: 0.12rem 0.5rem; border-radius: 999px; background: var(--st-raise); color: var(--st-muted); border: 1px solid var(--st-line); }

  .status { display: inline-flex; align-items: center; gap: 0.4rem; height: 24px; padding: 0 0.65rem; border-radius: 999px; font-size: 0.74rem; font-weight: 600;
    background: var(--st-raise); color: var(--st-muted); border: 1px solid var(--st-line); white-space: nowrap; }
  .status i { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
  .status.st-ok { color: var(--st-ok-text); }
  .status.st-warn { color: var(--st-warn-text); }
  .status.st-bad { color: var(--st-bad-text); border-color: rgba(255, 59, 69, 0.45); }
  .status.st-busy i { animation: blink 0.9s ease-in-out infinite; }
  @keyframes blink { 50% { opacity: 0.25; } }

  .hbtns { display: flex; align-items: center; gap: 0.3rem; flex: none; }
  .grp { display: inline-flex; gap: 2px; padding: 2px; border-radius: 999px; background: var(--st-raise); border: 1px solid var(--st-line); }
  .vsep { width: 1px; height: 18px; background: var(--st-line); margin: 0 0.2rem; }
  .icon { width: 28px; height: 28px; border-radius: 999px; display: grid; place-items: center; color: var(--st-text); font-size: 1rem; }
  .icon:hover:not(:disabled) { background: var(--st-hover); }
  .icon:disabled { opacity: 0.35; }
  .studio :global(.btn.save) { height: 28px; padding: 0 1rem; border-radius: 999px; background: var(--st-ink); border-color: var(--st-ink); color: var(--st-on-ink); font-weight: 800; }
  .studio :global(.btn.save:hover:not(:disabled)) { background: var(--st-ink); opacity: 0.88; }
  .studio :global(.btn.save:disabled) { background: var(--st-raise); border-color: var(--st-line); color: var(--st-muted); opacity: 1; }
  .tour-btn.on { background: var(--st-ink); color: var(--st-on-ink); }


  /* ---- preview ---- */
  .stage-col { grid-area: stage; display: grid; grid-template-rows: minmax(0, 1fr) auto; min-height: 0; min-width: 0; padding: 0.45rem 0.55rem 0.35rem; gap: 0.35rem; }
  .stage { position: relative; background: #000; border-radius: 12px; overflow: hidden; min-height: 0; container-type: size; display: grid; place-items: center; box-shadow: 0 0 0 1px var(--st-line); }
  .frame { position: relative; width: min(100cqw, calc(100cqh * 16 / 9)); aspect-ratio: 16 / 9; overflow: hidden; container-type: inline-size; background: #000; }
  /* Positioned, so it paints over the canvas's blurred fill behind it. */
  .frame video { position: relative; width: 100%; height: 100%; object-fit: contain; display: block; cursor: pointer; transition: filter 150ms; }
  .badges { position: absolute; top: 8px; left: 8px; right: 8px; display: flex; pointer-events: none; z-index: 6; }
  .badge { display: inline-flex; gap: 0.35rem; align-items: center; height: 26px; padding: 0 0.65rem; border-radius: 999px; background: rgba(0,0,0,.72); color: #fff; font-size: 0.74rem; font-weight: 600; }
  .badge.warn { background: rgba(245,197,24,.92); color: #111; }
  .badge.bad { background: rgba(255,59,69,.92); color: #fff; }
  .endcard { position: absolute; inset: auto 0 0 0; padding: 1rem; background: linear-gradient(transparent, rgba(0,0,0,.9) 35%); color: #fff; display: grid; gap: 0.5rem; z-index: 7; }
  .endcard p { font-weight: 600; }
  /* Always on the dark overlay, whatever the theme. */
  .endcard :global(.btn.ghost) { color: #fff; border-color: rgba(255, 255, 255, 0.35); }
  .perr { position: absolute; inset: auto 0 0 0; padding: 0.55rem 0.85rem; font-size: 0.8rem; background: rgba(0,0,0,.78); color: #fff; z-index: 7; }
  .notice { position: absolute; left: 50%; bottom: 14px; translate: -50% 0; max-width: 90%; padding: 0.5rem 0.95rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600; z-index: 8; box-shadow: 0 8px 24px rgba(0,0,0,.4); animation: pop-in 220ms ease-out; }
  .notice.ok { background: #e6fff5; color: #04392a; }
  .notice.bad { background: #ffe1e3; color: #6a0710; }
  @keyframes pop-in { from { opacity: 0; translate: -50% 8px; } }

  /* ---- transport ---- */
  .transport { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 0.6rem; padding: 0.25rem 0.45rem; border-radius: 10px; background: var(--st-panel); border: 1px solid var(--st-line); }
  .tc-box { display: grid; gap: 1px; min-width: 0; }
  .tc { font-size: 0.98rem; font-weight: 700; letter-spacing: -0.01em; line-height: 1.1; }
  .tc small { font-size: 0.75rem; color: var(--st-muted); }
  .tc-sub { font-size: 0.64rem; color: var(--st-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tc-sub b { color: var(--st-text); }
  .tgrp { display: flex; gap: 0.2rem; align-items: center; }
  .tgrp.right { justify-content: flex-end; flex-wrap: wrap; gap: 0.4rem; }
  .tgroup { display: inline-flex; align-items: center; gap: 0.15rem; padding: 2px 2px 2px 0.45rem; border-radius: 8px; background: var(--st-deep); border: 1px solid var(--st-line); }
  .tglabel { font-size: 0.56rem; font-weight: 800; letter-spacing: 0.08em; text-transform: uppercase; color: var(--st-muted); margin-right: 0.2rem; }
  .tb { min-width: 30px; height: 24px; padding: 0 0.4rem; border-radius: 6px; background: var(--st-raise); color: var(--st-text); font-size: 0.76rem; font-weight: 700; }
  .tb:hover:not(:disabled) { background: var(--st-hover); }
  .tb.on { background: var(--st-sel); color: var(--st-on-sel); }
  .tb:disabled { opacity: 0.4; }
  .tb.play { width: 36px; height: 30px; background: var(--st-ink); color: var(--st-on-ink); border-radius: 999px; display: grid; place-items: center; }
  .tb.play:hover { background: var(--st-ink); scale: 1.05; }
  .rate { height: 24px; border-radius: 6px; background: var(--st-raise); color: var(--st-text); border: 0; font-size: 0.76rem; padding: 0 0.3rem; }

  /* ---- properties panel ---- */
  .props { grid-area: props; display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 0; border-left: 1px solid var(--st-line); background: var(--st-bg); }
  .props-head { display: flex; align-items: flex-start; gap: 0.55rem; padding: 0.5rem 0.7rem 0.5rem; border-bottom: 1px solid var(--st-line); background: var(--st-panel); }
  .ph-ico { flex: none; width: 28px; height: 28px; border-radius: 7px; display: grid; place-items: center; font-size: 1rem; background: var(--st-hot); color: #fff; }
  .ph-txt { display: grid; gap: 0.1rem; min-width: 0; flex: 1; }
  .ph-txt b { font-size: 0.88rem; }
  .ph-txt span { font-size: 0.7rem; color: var(--st-muted); line-height: 1.4; }
  .done { flex: none; height: 26px; padding: 0 0.75rem; border-radius: 999px; background: var(--st-raise); color: var(--st-text); font-weight: 700; font-size: 0.76rem; border: 1px solid var(--st-line); }
  .done:hover { background: var(--st-hover); }
  .sheet-body { overflow-y: auto; padding: 0.55rem; display: grid; align-content: start; gap: 0.5rem; animation: sheet-in 180ms ease-out; }
  @keyframes sheet-in { from { opacity: 0; translate: 10px 0; } }

  /* overview */
  .kick { font-size: 0.62rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--st-muted); }
  .selcard { border-color: rgba(255, 59, 69, 0.5); }
  .selrow { display: flex; justify-content: space-between; gap: 0.6rem; align-items: baseline; }
  .selname { font-size: 0.9rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 0.35rem; margin: 0; }
  .stats div { display: grid; gap: 0; padding: 0.3rem 0.5rem; border-radius: 8px; background: var(--st-deep); border: 1px solid var(--st-line); }
  .stats dt { font-size: 0.66rem; color: var(--st-muted); font-weight: 600; }
  .stats dd { margin: 0; font-size: 0.86rem; font-weight: 700; }
  .stats dd.strong { color: var(--st-ok-text); }
  .warnt { font-size: 0.7rem; color: var(--st-bad-text); font-weight: 600; }
  .edits { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
  .editrow { width: 100%; display: grid; grid-template-columns: 2.4rem minmax(0, 1fr) auto; align-items: center; gap: 0.45rem; padding: 0.25rem 0.4rem; border-radius: 7px; text-align: left; color: var(--st-text); }
  .editrow:hover { background: var(--st-raise); }
  .er-n { justify-self: center; min-width: 1.9rem; text-align: center; padding: 0.1rem 0.35rem; border-radius: 6px; background: var(--st-raise); font-weight: 700; font-size: 0.78rem; }
  .editrow.zero .er-n { color: var(--st-muted); background: transparent; border: 1px dashed var(--st-line); }
  .er-l { display: grid; font-size: 0.8rem; font-weight: 600; }
  .er-l small { font-size: 0.68rem; font-weight: 500; color: var(--st-muted); }
  .er-go { color: var(--st-muted); font-size: 1rem; }
  .quick { display: grid; grid-template-columns: 1fr 1fr; gap: 0.3rem; }
  .quick .btn { justify-content: space-between; }
  .linkbtn { justify-self: start; font-size: 0.74rem; color: var(--st-muted); text-decoration: underline dotted; }
  .linkbtn:hover { color: var(--st-text); }

  /* ---- timeline ---- */
  .tl-wrap { grid-area: tl; padding: 0.3rem 0.6rem 0.4rem; border-top: 1px solid var(--st-line); background: var(--st-panel); display: grid; min-width: 0; }
  .tl-head { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; min-width: 0; }
  .tl-head b { font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--st-muted); font-weight: 800; }
  .legend { display: flex; gap: 0.8rem; flex-wrap: wrap; font-size: 0.68rem; color: var(--st-muted); }
  .legend span { display: inline-flex; align-items: center; gap: 0.3rem; }
  .legend i { width: 14px; height: 8px; border-radius: 2px; display: inline-block; }
  .lg-kept { box-shadow: inset 0 0 0 2px var(--st-ink); }
  .lg-cut { background: repeating-linear-gradient(135deg, rgba(255,77,94,.75) 0 3px, rgba(80,10,20,.9) 3px 6px); }
  .lg-split { background: #f5c518; width: 4px !important; }
  .lg-text { background: rgba(255,210,63,.35); box-shadow: inset 0 0 0 1px #ffd23f; }
  .lg-ch { background: rgba(180,139,255,.3); box-shadow: inset 2px 0 0 #b48bff; }

  /* ---- the dock row: under the timeline, above everything it overlaps when it grows ---- */
  .dock-row { grid-area: dock; position: relative; z-index: 15; padding: 0.35rem 0.6rem 0.5rem; background: var(--st-bg); border-top: 1px solid var(--st-line); }

  /* ---- tour offer, shortcuts ---- */
  .offer { position: absolute; left: 14px; bottom: 300px; z-index: 30; width: min(380px, calc(100vw - 28px)); display: grid; gap: 0.45rem; padding: 0.85rem 0.95rem;
    border-radius: 16px; background: #fff; color: #15151a; box-shadow: 0 20px 50px rgba(0,0,0,.5); font-size: 0.82rem; line-height: 1.45; animation: pop-in 260ms ease-out; }
  .offer b { font-size: 0.95rem; }
  .offer .btn.ghost { color: #15151a; border-color: #d4d4dc; }
  .help { position: absolute; inset: 0; background: rgba(0,0,0,.6); display: grid; place-items: center; z-index: 20; padding: 1rem; }
  .help-in { background: var(--st-panel); border: 1px solid var(--st-line); border-radius: 16px; padding: 1.1rem 1.3rem 1.3rem; display: grid; gap: 0.9rem; width: min(760px, 100%); max-height: 90vh; overflow: auto; box-shadow: var(--st-shadow); }
  .help-h { display: flex; justify-content: space-between; align-items: center; }
  .help-h h3 { font-size: 1.05rem; }
  .help-cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem 1.6rem; }
  .help h4 { font-size: 0.66rem; font-weight: 800; letter-spacing: 0.1em; text-transform: uppercase; color: var(--st-muted); margin-bottom: 0.45rem; }
  .help dl { display: grid; grid-template-columns: auto 1fr; gap: 0.35rem 1rem; font-size: 0.8rem; margin: 0; }
  .help dt { font-family: ui-monospace, Consolas, monospace; color: var(--st-text); font-size: 0.74rem; font-weight: 600; }
  .help dd { margin: 0; color: var(--st-muted); }

  /* ---- layout options: hidden panel, timeline height ---- */
  .icon.pressed { background: var(--st-panel); box-shadow: 0 1px 2px rgba(0,0,0,.14); }
  /* Panel hidden: the preview takes its width. */
  .studio.no-props { grid-template-columns: minmax(0, 1fr); grid-template-areas: 'top' 'stage' 'tl' 'dock'; }
  .no-props .props { display: none; }
  /* Timeline: resizable from its top edge; lanes scroll when it's shorter than they are. */
  .tl-wrap { position: relative; }
  .tl-grip { position: absolute; left: 0; right: 0; top: -4px; height: 9px; cursor: ns-resize; z-index: 5; display: grid; place-items: center; touch-action: none; }
  .tl-grip span { width: 44px; height: 4px; border-radius: 4px; background: var(--st-line); transition: background-color 120ms; }
  .tl-grip:hover span { background: var(--st-muted); }
  .studio .tl-wrap :global(.tl-body) { max-height: var(--tl-max, none); overflow-y: auto; overflow-x: hidden; }

  /* ---- smaller screens ---- */
  /* Laptop: slimmer panel. */
  @media (max-width: 1360px) {
    .studio { --props-w: 320px; }
  }
  /* Tablet: the panel shows only while a tool is open, over the preview. */
  @media (max-width: 1100px) {
    .studio { grid-template-columns: minmax(0, 1fr); grid-template-areas: 'top' 'stage' 'tl' 'dock'; }
    .props { display: none; }
    .props.sheet { display: grid; position: absolute; right: 0; top: 41px; bottom: 0; width: min(380px, 92vw); z-index: 20; box-shadow: -18px 0 40px rgba(0,0,0,.5); animation: sheet-in 200ms ease-out; }
    .status { display: none; }
  }
  /* Phone: the dock becomes a strip you swipe, the panel a sheet. */
  @media (max-width: 760px) {
    .studio, .studio.no-props { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr) auto auto; grid-template-areas: 'top' 'stage' 'tl' 'dock'; }
    .dock-row { padding: 0; border-top: 0; }
    .props.sheet { left: 0; right: 0; top: auto; width: auto; max-height: 64vh; border-left: 0; border-top: 1px solid var(--st-line); border-radius: 18px 18px 0 0; box-shadow: 0 -18px 40px rgba(0,0,0,.5); }
    .transport { grid-template-columns: auto 1fr; }
    .tgrp.mid { justify-content: flex-end; }
    .tgrp.right { grid-column: 1 / -1; justify-content: flex-start; }
    .hide-sm, .crumbs, .help-btn, .vsep { display: none; }
    .top { gap: 0.5rem; padding: 0.45rem 0.6rem; }
    .ttl h2 { font-size: 0.9rem; }
    .offer { left: 14px; bottom: 120px; }
  }


  /* ---- shared by every panel ---- */
  .studio :global(.p-sec) { display: grid; gap: 0.4rem; padding: 0.55rem 0.6rem; border: 1px solid var(--st-line); border-radius: 10px; background: var(--st-panel); }
  .studio :global(.p-h) { font-size: 0.8rem; font-weight: 700; }
  .studio :global(.p-note) { font-size: 0.75rem; color: var(--st-muted); line-height: 1.45; }
  .studio :global(.p-bad) { font-size: 0.76rem; color: var(--st-bad-text); line-height: 1.45; }
  .studio :global(.row) { display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center; }
  .studio :global(.row.tight) { gap: 0.25rem; }
  .studio :global(.muted) { color: var(--st-muted); }
  .studio :global(.mono) { font-family: ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; }
  .studio :global(kbd) { font: inherit; font-size: 0.66rem; padding: 0 0.3em; border: 1px solid var(--st-line); border-radius: 4px; margin-left: 0.2rem; opacity: 0.85; }
  .studio :global(.btn) { display: inline-flex; align-items: center; gap: 0.35rem; height: 28px; padding: 0 0.75rem; border-radius: 7px; border: 1px solid var(--st-line); background: var(--st-raise); color: var(--st-text); font-weight: 600; font-size: 0.78rem; white-space: nowrap; }
  .studio :global(.btn:hover:not(:disabled)) { background: var(--st-hover); }
  .studio :global(.btn.sm) { height: 25px; padding: 0 0.6rem; font-size: 0.74rem; }
  .studio :global(.btn.xs) { height: 21px; padding: 0 0.45rem; font-size: 0.68rem; border-radius: 5px; }
  .studio :global(.btn.hot) { background: var(--st-hot); border-color: var(--st-hot); color: #fff; }
  .studio :global(.btn.hot:hover:not(:disabled)) { background: #ff5960; }
  .studio :global(.btn.ai) { background: linear-gradient(135deg, #7b5cff, #4f7dff); border-color: transparent; color: #fff; }
  .studio :global(.btn.ghost) { background: transparent; }
  .studio :global(.btn.danger:hover:not(:disabled)) { background: rgba(255,59,69,.16); color: var(--st-bad-text); }
  .studio :global(.btn:disabled) { opacity: 0.45; cursor: not-allowed; }
  .studio :global(.btn svg) { font-size: 0.95em; }
  .studio :global(.field) { display: grid; gap: 0.25rem; font-size: 0.74rem; font-weight: 600; color: var(--st-muted); }
  .studio :global(input[type='text']), .studio :global(input[type='search']), .studio :global(select) {
    font: inherit; font-size: 0.82rem; color: var(--st-text); background: var(--st-deep); border: 1px solid var(--st-line); border-radius: 6px; padding: 0.22rem 0.45rem; min-width: 0;
  }
  .studio :global(input[type='text']:focus), .studio :global(input[type='search']:focus), .studio :global(select:focus) { outline: none; border-color: var(--st-focus); }
  .studio :global(.field.sm input) { width: 110px; font-variant-numeric: tabular-nums; }
  .studio :global(.seg-ctl) { display: inline-flex; padding: 2px; border-radius: 9px; background: var(--st-deep); border: 1px solid var(--st-line); flex-wrap: wrap; }
  .studio :global(.seg-ctl button) { height: 22px; padding: 0 0.55rem; border-radius: 7px; color: var(--st-muted); font-size: 0.74rem; font-weight: 600; }
  .studio :global(.seg-ctl.small button) { padding: 0 0.5rem; font-size: 0.7rem; }
  .studio :global(.seg-ctl button.on) { background: var(--st-panel); color: var(--st-text); box-shadow: 0 1px 2px rgba(0,0,0,.12); }
  .studio :global(.seg-ctl button:disabled) { opacity: 0.4; }
  .studio :global(.list) { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.25rem; }
  .studio :global(.list li) { display: grid; gap: 0.25rem; padding: 0.3rem 0.45rem; border: 1px solid var(--st-line); border-radius: 10px; background: var(--st-raise); font-size: 0.8rem; }
  .studio :global(.list li.cur) { border-color: var(--st-focus); }
  .studio :global(.list li.bad) { border-color: #ff4d5e; }
  .studio :global(.li-main) { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: baseline; }
</style>
