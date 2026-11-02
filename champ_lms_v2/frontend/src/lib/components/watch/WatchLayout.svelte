<script lang="ts">
  /**
   * The one layout every video-viewing page uses (standalone episodes, series
   * episodes and the full course player), so watching looks and behaves the
   * same everywhere:
   *
   *   ┌ bar: [playlist] context ··········· ‹ Previous  Next › ┐
   *   │ stage (the player, 16:9)               │ playlist     │
   *   │ body (title, tabs, tab content)        │ (sticky)     │
   *   └────────────────────────────────────────┴──────────────┘
   *
   * The playlist sits on the right and can be hidden; full screen shows the
   * player alone, with the playlist as an optional drawer.
   */
  import { onDestroy, onMount, tick } from 'svelte';
  import { icons } from '$lib/components/course/icons';

  /** Short "where am I" line on the bar, e.g. "Basics › Episode 3 of 8". */
  export let context = '';
  export let onPrev: (() => void) | null = null;
  export let onNext: (() => void) | null = null;
  export let prevDisabled = false;
  export let nextDisabled = false;
  export let prevLabel = 'Previous';
  export let nextLabel = 'Next';
  /** Show the player area (false for quiz, test and notes steps). */
  export let stage = true;
  /** Show the playlist column. */
  export let side = true;
  export let sideTitle = '';
  export let sideMeta = '';
  /** 0–100 progress bar under the playlist title; null hides it. */
  export let sideProgress: number | null = null;
  export let sideLabel = 'Episodes';

  let sideOpen = true;
  let theater = false;
  let rootEl: HTMLElement;

  function onFs() { if (!document.fullscreenElement && theater) { theater = false; sideOpen = true; } }
  onMount(() => document.addEventListener('fullscreenchange', onFs));
  onDestroy(() => { if (typeof document !== 'undefined') document.removeEventListener('fullscreenchange', onFs); });

  /** Full screen: the player fills the screen, the playlist becomes a drawer.
   *  The player's own full-screen button calls this. */
  export async function toggleTheater() {
    theater = !theater;
    sideOpen = !theater;
    try {
      if (theater && rootEl?.requestFullscreen) await rootEl.requestFullscreen();
      else if (!theater && document.fullscreenElement) await document.exitFullscreen();
    } catch { /* not allowed here: the CSS version still fills the window */ }
  }

  /** Leave full screen, e.g. before jumping to a tab below the player. */
  export async function exitTheater() {
    if (theater) await toggleTheater();
    await tick();
  }

  $: showSide = side && sideOpen;

  // Full screen is for watching: picking a quiz, test or notes step (no
  // player) leaves it, or the learner would see only black and the drawer.
  $: if (theater && !stage) exitTheater();
  // On a phone the drawer covers the player in full screen: once a new step
  // is picked from it, close it so the video shows.
  let lastContext = context;
  $: if (context !== lastContext) {
    lastContext = context;
    if (theater && typeof window !== 'undefined' && window.innerWidth <= 760) sideOpen = false;
  }
</script>

<div class="wl" class:theater class:no-side={!showSide} bind:this={rootEl}>
  <div class="wl-main">
    <div class="wl-bar">
      <span class="wl-ctx">
        {#if side && !sideOpen && !theater}
          <button class="wbtn sm" on:click={() => (sideOpen = true)}>{@html icons.panel} {sideLabel}</button>
        {/if}
        {#if context}<span class="wl-ctx-t">{context}</span>{/if}
      </span>
      {#if onPrev || onNext}
        <span class="wl-nav">
          {#if onPrev}<button class="wbtn sm ghost" on:click={onPrev} disabled={prevDisabled}>{@html icons.back} {prevLabel}</button>{/if}
          {#if onNext}<button class="wbtn sm" on:click={onNext} disabled={nextDisabled}>{nextLabel} {@html icons.next}</button>{/if}
        </span>
      {/if}
    </div>

    {#if stage}
      <div class="wl-stage">
        <slot name="stage" />
        {#if theater && side}
          <!-- Full screen comes from the player's own control bar; here only the playlist drawer. -->
          <div class="wl-tools">
            <button class="otool" on:click={() => (sideOpen = !sideOpen)} aria-label={sideOpen ? `Hide ${sideLabel.toLowerCase()}` : `Show ${sideLabel.toLowerCase()}`} title={sideLabel}>{@html icons.panel}</button>
          </div>
        {/if}
      </div>
    {/if}

    <div class="wl-body"><slot /></div>
  </div>

  {#if showSide}
    <aside class="wl-side" aria-label={sideLabel}>
      <div class="wl-side-h">
        <div class="wl-side-row">
          <h3>{sideTitle}</h3>
          <!-- Always there, full screen included: on a phone the open drawer
               covers the player, and this is the way back to the video. -->
          <button class="ibtn" on:click={() => (sideOpen = false)} aria-label={`Hide ${sideLabel.toLowerCase()}`} title={`Hide ${sideLabel.toLowerCase()}`}>{@html icons.panel}</button>
        </div>
        {#if sideProgress !== null}<div class="wl-bar-p"><i style="width:{Math.max(0, Math.min(100, sideProgress))}%"></i></div>{/if}
        {#if sideMeta}<span class="wl-side-m">{sideMeta}</span>{/if}
      </div>
      <div class="wl-side-b"><slot name="side" /></div>
    </aside>
  {/if}
</div>

<style>
  .wl { display: grid; gap: 1.2rem; grid-template-columns: minmax(0, 1fr); align-items: start; }
  @media (min-width: 1080px) { .wl:not(.no-side) { grid-template-columns: minmax(0, 1fr) 360px; } }
  .wl-main { min-width: 0; display: grid; gap: 1rem; animation: rise 480ms var(--ease-out) backwards; }

  .wl-bar {
    display: flex; gap: 0.6rem; align-items: center; justify-content: space-between; flex-wrap: wrap;
    font-size: 0.84rem; color: var(--text-secondary); font-weight: 500; min-height: 34px;
  }
  .wl-ctx, .wl-nav { display: flex; gap: 0.4rem; align-items: center; min-width: 0; }
  .wl-ctx-t { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .wbtn {
    display: inline-flex; align-items: center; gap: 0.4rem; height: 34px; padding: 0 0.85rem; border-radius: var(--radius-pill);
    font-weight: 600; font-size: 0.8rem; background: var(--surface2); color: var(--text); white-space: nowrap;
    transition: background-color var(--dur-2) var(--ease-out), translate var(--dur-2) var(--ease-out);
  }
  .wbtn:hover:not(:disabled) { background: var(--surface3); translate: 0 -1px; }
  .wbtn.ghost { background: transparent; }
  .wbtn.ghost:hover:not(:disabled) { background: var(--surface2); }
  .wbtn:disabled { opacity: 0.45; cursor: not-allowed; }
  .wbtn :global(svg) { transition: translate var(--dur-2) var(--ease-out); }
  .wbtn:hover:not(:disabled) :global(svg) { translate: 2px 0; }
  .wbtn.ghost:hover:not(:disabled) :global(svg:first-child) { translate: -2px 0; }

  .wl-stage { position: relative; }
  .wl-tools { position: absolute; top: 12px; right: 12px; z-index: 5; display: flex; gap: 0.35rem; }
  .otool {
    display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%; font-size: 1.05rem;
    color: #fff; background: rgba(0, 0, 0, 0.5); transition: background-color var(--dur-2), scale var(--dur-2) var(--ease-out);
  }
  .otool:hover { background: rgba(0, 0, 0, 0.72); scale: 1.08; }

  .wl-body { min-width: 0; display: grid; gap: 1rem; }

  .wl-side {
    background: var(--surface); border-radius: var(--radius-xl); box-shadow: var(--shadow-sm); overflow: auto;
    position: sticky; top: 80px; max-height: calc(100vh - 96px);
    animation: rise 520ms var(--ease-out) 120ms backwards;
  }
  @media (max-width: 1079px) { .wl-side { position: static; max-height: 560px; } }
  .wl-side-h { position: sticky; top: 0; z-index: 2; background: var(--bg-alt); padding: 1rem 1rem 0.9rem; display: grid; gap: 0.55rem; }
  .wl-side-row { display: flex; gap: 0.5rem; align-items: center; justify-content: space-between; }
  .wl-side-h h3 { font-size: 1.05rem; font-weight: 700; letter-spacing: -0.015em; min-width: 0; }
  .wl-side-m { font-size: 0.76rem; color: var(--muted); font-variant-numeric: tabular-nums; }
  .wl-bar-p { height: 6px; border-radius: 9px; background: var(--surface3); overflow: hidden; }
  .wl-bar-p i {
    display: block; height: 100%; border-radius: inherit; background: var(--success); transform-origin: left;
    animation: wl-grow 1s var(--ease-out) 300ms backwards; transition: width var(--dur-3) var(--ease-out);
  }
  @keyframes wl-grow { from { transform: scaleX(0); } }
  .wl-side-b { padding: 0.5rem; display: grid; gap: 0.15rem; }
  .ibtn {
    flex: none; display: inline-grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; color: var(--muted); font-size: 1.05rem;
    transition: background-color var(--dur-2), color var(--dur-2), scale var(--dur-2) var(--ease-out);
  }
  .ibtn:hover { background: var(--surface2); color: var(--text); scale: 1.08; }

  /* full screen: the player fills the screen, the playlist becomes a drawer */
  .wl.theater {
    position: fixed; inset: 0; z-index: 250; background: #000; gap: 0; padding: 0;
    grid-template-columns: minmax(0, 1fr) 340px;
  }
  .wl.theater.no-side { grid-template-columns: minmax(0, 1fr); }
  .wl.theater .wl-main { height: 100vh; display: grid; place-items: center; gap: 0; animation: none; }
  .wl.theater .wl-bar, .wl.theater .wl-body { display: none; }
  .wl.theater .wl-stage { width: min(100%, calc(100vh * 16 / 9)); }
  .wl.theater .wl-stage :global(.player-wrap), .wl.theater .wl-stage :global(.stage-ph) { border-radius: 0; box-shadow: none; }
  .wl.theater .wl-side { position: static; height: 100vh; max-height: 100vh; border-radius: 0; box-shadow: none; animation: none; }
  @media (max-width: 760px) {
    .wl.theater:not(.no-side) { grid-template-columns: minmax(0, 1fr); }
    .wl.theater:not(.no-side) .wl-main { display: none; }
  }
</style>
