<script lang="ts" context="module">
  export type DockTool = { id: string; label: string; icon: string; desc: string; key?: string; run?: () => void };
  export type DockGroup = { name: string; tools: DockTool[] };
</script>

<script lang="ts">
  // The studio's tools as a floating dock along the bottom (a Svelte take on
  // Aceternity's Floating Dock): icons in a row that magnify as the pointer
  // moves along them, a divider between groups, a dot under the open tool.
  // On touch screens, narrow ones and with reduced motion it is a plain strip
  // you swipe, without the magnifying.
  import { createEventDispatcher, onMount } from 'svelte';
  import DockItem from './DockItem.svelte';

  export let groups: DockGroup[] = [];
  /** The open tool's id. */
  export let active: string | null = null;
  /** Smaller icons when space is tight. */
  export let small = false;

  const dispatch = createEventDispatcher<{ use: DockTool }>();
  let dockEl: HTMLElement;
  let mouseX = Infinity;
  let centers: number[] = [];
  // Touch screens and phone widths: a strip you swipe (no hover to drive the
  // magnifying). Reduced motion (Windows' "animation effects" off, common on
  // office PCs) keeps the dock and its tooltips; icons just resize without
  // the springy animation.
  let touch = false;
  let instant = false;
  onMount(() => {
    const strip = window.matchMedia('(hover: none), (max-width: 760px)');
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)');
    const on = () => { touch = strip.matches; instant = calm.matches; };
    on();
    strip.addEventListener('change', on); calm.addEventListener('change', on);
    return () => { strip.removeEventListener('change', on); calm.removeEventListener('change', on); };
  });
  // The dock only magnifies when it fits with room for icons to grow;
  // otherwise (a window too narrow for every tool) it's the strip you
  // scroll, so no tool ends up off-screen and hover never picks the wrong one.
  let roomW = Infinity;
  const GROW_ROOM = 72;
  $: still = touch || restOffsets.width + 2 + GROW_ROOM > roomW;

  $: base = small ? 34 : 38;
  $: max = small ? 50 : 56;
  // Keep in step with the CSS below: padding, gaps and the divider's width.
  const PAD = 14, GAP = 8, DIVIDER = 1 + 2 * 2;
  $: flat = groups.flatMap(g => g.tools);
  // Each icon's centre measured from the dock's left edge, every icon at rest.
  $: restOffsets = (() => {
    const out: number[] = [];
    let x = PAD;
    groups.forEach((g, gi) => {
      if (gi > 0) x += GAP + DIVIDER + GAP;
      g.tools.forEach((_, ti) => {
        if (ti > 0) x += GAP;
        out.push(x + base / 2);
        x += base;
      });
    });
    return { out, width: x + PAD };
  })();

  // The dock is centred, so its centre doesn't move as icons grow: resting
  // centres taken from it stay put, which keeps the sizes from feeding back.
  function onMove(e: MouseEvent) {
    if (still || !dockEl) { mouseX = Infinity; return; }
    const r = dockEl.getBoundingClientRect();
    const left = r.left + r.width / 2 - restOffsets.width / 2;
    centers = restOffsets.out.map(o => left + o);
    mouseX = e.clientX;
  }
  function onLeave() { mouseX = Infinity; }
</script>

<div class="room" bind:clientWidth={roomW}>
<!-- svelte-ignore a11y-no-static-element-interactions -->
<nav class="dock" aria-label="Studio tools" class:still bind:this={dockEl} on:mousemove={onMove} on:mouseleave={onLeave}>
  {#each groups as g, gi}
    {#if gi > 0}<span class="divider" aria-hidden="true"></span>{/if}
    <span class="grp" role="group" aria-label={g.name}>
      {#each g.tools as tl}
        {@const i = flat.indexOf(tl)}
        <DockItem label={tl.label} icon={tl.icon} desc={tl.desc} shortcut={tl.key ?? ''} action={!!tl.run}
          active={!tl.run && active === tl.id} {mouseX} center={centers[i] ?? NaN} {base} {max} {still} {instant}
          on:click={() => dispatch('use', tl)} />
      {/each}
    </span>
  {/each}
</nav>
</div>

<style>
  .room { width: 100%; min-width: 0; }
  /* Champ LMS look: a pill like the app's top-bar tabs, on the theme's
     surface, with the app's soft shadow. Icons sit on its bottom edge and
     grow upwards out of it. */
  .dock {
    display: flex; align-items: flex-end; gap: 8px; width: max-content; max-width: 100%; margin: 0 auto;
    height: 52px; padding: 0 14px 7px; border-radius: var(--radius-pill, 999px);
    background: var(--st-panel); border: 1px solid var(--st-line);
    box-shadow: 0 2px 6px rgba(18, 18, 20, 0.05), 0 14px 32px -14px rgba(18, 18, 20, 0.28);
  }
  .grp { display: flex; align-items: flex-end; gap: 8px; }
  .divider { flex: none; align-self: flex-end; width: 1px; height: 28px; margin: 0 2px 5px; background: var(--st-line); }
  /* Touch, narrow screens, reduced motion: a strip you swipe, no magnifying. */
  .dock.still { overflow-x: auto; scrollbar-width: none; align-items: center; height: 50px; padding: 0 10px; }
  .dock.still::-webkit-scrollbar { display: none; }
  .dock.still .grp, .dock.still .divider { align-self: center; }
  .dock.still .divider { margin: 0 2px; }
  @media (max-width: 760px) {
    .dock { width: 100%; border-radius: 0; box-shadow: none; border-width: 1px 0 0; }
  }
</style>
