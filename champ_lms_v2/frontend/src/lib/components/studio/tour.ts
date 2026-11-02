// The studio's guided tour and feature check. Each step points at one part
// of the studio and says what it does. Most can also try it: "Show me" makes
// the edit on this video, then checks it really works the way learners will
// get it, by playing the preview and looking at what happens (playback
// jumps a cut, the speed changes, the frame holds, the sticker shows, the
// music sounds). The results make a feature check anyone can run.
//
// The tour's edits are ordinary, undoable edits. StudioTour snapshots the
// video's edits before the first one and offers to put them back at the end,
// so a tour never leaves anything behind unless the admin chooses to keep it.
import { get } from 'svelte/store';
import { api } from '$lib/api/client';
import { clock } from '$lib/utils/transcribe';
import type { Effect, Overlay } from '$lib/utils/video-edits';
import { MIN_PART, addCut, round, splitAt, type Studio, type Tab } from './studio';

export type Status = 'idle' | 'running' | 'pass' | 'fail' | 'skip';
export interface Result { status: Status; note: string; }

export interface Ctx {
  st: Studio;
  // The studio element: checks look at what it draws.
  root: HTMLElement;
}

export interface Step {
  id: string;
  title: string;
  body: string;
  // What to spotlight, inside the studio.
  target?: string;
  // The tool sheet to open for this step.
  tab?: Tab | null;
  // Make the edit and check it works.
  run?: (c: Ctx) => Promise<Result>;
  // For steps that need the person (recording a voice-over): true once they've done it.
  watch?: (c: Ctx, base: number) => boolean;
  // What `watch` compares against, taken when the step opens.
  baseline?: (c: Ctx) => number;
}

const pass = (note: string): Result => ({ status: 'pass', note });
const fail = (note: string): Result => ({ status: 'fail', note });
const skip = (note: string): Result => ({ status: 'skip', note });
const wait = (ms: number) => new Promise(r => setTimeout(r, ms));

/**
 * A moment inside the kept part for the tour's sample edits: `at` seconds
 * into a 24-second stretch near its start, squeezed to fit a shorter video.
 */
export function spot(st: Studio, at: number): number {
  const d = get(st.doc);
  const len = d.end - d.start;
  const k = Math.min(1, Math.max(0.3, (len - 1) / 25));
  return round(Math.min(d.end - 0.6, d.start + 0.3 + at * k));
}

/** Why the preview can't be played yet, or null when it can. */
function previewProblem(c: Ctx): string | null {
  const v = c.st.video();
  const err = c.root.querySelector('.perr')?.textContent?.trim();
  if (err) return err;
  if (!v) return 'There is no preview video.';
  if (v.readyState < 2) return "The preview hasn't loaded yet. Wait a moment and try again.";
  return null;
}

async function seekTo(c: Ctx, t: number) {
  const v = c.st.video();
  c.st.pause();
  c.st.seek(t);
  if (v?.seeking) {
    await new Promise<void>(res => {
      const done = () => { v.removeEventListener('seeked', done); res(); };
      v.addEventListener('seeked', done);
      setTimeout(done, 6000);
    });
  }
  await wait(180);
}

/**
 * Play from `t` for `ms`, calling `probe` every frame or so. Returns what the
 * probe saw; playback is paused again at the end.
 */
async function playFrom(c: Ctx, t: number, ms: number, probe: () => void = () => {}) {
  await seekTo(c, t);
  c.st.play();
  const until = performance.now() + ms;
  while (performance.now() < until) { probe(); await wait(40); }
  c.st.pause();
  await wait(120);
}

const $ = (c: Ctx, sel: string) => c.root.querySelector(sel);
const styleOf = (c: Ctx) => c.st.video()?.getAttribute('style') ?? '';

function addEffects(c: Ctx, ...list: Effect[]) {
  c.st.commit(d => { d.edits.effects = [...d.edits.effects, ...list].sort((x, y) => x.start - y.start); });
}

function addOverlay(c: Ctx, o: Overlay) {
  c.st.commit(d => { d.edits.overlays = [...d.edits.overlays, o].sort((a, b) => a.start - b.start); });
}

/** A short, soft three-note chime as a WAV file, made in the browser: the tour's sample music. */
async function chime(seconds = 6): Promise<Blob> {
  const rate = 22050;
  const ctx = new OfflineAudioContext(1, rate * seconds, rate);
  [523.25, 659.25, 783.99].forEach((f, i) => {
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.frequency.value = f;
    g.gain.setValueAtTime(0.0001, 0);
    g.gain.linearRampToValueAtTime(0.16, 0.05 + i * 0.4);
    g.gain.exponentialRampToValueAtTime(0.002, seconds);
    o.connect(g).connect(ctx.destination);
    o.start(i * 0.4);
  });
  const pcm = (await ctx.startRendering()).getChannelData(0);
  const view = new DataView(new ArrayBuffer(44 + pcm.length * 2));
  const text = (at: number, s: string) => [...s].forEach((ch, i) => view.setUint8(at + i, ch.charCodeAt(0)));
  text(0, 'RIFF'); view.setUint32(4, 36 + pcm.length * 2, true); text(8, 'WAVE');
  text(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, 'data'); view.setUint32(40, pcm.length * 2, true);
  pcm.forEach((v, i) => view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, v)) * 0x7fff, true));
  return new Blob([view], { type: 'audio/wav' });
}

const voiceTracks = (c: Ctx) => get(c.st.doc).edits.audio.tracks.filter(t => t.kind === 'voice').length;

export const STEPS: Step[] = [
  {
    id: 'welcome', title: 'Welcome to the video studio',
    body: "A quick tour of every tool. On each step, Show me makes the edit on this video and checks it works the way learners will get it. Nothing is saved: at the end you can undo everything the tour did.",
  },
  {
    id: 'preview', title: 'The preview', target: '.stage', tab: null,
    body: 'What learners will see, with every edit applied as it plays. Click it, or press Space, to play and pause.',
    async run(c) {
      const why = previewProblem(c);
      if (why) return fail(why);
      const from = spot(c.st, 0);
      let reached = from;
      await playFrom(c, from, 1300, () => { reached = Math.max(reached, c.st.video()?.currentTime ?? 0); });
      return reached - from > 0.4
        ? pass(`It plays: ${(reached - from).toFixed(1)} s went by in 1.3 s.`)
        : fail("Play was pressed but the video didn't move. Check the connection, then reload the studio.");
    },
  },
  {
    id: 'timeline', title: 'The timeline', target: '.tl-wrap', tab: null,
    body: 'The playhead stays in the middle and the video moves under it. Drag the timeline to move through it, Ctrl+scroll to zoom, Shift-drag to mark a range. Each row holds one kind of edit.',
    async run(c) {
      const t = spot(c.st, 5);
      await seekTo(c, t);
      const shown = $(c, '.tl-wrap .ph-time')?.textContent?.trim();
      return shown === clock(t) ? pass(`Moved to ${clock(t)}; the playhead shows the same time.`) : fail(`The playhead shows ${shown}, not ${clock(t)}.`);
    },
  },
  {
    id: 'split', title: 'Trim and split', target: '[data-tool="Split"]', tab: 'trim',
    body: "Drag the white handles at either end of the video row to trim. Split (S) cuts the video into parts at the playhead: each part becomes its own episode, so a quiz can sit between them.",
    async run(c) {
      const d = get(c.st.doc);
      if (d.end - d.start < MIN_PART * 2 + 1) return skip(`The kept part is too short to split: each part needs ${MIN_PART} seconds.`);
      const before = get(c.st.parts).length;
      const at = Math.min(d.end - MIN_PART - 0.5, Math.max(d.start + MIN_PART + 0.5, spot(c.st, 12)));
      splitAt(c.st, at);
      await wait(100);
      const after = get(c.st.parts).length;
      // Taken out again: the rest of the tour adds edits that would leave a
      // part under the minimum, and its checks play the video as one.
      c.st.commit(dd => { dd.splits = dd.splits.filter(x => Math.abs(x - at) > 0.01); });
      return after === before + 1
        ? pass(`Split at ${clock(at)} into ${after} parts (saving would make ${after} episodes), then joined again for the rest of the tour.`)
        : fail("The split didn't happen.");
    },
  },
  {
    id: 'cut', title: 'Cut', target: '[data-tool="Cut"]', tab: 'cuts',
    body: "Cut out a cough or a tangent: mark it with I and O (or Shift-drag on the timeline) and press C. Learners skip it. The Cut sheet also removes silences and cuts by striking out transcript lines.",
    async run(c) {
      const a = spot(c.st, 2), b = spot(c.st, 3.5);
      c.st.commit(d => addCut(d, a, b));
      const cut = get(c.st.doc).edits.cuts.find(x => x.start <= a + 0.1 && x.end >= b - 0.1);
      if (!cut) return fail("The cut wasn't added.");
      const why = previewProblem(c);
      if (why) return skip(`Cut added, but it couldn't be played: ${why}`);
      let inside = 0, after = false;
      await playFrom(c, cut.start - 0.7, 1500, () => {
        const t = c.st.video()?.currentTime ?? 0;
        if (t > cut.start + 0.25 && t < cut.end - 0.25) inside++;
        if (t >= cut.end) after = true;
      });
      if (!after) return fail('Playback never got past the cut.');
      return inside <= 2 ? pass(`Playback jumped from ${clock(cut.start)} to ${clock(cut.end)}: learners skip it.`) : fail('Playback ran through the cut instead of jumping it.');
    },
  },
  {
    id: 'speed', title: 'Speed', target: '[data-tool="Speed"]', tab: 'speed',
    body: 'Hurry a slow stretch (a screen loading, typing) or slow one down: choose the speed and apply it to the marked range or the part.',
    async run(c) {
      const a = spot(c.st, 6), b = spot(c.st, 9.5);
      addEffects(c, { kind: 'speed', start: a, end: b, rate: 2 });
      const why = previewProblem(c);
      if (why) return skip(`2× added from ${clock(a)}, but it couldn't be played: ${why}`);
      let top = 0;
      await playFrom(c, a + 0.3, 900, () => { top = Math.max(top, c.st.video()?.playbackRate ?? 0); });
      return top >= 1.9 ? pass(`Plays at ${top}× from ${clock(a)} to ${clock(b)}.`) : fail(`Expected 2×, but it played at ${top}×.`);
    },
  },
  {
    id: 'freeze', title: 'Freeze frame', target: '[data-tool="Freeze"]', tab: 'speed',
    body: 'Hold the picture for a moment (F): to point at something on screen or let a slide sink in. Then it plays on.',
    async run(c) {
      const at = spot(c.st, 11);
      addEffects(c, { kind: 'freeze', start: at, end: round(at + 0.5), hold: 1.5 });
      const why = previewProblem(c);
      if (why) return skip(`Freeze added at ${clock(at)}, but it couldn't be played: ${why}`);
      let held = false;
      let resumed = false;
      await seekTo(c, at - 0.4);
      c.st.play();
      const until = performance.now() + 3200;
      while (performance.now() < until) {
        const v = c.st.video();
        const badge = [...c.root.querySelectorAll('.badge')].some(b => b.textContent?.includes('Frozen'));
        if (badge && v?.paused) held = true;
        if (held && v && !v.paused && v.currentTime > at + 0.1) { resumed = true; break; }
        await wait(50);
      }
      c.st.pause();
      if (!held) return fail("The frame didn't hold.");
      return resumed ? pass(`Held the frame at ${clock(at)} for 1.5 s, then played on.`) : fail('The frame held, but playback never carried on.');
    },
  },
  {
    id: 'canvas', title: 'Canvas', target: '[data-tool="Canvas"]', tab: 'canvas',
    body: "For a picture that isn't 16:9 (a 4:3 slide, a phone video): fill the bars with a blurred copy or a colour. Turn, mirror or flip it, and zoom in to frame it.",
    async run(c) {
      const before = get(c.st.doc).edits.look;
      c.st.commit(d => { d.edits.look = { ...d.edits.look, background: 'blur', rotate: 90 }; });
      await wait(250);
      const fill = !!$(c, '.frame canvas.fill');
      const turned = styleOf(c).includes('rotate(90');
      c.st.commit(d => { d.edits.look = { ...d.edits.look, rotate: before.rotate }; });
      if (!fill) return fail("The blurred background wasn't drawn.");
      return turned ? pass('Blurred background drawn behind the picture; turning it works (turned back again).') : fail("The picture didn't turn.");
    },
  },
  {
    id: 'filter', title: 'Filter', target: '[data-tool="Filter"]', tab: 'filter',
    body: 'Pick a look and its strength; each preset previews on the frame under the playhead. Adjust has brightness, contrast, warmth, hue and vignette.',
    async run(c) {
      c.st.commit(d => { d.edits.look = { ...d.edits.look, filter: 'vivid', filter_strength: 100 }; });
      await wait(200);
      const f = getComputedStyle(c.st.video()!).filter;
      return f.includes('saturate') ? pass('The Vivid filter is on the picture.') : fail(`No filter on the picture (${f || 'none'}).`);
    },
  },
  {
    id: 'effects', title: 'Effects', target: '[data-tool="Effects"]', tab: 'effects',
    body: 'Visual effects (shake, glitch, analog, flash…) over a stretch, plus a punch-in zoom, a blur box to hide something on screen, and mute. Each sits on the Effects row; drag its ends to fit.',
    async run(c) {
      const a = spot(c.st, 13), b = spot(c.st, 15.5), m0 = spot(c.st, 16), m1 = spot(c.st, 18);
      addEffects(c,
        { kind: 'fx', start: a, end: b, style: 'shake' },
        { kind: 'blur', start: a, end: b, x: 60, y: 60, w: 25, h: 20, mode: 'blur' },
        { kind: 'mute', start: m0, end: m1 },
      );
      await seekTo(c, round((a + b) / 2));
      const shook = styleOf(c).includes('translate(');
      const blurred = !!$(c, '.redact');
      const notes = [shook ? 'shake moves the picture' : 'shake did NOT move the picture', blurred ? 'the blur box is drawn' : 'the blur box is NOT drawn'];
      let muted: boolean | null = null;
      if (!previewProblem(c)) {
        muted = false;
        await playFrom(c, m0 + 0.2, 600, () => { if (c.st.video()?.muted) muted = true; });
        notes.push(muted ? 'the sound mutes' : 'the sound did NOT mute');
      }
      const ok = shook && blurred && muted !== false;
      const text = notes.join(', ') + '.';
      return ok ? pass(text[0].toUpperCase() + text.slice(1)) : fail(text[0].toUpperCase() + text.slice(1));
    },
  },
  {
    id: 'transition', title: 'Transitions', target: '[data-tool="Transition"]', tab: 'transition',
    body: 'What plays where a cut joins: fade, flash, blur, zoom or shake. One style for every cut.',
    async run(c) {
      let cut = get(c.st.doc).edits.cuts[0];
      if (!cut) { c.st.commit(d => addCut(d, spot(c.st, 2), spot(c.st, 3.5))); cut = get(c.st.doc).edits.cuts[0]; }
      c.st.commit(d => { d.edits.look = { ...d.edits.look, transition: 'flash' }; });
      await seekTo(c, cut.end + 0.06);
      return $(c, '.frame .flash') ? pass(`A flash plays where the cut at ${clock(cut.start)} joins.`) : fail("No flash at the cut.");
    },
  },
  {
    id: 'text', title: 'Text', target: '[data-tool="Text"]', tab: 'text',
    body: 'Titles, callouts, lower thirds and quotes (T). Set the size, colour and entrance, and drag it anywhere on the preview.',
    async run(c) {
      const a = spot(c.st, 17);
      addOverlay(c, { start: a, end: round(a + 3), text: 'Tour: key point', subtext: null, position: 'free', x: 30, y: 22, style: 'callout', size: 'm', anim: 'pop', color: null });
      await seekTo(c, a + 1);
      const el = [...c.root.querySelectorAll('.frame .ov')].find(e => e.textContent?.includes('Tour: key point'));
      return el ? pass(`"Tour: key point" shows at ${clock(a)} for 3 s. Drag it on the preview to move it.`) : fail("The text doesn't show on the picture.");
    },
  },
  {
    id: 'sticker', title: 'Stickers', target: '[data-tool="Sticker"]', tab: 'sticker',
    body: 'Emoji on the picture for a few seconds: reactions, arrows to point at things, marks. Drag one on the preview to place it.',
    async run(c) {
      const a = spot(c.st, 18);
      addOverlay(c, { start: a, end: round(a + 3), text: '👍', subtext: null, position: 'free', x: 78, y: 28, style: 'sticker', size: 'l', anim: 'bounce', color: null });
      await seekTo(c, a + 1);
      return $(c, '.frame .st-sticker') ? pass(`👍 shows at ${clock(a)}, bouncing.`) : fail("The sticker doesn't show on the picture.");
    },
  },
  {
    id: 'music', title: 'Music', target: '[data-tool="Music"]', tab: 'music',
    body: "Add a music track under the video, set its volume, loop and fades, and turn the video's own sound down under it. The tour adds a short chime to try.",
    async run(c) {
      const ep = get(c.st.ep);
      let id: string;
      try {
        const file = await chime();
        const up = await api.uploadStudioAudio(ep.id, file, 'tour-chime.wav', 'music', 6);
        id = up.id;
        c.st.mixer.add(id, file);
      } catch (e: any) {
        return fail(`The music couldn't be uploaded: ${e.message}`);
      }
      const start = spot(c.st, 0);
      c.st.commit(d => {
        d.edits.audio.tracks = [...d.edits.audio.tracks, { id, kind: 'music', name: 'Tour chime', start, duration: 6, volume: 70, loop: false, fade_in: false, fade_out: false }];
      });
      const why = previewProblem(c);
      if (why) return skip(`Chime uploaded and added, but it couldn't be played: ${why}`);
      let heard = false;
      await playFrom(c, start + 0.3, 1400, () => { if (c.st.mixer.playing().includes(id)) heard = true; });
      return heard ? pass(`Uploaded a chime and it played under the video from ${clock(start)}.`) : fail("The chime was added but didn't play with the video.");
    },
  },
  {
    id: 'voice', title: 'Voice-over', target: '[data-tool="Record"]', tab: 'voice',
    body: 'Record yourself over the video: press Record, talk as it plays, press Stop. The recording lands on the Audio row where you started. Try it now, or let the check record 2 seconds.',
    baseline: voiceTracks,
    watch: (c, base) => voiceTracks(c) > base,
    async run(c) {
      const perm = await navigator.permissions?.query({ name: 'microphone' as PermissionName }).catch(() => null);
      if (perm?.state !== 'granted') return skip("The microphone isn't allowed yet. Press Record in this sheet and allow it to try a voice-over.");
      let stream: MediaStream;
      try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
      catch { return fail("The microphone wouldn't start."); }
      const rec = new MediaRecorder(stream);
      const parts: Blob[] = [];
      rec.ondataavailable = e => { if (e.data.size) parts.push(e.data); };
      const stopped = new Promise(r => (rec.onstop = r));
      rec.start(200);
      await wait(2000);
      rec.stop();
      await stopped;
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(parts, { type: (rec.mimeType || 'audio/webm').split(';')[0] });
      if (!blob.size) return fail('The microphone recorded nothing.');
      try {
        const up = await api.uploadStudioAudio(get(c.st.ep).id, blob, 'tour-voice.webm', 'voice', 2);
        c.st.mixer.add(up.id, blob);
        const start = spot(c.st, 4);
        c.st.commit(d => { d.edits.audio.tracks = [...d.edits.audio.tracks, { id: up.id, kind: 'voice', name: 'Tour voice-over', start, duration: 2, volume: 100, loop: false, fade_in: false, fade_out: false }]; });
        return pass(`Recorded 2 s from the microphone and added it at ${clock(start)}.`);
      } catch (e: any) {
        return fail(`The recording couldn't be uploaded: ${e.message}`);
      }
    },
  },
  {
    id: 'captions', title: 'Captions', target: '[data-tool="Captions"]', tab: 'captions',
    body: 'Captions come from the transcript. Pick a style (Pop lights up the word being said), font and colours, fix any word, and turn them on by default. No transcript? Make one in this sheet.',
    async run(c) {
      const d = get(c.st.doc);
      const line = d.segments.find(s => s.end > d.start && s.start < d.end && s.end - s.start > 0.4);
      if (!line) return skip('This video has no transcript yet, so there are no captions to show. Make one in the Captions sheet.');
      c.st.commit(dd => { dd.edits.captions = { ...dd.edits.captions, preset: 'pop' }; });
      c.st.ccOn.set(true);
      await seekTo(c, round((line.start + line.end) / 2));
      return $(c, '.frame .cap') ? pass(`Captions show in the Pop style ("${line.text.slice(0, 40)}…").`) : fail("No caption on the picture during a transcript line.");
    },
  },
  {
    id: 'chapters', title: 'Chapters', target: '[data-tool="Chapters"]', tab: 'chapters',
    body: 'Name the sections of the video (M). Learners see them on the scrub bar and can jump between them.',
    async run(c) {
      const at = spot(c.st, 8);
      const d = get(c.st.doc);
      if (d.edits.chapters.some(x => Math.abs(x.start - at) < 1)) return pass('A chapter is already here.');
      c.st.commit(dd => { dd.edits.chapters = [...dd.edits.chapters, { start: at, title: 'Tour chapter' }].sort((x, y) => x.start - y.start); });
      await wait(150);
      const flag = [...c.root.querySelectorAll('.tl-wrap .flag')].some(f => f.textContent?.includes('Tour chapter'));
      return flag ? pass(`"Tour chapter" added at ${clock(at)}, and it's on the timeline.`) : fail("The chapter isn't on the timeline.");
    },
  },
  {
    id: 'ai', title: 'AI editor', target: '[data-tool="AI"]', tab: 'ai',
    body: 'The AI reads the transcript: it finds the strongest moments, writes chapters and an opening hook, and suggests cuts. One-click polish does the lot. Nothing changes until you apply a suggestion.',
    async run(c) {
      const ep = get(c.st.ep);
      if (ep.transcript_segments.length < 3) return skip('The AI works from the transcript, and this video has too little of one.');
      const d = get(c.st.doc);
      try {
        const r = await api.studioAi(ep.id, { task: 'highlights', count: 3, start: d.start, end: d.end });
        return pass(`The AI answered with ${r.suggestions.length} highlight${r.suggestions.length === 1 ? '' : 's'}.`);
      } catch (e: any) {
        if (e.status === 503) return skip("AI isn't switched on for this server (OPENROUTER_API_KEY).");
        return fail(`The AI didn't answer: ${e.message}`);
      }
    },
  },
  {
    id: 'brand', title: 'Brand and fades', target: '[data-tool="Brand"]', tab: 'look',
    body: 'Fade in and out at each end, the Champions Group mark in a corner, and a progress bar along the top.',
    async run(c) {
      c.st.commit(d => { d.edits.brand = { ...d.edits.brand, progress_bar: true }; });
      await seekTo(c, spot(c.st, 3));
      const bar = $(c, '.frame .progress i') as HTMLElement | null;
      return bar && parseFloat(bar.style.width) > 0 ? pass(`The progress bar shows, ${Math.round(parseFloat(bar.style.width))}% of the way through.`) : fail("The progress bar isn't drawn.");
    },
  },
  {
    id: 'undo', title: 'Undo and redo', target: '.top .hbtns', tab: null,
    body: 'Every edit can be undone (Ctrl+Z) and redone (Ctrl+Shift+Z), right up until you save.',
    async run(c) {
      const n = () => get(c.st.doc).edits.chapters.length;
      const before = n();
      c.st.commit(d => { d.edits.chapters = [...d.edits.chapters, { start: spot(c.st, 20), title: 'Undo me' }].sort((x, y) => x.start - y.start); });
      const added = n();
      c.st.undo();
      const undone = n();
      c.st.redo();
      const redone = n();
      c.st.undo();
      return added === before + 1 && undone === before && redone === added ? pass('Added a chapter, undid it, redid it, then undid it again.') : fail(`Undo or redo didn't put things back (${before} → ${added} → ${undone} → ${redone}).`);
    },
  },
  {
    id: 'learner', title: 'Preview as learner', target: '[data-tour="preview"]', tab: null,
    body: 'Plays the video exactly as learners will get it: trimmed, cut, sped up, frozen, with music, stopping at the end of each part.',
    async run(c) {
      const why = previewProblem(c);
      if (why) return skip(why);
      const btn = $(c, '[data-tour="preview"]') as HTMLButtonElement | null;
      if (btn?.disabled) return skip(`It's switched off while a part plays for under ${MIN_PART} seconds after its edits. Lengthen that part (or undo an edit), and it comes back.`);
      btn?.click();
      await wait(700);
      const on = !!$(c, '.badge.play');
      c.st.pause();
      c.st.stopPreview();
      return on ? pass('It plays from the start of the kept part, as a learner would.') : fail("The learner preview didn't start.");
    },
  },
  {
    id: 'thumb', title: 'Thumbnail', target: '[data-tool="Thumbnail"]', tab: 'thumb',
    body: 'Grab the frame under the playhead as the thumbnail (with the filter applied), or design one in the thumbnail studio.',
    async run(c) {
      const v = c.st.video();
      if (!v || !v.videoWidth) return skip('The preview has no picture yet.');
      const cv = document.createElement('canvas');
      cv.width = 160; cv.height = 90;
      try {
        cv.getContext('2d')!.drawImage(v, 0, 0, 160, 90);
        const blob = await new Promise<Blob | null>(r => cv.toBlob(r, 'image/jpeg', 0.8));
        return blob ? pass('A frame can be grabbed as the thumbnail (not saved by the tour).') : fail('The frame came out empty.');
      } catch {
        return skip("This video's server doesn't let the page read its frames, so Grab the frame can't work here. Upload a thumbnail in the thumbnail studio instead.");
      }
    },
  },
  {
    id: 'save', title: "Save when you're happy", target: '.btn.save', tab: null,
    body: "Nothing reaches learners until you press Save (Ctrl+S). The tour's edits aren't saved: on the next screen, undo them or keep them.",
  },
];
