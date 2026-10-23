<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { player } from '$lib/stores/player';
  import type { TranscriptSegment } from '$lib/api/client';
  import { icons } from '$lib/components/course/icons';
  import { segmentsToVtt } from '$lib/utils/transcribe';
  import {
    chapterIndexAt, cutAt, cutSecondsBetween, frameStyle, lookFilter, mutedAt, speedAt, type VideoEdits,
  } from '$lib/utils/video-edits';
  import EditedLayer from '$lib/components/video/EditedLayer.svelte';

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
  // Video studio edits in clip time: cuts are jumped over, chapters marked on
  // the scrub bar, speed and mute effects applied as it plays, and overlays,
  // caption style, look, zooms and brand drawn over it.
  export let edits: VideoEdits | null = null;
  $: cuts = edits?.cuts ?? [];
  $: chapters = edits?.chapters ?? [];
  $: effects = edits?.effects ?? [];
  // Speed and mute change playback itself, so the player has to own its controls.
  $: timed = effects.some(e => e.kind === 'speed' || e.kind === 'mute');
  $: chapterIdx = chapterIndexAt(chapters, rel);
  $: videoStyle = [lookFilter(edits?.look) && `filter: ${lookFilter(edits?.look)};`, frameStyle(edits?.look, effects, frameT)].filter(Boolean).join(' ');
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
    else applyEffects(frameT);
    raf = requestAnimationFrame(tick);
  }
  /** The learner's speed times the edit's, and their mute or the edit's. */
  function applyEffects(t: number) {
    if (!videoEl || !timed) return;
    const want = rate * speedAt(effects, t);
    if (Math.abs(videoEl.playbackRate - want) > 0.001) videoEl.playbackRate = want;
    const mute = muted || mutedAt(effects, t);
    if (videoEl.muted !== mute) videoEl.muted = mute;
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
      ? URL.createObjectURL(new Blob([segmentsToVtt(captions, clipStart, custom ? 'line:80%' : '')], { type: 'text/vtt' }))
      : '';
  }
  // Captions are drawn over the video (.caption), sized to the player, since
  // the browser's own caption text is large and can't be styled reliably. The
  // track is shown only when the video element itself is full screen, where
  // nothing drawn over it can appear.
  let videoFs = false;
  const onFsChange = () => { videoFs = !!videoEl && document.fullscreenElement === videoEl; };
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
  // Own controls for a clipped part, and for a video with cuts or chapters,
  // which the browser's scrub bar can't show.
  $: custom = clipped || cuts.length > 0 || chapters.length > 0 || timed;
  let duration = 0; // the whole video's, once known
  $: endAbs = clipEnd ?? duration;
  $: clipLength = Math.max(0, endAbs - clipStart);

  // Custom-controls state (clipped parts and edited videos).
  let paused = true;
  let muted = false;
  let rate = 1;
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
    if (clipped) {
      const end = endAbs || videoEl.duration || Infinity;
      target = Math.min(Math.max(target, clipStart), end);
      if (target < end - 0.5) clipEnded = false;
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
    if (track) player.startTracking(episodeId);
    furthest = Math.max(furthestStart, startAt);

    if (!streamUrl) return;

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
      hls.on(Hls.Events.MANIFEST_PARSED, () => videoEl.play().catch(() => {}));
      videoEl.addEventListener('loadedmetadata', applyStart, { once: true });
    } else if (videoEl.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari native HLS
      videoEl.src = streamUrl;
      videoEl.addEventListener('loadedmetadata', applyStart, { once: true });
      videoEl.addEventListener('error', () => fallbackToEmbed('safari-native'));
      videoEl.play();
    } else {
      fallbackToEmbed('hls-unsupported');
    }
  });

  let destroyed = false;
  onDestroy(() => {
    destroyed = true;
    if (raf) cancelAnimationFrame(raf);
    hls?.destroy();
    if (vttUrl) URL.revokeObjectURL(vttUrl);
    if (typeof document !== 'undefined') document.removeEventListener('fullscreenchange', onFsChange);
    if (track) player.stopTracking();
    stopAutoAdvance();
    if (noticeTimer) clearTimeout(noticeTimer);
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

  // ---- custom controls for a clipped part or an edited video ---------------
  function togglePlay() {
    if (!videoEl) return;
    if (videoEl.paused) {
      if (clipEnded) { clipEnded = false; videoEl.currentTime = clipStart; }
      videoEl.play().catch(() => {});
    } else videoEl.pause();
  }
  function onScrub(e: Event) {
    if (videoEl) videoEl.currentTime = clipStart + +(e.target as HTMLInputElement).value;
  }
  function nudge(by: number) {
    if (videoEl) videoEl.currentTime = Math.max(clipStart, videoEl.currentTime + by);
  }
  function cycleRate() {
    const rates = [1, 1.25, 1.5, 2];
    rate = rates[(rates.indexOf(rate) + 1) % rates.length];
    if (videoEl) videoEl.playbackRate = rate * speedAt(effects, rel);
  }
  function toggleMute() { muted = !muted; if (videoEl) videoEl.muted = muted || mutedAt(effects, rel); }
  function fullscreen() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else container.requestFullscreen?.().catch(() => {});
  }
  function jumpToChapter(i: number) {
    chaptersOpen = false;
    if (videoEl && chapters[i]) { videoEl.currentTime = clipStart + chapters[i].start; videoEl.play().catch(() => {}); }
  }
  function onKey(e: KeyboardEvent) {
    if (!custom || (e.target as HTMLElement).closest('input, button, select')) return;
    if (e.key === ' ' || e.key === 'k') { e.preventDefault(); togglePlay(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); nudge(5); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); nudge(-5); }
    else if (e.key === 'm') toggleMute();
    else if (e.key === 'f') fullscreen();
  }
  const clock = (s: number) => {
    s = Math.max(0, Math.floor(s));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    return h ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}` : `${m}:${String(r).padStart(2, '0')}`;
  };
</script>

<!-- Keyboard control for a clipped part's own controls; the native player
     handles its own keys. -->
<!-- svelte-ignore a11y-no-noninteractive-tabindex a11y-no-noninteractive-element-interactions -->
<div bind:this={container} class="player-wrap" class:clipped={custom} role="region" aria-label="Video player"
     tabindex={custom ? 0 : -1} on:keydown={onKey}>
  {#if useNative}
    <!-- Preferred: token-authenticated HLS in a native player. This is the ONLY
         path that fires timeupdate/ended, so it is the only one that records
         watch progress. -->
    <!-- svelte-ignore a11y-media-has-caption a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
    <video
      bind:this={videoEl}
      class="video"
      controls={!custom}
      preload="metadata"
      style={videoStyle}
      on:click={() => custom && togglePlay()}
      on:timeupdate={onTimeUpdate}
      on:seeking={onSeeking}
      on:seeked={onSeeked}
      on:playing={onPlaying}
      on:pause={() => (paused = true)}
      on:loadedmetadata={() => (duration = videoEl.duration || 0)}
      on:ended={onEnded}
    >
      {#if vttUrl}
        <track bind:this={trackEl} kind="captions" srclang="en" label="Transcript" src={vttUrl}
          on:load={() => { if (trackEl?.track) trackEl.track.mode = trackMode; }} />
      {/if}
    </video>
    {#if custom}
      <div class="cbar">
        <button on:click={togglePlay} aria-label={paused ? 'Play' : 'Pause'}>
          {#if paused}<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l10.5-6.5z"/></svg>
          {:else}<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>{/if}
        </button>
        <span class="ctime">{clock(rel)} / {clock(clipLength)}</span>
        <span class="scrub">
          <input class="cscrub" type="range" min="0" max={clipLength || 0} step="0.1" value={rel} on:input={onScrub}
            aria-label="Seek" style="--pct:{clipLength ? (rel / clipLength) * 100 : 0}%" />
          {#if clipLength}
            {#each cuts as c}<i class="cutzone" style="left:{(c.start / clipLength) * 100}%; width:{((c.end - c.start) / clipLength) * 100}%"></i>{/each}
            {#each chapters as c, i}{#if i > 0}<i class="chtick" style="left:{(c.start / clipLength) * 100}%"></i>{/if}{/each}
          {/if}
        </span>
        {#if chapters.length}
          <span class="chwrap">
            <button class="txt chname" on:click={() => (chaptersOpen = !chaptersOpen)} aria-expanded={chaptersOpen}
              title="Chapters">{chapterIdx >= 0 ? chapters[chapterIdx].title : 'Chapters'}</button>
            {#if chaptersOpen}
              <span class="chmenu" role="menu">
                {#each chapters as c, i}
                  <button role="menuitem" class:cur={i === chapterIdx} on:click={() => jumpToChapter(i)}>
                    <span class="mono">{clock(c.start)}</span> {c.title}
                  </button>
                {/each}
              </span>
            {/if}
          </span>
        {/if}
        <button class="txt" on:click={cycleRate} aria-label="Playback speed">{rate}×</button>
        <button on:click={toggleMute} aria-label={muted ? 'Unmute' : 'Mute'}>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/>{#if muted}<path d="M16 9.5l5 5M21 9.5l-5 5"/>{:else}<path d="M15.5 9a4 4 0 010 6M18 6.5a7.5 7.5 0 010 11"/>{/if}</svg>
        </button>
        <button on:click={fullscreen} aria-label="Full screen">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>
        </button>
      </div>
    {/if}
  {:else if embedUrl}
    <!-- Fallback: Bunny's iframe embed. Plays reliably but reports NO progress,
         so a learner watching here will not have completion recorded. -->
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

  {#if useNative}
    <EditedLayer {edits} t={frameT} from={0} to={clipLength} {captions} ccOn={ccOn && !videoFs} raised={custom} />
  {/if}

  {#if useNative || onQna}
    <!-- Over the video, top left: the page keeps its own tools top right. -->
    <div class="overlay-tools">
      {#if useNative}
        <button class="otool" class:on={ccOn && !!captions.length} on:click={toggleCc} aria-pressed={ccOn}
          disabled={!captions.length}
          aria-label={!captions.length ? 'No captions for this video yet' : ccOn ? 'Turn captions off' : 'Turn captions on'}
          title={!captions.length ? 'No captions for this video yet' : ccOn ? 'Captions on' : 'Captions off'}>
          {@html icons.cc}<span>CC</span>
        </button>
      {/if}
      {#if onQna}
        <button class="otool" on:click={openQna} aria-label="Ask a question about this moment, or read the Q&A" title="Q&A">
          {@html icons.qna}<span>Q&amp;A</span>{#if qnaCount}<b class="count">{qnaCount}</b>{/if}
        </button>
      {/if}
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
    border-radius: 28px;
    overflow: hidden;
    box-shadow: var(--shadow-md);
    animation: modal-in 520ms var(--ease-out) backwards;
  }
  .player-wrap:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .video, .bunny-embed {
    display: block; width: 100%; height: 100%; border: none;
  }
  .clipped .video { cursor: pointer; }
  .placeholder {
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.9rem;
    height: 100%; color: rgba(244, 244, 246, 0.7); font-size: 0.9rem;
  }
  .cbar {
    position: absolute; left: 0; right: 0; bottom: 0;
    display: flex; align-items: center; gap: 0.5rem;
    padding: 1.4rem 0.75rem 0.55rem;
    background: linear-gradient(transparent, rgba(0, 0, 0, 0.78));
    color: #fff;
    opacity: 0; transition: opacity 0.2s;
  }
  .player-wrap:hover .cbar, .player-wrap:focus-within .cbar { opacity: 1; }
  @media (hover: none) { .cbar { opacity: 1; } }
  .cbar button {
    display: grid; place-items: center; min-width: 32px; height: 32px;
    border-radius: 6px; color: #fff;
  }
  .cbar button:hover { background: rgba(255, 255, 255, 0.15); }
  .cbar .txt { font-size: 0.78rem; font-weight: 700; padding: 0 0.4rem; font-variant-numeric: tabular-nums; }
  .ctime { font-size: 0.78rem; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .cscrub {
    height: 4px; appearance: none; border-radius: 4px; cursor: pointer;
    background: linear-gradient(to right, var(--accent) var(--pct), rgba(255, 255, 255, 0.3) var(--pct));
  }
  .cscrub::-webkit-slider-thumb { appearance: none; width: 13px; height: 13px; border-radius: 50%; background: #fff; }
  .cscrub::-moz-range-thumb { width: 13px; height: 13px; border: 0; border-radius: 50%; background: #fff; }
  .overlay-tools {
    position: absolute; top: 10px; left: 10px; z-index: 4;
    display: flex; gap: 0.35rem;
    opacity: 0.8; transition: opacity 0.2s;
  }
  .player-wrap:hover .overlay-tools, .overlay-tools:focus-within { opacity: 1; }
  .otool {
    display: inline-flex; align-items: center; gap: 0.35rem; height: 32px; padding: 0 0.65rem;
    border-radius: 8px; color: #fff; background: rgba(0, 0, 0, 0.55); font-size: 0.76rem; font-weight: 700;
    border: 1px solid rgba(255, 255, 255, 0.14);
  }
  .otool :global(svg) { font-size: 1.05rem; }
  .otool:hover { background: rgba(0, 0, 0, 0.75); }
  .otool.on { background: #fff; color: #000; border-color: #fff; }
  .otool:disabled { opacity: 0.5; cursor: not-allowed; }
  .otool .count {
    min-width: 18px; height: 18px; padding: 0 5px; border-radius: 99px; display: grid; place-items: center;
    background: var(--accent); color: var(--on-accent); font-size: 0.68rem;
  }
  /* Overlays and captions (EditedLayer) are sized to the player's width. */
  .player-wrap { container-type: inline-size; }
  .scrub { position: relative; flex: 1; min-width: 60px; display: flex; align-items: center; }
  .scrub .cscrub { width: 100%; }
  .cutzone { position: absolute; top: 50%; height: 4px; translate: 0 -50%; pointer-events: none;
    background: repeating-linear-gradient(135deg, rgba(0,0,0,.65) 0 3px, rgba(255,255,255,.18) 3px 6px); border-radius: 2px; }
  .chtick { position: absolute; top: 50%; width: 3px; height: 8px; translate: -50% -50%; background: rgba(0,0,0,.85); pointer-events: none; border-radius: 1px; }
  .chwrap { position: relative; }
  .cbar .chname { max-width: 14em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; line-height: 32px; }
  .chmenu { position: absolute; right: 0; bottom: 40px; min-width: 15rem; max-height: 14rem; overflow: auto; display: grid;
    background: rgba(14,14,18,.96); border: 1px solid rgba(255,255,255,.14); border-radius: 10px; padding: 0.3rem; z-index: 6; }
  .cbar .chmenu button { display: flex; gap: 0.6rem; justify-content: flex-start; text-align: left; height: auto;
    padding: 0.45rem 0.55rem; font-size: 0.8rem; border-radius: 7px; }
  .cbar .chmenu button.cur { background: rgba(255,255,255,.14); }
  .chmenu .mono { font-variant-numeric: tabular-nums; opacity: 0.7; }
  .video { transition: filter 200ms; }
  /* The browser's own captions, in its full screen only: smaller than its default. */
  .video::cue { background: rgba(8, 8, 12, 0.72); color: #fff; font-size: 70%; line-height: 1.4; }
  .skip-notice {
    position: absolute; left: 50%; top: 1.25rem; transform: translateX(-50%);
    max-width: calc(100% - 2rem); text-align: center;
    background: rgba(0,0,0,0.82); color: #fff;
    border: 1px solid var(--border);
    border-radius: 8px; padding: 0.55rem 0.9rem; font-size: 0.88rem;
    pointer-events: none;
  }
  .ring {
    width: 38px; height: 38px; border-radius: 50%;
    border: 3px solid rgba(255, 255, 255, 0.15); border-top-color: #f4f4f6;
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin { to { rotate: 360deg; } }
  .auto-advance {
    position: absolute; bottom: 1.5rem; right: 1.5rem;
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
