<script lang="ts">
  import { tick } from 'svelte';
  import { clock } from '$lib/utils/transcribe';
  import type { Overlay, OverlayAnim, OverlayPosition, OverlayStyle } from '$lib/utils/video-edits';
  import { round, useStudio } from './studio';

  const st = useStudio();
  const { doc, time, selected } = st;

  const STYLES: { id: OverlayStyle; name: string; pos: OverlayPosition; text: string }[] = [
    { id: 'title', name: 'Title', pos: 'center', text: 'Your title here' },
    { id: 'callout', name: 'Callout', pos: 'top', text: 'Key point' },
    { id: 'label', name: 'Lower third', pos: 'lower-third', text: 'Name or topic' },
    { id: 'quote', name: 'Quote', pos: 'center', text: 'Something worth remembering' },
  ];
  const POSITIONS = [['top', 'Top'], ['center', 'Centre'], ['lower-third', 'Lower third'], ['bottom', 'Bottom']] as const;
  const SIZES = [['s', 'Small'], ['m', 'Medium'], ['l', 'Large']] as const;
  const ANIMS: [OverlayAnim, string][] = [['rise', 'Rise'], ['fade', 'Fade'], ['pop', 'Pop'], ['type', 'Type'], ['none', 'None']];
  const COLORS = ['#ffd23f', '#ff3b45', '#e50914', '#6ea8ff', '#7ef0a8', '#ffffff'];

  let listEl: HTMLOListElement;

  async function add(s: (typeof STYLES)[number]) {
    const start = round($time);
    const o: Overlay = {
      start, end: round(Math.min(st.length, start + 4)), text: s.text, subtext: null, position: s.pos, style: s.id,
      size: 'm', anim: 'rise', color: null,
    };
    let index = 0;
    st.commit(d => {
      d.edits.overlays = [...d.edits.overlays, o].sort((a, b) => a.start - b.start);
      index = d.edits.overlays.indexOf(o);
    });
    selected.set({ kind: 'overlay', index });
    await tick();
    listEl?.querySelector<HTMLInputElement>(`li[data-i="${index}"] input`)?.select();
  }

  function edit(i: number, patch: Partial<Overlay>, key?: string) {
    st.commit(d => { Object.assign(d.edits.overlays[i], patch); }, key);
  }

  // Templates can't hold type casts in Svelte 4.
  const setStyle = (i: number, v: string) => edit(i, { style: v as OverlayStyle });

  // A copy right after it, for a second callout in the same look.
  function duplicate(i: number) {
    let index = 0;
    st.commit(d => {
      const o = d.edits.overlays[i];
      const len = o.end - o.start;
      const copy = { ...o, start: round(Math.min(st.length - len, o.end)), end: round(Math.min(st.length, o.end + len)) };
      d.edits.overlays = [...d.edits.overlays, copy].sort((a, b) => a.start - b.start);
      index = d.edits.overlays.indexOf(copy);
    });
    selected.set({ kind: 'overlay', index });
  }

  $: sel = $selected?.kind === 'overlay' ? $selected.index : -1;
  $: if (sel >= 0 && listEl) listEl.querySelector(`li[data-i="${sel}"]`)?.scrollIntoView({ block: 'nearest' });
</script>

<div class="p-sec">
  <h3 class="p-h">Add text</h3>
  <p class="p-note">Text appears over the video at the playhead for 4 seconds. Drag it on the preview to place it anywhere, and its block on the timeline to change when and how long.</p>
  <div class="styles">
    {#each STYLES as s}
      <button class="sty st-{s.id}" on:click={() => add(s)}><span class="demo">{s.name}</span></button>
    {/each}
  </div>
</div>

{#if $doc.edits.overlays.some(o => o.style !== 'sticker')}
  <div class="p-sec">
    <h3 class="p-h">On this video</h3>
    <ol class="ovl" bind:this={listEl}>
      {#each $doc.edits.overlays as o, i}{#if o.style !== 'sticker'}
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
        <li data-i={i} class:cur={sel === i} on:click={() => selected.set({ kind: 'overlay', index: i })}>
          <div class="ovh">
            <select value={o.style} on:change={e => setStyle(i, e.currentTarget.value)} aria-label="Style">
              {#each STYLES as s}<option value={s.id}>{s.name}</option>{/each}
            </select>
            <button class="linkish mono" on:click|stopPropagation={() => st.seek(o.start)}>{clock(o.start)} – {clock(o.end)}</button>
            <button class="btn xs ghost danger" on:click|stopPropagation={() => { st.commit(d => { d.edits.overlays.splice(i, 1); }); selected.set(null); }}>Remove</button>
          </div>
          <input type="text" value={o.text} maxlength="200" placeholder="Text" on:input={e => edit(i, { text: e.currentTarget.value }, `ov-text-${i}`)} />
          <input type="text" value={o.subtext ?? ''} maxlength="200" placeholder="Second line (optional)" on:input={e => edit(i, { subtext: e.currentTarget.value || null }, `ov-sub-${i}`)} />
          <div class="seg-ctl small" role="radiogroup" aria-label="Position">
            {#each POSITIONS as [v, l]}
              <button role="radio" aria-checked={o.position === v} class:on={o.position === v} on:click={() => edit(i, { position: v })}>{l}</button>
            {/each}
            {#if o.position === 'free'}<button role="radio" aria-checked="true" class="on" title="Placed by dragging it on the preview">Dragged</button>{/if}
          </div>
          {#if sel === i}
            <div class="opts">
              <span>Size</span>
              <div class="seg-ctl small" role="radiogroup" aria-label="Size">
                {#each SIZES as [v, l]}<button role="radio" aria-checked={(o.size ?? 'm') === v} class:on={(o.size ?? 'm') === v} on:click={() => edit(i, { size: v })}>{l}</button>{/each}
              </div>
              <span>Entrance</span>
              <div class="seg-ctl small" role="radiogroup" aria-label="Entrance">
                {#each ANIMS as [v, l]}<button role="radio" aria-checked={(o.anim ?? 'rise') === v} class:on={(o.anim ?? 'rise') === v} on:click={() => edit(i, { anim: v })}>{l}</button>{/each}
              </div>
              <span>Colour</span>
              <div class="swatches">
                <button class="sw auto" class:on={!o.color} on:click={() => edit(i, { color: null })} title="The style's own colour">A</button>
                {#each COLORS as c}<button class="sw" class:on={o.color === c} style="background:{c}" on:click={() => edit(i, { color: c })} aria-label="Colour {c}"></button>{/each}
                <input type="color" value={o.color ?? '#ffd23f'} on:input={e => edit(i, { color: e.currentTarget.value }, `ov-color-${i}`)} aria-label="Any colour" />
              </div>
            </div>
          {/if}
          <div class="row tight">
            <button class="btn xs" on:click={() => edit(i, { start: Math.min(round($time), o.end - 0.5) })}>Start at playhead</button>
            <button class="btn xs" on:click={() => edit(i, { end: Math.max(round($time), o.start + 0.5) })}>End at playhead</button>
            <button class="btn xs ghost" on:click={() => st.playRange(Math.max(0, o.start - 1), o.end + 0.5, 'the text')}>▶ Preview</button>
            <button class="btn xs ghost" on:click|stopPropagation={() => duplicate(i)}>Duplicate</button>
          </div>
        </li>
      {/if}{/each}
    </ol>
  </div>
{/if}

<style>
  .styles { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
  .sty { height: 58px; border-radius: 10px; border: 1px solid var(--st-line); display: grid; place-items: center;
    background: linear-gradient(135deg, #3a4a5c, #1d2633 60%, #45392d); }
  .sty:hover { border-color: var(--st-text); }
  .demo { font-size: 0.8rem; font-weight: 800; }
  .st-title .demo { color: #fff; font-size: 1rem; text-shadow: 0 2px 8px rgba(0,0,0,.6); }
  .st-callout .demo { background: #ffd23f; color: #111; padding: 0.2em 0.6em; border-radius: 7px; }
  .st-label .demo { background: rgba(10,10,14,.85); color: #fff; padding: 0.2em 0.6em; border-radius: 5px; border-left: 3px solid #e50914; justify-self: start; margin-left: 10px; }
  .st-quote .demo { background: #fff; color: #15151a; font-style: italic; font-weight: 600; padding: 0.2em 0.6em; border-radius: 8px; }
  .ovl { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.5rem; }
  .ovl li { display: grid; gap: 0.4rem; padding: 0.55rem; border: 1px solid var(--st-line); border-radius: 10px; background: var(--st-raise); }
  .ovl li.cur { border-color: #ffd23f; }
  .ovh { display: flex; gap: 0.5rem; align-items: center; }
  .ovh select { flex: 0 0 auto; }
  .ovh .linkish { margin-right: auto; }
  .linkish { font-size: 0.76rem; color: var(--st-text); text-decoration: underline dotted; }
  .opts { display: grid; grid-template-columns: auto 1fr; gap: 0.35rem 0.6rem; align-items: center; font-size: 0.72rem; color: var(--st-muted); font-weight: 600; }
  .swatches { display: flex; gap: 0.3rem; align-items: center; flex-wrap: wrap; }
  .sw { width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--st-line); }
  .sw.on { border-color: #fff; box-shadow: 0 0 0 2px var(--st-hot); }
  .sw.auto { background: var(--st-deep); color: var(--st-muted); font-size: 0.62rem; font-weight: 800; }
  .swatches input[type='color'] { width: 28px; height: 24px; padding: 0; border: 1px solid var(--st-line); border-radius: 6px; background: none; }
</style>
