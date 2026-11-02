<script lang="ts">
  // One row of the watch-page playlist: the same look for a standalone
  // episode, a series episode and every kind of course step.
  import Thumb from '$lib/components/Thumb.svelte';
  import { icons } from '$lib/components/course/icons';

  export let title: string;
  export let sub = '';
  export let kind: 'video' | 'quiz' | 'test' | 'notes' = 'video';
  export let thumb: string | null | undefined = null;
  export let duration = '';
  export let current = false;
  export let done = false;
  export let locked = false;
  export let lockedHint = '';
  /** 0–100 watched; drawn under the thumbnail until the item is done. */
  export let progress = 0;
</script>

<button class="pi k-{kind}" class:cur={current} class:done class:locked on:click
  aria-current={current ? 'true' : undefined} aria-disabled={locked} title={locked ? lockedHint : ''}>
  <span class="pi-th">
    {#if kind === 'video' && thumb && !locked}<Thumb src={thumb} />{/if}
    <span class="pi-ico">{@html locked ? icons.lock : kind === 'video' ? icons.play : icons[kind]}</span>
    {#if done && !locked}<span class="pi-done" aria-label="Done">{@html icons.check}</span>{/if}
    {#if progress > 0 && !done && !locked}<i style="width:{Math.min(100, progress)}%"></i>{/if}
  </span>
  <span class="pi-b">
    <b>{title}</b>
    {#if sub}<small>{sub}</small>{/if}
  </span>
  {#if duration}<span class="pi-d">{duration}</span>{/if}
</button>

<style>
  .k-video { --kc: var(--info); --kt: var(--tile-lilac); }
  .k-quiz { --kc: var(--violet); --kt: var(--tile-lilac); }
  .k-test { --kc: var(--gold); --kt: var(--tile-butter); }
  .k-notes { --kc: var(--teal); --kt: var(--tile-mint); }
  .pi {
    display: grid; grid-template-columns: 92px minmax(0, 1fr) auto; gap: 0.7rem; align-items: center; width: 100%;
    padding: 0.45rem; border-radius: var(--radius-lg); text-align: left;
    transition: background-color var(--dur-2), translate var(--dur-2) var(--ease-out);
  }
  .pi:hover:not(.locked) { background: var(--surface2); translate: 2px 0; }
  .pi.cur { background: var(--tile-lilac); color: var(--tile-ink); }
  .pi.cur small, .pi.cur .pi-d { color: inherit; opacity: 0.72; }
  .pi.locked { opacity: 0.55; cursor: not-allowed; }

  .pi-th {
    position: relative; aspect-ratio: 16 / 9; border-radius: var(--radius); overflow: hidden; display: grid; place-items: center;
    background: var(--kt); color: var(--kc);
  }
  .pi:hover:not(.locked) .pi-th :global(.thumb-media) { scale: 1.06; }
  .pi-ico {
    position: relative; z-index: 1; display: grid; place-items: center; width: 26px; height: 26px; border-radius: 50%;
    font-size: 0.8rem; background: var(--surface); color: var(--text); transition: scale var(--dur-3) var(--ease-out);
  }
  .k-quiz .pi-ico, .k-test .pi-ico, .k-notes .pi-ico { color: var(--kc); }
  .locked .pi-ico { color: var(--warn); }
  .pi:hover:not(.locked) .pi-ico { scale: 1.12; }
  .pi-done {
    position: absolute; z-index: 2; right: 4px; top: 4px; width: 18px; height: 18px; border-radius: 50%;
    display: grid; place-items: center; font-size: 0.62rem; background: var(--success); color: var(--on-accent);
    animation: pop 420ms var(--ease-out) backwards;
  }
  .pi-th i { position: absolute; z-index: 2; left: 0; bottom: 0; height: 3px; background: var(--brand); }

  .pi-b { display: grid; gap: 2px; min-width: 0; }
  .pi-b b {
    font-weight: 600; font-size: 0.86rem; line-height: 1.3;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .pi-b small { font-size: 0.73rem; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pi-d { font-size: 0.72rem; color: var(--muted); font-variant-numeric: tabular-nums; align-self: start; padding-top: 2px; }
</style>
