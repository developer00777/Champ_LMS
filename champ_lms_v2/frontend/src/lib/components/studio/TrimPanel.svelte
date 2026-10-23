<script lang="ts">
  import { api } from '$lib/api/client';
  import { clock } from '$lib/utils/transcribe';
  import { MIN_PART, splitAt, trimEnd, trimStart, useStudio } from './studio';

  export let dirty = false;
  export let onJoined: () => void;

  const st = useStudio();
  const { doc, parts, time, ep } = st;
  const L = st.length;

  let startText = clock($doc.start);
  let endText = clock($doc.end);
  $: startText = clock($doc.start);
  $: endText = clock($doc.end);
  let joining = false;

  function parseTime(text: string): number | null {
    const bits = text.trim().split(':').map(Number);
    if (!bits.length || bits.some(n => Number.isNaN(n) || n < 0)) return null;
    return bits.reduce((acc, n) => acc * 60 + n, 0);
  }

  const setStart = (x: number) => trimStart(st, x);
  const setEnd = (x: number) => trimEnd(st, x);

  async function joinNext() {
    if (dirty && !confirm('Joining reloads the studio, and unsaved changes here will be lost. Join anyway?')) return;
    joining = true;
    try { st.reset(await api.studioJoinNext($ep.id)); st.say('Joined with the next part.'); onJoined(); }
    catch (e: any) { st.say(e.message, 'bad'); }
    finally { joining = false; }
  }

  $: isCanvas = $ep.layout === 'canvas';
</script>

<div class="p-sec">
  <h3 class="p-h">Trim</h3>
  <p class="p-note">The video on Bunny isn't changed: this sets which part plays. Drag the blue edges on the timeline, or use the playhead.</p>
  <div class="row">
    <label class="field sm">Starts at
      <input type="text" bind:value={startText} on:change={() => { const v = parseTime(startText); if (v !== null) setStart(v); else startText = clock($doc.start); }} />
    </label>
    <label class="field sm">Ends at
      <input type="text" bind:value={endText} on:change={() => { const v = parseTime(endText); if (v !== null) setEnd(v); else endText = clock($doc.end); }} />
    </label>
  </div>
  <div class="row">
    <button class="btn sm" on:click={() => setStart($time)}>Start at playhead</button>
    <button class="btn sm" on:click={() => setEnd($time)}>End at playhead</button>
    <button class="btn sm ghost" on:click={() => st.commit(d => { d.start = 0; d.end = L; d.splits = []; })}>Use whole video</button>
  </div>
</div>

<div class="p-sec">
  <h3 class="p-h">Split into parts</h3>
  <p class="p-note">
    {#if isCanvas}Each part becomes its own episode, so a quiz or test can sit between them on the course canvas.
    {:else}Each part becomes its own episode in this module, right after this one, in order.{/if}
  </p>
  <div class="row"><button class="btn sm hot" on:click={() => splitAt(st, $time)}>Split at playhead <kbd>S</kbd></button></div>
  <ol class="list">
    {#each $parts as p, i}
      <li class:bad={p.played < MIN_PART}>
        <div class="li-main">
          <b>{$parts.length > 1 ? `Part ${i + 1}` : 'Plays'}</b>
          <span class="mono">{clock(p.from)} – {clock(p.to)}</span>
          <span class="muted">{clock(p.played)}{p.played < p.len - 0.5 ? ' after cuts' : ''}{$parts.length > 1 ? (i === 0 ? ' · this episode' : ' · new episode') : ''}</span>
        </div>
        <div class="row tight">
          <button class="btn xs" on:click={() => st.playRange(p.from, p.to, $parts.length > 1 ? `part ${i + 1}` : 'the kept video')}>▶ Play</button>
          <button class="btn xs ghost" on:click={() => st.playRange(Math.max(p.from, p.to - 5), p.to, 'the ending')} title="The last 5 seconds">Ending</button>
          {#if i > 0}
            <button class="btn xs ghost" on:click={() => st.playRange(Math.max($doc.start, p.from - 4), Math.min($doc.end, p.from + 4), `the split at ${clock(p.from)}`)}>Hear the cut</button>
            <button class="btn xs ghost danger" on:click={() => st.commit(d => { d.splits = d.splits.filter(s => s !== p.from); })} aria-label="Remove the split at {clock(p.from)}">Remove split</button>
          {/if}
        </div>
      </li>
    {/each}
  </ol>
  {#if $parts.some(p => p.played < MIN_PART)}<p class="p-bad">Each part needs at least {MIN_PART} seconds left to play.</p>{/if}
</div>

{#if $ep.part || $ep.can_join_next}
  <div class="p-sec">
    <h3 class="p-h">Saved parts of this video</h3>
    <ol class="list">
      {#each $ep.parts as p, i}
        <li class:cur={p.is_this}><div class="li-main"><b>Part {i + 1}</b><span class="mono">{clock(p.clip_start)} – {clock(p.clip_end ?? L)}</span><span class="muted">{p.is_this ? 'open here' : p.title}</span></div></li>
      {/each}
    </ol>
    <p class="p-note">The timeline shows the whole video. Edits here (cuts, text, chapters, look) apply to every part.</p>
    {#if $ep.can_join_next}
      <button class="btn sm" on:click={joinNext} disabled={joining}>{joining ? 'Joining…' : 'Join with the next part'}</button>
    {/if}
  </div>
{/if}
