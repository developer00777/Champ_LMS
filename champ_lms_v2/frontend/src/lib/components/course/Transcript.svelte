<script lang="ts">
  import { tick } from 'svelte';
  import type { TranscriptSegment } from '$lib/api/client';
  import { clock } from '$lib/utils/transcribe';
  import { icons } from './icons';

  export let segments: TranscriptSegment[] = [];
  export let source: string | null = null;
  export let time = 0;
  export let onSeek: (seconds: number) => void;

  let query = '';
  let list: HTMLOListElement;
  let follow = true;
  let lastActive = -1;

  $: active = (() => {
    let k = -1;
    for (let i = 0; i < segments.length; i++) { if (segments[i].start <= time + 0.25) k = i; else break; }
    return k;
  })();
  $: shown = segments.map((s, i) => ({ ...s, i })).filter(s => !query || s.text.toLowerCase().includes(query.toLowerCase()));

  // Keep the current line in view while the video plays, unless the learner
  // is searching or has scrolled away to read.
  $: if (active !== lastActive) { lastActive = active; if (follow && !query) scrollToActive(); }
  async function scrollToActive() {
    await tick();
    const el = list?.querySelector<HTMLElement>(`[data-i="${active}"]`);
    if (el && list) list.scrollTo({ top: el.offsetTop - 60, behavior: 'smooth' });
  }
</script>

<div class="tx">
  <div class="tx-h">
    <input type="search" bind:value={query} placeholder="Search the transcript" aria-label="Search the transcript" />
    <label class="follow"><input type="checkbox" bind:checked={follow} /> Follow video</label>
    <span class="src">{#if source === 'auto'}{@html icons.sparkle} Auto-generated{:else if source === 'manual'}Checked by your admin{/if}</span>
  </div>
  {#if !segments.length}
    <p class="empty">No transcript for this episode yet.</p>
  {:else}
    <ol class="tx-list" bind:this={list}>
      {#each shown as s (s.i)}
        <li data-i={s.i}>
          <button class="line" class:active={s.i === active} on:click={() => onSeek(s.start)}>
            <span class="t">{clock(s.start)}</span><span>{s.text}</span>
          </button>
        </li>
      {:else}
        <li class="empty">No line matches “{query}”.</li>
      {/each}
    </ol>
  {/if}
</div>

<style>
  .tx { display: grid; gap: 0.6rem; animation: fade 420ms var(--ease-out) backwards; }
  .tx-h { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  .tx-h input[type='search'] {
    flex: 1; min-width: 180px; font: inherit; font-size: 0.88rem; color: var(--text); height: 42px;
    background: var(--surface2); border: none; border-radius: 999px; padding: 0 1rem;
    transition: background-color var(--dur-2), box-shadow var(--dur-2) var(--ease-out);
  }
  .tx-h input[type='search']:focus { background: var(--surface); box-shadow: 0 0 0 2px var(--accent); outline: none; }
  .follow {
    display: inline-flex; gap: 0.4rem; align-items: center; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary);
    height: 34px; padding: 0 0.8rem; border-radius: 999px; background: var(--surface2); cursor: pointer;
  }
  .follow input { accent-color: var(--accent); }
  .src { display: inline-flex; gap: 0.3rem; align-items: center; font-size: 0.76rem; color: var(--muted); white-space: nowrap; }
  .tx-list { position: relative; list-style: none; margin: 0; padding: 0; max-height: 380px; overflow: auto; }
  .line {
    display: grid; grid-template-columns: 56px 1fr; gap: 0.6rem; width: 100%; text-align: left;
    padding: 0.5rem 0.6rem; border-radius: 16px; color: var(--text-secondary); font-size: 0.92rem; line-height: 1.55;
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2);
  }
  .line:hover { background: var(--surface2); }
  .line:hover .t { color: var(--text); }
  .line.active { background: var(--tile-lilac); color: var(--tile-ink); }
  .line.active .t { background: var(--accent); color: var(--on-accent); }
  .t {
    font-size: 0.72rem; font-weight: 600; color: var(--muted); font-variant-numeric: tabular-nums;
    height: 22px; display: inline-grid; place-items: center; border-radius: 99px; background: var(--surface2);
    transition: background-color var(--dur-2), color var(--dur-2);
  }
  .empty { color: var(--muted); font-size: 0.88rem; padding: 0.5rem; }
</style>
