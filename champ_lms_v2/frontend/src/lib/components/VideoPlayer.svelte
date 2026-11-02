<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { player } from '$lib/stores/player';
  import { api, type TranscriptSegment } from '$lib/api/client';
  import { icons } from '$lib/components/course/icons';
  import { segmentsToVtt } from '$lib/utils/transcribe';
  import {
    chapterIndexAt, cutAt, cutSecondsBetween, frameStyle, freezeAt, lookFilter, mutedAt, speedAt,
    type Effect, type VideoEdits,
  } from '$lib/utils/video-edits';
  import { AudioMixer } from '$lib/utils/audio-mix';
  import EditedLayer from '$lib/components/video/EditedLayer.svelte';
  import BackdropFill from '$lib/components/video/BackdropFill.svelte';

  export let episodeId: string;
  export let embedUrl: string = '';   // Bunny iframe embed fallback
  export let streamUrl: string = '';  // Bunny token-auth HLS URL

  let videoEl: HTMLVideoElement;
  let container: HTMLElement;
  let hls: any = null;
  // One countdown drives auto-advance; Cancel and leaving the page both stop it.
  let autoAdvanceTimer: ReturnType<typeof setInterval> | null = null;
  let showAutoAdvance = false;
  let countdown = 5;

  // * Playback-path selection. The native <video> + hls.js path is the ONLY one
  // * that emits timeupdate/ended, so it is the only path that records watch
  // * progress. The Bunny iframe embed cannot report progress at all.
  // * Previously the template tested `{#if embedUrl}` first and the backend
  // * always supplied an embedUrl, so the native path was unreachable and every
  // * learner's progress was posted as 0 seconds forever.
  // * Now: prefer streamUrl, and fall back to the iframe only if HLS actually
  // * fails (e.g. the token is rejected), so a broken token degrades to
  // * playback-without-tracking instead of a black screen.
  let hlsFailed = false;
  $: useNative = !!streamUrl && !hlsFailed;

  function fallbackToEmbed(reason: string) {
    if (!embedUrl) return; // nothing to fall back to; leave the error visible
    console.warn(`[VideoPlayer] HLS failed (${reason}) — falling back to embed; progress tracking disabled`);
    hls?.destroy();
    hls = null;
    hlsFailed = true;
  }

  export let onComplete: (() => void) | undefined = undefined;
  export let onAutoAdvance: (() => void) | undefined = undefined;
  // Reports the playhead so a synced transcript can follow along.
  export let onTime: ((seconds: number) => void) | undefined = undefined;
  // Where to start, e.g. to resume an episode part-way through.
  export let startAt = 0;
  // Course videos: how far past the furthest point reached a learner may jump
  // ahead in one go, in seconds. null = seek freely (classic modules, finished
  // episodes, admins). The server holds recorded progress to the same limit.
  export let skipLimitSeconds: number | null = null;
  // The furthest point already recorded for this learner, so the limit
  // carries over from an earlier session.
  export let furthestStart = 0;
  // A trimmed or split course episode plays only [clipStart, clipEnd] of its
  // video (seconds of the whole video; clipEnd null = to the end). Everything
  // else here (startAt, furthestStart, onTime, seek, reported progress) is in
  // clip time, counted from clipStart. A clipped part gets its own controls, so
  // the scrub bar and the time shown are the part's, not the whole video's.
  export let clipStart = 0;
  export let clipEnd: number | null = null;
  // false = don't report watch progress (an admin previewing in the editor).
  export let track = true;
  // Transcript lines in clip time. When there are any, a CC button over the
  // video turns them into captions. They go in as a real caption track, so they
  // also show in the browser's own full screen.
  export let captions: TranscriptSegment[] = [];
  // Set to show a Q&A button over the video. Called with the playhead (clip
  // time) after the video pauses, so a question can be pinned to that moment.
  export let onQna: ((atSeconds: number) => void) | null = null;
  export let qnaCount = 0;
  // The full-screen button. Watch pages pass the layout's full screen (player
  // plus an optional playlist drawer); without it the player itself goes full
  // screen.
  export let onFullscreen: (() => void) | null = null;
  // Video studio edits in clip time: cuts are jumped over, chapters marked on
  // the scrub bar, speed, mute and freeze effects applied as it plays, music
  // and voice-overs mixed in, and overlays, caption style, look (filter,
  // canvas, zooms, transitions) and brand drawn over it.
  export let edits: VideoEdits | null = null;
  $: cuts = edits?.cuts ?? [];
  $: chapters = edits?.chapters ?? [];
  $: effects = edits?.effects ?? [];
  $: tracks = edits?.audio?.tracks ?? [];
  // The video's own sound level set in the studio; the learner's volume scales it.
  $: ownVolume = (edits?.audio?.volume ?? 100) / 100;
  $: timed = effects.some(e => e.kind === 'speed' || e.kind === 'mute' || e.kind === 'freeze') || tracks.length > 0 || ownVolume < 1;
  $: chapterIdx = chapterIndexAt(chapters, rel);
  $: videoStyle = [lookFilter(edits?.look) && `filter: ${lookFilter(edits?.look)};`, frameStyle(edits?.look, effects, frameT, cuts)].filter(Boolean).join(' ');
  $: canvasBg = edits?.look?.background === 'color' ? `background:${edits.look.bg_color};` : '';
  let mixer: AudioMixer | null = null;
  $: if (tracks.length && !mixer) mixer = new AudioMixer(id => api.studioAudio(episodeId, id));
  // A freeze holds the picture: the video pauses for its hold, then plays on.
  let holding = false;
  let holdTimer: ReturnType<typeof setTimeout> | null = null;
  const frozen = new Set<Effect>();
  let chaptersOpen = false;
  // Overlays, word-by-word captions and cut skips follow the frame, not the
  // video's few time updates a second.
  let frameT = 0;
  let raf = 0;
  function tick() {
    raf = 0;
    if (!videoEl || videoEl.paused) return;
    frameT = Math.max(0, videoEl.currentTime - clipStart);
    const cut = !videoEl.seeking && cutAt(cuts, frameT);
    if (cut) videoEl.currentTime = clipStart + cut.end;
    else {
      const fz = freezeAt(effects, frameT);
      if (fz && !frozen.has(fz)) { hold(fz); return; }
      applyEffects(frameT);
      mixer?.sync(edits, frameT, { playing: true, rate, master: muted ? 0 : volume, end: clipLength });
    }
    raf = requestAnimationFrame(tick);
  }
  function hold(fz: Effect) {
    if (!videoEl) return;
    frozen.add(fz);
    holding = true;
    videoEl.pause();
    // Music and voice play on through the hold, untouched.
    holdTimer = setTimeout(() => {
      holding = false;
      holdTimer = null;
      videoEl?.play().catch(() => {});
    }, ((fz.hold ?? 2) * 1000) / rate);
  }
  // A freeze's own pause isn't the learner pausing: no play button, no mixer stop.
  function onPause() {
    if (holding) return;
    paused = true;
    settled = true;
    mixer?.pauseAll();
  }
  /** The learner's speed times the edit's, and their mute or the edit's. */
  function applyEffects(t: number) {
    if (!videoEl || !timed) return;
    const want = rate * speedAt(effects, t);
    if (Math.abs(videoEl.playbackRate - want) > 0.001) videoEl.playbackRate = want;
    const mute = muted || mutedAt(effects, t);
    if (videoEl.muted !== mute) videoEl.muted = mute;
    const vol = volume * ownVolume;
    if (Math.abs(videoEl.volume - vol) > 0.001) videoEl.volume = vol;
  }
  function startFrames() { if (!raf && typeof requestAnimationFrame !== 'undefined') raf = requestAnimationFrame(tick); }

  // ---- captions ------------------------------------------------------------
  const CC_KEY = 'champ_cc';
  let ccOn = false;
  // The learner's own choice wins; until they make one, the studio's default.
  try {
    const saved = localStorage.getItem(CC_KEY);
    ccOn = saved === null ? !!edits?.captions?.default_on : saved === '1';
  } catch { ccOn = !!edits?.captions?.default_on; }
  let trackEl: HTMLTrackElement;
  let vttUrl = '';
  // Cues sit in source time: the video element plays the whole Bunny video.
  // A clipped part's own controls cover the bottom, so its captions sit higher.
  $: {
    if (vttUrl) URL.revokeObjectURL(vttUrl);
    vttUrl = captions.length
      ? URL.createObjectURL(new Blob([segmentsToVtt(captions, clipStart, useNative ? 'line:80%' : '')], { type: 'text/vtt' }))
      : '';
  }
  // Captions are drawn over the video (.caption), sized to the player, since
  // the browser's own caption text is large and can't be styled reliably. The
  // track is shown only when the video element itself is full screen, where
  // nothing drawn over it can appear.
  let videoFs = false;
  let isFs = false; // the player, or the watch layout around it, is full screen
  const onFsChange = () => {
    videoFs = !!videoEl && document.fullscreenElement === videoEl;
    isFs = !!document.fullscreenElement && !!container && document.fullscreenElement.contains(container);
  };
  let trackMode: TextTrackMode = 'hidden';
  $: trackMode = ccOn && vttUrl && videoFs ? 'showing' : 'hidden';
  $: if (trackEl?.track) trackEl.track.mode = trackMode;
  function toggleCc() {
    ccOn = !ccOn;
    try { localStorage.setItem(CC_KEY, ccOn ? '1' : '0'); } catch { /* storage blocked */ }
  }
  function openQna() {
    videoEl?.pause();
    onQna?.(videoEl ? Math.max(0, videoEl.currentTime - clipStart) : 0);
  }

  $: clipped = clipStart > 0 || clipEnd !== null;
  let duration = 0; // the whole video's, once known
  $: endAbs = clipEnd ?? duration;
  $: clipLength = Math.max(0, endAbs - clipStart);

  // Control-bar state. Every video gets the same themed controls; for a whole
  // video clipStart is 0 and clipLength is its duration, so one set of maths
  // covers both.
  let paused = true;
  let muted = false;
  let volume = 1;
  try { const v = parseFloat(localStorage.getItem('champ_volume') ?? ''); if (v >= 0 && v <= 1) volume = v; } catch { /* storage blocked */ }
  let rate = 1;
  let rateMenu = false;
  let buffering = false;
  let bufferedRel = 0; // clip time buffered ahead of the playhead
  let hoverPct: number | null = null; // pointer over the seek bar, 0–1
  let active = true; // pointer moved recently: show the bar while playing
  let hideTimer: ReturnType<typeof setTimeout> | null = null;
  let pipOn = false;
  const canPip = typeof document !== 'undefined' && 'pictureInPictureEnabled' in document && (document as any).pictureInPictureEnabled;
  let rel = 0; // current position in clip time
  let clipEnded = false;
  // Once per play-through: a part whose clipEnd is at the video's end gets
  // both the clipEnd stop and the native `ended` event.
  let finishing = false;

  /** Jump to a point in clip time (a transcript line was clicked). */
  export function seek(seconds: number) {
    if (!videoEl) return;
    videoEl.currentTime = clipStart + seconds;
    videoEl.play().catch(() => {});
  }

  function applyStart() {
    if (!videoEl) return;
    duration = videoEl.duration || 0;
    const len = (clipEnd ?? duration) - clipStart;
    const from = startAt > 0 && startAt < len - 5 ? startAt : 0;
    if (clipStart + from > 0) videoEl.currentTime = clipStart + from;
  }

  let furthest = 0; // clip time
  let skipNotice = '';
  let noticeTimer: ReturnType<typeof setTimeout> | null = null;
  let reportedStart = false;
  // The furthest point as it stood when the current seek began. The browser
  // fires a time update just before "seeked", which already moves `furthest`,
  // so the end of a seek compares against this instead.
  let furthestAtSeek: number | null = null;

  function showSkipNotice() {
    const mins = Math.round((skipLimitSeconds ?? 0) / 60);
    skipNotice = `You can skip ahead up to ${mins} minute${mins === 1 ? '' : 's'} at a time.`;
    if (noticeTimer) clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => (skipNotice = ''), 3500);
  }

  function report() {
    if (!videoEl || !track) return;
    const len = clipped ? clipLength : Math.floor(videoEl.duration || 0);
    player.updateTime(Math.floor(Math.max(0, videoEl.currentTime - clipStart)), Math.floor(len));
  }

  // Every seek comes through here: the scrub bar, the keyboard, a transcript
  // line. A clipped part never plays outside its range, and a jump further
  // than the skip limit past the furthest point reached is held at the limit.
  // Going back, and returning to where you were, is free.
  function onSeeking() {
    if (!videoEl) return;
    if (furthestAtSeek === null) furthestAtSeek = furthest;
    let target = videoEl.currentTime;
    // A seek ends a freeze early, and freezes ahead of where it lands play again.
    if (holding) { holding = false; if (holdTimer) clearTimeout(holdTimer); holdTimer = null; }
    for (const f of frozen) if (clipStart + f.start > target) frozen.delete(f);
    if (clipped) {
      const end = endAbs || videoEl.duration || Infinity;
      target = Math.min(Math.max(target, clipStart), end);
      if (target < end - 0.5) clipEnded = false;
    } else if (clipEnded && target < (videoEl.duration || Infinity) - 0.5) {
      // A whole video that has ended, sought back into: it is no longer at
      // its end, so Play continues from here instead of restarting.
      clipEnded = false;
    }
    // Landing inside a cut plays on from its end.
    const cut = cutAt(cuts, target - clipStart);
    if (cut) target = clipStart + cut.end;
    if (skipLimitSeconds != null) {
      // Cuts are jumped over unplayed, so they don't count towards the limit.
      const limit = clipStart + furthestAtSeek + skipLimitSeconds
        + cutSecondsBetween(cuts, furthestAtSeek, target - clipStart);
      if (target > limit + 0.5) { target = limit; showSkipNotice(); }
    }
    if (Math.abs(target - videoEl.currentTime) > 0.05) videoEl.currentTime = target;
  }

  // After a skip past the furthest point, report it straight away so each skip
  // reaches the server on its own rather than several at once.
  function onSeeked() {
    if (!videoEl) return;
    const before = furthestAtSeek ?? furthest;
    furthestAtSeek = null;
    const now = videoEl.currentTime - clipStart;
    if (now > before + 1) {
      furthest = Math.max(furthest, now);
      if (skipLimitSeconds != null && track) {
        report();
        player.sync();
      }
    }
  }

  // The first report marks when watching began, which the server's limit
  // counts real playback time from.
  function onPlaying() {
    paused = false;
    startFrames();
    finishing = false;
    if (reportedStart || skipLimitSeconds == null || !videoEl || !track) return;
    reportedStart = true;
    report();
    player.sync();
  }

  onMount(async () => {
    document.addEventListener('fullscreenchange', onFsChange);
    // A player created while the page is already full screen (auto-advance
    // to the next episode) starts with the right full-screen button.
    onFsChange();
    if (track) player.startTracking(episodeId);
    furthest = Math.max(furthestStart, startAt);

    if (!streamUrl) return;
    videoEl.volume = volume;
    videoEl.addEventListener('enterpictureinpicture', () => (pipOn = true));
    videoEl.addEventListener('leavepictureinpicture', () => (pipOn = false));
    wake();

    // Dynamically import HLS.js — works with Bunny Stream HLS URLs
    const { default: Hls } = await import('hls.js/dist/hls.min.js');

    if (Hls.isSupported()) {
      hls = new Hls({
        enableWorker: true,
        lowLatencyMode: false,
        backBufferLength: 90,
        // A part that starts late in the video shouldn't fetch its opening.
        startPosition: clipStart + (startAt > 0 ? startAt : 0),
      });
      // Surface fatal errors instead of leaving a silent black player — a
      // rejected token is the likely cause and the iframe still works.
      hls.on(Hls.Events.ERROR, (_e: unknown, data: any) => {
        if (data?.fatal) fallbackToEmbed(data?.details ?? 'fatal');
      });
      hls.loadSource(streamUrl);
      hls.attachMedia(videoEl);
      // Autoplay can be refused (no interaction yet): then show the play button.
      hls.on(Hls.Events.MANIFEST_PARSED, () => videoEl.play().catch(() => { settled = true; }));
      videoEl.addEventListener('loadedmetadata', applyStart, { once: true });
    } else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari native HLS
      videoEl.src = streamUrl;
      videoEl.addEventListener('loadedmetadata', applyStart, { once: true });
      videoEl.addEventListener('error', () => fallbackToEmbed('safari-native'));
      videoEl.play().catch(() => { settled = true; });
    } else {
      fallbackToEmbed('hls-unsupported');
    }
  });

  let destroyed = false;
  onDestroy(() => {
    destroyed = true;
    if (raf) cancelAnimationFrame(raf);
    if (holdTimer) clearTimeout(holdTimer);
    mixer?.destroy();
    hls?.destroy();
    if (vttUrl) URL.revokeObjectURL(vttUrl);
    if (typeof document !== 'undefined') document.removeEventListener('fullscreenchange', onFsChange);
    if (track) player.stopTracking();
    stopAutoAdvance();
    if (noticeTimer) clearTimeout(noticeTimer);
    if (hideTimer) clearTimeout(hideTimer);
  });

  function onTimeUpdate() {
    if (!videoEl) return;
    const t = videoEl.currentTime;
    if (clipped && !videoEl.seeking) {
      if (t < clipStart - 0.5) { videoEl.currentTime = clipStart; return; }
      // The part ends before the video does: stop there, as if it had ended.
      if (clipEnd !== null && t >= clipEnd - 0.05 && !clipEnded) {
        clipEnded = true;
        videoEl.pause();
        videoEl.currentTime = clipEnd;
        rel = clipLength;
        report();
        onEnded();
        return;
      }
    }
    rel = Math.max(0, t - clipStart);
    if (videoEl.paused) frameT = rel;
    if (videoEl.paused && !holding) mixer?.sync(edits, rel, { playing: false, rate, master: muted ? 0 : volume, end: clipLength });
    const cut = !videoEl.seeking && cutAt(cuts, rel);
    if (cut) {
      videoEl.currentTime = clipStart + cut.end;
      return;
    }
    applyEffects(rel);
    report();
    if (!videoEl.seeking) furthest = Math.max(furthest, rel);
    onTime?.(rel);
  }

  async function onEnded() {
    if (clipped && clipEnd !== null && !clipEnded) return; // a part stops at clipEnd, not here
    if (finishing) return;
    finishing = true;
    clipEnded = true;
    if (track) await player.complete();
    // The learner may have left while completion was being saved.
    if (destroyed) return;
    onComplete?.();
    // Auto-advance
    stopAutoAdvance();
    showAutoAdvance = true;
    countdown = 5;
    autoAdvanceTimer = setInterval(() => {
      countdown--;
      if (countdown <= 0) {
        stopAutoAdvance();
        onAutoAdvance?.();
      }
    }, 1000);
  }

  function stopAutoAdvance() {
    if (autoAdvanceTimer) clearInterval(autoAdvanceTimer);
    autoAdvanceTimer = null;
    showAutoAdvance = false;
  }

  const cancelAutoAdvance = stopAutoAdvance;

  // ---- the control bar (every video) ---------------------------------------
  // Every seek below just sets currentTime, so onSeeking still keeps a part
  // inside its range and holds course videos to the skip limit.
  function togglePlay() {
    if (!videoEl) return;
    rateMenu = false;
    if (videoEl.paused) {
      if (clipEnded) { clipEnded = false; videoEl.currentTime = clipStart; }
      videoEl.play().catch(() => {});
    } else videoEl.pause();
  }
  function onScrub(e: Event) {
    if (videoEl) videoEl.currentTime = clipStart + +(e.target as HTMLInputElement).value;
  }
  function nudge(by: number) {
    if (!videoEl) return;
    const end = clipLength ? clipStart + clipLength : videoEl.duration || Infinity;
    videoEl.currentTime = Math.min(Math.max(clipStart, videoEl.currentTime + by), end);
    wake();
  }
  const RATES = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
  function setRate(r: number) {
    rate = r; rateMenu = false;
    // Times any Video studio speed effect at this moment.
    if (videoEl) videoEl.playbackRate = r * speedAt(effects, rel);
  }
  function toggleMute() {
    muted = !muted;
    if (!muted && volume === 0) volume = 0.5;
    applyVolume();
  }
  function onVolume(e: Event) {
    volume = +(e.target as HTMLInputElement).value;
    muted = volume === 0;
    applyVolume();
  }
  function changeVolume(by: number) {
    volume = Math.min(1, Math.max(0, Math.round((volume + by) * 100) / 100));
    muted = volume === 0;
    applyVolume();
    wake();
  }
  function applyVolume() {
    // The learner's mute, or a Video studio mute effect at this moment.
    if (videoEl) { videoEl.volume = volume * ownVolume; videoEl.muted = muted || mutedAt(effects, rel); }
    try { localStorage.setItem('champ_volume', String(volume)); } catch { /* storage blocked */ }
  }
  function fullscreen() {
    rateMenu = false;
    if (onFullscreen) { onFullscreen(); return; }
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else container.requestFullscreen?.().catch(() => {});
  }
  async function togglePip() {
    if (!videoEl) return;
    try {
      if ((document as any).pictureInPictureElement) await (document as any).exitPictureInPicture();
      else await (videoEl as any).requestPictureInPicture();
    } catch { /* not allowed here */ }
  }
  function onProgress() {
    if (!videoEl) return;
    const t = videoEl.currentTime, b = videoEl.buffered;
    for (let i = 0; i < b.length; i++) {
      if (b.start(i) <= t + 0.5 && b.end(i) >= t) { bufferedRel = Math.max(0, Math.min(b.end(i), endAbs || Infinity) - clipStart); return; }
    }
  }
  function onBarHover(e: MouseEvent) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    hoverPct = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
  }
  // Show the bar on any pointer movement; hide it again after a moment of
  // stillness while the video plays.
  function wake() {
    active = true;
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { active = false; }, 2600);
  }
  $: showBar = paused || active || rateMenu || chaptersOpen || clipEnded;
  // A click anywhere outside the speed or chapters menu closes it (otherwise
  // it, and the bar it keeps visible, would stay up for the rest of the video).
  function closeRateMenu(e: MouseEvent) {
    const el = e.target as Element;
    if (rateMenu && !el?.closest?.('.rate-wrap')) rateMenu = false;
    if (chaptersOpen && !el?.closest?.('.chwrap')) chaptersOpen = false;
  }
  function jumpToChapter(i: number) {
    chaptersOpen = false;
    if (videoEl && chapters[i]) { videoEl.currentTime = clipStart + chapters[i].start; videoEl.play().catch(() => {}); }
  }
  // Until the video first plays (or autoplay is refused, or the learner
  // pauses), "paused" only means "still starting": show the loading ring, not
  // the play button, so it doesn't flash at the start of every video.
  let settled = false;
  // The centre button is a play/pause toggle: Play (or Replay) while paused,
  // Pause while playing, shown whenever the control bar is (pointer moved,
  // paused) and hidden with it. Never while loading or buffering, where the
  // ring takes its place.
  $: showBig = settled && !showAutoAdvance && !(buffering && !paused) && showBar;
  $: bigLabel = !paused ? 'Pause' : clipEnded ? 'Replay' : 'Play';
  // On touch screens the first tap on a playing video only reveals the
  // controls (with the centre Pause); a tap while they show toggles play.
  let tapReveals = false;
  function onTouch() { tapReveals = !showBar; wake(); }
  function onVideoClick() {
    if (tapReveals) { tapReveals = false; return; }
    togglePlay();
  }
  function onKey(e: KeyboardEvent) {
    // The volume slider keeps its own arrow keys; the seek bar uses the
    // player's (its native step would move a tenth of a second).
    if (!useNative || (e.target as HTMLElement).closest('select, .vslider') || e.ctrlKey || e.metaKey || e.altKey) return;
    wake();
    const k = e.key.toLowerCase();
    // Space on a focused button presses that button; k always plays/pauses.
    if (k === ' ' && (e.target as HTMLElement).closest('button')) return;
    if (k === ' ' || k === 'k') { e.preventDefault(); togglePlay(); }
    else if (k === 'arrowright' || k === 'l') { e.preventDefault(); nudge(k === 'l' ? 10 : 5); }
    else if (k === 'arrowleft' || k === 'j') { e.preventDefault(); nudge(k === 'j' ? -10 : -5); }
    else if (k === 'arrowup') { e.preventDefault(); changeVolume(0.1); }
    else if (k === 'arrowdown') { e.preventDefault(); changeVolume(-0.1); }
    else if (k === 'm') toggleMute();
    else if (k === 'f') fullscreen();
    else if (k === 'c' && captions.length) toggleCc();
    else if (k === 'escape' && rateMenu) rateMenu = false;
  }
  const clock = (s: number) => {
    s = Math.max(0, Math.floor(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
  };
</script>

<svelte:window on:click={closeRateMenu} />

<!-- One themed control bar on every video (whole or trimmed part). Keys work
     while the player has focus: k/space, j/l, arrows, m, f, c. -->
<!-- svelte-ignore a11y-no-noninteractive-tabindex a11y-no-noninteractive-element-interactions -->
<div bind:this={container} class="player-wrap" class:native={useNative} class:idle={useNative && !showBar}
     role="region" aria-label="Video player" tabindex={useNative ? 0 : -1} style={canvasBg}
     on:keydown={onKey} on:mousemove={wake} on:touchstart={onTouch}
     on:mouseleave={() => { if (!paused) active = false; hoverPct = null; }}>
  {#if useNative}
    <!-- The studio's canvas: a blurred copy of the picture filling the frame. -->
    <BackdropFill video={videoEl} active={edits?.look?.background === 'blur'} />
    <!-- Preferred: token-authenticated HLS in a native player. This is the ONLY
         path that fires timeupdate/ended, so it is the only one that records
         watch progress. -->
    <!-- svelte-ignore a11y-media-has-caption a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
    <video
      bind:this={videoEl}
      class="video"
      preload="metadata"
      style={videoStyle}
      playsinline
      on:click={onVideoClick}
      on:dblclick={fullscreen}
      on:timeupdate={onTimeUpdate}
      on:seeking={onSeeking}
      on:seeked={() => { onSeeked(); buffering = false; onProgress(); }}
      on:playing={() => { onPlaying(); buffering = false; settled = true; }}
      on:play={() => { paused = false; wake(); if (showAutoAdvance) stopAutoAdvance(); }}
      on:pause={onPause}
      on:waiting={() => (buffering = true)}
      on:canplay={() => (buffering = false)}
      on:progress={onProgress}
      on:loadedmetadata={() => { duration = videoEl.duration || 0; applyVolume(); }}
      on:ended={onEnded}
    >
      {#if vttUrl}
        <track bind:this={trackEl} kind="captions" srclang="en" label="Transcript" src={vttUrl}
          on:load={() => { if (trackEl?.track) trackEl.track.mode = trackMode; }} />
      {/if}
    </video>

    <!-- Centre of the video: one layer that fills the player and centres its
         contents, so nothing here is positioned by offsets. The play button
         is always in the DOM and only fades, so play/pause never re-creates
         it (that re-creation, with its pop-in animation, made it jump). -->
    <div class="center-layer">
      {#if !settled || (buffering && !paused)}<span class="ring" aria-hidden="true"></span>{/if}
      <button class="bigplay" class:show={showBig} class:is-play={bigLabel === 'Play'} on:click={() => { togglePlay(); wake(); }}
        tabindex={showBig ? 0 : -1} aria-hidden={!showBig} aria-label={bigLabel} title={`${bigLabel} (k)`}>
        {#if bigLabel === 'Pause'}
          <svg viewBox="0 0 24 24" width="30" height="30" fill="currentColor" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>
        {:else if bigLabel === 'Replay'}
          <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>
        {:else}
          <svg viewBox="0 0 24 24" width="30" height="30" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg>
        {/if}
      </button>
    </div>

    <div class="cbar" class:show={showBar}>
      <!-- svelte-ignore a11y-no-static-element-interactions -->
      <div class="seek" on:mousemove={onBarHover} on:mouseleave={() => (hoverPct = null)}>
        {#if hoverPct !== null && clipLength}
          <span class="seek-tip" style="left:{hoverPct * 100}%">{clock(hoverPct * clipLength)}</span>
        {/if}
        <input class="cscrub" type="range" min="0" max={clipLength || 0} step="0.1" value={rel} on:input={onScrub}
          aria-label="Seek" aria-valuetext="{clock(rel)} of {clock(clipLength)}"
          style="--pct:{clipLength ? (rel / clipLength) * 100 : 0}%; --buf:{clipLength ? Math.min(100, (bufferedRel / clipLength) * 100) : 0}%" />
        <!-- Video studio: cut-out parts (skipped) and chapter starts. -->
        {#if clipLength}
          {#each cuts as c}<i class="cutzone" style="left:{(c.start / clipLength) * 100}%; width:{((c.end - c.start) / clipLength) * 100}%"></i>{/each}
          {#each chapters as c, i}{#if i > 0}<i class="chtick" style="left:{(c.start / clipLength) * 100}%"></i>{/if}{/each}
        {/if}
      </div>
      <div class="crow">
        <button on:click={togglePlay} aria-label={paused ? 'Play' : 'Pause'} title={paused ? 'Play (k)' : 'Pause (k)'}>
          {#if paused}<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg>
          {:else}<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>{/if}
        </button>
        <button on:click={() => nudge(-10)} aria-label="Back 10 seconds" title="Back 10 s (j)">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 12a8.5 8.5 0 1 0 2.8-6.3L3.5 8"/><path d="M3.5 3.5V8H8"/><text x="12.6" y="15.6" text-anchor="middle" font-size="7.2" font-weight="700" fill="currentColor" stroke="none">10</text></svg>
        </button>
        <button on:click={() => nudge(10)} aria-label="Forward 10 seconds" title="Forward 10 s (l)">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 12a8.5 8.5 0 1 1-2.8-6.3L20.5 8"/><path d="M20.5 3.5V8H16"/><text x="11.4" y="15.6" text-anchor="middle" font-size="7.2" font-weight="700" fill="currentColor" stroke="none">10</text></svg>
        </button>
        <span class="vol">
          <button on:click={toggleMute} aria-label={muted || volume === 0 ? 'Unmute' : 'Mute'} title="Mute (m)">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/>{#if muted || volume === 0}<path d="M16 9.5l5 5M21 9.5l-5 5"/>{:else if volume < 0.5}<path d="M15.5 9a4 4 0 010 6"/>{:else}<path d="M15.5 9a4 4 0 010 6M18 6.5a7.5 7.5 0 010 11"/>{/if}</svg>
          </button>
          <input class="vslider" type="range" min="0" max="1" step="0.05" value={muted ? 0 : volume} on:input={onVolume}
            aria-label="Volume" style="--pct:{(muted ? 0 : volume) * 100}%" />
        </span>
        <span class="ctime">{clock(rel)} <i>/</i> {clock(clipLength)}</span>
        {#if chapters.length}
          <span class="chwrap">
            <button class="txt chname" on:click={() => (chaptersOpen = !chaptersOpen)} aria-haspopup="menu" aria-expanded={chaptersOpen}
              title="Chapters">{chapterIdx >= 0 ? chapters[chapterIdx].title : 'Chapters'}</button>
            {#if chaptersOpen}
              <div class="chmenu" role="menu">
                {#each chapters as c, i}
                  <button role="menuitem" class:on={i === chapterIdx} on:click={() => jumpToChapter(i)}>
                    <span class="chtime">{clock(c.start)}</span> {c.title}
                  </button>
                {/each}
              </div>
            {/if}
          </span>
        {/if}
        <span class="grow"></span>
        <button class="txt" class:on={ccOn && !!captions.length} on:click={toggleCc} disabled={!captions.length} aria-pressed={ccOn}
          aria-label={!captions.length ? 'No captions for this video yet' : ccOn ? 'Turn captions off' : 'Turn captions on'}
          title={!captions.length ? 'No captions for this video yet' : 'Captions (c)'}>
          {@html icons.cc}<span class="lbl">CC</span>
        </button>
        {#if onQna}
          <button class="txt" on:click={openQna} aria-label="Ask a question about this moment, or read the Q&A" title="Q&A">
            {@html icons.qna}<span class="lbl">Q&amp;A</span>{#if qnaCount}<b class="count">{qnaCount}</b>{/if}
          </button>
        {/if}
        <span class="rate-wrap">
          <button class="txt" on:click={() => (rateMenu = !rateMenu)} aria-haspopup="menu" aria-expanded={rateMenu} aria-label="Playback speed" title="Playback speed">
            {rate === 1 ? '1×' : `${rate}×`}
          </button>
          {#if rateMenu}
            <div class="rate-menu" role="menu">
              {#each RATES as r}
                <button role="menuitemradio" aria-checked={r === rate} class:on={r === rate} on:click={() => setRate(r)}>{r === 1 ? 'Normal' : `${r}×`}</button>
              {/each}
            </div>
          {/if}
        </span>
        {#if canPip}
          <button on:click={togglePip} aria-label={pipOn ? 'Exit picture in picture' : 'Picture in picture'} title="Picture in picture">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><rect x="12" y="11.5" width="6.5" height="5" rx="1" fill="currentColor"/></svg>
          </button>
        {/if}
        <button on:click={fullscreen} aria-label={isFs ? 'Exit full screen' : 'Full screen'} title="Full screen (f)">
          {#if isFs}<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>
          {:else}<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>{/if}
        </button>
      </div>
    </div>
  {:else if embedUrl}
    <!-- Fallback: Bunny's iframe embed. Plays reliably but reports NO progress,
         so a learner watching here will not have completion recorded. It has
         its own controls. -->
    <iframe
      src={embedUrl}
      class="bunny-embed"
      title="Video player"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
      allowfullscreen
    ></iframe>
  {:else}
    <div class="placeholder"><span class="ring"></span>Loading video…</div>
  {/if}

  <!-- Captions (styled by the Video studio when it has a caption style) and
       the studio's overlays, look and brand. Raised clear of the control bar
       while it shows. -->
  {#if useNative}
    <EditedLayer {edits} t={frameT} from={0} to={clipLength} {captions} ccOn={ccOn && !videoFs} raised={showBar} />
  {/if}

  {#if !useNative && onQna}
    <!-- The embed has its own controls, so Q&A sits over it, top left. -->
    <div class="overlay-tools">
      <button class="otool" on:click={openQna} aria-label="Ask a question about this moment, or read the Q&A" title="Q&A">
        {@html icons.qna}<span>Q&amp;A</span>{#if qnaCount}<b class="count">{qnaCount}</b>{/if}
      </button>
    </div>
  {/if}

  {#if skipNotice}
    <div class="skip-notice" role="status">{skipNotice}</div>
  {/if}

  {#if showAutoAdvance}
    <div class="auto-advance">
      <span class="aa-count" style="--p:{(countdown / 5) * 100}%"><b>{countdown}</b></span>
      <p>Next episode in <strong>{countdown}s</strong></p>
      <button class="btn-ghost" on:click={cancelAutoAdvance}>Cancel</button>
    </div>
  {/if}
</div>

<style>
  .player-wrap {
    position: relative;
    width: 100%;
    aspect-ratio: 16/9;
    background: #0b0b0d;
    border-radius: var(--radius-xl);
    overflow: hidden;
    box-shadow: var(--shadow-md);
    animation: modal-in 520ms var(--ease-out) backwards;
  }
  .player-wrap:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .video, .bunny-embed {
    display: block; width: 100%; height: 100%; border: none;
  }
  .native .video { cursor: pointer; }
  .player-wrap.idle, .player-wrap.idle .video { cursor: none; }
  .placeholder {
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.9rem;
    height: 100%; color: rgba(244, 244, 246, 0.7); font-size: 0.9rem;
  }
  /* ---- the control bar ---- */
  .cbar {
    /* Layers: video < studio overlays and captions (EditedLayer, 1-5) <
       centre play (6) < this bar (7) < notices (8). */
    position: absolute; left: 0; right: 0; bottom: 0; z-index: 7;
    display: grid; gap: 0.15rem;
    padding: 2.2rem 0.8rem 0.55rem;
    background: linear-gradient(transparent, rgba(0, 0, 0, 0.55) 45%, rgba(0, 0, 0, 0.82));
    color: #fff;
    opacity: 0; translate: 0 6px; pointer-events: none;
    transition: opacity 220ms var(--ease-out), translate 220ms var(--ease-out);
  }
  .cbar.show, .cbar:has(:focus-visible) { opacity: 1; translate: 0 0; pointer-events: auto; }
  .crow { display: flex; align-items: center; gap: 0.15rem; min-width: 0; }
  .grow { flex: 1; min-width: 0.25rem; }
  .cbar button {
    position: relative; display: inline-flex; align-items: center; justify-content: center; gap: 0.3rem;
    min-width: 36px; height: 36px; padding: 0 0.35rem; border-radius: var(--radius-pill); color: #fff; flex: none;
    transition: background-color var(--dur-2), scale var(--dur-2) var(--ease-out);
  }
  .cbar button:hover:not(:disabled) { background: rgba(255, 255, 255, 0.16); }
  .cbar button:active:not(:disabled) { scale: 0.92; }
  .cbar button:focus-visible { outline: 2px solid #fff; outline-offset: 1px; }
  .cbar button:disabled { opacity: 0.4; cursor: not-allowed; }
  .cbar .txt { font-size: 0.78rem; font-weight: 700; padding: 0 0.6rem; font-variant-numeric: tabular-nums; }
  .cbar .txt :global(svg) { font-size: 1.1rem; }
  .cbar .txt.on { background: #fff; color: #000; }
  /* The player is always dark, so it uses the brand red (as the watch-progress
     bars on thumbnails do), never --accent, which is near-black in light mode. */
  .cbar .count {
    min-width: 18px; height: 18px; padding: 0 5px; border-radius: var(--radius-pill); display: grid; place-items: center;
    background: var(--brand); color: #fff; font-size: 0.68rem;
  }
  .ctime { margin-left: 0.4rem; font-size: 0.8rem; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .ctime i { font-style: normal; opacity: 0.55; margin: 0 0.1rem; }

  /* seek bar: played (accent), buffered (light), rest (faint) */
  .seek { position: relative; display: flex; align-items: center; height: 18px; }
  .cscrub {
    flex: 1; width: 100%; height: 4px; appearance: none; border-radius: 4px; cursor: pointer; margin: 0;
    background: linear-gradient(to right,
      var(--brand) var(--pct), rgba(255, 255, 255, 0.5) var(--pct),
      rgba(255, 255, 255, 0.5) var(--buf), rgba(255, 255, 255, 0.22) var(--buf));
    transition: height 150ms var(--ease-out);
  }
  .seek:hover .cscrub { height: 6px; }
  .cscrub::-webkit-slider-thumb { appearance: none; width: 14px; height: 14px; border-radius: 50%; background: #fff; box-shadow: 0 0 0 4px color-mix(in srgb, var(--brand) 40%, transparent); }
  .cscrub::-moz-range-thumb { width: 14px; height: 14px; border: 0; border-radius: 50%; background: #fff; }
  .cscrub:focus-visible { outline: 2px solid #fff; outline-offset: 4px; }
  .seek-tip {
    position: absolute; bottom: 20px; translate: -50% 0; pointer-events: none;
    padding: 0.15rem 0.45rem; border-radius: 6px; background: rgba(0, 0, 0, 0.82); color: #fff;
    font-size: 0.72rem; font-weight: 600; font-variant-numeric: tabular-nums; white-space: nowrap;
  }

  /* volume: the slider opens beside the speaker on hover / focus */
  .vol { display: inline-flex; align-items: center; }
  .vslider {
    width: 0; opacity: 0; height: 4px; appearance: none; border-radius: 4px; cursor: pointer; margin: 0;
    background: linear-gradient(to right, #fff var(--pct), rgba(255, 255, 255, 0.3) var(--pct));
    transition: width 200ms var(--ease-out), opacity 200ms, margin 200ms;
  }
  .vol:hover .vslider, .vol:focus-within .vslider { width: 72px; opacity: 1; margin: 0 0.5rem 0 0.2rem; }
  .vslider::-webkit-slider-thumb { appearance: none; width: 12px; height: 12px; border-radius: 50%; background: #fff; }
  .vslider::-moz-range-thumb { width: 12px; height: 12px; border: 0; border-radius: 50%; background: #fff; }
  @media (hover: none) { .vslider { display: none; } }

  /* speed menu */
  .rate-wrap { position: relative; display: inline-flex; }
  .rate-menu {
    position: absolute; right: 0; bottom: 44px; z-index: 6; display: grid; min-width: 112px; padding: 0.3rem;
    border-radius: var(--radius-lg); background: rgba(16, 16, 20, 0.94); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
    animation: pop 200ms var(--ease-out);
  }
  .cbar .rate-menu button { justify-content: flex-start; height: 32px; padding: 0 0.75rem; border-radius: var(--radius); font-size: 0.8rem; font-weight: 600; }
  .cbar .rate-menu button.on { background: rgba(255, 255, 255, 0.16); }

  /* centre: big play / replay, and the buffering ring */
  .center-layer {
    position: absolute; inset: 0; z-index: 6; display: grid; place-items: center; pointer-events: none;
  }
  .center-layer > * { grid-area: 1 / 1; }
  /* Hidden = faded and slightly smaller, in place. Only opacity and scale
     change (no translate, no backdrop blur), so it never shifts or flickers. */
  .bigplay {
    width: 72px; height: 72px; border-radius: 50%; display: grid; place-items: center; padding: 0;
    color: #fff; background: rgba(0, 0, 0, 0.6); border: 1px solid rgba(255, 255, 255, 0.18);
    opacity: 0; scale: 0.9; visibility: hidden; pointer-events: none;
    transition: opacity 180ms var(--ease-out), scale 180ms var(--ease-out), visibility 0s linear 180ms, background-color var(--dur-2);
  }
  .bigplay.show {
    opacity: 1; scale: 1; visibility: visible; pointer-events: auto;
    transition: opacity 180ms var(--ease-out), scale 180ms var(--ease-out), visibility 0s, background-color var(--dur-2);
  }
  /* The triangle's visual centre sits left of its box; nudge the icon, not the button. */
  .bigplay.is-play svg { translate: 2px 0; }
  .bigplay.show:hover { background: var(--brand); border-color: var(--brand); scale: 1.06; }
  .bigplay.show:active { scale: 0.96; }

  /* narrow players: keep the essentials */
  @container (max-width: 520px) {
    .lbl, .vol .vslider { display: none; }
    .ctime { font-size: 0.72rem; margin-left: 0.2rem; }
    .cbar button { min-width: 32px; height: 32px; }
  }
  @container (max-width: 380px) {
    .crow > button:nth-child(2), .crow > button:nth-child(3) { display: none; }
  }
  .overlay-tools {
    position: absolute; top: 10px; left: 10px; z-index: 4;
    display: flex; gap: 0.35rem;
    opacity: 0.8; transition: opacity 0.2s;
  }
  .player-wrap:hover .overlay-tools, .overlay-tools:focus-within { opacity: 1; }
  .otool {
    display: inline-flex; align-items: center; gap: 0.35rem; height: 36px; padding: 0 0.8rem;
    border-radius: var(--radius-pill); color: #fff; background: rgba(0, 0, 0, 0.55); font-size: 0.78rem; font-weight: 700;
    border: 1px solid rgba(255, 255, 255, 0.14);
  }
  .otool :global(svg) { font-size: 1.1rem; }
  .otool:hover { background: rgba(0, 0, 0, 0.75); }
  .otool .count {
    min-width: 18px; height: 18px; padding: 0 5px; border-radius: var(--radius-pill); display: grid; place-items: center;
    background: var(--brand); color: #fff; font-size: 0.68rem;
  }
  /* Overlays and captions (EditedLayer) are sized to the player's width. */
  .player-wrap { container-type: inline-size; }
  /* Positioned, so it paints over the canvas's blurred fill behind it. */
  .video { position: relative; transition: filter 200ms; }

  /* Video studio marks on the seek bar: cut-out parts and chapter starts. */
  .cutzone {
    position: absolute; top: 50%; height: 4px; translate: 0 -50%; pointer-events: none; border-radius: 2px;
    background: repeating-linear-gradient(135deg, rgba(0, 0, 0, 0.65) 0 3px, rgba(255, 255, 255, 0.18) 3px 6px);
  }
  .chtick { position: absolute; top: 50%; width: 3px; height: 8px; translate: -50% -50%; background: rgba(0, 0, 0, 0.85); pointer-events: none; border-radius: 1px; }
  /* chapters menu: same look as the speed menu */
  .chwrap { position: relative; display: inline-flex; min-width: 0; }
  .cbar .chname { max-width: 14em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; line-height: 36px; }
  .chmenu {
    position: absolute; left: 0; bottom: 44px; z-index: 6; display: grid; min-width: 15rem; max-height: 14rem; overflow: auto; padding: 0.3rem;
    border-radius: var(--radius-lg); background: rgba(16, 16, 20, 0.94); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
    animation: pop 200ms var(--ease-out);
  }
  .cbar .chmenu button { justify-content: flex-start; gap: 0.6rem; height: auto; padding: 0.45rem 0.7rem; border-radius: var(--radius); font-size: 0.8rem; font-weight: 600; text-align: left; }
  .cbar .chmenu button.on { background: rgba(255, 255, 255, 0.16); }
  .chtime { font-variant-numeric: tabular-nums; opacity: 0.7; }
  @container (max-width: 520px) { .chwrap { display: none; } }
  /* The browser's own captions, in its full screen only: smaller than its default. */
  .video::cue { background: rgba(8, 8, 12, 0.72); color: #fff; font-size: 70%; line-height: 1.4; }
  .skip-notice {
    position: absolute; left: 50%; top: 1.25rem; transform: translateX(-50%); z-index: 8;
    max-width: calc(100% - 2rem); text-align: center;
    background: rgba(0,0,0,0.82); color: #fff;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: var(--radius-pill); padding: 0.55rem 1.1rem; font-size: 0.86rem; font-weight: 500;
    animation: pop 260ms var(--ease-out);
    pointer-events: none;
  }
  .ring {
    width: 38px; height: 38px; border-radius: 50%;
    border: 3px solid rgba(255, 255, 255, 0.15); border-top-color: #f4f4f6;
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin { to { rotate: 360deg; } }
  .auto-advance {
    /* Above the bar, which also shows once the video has ended. */
    position: absolute; bottom: 5.5rem; right: 1.5rem; z-index: 8;
    background: rgba(12, 12, 14, 0.88); color: #f4f4f6;
    border-radius: 999px;
    padding: 0.45rem 0.5rem 0.45rem 0.5rem;
    display: flex; align-items: center; gap: 0.8rem;
    font-size: 0.9rem;
    animation: rise 420ms var(--ease-out) backwards;
  }
  /* Named aa-count, not count: the Q&A button's badge is .otool .count. */
  .aa-count {
    width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center;
    background: conic-gradient(#f4f4f6 var(--p), rgba(255, 255, 255, 0.15) 0);
    transition: background 900ms linear;
  }
  .aa-count b {
    width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center;
    background: #0c0c0e; font-size: 0.85rem; animation: pop 400ms var(--ease-out);
  }
  .btn-ghost {
    background: rgba(255, 255, 255, 0.14);
    color: #f4f4f6;
    height: 34px; padding: 0 0.95rem;
    border-radius: 999px;
    font-size: 0.8rem; font-weight: 600;
    transition: background-color var(--dur-2);
  }
  .btn-ghost:hover { background: rgba(255, 255, 255, 0.24); }
</style>
