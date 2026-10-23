<script lang="ts">
  // Speed and freeze. Speed applies to a stretch: the marked range, the part
  // under the playhead, or the whole kept video. A freeze holds the frame at
  // the playhead for a few seconds, then plays on.
  import { clock } from '$lib/utils/transcribe';
  import { playedLength, type Effect } from '$lib/utils/video-edits';
  import { addEffect, clockShort, round, useStudio } from './studio';

  const st = useStudio();
  const { doc, time, mark, parts, selected } = st;

  const RATES = [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];
  let rate = 2;
  let scope: 'mark' | 'part' | 'all' = 'part';

  $: marked = $mark.in !== null && $mark.out !== null && Math.abs($mark.out - $mark.in) >= 0.5;
  $: if (marked) scope = 'mark';
  $: part = $parts.find(p => $time >= p.from - 0.05 && $time <= p.to + 0.05) ?? $parts[0];
  $: target = scope === 'mark' && marked
    ? { from: Math.min($mark.in!, $mark.out!), to: Math.max($mark.in!, $mark.out!) }
    : scope === 'part' && part ? { from: part.from, to: part.to } : { from: $doc.start, to: $doc.end };
  $: before = playedLength($doc.edits, target.from, target.to);
  $: speeds = $doc.edits.effects.map((e, i) => ({ e, i })).filter(x => x.e.kind === 'speed');
  $: freezes = $doc.edits.effects.map((e, i) => ({ e, i })).filter(x => x.e.kind === 'freeze');

  /** Speed over the target, replacing any speed already on it. */
  function apply() {
    const { from, to } = target;
    st.commit(d => {
      const out: Effect[] = [];
      for (const e of d.edits.effects) {
        if (e.kind !== 'speed' || e.end <= from || e.start >= to) { out.push(e); continue; }
        // Keep the bits of an earlier speed outside the target.
        if (e.start < from && from - e.start >= 0.5) out.push({ ...e, end: from });
        if (e.end > to && e.end - to >= 0.5) out.push({ ...e, start: to });
      }
      if (rate !== 1) out.push({ kind: 'speed', start: round(from), end: round(to), rate });
      d.edits.effects = out.sort((a, b) => a.start - b.start);
    });
    if (scope === 'mark') mark.set({ in: null, out: null });
    st.say(rate === 1 ? 'Back to normal speed.' : `${rate}× from ${clock(from)} to ${clock(to)}.`);
  }

  function addFreeze() {
    if (freezes.some(x => Math.abs(x.e.start - $time) < 0.5)) { st.say('There is already a freeze here.', 'bad'); return; }
    addEffect(st, 'freeze');
    st.say(`The frame at ${clock($time)} holds for 2 seconds.`);
  }
  const edit = (i: number, patch: Partial<Effect>, key?: string) => st.commit(d => { Object.assign(d.edits.effects[i], patch); }, key);
  const remove = (i: number) => { st.commit(d => { d.edits.effects.splice(i, 1); }); selected.set(null); };
</script>

<div class="p-sec">
  <h3 class="p-h">Speed</h3>
  <div class="seg-ctl" role="radiogroup" aria-label="What to speed up">
    <button role="radio" aria-checked={scope === 'mark'} class:on={scope === 'mark'} disabled={!marked} on:click={() => (scope = 'mark')}
      title={marked ? '' : 'Mark a range first: I and O, or Shift-drag on the timeline'}>Marked range</button>
    <button role="radio" aria-checked={scope === 'part'} class:on={scope === 'part'} on:click={() => (scope = 'part')}>{$parts.length > 1 ? 'This part' : 'Kept video'}</button>
    {#if $parts.length > 1}<button role="radio" aria-checked={scope === 'all'} class:on={scope === 'all'} on:click={() => (scope = 'all')}>All parts</button>{/if}
  </div>
  <div class="rate">
    <b class="big mono">{rate}×</b>
    <input type="range" min="0" max={RATES.length - 1} step="1" value={RATES.indexOf(rate)} on:input={e => (rate = RATES[+e.currentTarget.value])} aria-label="Speed" />
    <div class="ticks">{#each RATES as r}<button class:on={r === rate} on:click={() => (rate = r)}>{r}</button>{/each}</div>
  </div>
  <p class="p-note mono">{clock(target.from)} – {clock(target.to)}: plays {clock(before)} now{rate !== 1 ? `, about ${clock((target.to - target.from) / rate)} at ${rate}×` : ''}.</p>
  <button class="btn sm hot" on:click={apply}>Apply {rate}×</button>
</div>

{#if speeds.length}
  <div class="p-sec">
    <h3 class="p-h">Speed changes</h3>
    <ol class="list">
      {#each speeds as { e, i }}
        <li class:cur={$selected?.kind === 'effect' && $selected.index === i}>
          <div class="li-main">
            <button class="linkish mono" on:click={() => { selected.set({ kind: 'effect', index: i }); st.seek(e.start); }}>{clock(e.start)} – {clock(e.end)}</button>
            <b>{e.rate}×</b>
            <span class="muted">{clockShort((e.end - e.start) / (e.rate ?? 1))} instead of {clockShort(e.end - e.start)}</span>
          </div>
          <div class="row tight">
            {#each [0.5, 1.5, 2, 3, 4] as r}<button class="btn xs" class:hot={e.rate === r} on:click={() => edit(i, { rate: r })}>{r}×</button>{/each}
            <button class="btn xs ghost danger" on:click={() => remove(i)}>Remove</button>
          </div>
        </li>
      {/each}
    </ol>
  </div>
{/if}

<div class="p-sec">
  <h3 class="p-h">Freeze frame</h3>
  <p class="p-note">Hold the picture for a moment: to point at a screen, or let a slide sink in. The sound stops too; music and voice-overs play on.</p>
  <button class="btn sm hot" on:click={addFreeze}>❄ Freeze at {clock($time)}</button>
  {#if freezes.length}
    <ol class="list">
      {#each freezes as { e, i }}
        <li class:cur={$selected?.kind === 'effect' && $selected.index === i}>
          <div class="li-main">
            <button class="linkish mono" on:click={() => { selected.set({ kind: 'effect', index: i }); st.seek(e.start); }}>{clock(e.start)}</button>
            <span class="muted">holds {e.hold ?? 2} s</span>
            <button class="btn xs ghost danger" on:click={() => remove(i)} aria-label="Remove freeze">✕</button>
          </div>
          <input type="range" min="0.5" max="10" step="0.5" value={e.hold ?? 2} on:input={ev => edit(i, { hold: +ev.currentTarget.value }, `hold-${i}`)} aria-label="Hold for" />
          <button class="btn xs ghost" on:click={() => st.playRange(Math.max(0, e.start - 1.5), Math.min(st.length, e.start + 1.5), 'the freeze')}>▶ Preview</button>
        </li>
      {/each}
    </ol>
  {/if}
</div>

<style>
  .rate { display: grid; gap: 0.35rem; justify-items: center; padding: 0.3rem 0; }
  .big { font-size: 1.6rem; font-weight: 800; }
  .rate input { width: 100%; accent-color: var(--st-hot); }
  .ticks { display: flex; justify-content: space-between; width: 100%; }
  .ticks button { font-size: 0.66rem; color: var(--st-muted); padding: 0 0.2rem; font-variant-numeric: tabular-nums; }
  .ticks button.on { color: #fff; font-weight: 800; }
  .linkish { font-size: 0.76rem; color: var(--st-text); text-decoration: underline dotted; }
  .list input[type='range'] { width: 100%; accent-color: var(--st-hot); }
</style>
