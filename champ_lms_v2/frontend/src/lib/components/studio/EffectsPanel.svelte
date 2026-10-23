<script lang="ts">
  // Effects: stretches of the video played differently without cutting them.
  // Zoom punches in for emphasis, speed hurries a slow demo along, mute
  // silences a stretch, blur hides something on screen (a name, a password,
  // a customer's details). Each sits on the timeline's Effects lane.
  import { tick } from 'svelte';
  import { api } from '$lib/api/client';
  import { clock } from '$lib/utils/transcribe';
  import { cutSecondsBetween, type Effect, type EffectKind } from '$lib/utils/video-edits';
  import { EFFECT_NAMES, addEffect, clockShort, deadAir, round, useStudio } from './studio';

  const st = useStudio();
  const { doc, time, selected, mark, ep } = st;
  let listEl: HTMLOListElement;
  let busy = '';

  const KINDS: { kind: EffectKind; label: string; about: string }[] = [
    { kind: 'zoom', label: 'Zoom in', about: 'Punch in on a point' },
    { kind: 'speed', label: 'Speed up', about: 'Hurry a slow stretch' },
    { kind: 'mute', label: 'Mute', about: 'Silence the sound' },
    { kind: 'blur', label: 'Blur', about: 'Hide part of the screen' },
  ];
  const RATES = [0.5, 0.75, 1.25, 1.5, 2, 3, 4];

  $: d = $doc;
  $: sel = $selected?.kind === 'effect' ? $selected.index : -1;
  $: marked = $mark.in !== null && $mark.out !== null && Math.abs($mark.out - $mark.in) >= 0.5;
  $: if (sel >= 0 && listEl) listEl.querySelector(`li[data-i="${sel}"]`)?.scrollIntoView({ block: 'nearest' });

  async function add(kind: EffectKind) {
    const i = addEffect(st, kind);
    if (i < 0) return;
    if (kind === 'blur') st.say('Drag the box on the preview over what to hide, and its corner to size it.');
    else if (kind === 'zoom') st.say('Drag the frame on the preview to aim the zoom.');
    await tick();
  }

  function edit(i: number, patch: Partial<Effect>, key?: string) {
    st.commit(dd => { Object.assign(dd.edits.effects[i], patch); }, key);
  }
  function remove(i: number) {
    st.commit(dd => { dd.edits.effects.splice(i, 1); });
    selected.set(null);
  }
  function setStart(i: number, e: Effect) { edit(i, { start: Math.min(round($time), e.end - 0.5) }); }
  function setEnd(i: number, e: Effect) { edit(i, { end: Math.max(round($time), e.start + 0.5) }); }
  function pick(i: number) { selected.set({ kind: 'effect', index: i }); }

  // Pauses sped up instead of cut: the rhythm stays, the wait goes.
  function speedPauses() {
    const gaps = deadAir(d.segments, d.start, d.end, 2)
      .filter(g => cutSecondsBetween(d.edits.cuts, g.start, g.end) < 0.1)
      .filter(g => !d.edits.effects.some(e => e.kind === 'speed' && e.start < g.end && e.end > g.start));
    if (!gaps.length) { st.say('No pauses of 2 seconds or more left to speed up.', 'bad'); return; }
    st.commit(dd => {
      dd.edits.effects = [...dd.edits.effects, ...gaps.map(g => ({ kind: 'speed' as const, start: g.start, end: g.end, rate: 3 }))]
        .sort((a, b) => a.start - b.start);
    });
    st.say(`${gaps.length} pause${gaps.length === 1 ? '' : 's'} play at 3× now (${clockShort(gaps.reduce((a, g) => a + g.end - g.start, 0))} in all).`);
  }

  async function aiZooms() {
    busy = 'zooms';
    try {
      const r = await api.studioAi($ep.id, { task: 'zooms', count: 6, start: d.start, end: d.end });
      if (!r.suggestions.length) { st.say('The AI found no moments it was sure about.', 'bad'); return; }
      st.commit(dd => {
        const fresh = r.suggestions
          .filter(s => !dd.edits.effects.some(e => e.kind === 'zoom' && e.start < s.end && e.end > s.start))
          .map(s => ({ kind: 'zoom' as const, start: s.start, end: Math.max(s.end, s.start + 2), scale: 1.25, x: 50, y: 40 }));
        dd.edits.effects = [...dd.edits.effects, ...fresh].sort((a, b) => a.start - b.start);
      });
      st.say(`${r.suggestions.length} punch-in zooms on key moments. Aim any of them on the preview.`);
    } catch (e: any) { st.say(e.message, 'bad'); }
    finally { busy = ''; }
  }

  const summary = (e: Effect) =>
    e.kind === 'zoom' ? `${(e.scale ?? 1.4).toFixed(2)}×`
    : e.kind === 'speed' ? `${e.rate ?? 2}×`
    : e.kind === 'blur' ? (e.mode === 'black' ? 'black box' : 'blurred box')
    : 'no sound';
</script>

<div class="p-sec">
  <h3 class="p-h">Add an effect</h3>
  <p class="p-note">
    {#if marked}Goes over the marked range, {clock(Math.min($mark.in ?? 0, $mark.out ?? 0))} – {clock(Math.max($mark.in ?? 0, $mark.out ?? 0))}.
    {:else}Starts at the playhead. Mark a range first (<kbd>I</kbd> and <kbd>O</kbd>, or <kbd>Shift</kbd>-drag on the timeline) to cover exactly that.{/if}
  </p>
  <div class="kinds">
    {#each KINDS as k}
      <button class="kind k-{k.kind}" on:click={() => add(k.kind)}><b>{k.label}</b><span>{k.about}</span></button>
    {/each}
  </div>
</div>

<div class="p-sec">
  <h3 class="p-h">Quick effects</h3>
  <div class="row">
    <button class="btn sm ai" on:click={aiZooms} disabled={!!busy || $ep.transcript_segments.length < 3}>{busy === 'zooms' ? 'Reading…' : '✦ Zoom in on key moments'}</button>
    <button class="btn sm" on:click={speedPauses} disabled={!d.segments.length}>Speed up pauses</button>
  </div>
  <p class="p-note">The AI picks the points a learner mustn't miss and punches in on each. Speeding up pauses keeps them, at 3×, where cutting would jump.</p>
</div>

{#if d.edits.effects.length}
  <div class="p-sec">
    <h3 class="p-h">On this video</h3>
    <ol class="efl" bind:this={listEl}>
      {#each d.edits.effects as e, i}
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
        <li data-i={i} class="k-{e.kind}" class:cur={sel === i} on:click={() => pick(i)}>
          <div class="eh">
            <span class="dot"></span>
            <b>{EFFECT_NAMES[e.kind]}</b>
            <span class="muted">{summary(e)}</span>
            <button class="linkish mono" on:click|stopPropagation={() => { pick(i); st.seek(e.start); }}>{clock(e.start)} – {clock(e.end)}</button>
            <button class="btn xs ghost danger" on:click|stopPropagation={() => remove(i)} aria-label="Remove effect">✕</button>
          </div>
          {#if sel === i}
            {#if e.kind === 'zoom'}
              <label class="slider"><span>Zoom<b class="mono">{(e.scale ?? 1.4).toFixed(2)}×</b></span>
                <input type="range" min="1.05" max="3" step="0.05" value={e.scale ?? 1.4} on:input={ev => edit(i, { scale: +ev.currentTarget.value }, `ef-scale-${i}`)} /></label>
              <p class="p-note">Eases in and out. Drag the blue frame on the preview to aim it.</p>
            {:else if e.kind === 'speed'}
              <div class="seg-ctl small" role="radiogroup" aria-label="Speed">
                {#each RATES as r}<button role="radio" aria-checked={(e.rate ?? 2) === r} class:on={(e.rate ?? 2) === r} on:click|stopPropagation={() => edit(i, { rate: r })}>{r}×</button>{/each}
              </div>
              <p class="p-note">Plays for {clockShort((e.end - e.start) / (e.rate ?? 2))} instead of {clockShort(e.end - e.start)}. Learners' own speed multiplies it.</p>
            {:else if e.kind === 'blur'}
              <div class="seg-ctl small" role="radiogroup" aria-label="How it hides">
                <button role="radio" aria-checked={e.mode !== 'black'} class:on={e.mode !== 'black'} on:click|stopPropagation={() => edit(i, { mode: 'blur' })}>Blur</button>
                <button role="radio" aria-checked={e.mode === 'black'} class:on={e.mode === 'black'} on:click|stopPropagation={() => edit(i, { mode: 'black' })}>Black box</button>
              </div>
              <p class="p-note">Drag the box on the preview; its corner sizes it. A black box hides text a blur might leave readable.</p>
            {:else}
              <p class="p-note">The picture plays on in silence. Learners can't unmute it.</p>
            {/if}
            <div class="row tight">
              <button class="btn xs" on:click|stopPropagation={() => setStart(i, e)}>Start at playhead</button>
              <button class="btn xs" on:click|stopPropagation={() => setEnd(i, e)}>End at playhead</button>
              <button class="btn xs ghost" on:click|stopPropagation={() => st.playRange(Math.max(0, e.start - 1.5), Math.min(st.length, e.end + 1), EFFECT_NAMES[e.kind].toLowerCase())}>▶ Preview</button>
            </div>
          {/if}
        </li>
      {/each}
    </ol>
  </div>
{/if}

<style>
  .kinds { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
  .kind { display: grid; gap: 0.15rem; text-align: left; padding: 0.6rem 0.65rem; border-radius: 10px; border: 1px solid var(--st-line); background: var(--st-raise); color: var(--st-text); border-left: 3px solid var(--k); }
  .kind:hover { border-color: var(--k); }
  .kind b { font-size: 0.82rem; }
  .kind span { font-size: 0.7rem; color: var(--st-muted); }
  .k-zoom { --k: #6ea8ff; } .k-speed { --k: #ffb057; } .k-mute { --k: #b48bff; } .k-blur { --k: #7ef0a8; }
  .efl { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.4rem; }
  .efl li { display: grid; gap: 0.45rem; padding: 0.5rem 0.55rem; border: 1px solid var(--st-line); border-radius: 10px; background: var(--st-raise); cursor: pointer; }
  .efl li.cur { border-color: var(--k); cursor: default; }
  .eh { display: flex; gap: 0.45rem; align-items: center; font-size: 0.8rem; }
  .eh .linkish { margin-left: auto; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--k); flex: none; }
  .linkish { font-size: 0.74rem; color: var(--st-text); text-decoration: underline dotted; }
  .slider { display: grid; gap: 0.25rem; font-size: 0.76rem; }
  .slider span { display: flex; justify-content: space-between; color: var(--st-muted); }
  .slider b { color: var(--st-text); font-weight: 600; }
  .slider input { width: 100%; accent-color: var(--st-hot); }
</style>
