<script lang="ts">
  // One icon in the floating dock. It grows as the pointer comes near,
  // springing between sizes like a macOS dock, and shows its name above while
  // the pointer is over it. A Svelte take on Aceternity's Floating Dock item.
  //
  // Size and hover come from the icon's *resting* centre (worked out by the
  // dock), never from where it is on screen now: growing icons widen the
  // dock and slide each other along, and measuring that live made the sizes
  // feed back on themselves and wobble, and the tooltip flicker.
  import { spring } from 'svelte/motion';

  export let label: string;
  export let icon: string;
  export let desc = '';
  export let shortcut = '';
  export let active = false;
  /** Acts at the playhead straight away instead of opening a panel. */
  export let action = false;
  /** The pointer's x on screen; Infinity when it's away from the dock. */
  export let mouseX = Infinity;
  /** This icon's centre on screen with every icon at rest. */
  export let center = NaN;
  export let base = 38;
  export let max = 56;
  export let reach = 130;
  export let still = false; // touch / phone strip: no magnifying, no hover tooltip
  export let instant = false; // reduced motion: resize without the spring

  // Keyboard focus only: Chrome focuses a button on click too, and the
  // tooltip would then stay up after picking a tool.
  let focused = false;
  const size = spring(base, { stiffness: 0.16, damping: 0.7 });

  $: dist = Number.isFinite(mouseX) && Number.isFinite(center) ? Math.abs(mouseX - center) : Infinity;
  // Linear from `max` under the pointer to `base` at `reach` px away, as in
  // the original's useTransform(distance, [-150, 0, 150], [40, 80, 40]).
  $: target = still || dist >= reach ? base : base + (max - base) * (1 - dist / reach);
  $: size.set(target, still || instant ? { hard: true } : undefined);
  /** The pointer is over this icon right now (the dock checks every frame). */
  export let pointed = false;
  // The tooltip follows what's really under the pointer. (Working it out
  // from the resting slot, as the sizes are, named the wrong tool near the
  // dock's ends, where grown icons have slid furthest from their slots.) The
  // hit area spans the gaps either side, so moving along the dock never
  // drops the tooltip.
  $: hovered = !still && pointed;
  $: showTip = hovered || focused;
  $: iconSize = Math.round($size * 0.48);
</script>

<button class="dock-item" class:active class:action data-tool={label}
  style="width:{$size}px; height:{$size}px; --icon:{iconSize}px"
  on:click on:focus={e => (focused = e.currentTarget.matches(':focus-visible'))} on:blur={() => (focused = false)}
  aria-pressed={action ? undefined : active} aria-label={`${label}: ${desc}${shortcut ? ` (${shortcut})` : ''}`}>
  <span class="glyph" aria-hidden="true">{@html icon}</span>
  {#if showTip}
    <span class="tip" role="tooltip">
      <b>{label}</b>{#if shortcut}<kbd>{shortcut}</kbd>{/if}
      {#if desc}<small>{desc}</small>{/if}
    </span>
  {/if}
</button>

<style>
  .dock-item {
    position: relative; flex: none; display: grid; place-items: center; border-radius: 999px;
    background: var(--st-raise); color: var(--st-text); border: 1px solid var(--st-line);
    transition: background-color 140ms, border-color 140ms, color 140ms;
  }
  /* Hover area: half the 8px gap on each side (neighbours meet, never
     overlap) and down to the dock's bottom edge. */
  .dock-item::before { content: ''; position: absolute; inset: -6px -4px -9px; }
  .dock-item:hover { background: var(--st-hover); }
  .dock-item:focus-visible { outline: 2px solid var(--st-focus); outline-offset: 2px; }
  .dock-item.action { border-style: dashed; }
  .dock-item.active { background: var(--st-hot); border-color: var(--st-hot); color: #fff; }
  /* The open tool: a dot under it, as on a macOS dock. */
  .dock-item.active::after {
    content: ''; position: absolute; left: 50%; bottom: -7px; translate: -50% 0; width: 4px; height: 4px; border-radius: 50%; background: var(--st-hot);
  }
  .glyph { width: var(--icon); height: var(--icon); display: grid; place-items: center; font-size: var(--icon); line-height: 1; pointer-events: none; }
  .glyph :global(svg) { width: 100%; height: 100%; }

  /* The app's tooltip bubble (Tooltips.svelte): ink in light mode, light in
     dark, 11px corners, an arrow pointing at the icon. */
  .tip {
    position: absolute; left: 50%; bottom: calc(100% + 10px); translate: -50% 0; z-index: 20; pointer-events: none;
    display: grid; grid-template-columns: auto auto; justify-content: center; align-items: center; gap: 0.1rem 0.4rem;
    width: max-content; max-width: 220px; padding: 0.45rem 0.7rem; border-radius: 11px; text-align: center;
    background: var(--st-ink); color: var(--st-on-ink);
    box-shadow: 0 10px 28px -10px rgba(0, 0, 0, 0.45), 0 2px 6px rgba(0, 0, 0, 0.12);
    font-size: 0.76rem; font-weight: 600; line-height: 1.35; animation: tip-in 160ms ease-out;
  }
  .tip::after {
    content: ''; position: absolute; left: 50%; top: 100%; width: 10px; height: 10px; margin: -5px 0 0 -5px;
    background: inherit; border-radius: 0 0 3px 0; rotate: 45deg;
  }
  .tip b { font-weight: 700; }
  .tip kbd { font: inherit; font-size: 0.62rem; font-weight: 700; padding: 0 0.3em; border-radius: 4px; border: 1px solid color-mix(in srgb, var(--st-on-ink) 35%, transparent); }
  .tip small { grid-column: 1 / -1; font-size: 0.66rem; font-weight: 500; opacity: 0.75; }
  @keyframes tip-in { from { opacity: 0; translate: -50% 4px; } }
</style>
