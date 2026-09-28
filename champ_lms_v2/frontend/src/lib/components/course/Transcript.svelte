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
  .tx { display: grid; gap: 0.5rem; }
  .tx-h { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  .tx-h input[type='search'] {
    flex: 1; min-width: 180px; font: inherit; font-size: 0.88rem; color: var(--text);
    background: var(--surface); border: 1px solid var(--border-hover); border-radius: 8px; padding: 0.45rem 0.7rem;
  }
  .follow { display: inline-flex; gap: 0.35rem; align-items: center; font-size: 0.8rem; color: var(--muted); }
  .follow input { accent-color: var(--accent); }
  .src { display: inline-flex; gap: 0.3rem; align-items: center; font-size: 0.76rem; color: var(--muted); white-space: nowrap; }
  .tx-list { position: relative; list-style: none; margin: 0; padding: 0; max-height: 380px; overflow: auto; }
  .line {
    display: grid; grid-template-columns: 52px 1fr; gap: 0.6rem; width: 100%; text-align: left;
    padding: 0.45rem 0.5rem; border-radius: 8px; color: var(--text-secondary); font-size: 0.9rem; line-height: 1.5;
  }
  .line:hover { background: var(--surface2); }
  .line.active { background: rgba(229, 9, 20, 0.14); color: var(--text); }
  .t { font-family: ui-monospace, Consolas, monospace; font-size: 0.74rem; color: var(--muted); padding-top: 0.15rem; font-variant-numeric: tabular-nums; }
  .empty { color: var(--muted); font-size: 0.88rem; padding: 0.5rem; }
</style>
