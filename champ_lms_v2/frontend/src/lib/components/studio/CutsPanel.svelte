<script lang="ts">
  import { api } from '$lib/api/client';
  import { clock } from '$lib/utils/transcribe';
  import { cutSecondsBetween, mergeCuts } from '$lib/utils/video-edits';
  import { addCut, clockShort, cutMarked, deadAir, subtractRange, useStudio } from './studio';

  const st = useStudio();
  const { doc, time, mark, ep, selected, tighten, parts } = st;

  $: d = $doc;
  $: segs = $doc.segments;
  $: kept = segs.filter(s => s.end > d.start && s.start < d.end);
  $: removed = cutSecondsBetween(d.edits.cuts, d.start, d.end);
  $: playsFor = $parts.reduce((a, p) => a + p.played, 0);

  // ---- dead air -----------------------------------------------------------
  let gapMin = 2.5;
  $: gaps = deadAir(segs, d.start, d.end, gapMin).filter(g => cutSecondsBetween(d.edits.cuts, g.start, g.end) < g.end - g.start - 0.1);
  $: gapTotal = gaps.reduce((a, g) => a + g.end - g.start, 0);
  function cutGaps() {
    const n = gaps.length;
    st.commit(dd => { dd.edits.cuts = mergeCuts([...dd.edits.cuts, ...gaps]); });
    st.say(`Cut ${n} silent gap${n === 1 ? '' : 's'} (${clockShort(gapTotal)}).`);
  }

  // ---- AI tighten -----------------------------------------------------------
  let busy = false;
  export async function runTighten() {
    busy = true;
    try {
      const r = await api.studioAi($ep.id, { task: 'tighten', start: d.start, end: d.end });
      tighten.set(r.suggestions);
      if (!r.suggestions.length) st.say('Nothing to tighten: the AI found no stretch it was sure about.');
    } catch (e: any) { st.say(e.message, 'bad'); }
    finally { busy = false; }
  }
  function accept(i: number) {
    const s = ($tighten ?? [])[i];
    if (!s) return;
    st.commit(dd => addCut(dd, s.start, s.end));
    tighten.update(list => (list ?? []).filter((_, n) => n !== i));
  }
  function acceptAll() {
    const all = $tighten ?? [];
    st.commit(dd => { dd.edits.cuts = mergeCuts([...dd.edits.cuts, ...all.map(s => ({ start: s.start, end: s.end }))]); });
    st.say(`Cut ${all.length} stretch${all.length === 1 ? '' : 'es'}.`);
    tighten.set(null);
  }

  // ---- edit by transcript ----------------------------------------------------
  let query = '';
  $: shown = query.trim() ? kept.filter(s => s.text.toLowerCase().includes(query.trim().toLowerCase())) : kept;
  const isCut = (a: number, b: number) => d.edits.cuts.some(c => c.start <= a + 0.05 && c.end >= b - 0.05);
  function toggleLine(i: number) {
    const s = kept[i];
    if (!s) return;
    // A line runs to where the next begins, so cutting it takes its pause too.
    const next = kept[i + 1];
    const end = next && next.start - s.end < 1.5 ? next.start : s.end;
    if (isCut(s.start, s.end)) st.commit(dd => { dd.edits.cuts = subtractRange(dd.edits.cuts, s.start, end); });
    else st.commit(dd => addCut(dd, s.start, end));
  }
  $: nowLine = kept.findIndex(s => $time >= s.start && $time < Math.max(s.end, s.start + 0.5));
</script>

<div class="p-sec">
  <h3 class="p-h">Cut a range</h3>
  <p class="p-note">Cut stretches learners skip: a cough, a tangent, a slide that failed to load. Nothing is deleted; remove a cut to bring it back.</p>
  <div class="row">
    <button class="btn sm" on:click={() => mark.update(m => ({ ...m, in: $time }))}>Mark in <kbd>I</kbd></button>
    <button class="btn sm" on:click={() => mark.update(m => ({ ...m, out: $time }))}>Mark out <kbd>O</kbd></button>
    <button class="btn sm hot" on:click={() => cutMarked(st)} disabled={$mark.in === null || $mark.out === null}>✂ Cut range <kbd>C</kbd></button>
  </div>
  {#if $mark.in !== null || $mark.out !== null}
    <p class="p-note mono">Marked {$mark.in !== null ? clock($mark.in) : '…'} – {$mark.out !== null ? clock($mark.out) : '…'}</p>
  {/if}
  <div class="stat-row">
    <span><b>{d.edits.cuts.length}</b> cut{d.edits.cuts.length === 1 ? '' : 's'}</span>
    <span><b>{clockShort(removed)}</b> removed</span>
    <span><b>{clock(playsFor)}</b> plays</span>
  </div>
</div>

<div class="p-sec">
  <h3 class="p-h">Remove dead air</h3>
  <p class="p-note">Silences between transcript lines, found from its timing.</p>
  <div class="row">
    <div class="seg-ctl" role="radiogroup" aria-label="Shortest silence to cut">
      {#each [1.5, 2.5, 4] as g}
        <button role="radio" aria-checked={gapMin === g} class:on={gapMin === g} on:click={() => (gapMin = g)}>{g} s+</button>
      {/each}
    </div>
    <button class="btn sm" on:click={cutGaps} disabled={!gaps.length}>
      {gaps.length ? `Cut ${gaps.length} gap${gaps.length === 1 ? '' : 's'} · ${clockShort(gapTotal)}` : segs.length ? 'No gaps left' : 'Needs a transcript'}
    </button>
  </div>
</div>

<div class="p-sec">
  <h3 class="p-h">✦ Tighten with AI</h3>
  <p class="p-note">The AI reads the transcript for false starts, repeats and setup chatter, and suggests cuts. You choose which to keep.</p>
  <button class="btn sm ai" on:click={runTighten} disabled={busy || !segs.length}>{busy ? 'Reading the transcript…' : 'Find stretches to cut'}</button>
  {#if $tighten?.length}
    <ol class="list">
      {#each $tighten as s, i}
        <li>
          <div class="li-main"><span class="mono">{clock(s.start)} – {clock(s.end)}</span><span class="muted">{s.reason}</span></div>
          <div class="row tight">
            <button class="btn xs" on:click={() => st.playRange(s.start, s.end, 'the suggested cut')}>▶</button>
            <button class="btn xs hot" on:click={() => accept(i)}>Cut</button>
            <button class="btn xs ghost" on:click={() => tighten.update(l => (l ?? []).filter((_, n) => n !== i))}>Skip</button>
          </div>
        </li>
      {/each}
    </ol>
    <button class="btn sm hot" on:click={acceptAll}>Cut all {$tighten.length}</button>
  {/if}
</div>

{#if d.edits.cuts.length}
  <div class="p-sec">
    <h3 class="p-h">Cuts</h3>
    <ol class="list">
      {#each d.edits.cuts as c, i}
        <li class:cur={$selected?.kind === 'cut' && $selected.index === i}>
          <div class="li-main">
            <button class="linkish mono" on:click={() => { selected.set({ kind: 'cut', index: i }); st.seek(c.start); }}>{clock(c.start)} – {clock(c.end)}</button>
            <span class="muted">{clockShort(c.end - c.start)}</span>
          </div>
          <div class="row tight">
            <button class="btn xs" on:click={() => st.playRange(Math.max(0, c.start - 3), Math.min(st.length, c.end + 3), 'across the cut')} title="3 seconds either side, skipping the cut">Hear it</button>
            <button class="btn xs ghost danger" on:click={() => st.commit(dd => { dd.edits.cuts.splice(i, 1); })} aria-label="Remove this cut">Remove</button>
          </div>
        </li>
      {/each}
    </ol>
  </div>
{/if}

<div class="p-sec">
  <h3 class="p-h">Edit by transcript</h3>
  <p class="p-note">Cut a sentence by striking it out. Click a line's time to jump there.</p>
  {#if kept.length}
    <input class="search" type="search" placeholder="Find in the transcript…" bind:value={query} />
    <ol class="tx">
      {#each shown as s}
        {@const i = kept.indexOf(s)}
        <li class:gone={isCut(s.start, s.end)} class:now={i === nowLine}>
          <button class="t mono" on:click={() => st.seek(s.start)}>{clock(s.start)}</button>
          <span class="x">{s.text}</span>
          <button class="strike" on:click={() => toggleLine(i)} title={isCut(s.start, s.end) ? 'Bring this line back' : 'Cut this line'}
            aria-label={isCut(s.start, s.end) ? 'Bring this line back' : 'Cut this line'}>{isCut(s.start, s.end) ? '↺' : '✂'}</button>
        </li>
      {/each}
    </ol>
  {:else}
    <p class="p-note">No transcript inside the kept part yet. Add one from the video's Transcript tab, then cut by sentence here.</p>
  {/if}
</div>

<style>
  .stat-row { display: flex; gap: 1rem; font-size: 0.78rem; color: var(--st-muted); flex-wrap: wrap; }
  .stat-row b { color: var(--st-text); font-variant-numeric: tabular-nums; }
  .search { width: 100%; }
  .tx { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; max-height: 380px; overflow: auto; }
  .tx li { display: grid; grid-template-columns: auto 1fr auto; gap: 0.5rem; align-items: start; padding: 0.3rem 0.35rem; border-radius: 6px; font-size: 0.8rem; line-height: 1.4; }
  .tx li:hover { background: var(--st-raise); }
  .tx li.now { background: rgba(110,168,255,.14); }
  .tx li.gone .x { text-decoration: line-through; color: #ff9196; opacity: 0.8; }
  .t { font-size: 0.7rem; color: var(--st-muted); padding-top: 0.1rem; }
  .t:hover { color: var(--st-text); }
  .strike { width: 24px; height: 22px; border-radius: 5px; color: var(--st-muted); font-size: 0.8rem; }
  .strike:hover { background: rgba(255,77,94,.2); color: #fff; }
  .linkish { font-size: 0.78rem; color: var(--st-text); text-decoration: underline dotted; }
</style>
