<script lang="ts">
  // Stickers: emoji placed on the picture for a few seconds. They start in
  // the middle at the playhead; drag one on the preview to place it.
  import { clock } from '$lib/utils/transcribe';
  import type { Overlay, OverlayAnim } from '$lib/utils/video-edits';
  import { round, useStudio } from './studio';

  const st = useStudio();
  const { doc, time, selected } = st;

  const SETS: [string, string[]][] = [
    ['Reactions', ['👍', '👏', '🎉', '🔥', '💯', '😮', '🤔', '😂', '❤️', '🙌', '😎', '🤯']],
    ['Point at it', ['👉', '👈', '👆', '👇', '⬅️', '➡️', '⬆️', '⬇️', '🔴', '⭕', '✅', '❌']],
    ['Learning', ['💡', '📌', '⭐', '⚠️', '❓', '❗', '📈', '📉', '🎯', '🧠', '📝', '🏆']],
    ['Work', ['💼', '📞', '📧', '🤝', '💰', '📊', '🗓️', '⏱️', '🔒', '🔑', '🚀', '🛠️']],
  ];
  const SIZES = [['s', 'S'], ['m', 'M'], ['l', 'L'], ['xl', 'XL']] as const;
  const ANIMS: [OverlayAnim, string][] = [['pop', 'Pop'], ['bounce', 'Bounce'], ['fade', 'Fade'], ['none', 'None']];

  function add(emoji: string) {
    const start = round($time);
    const o: Overlay = {
      start, end: round(Math.min(st.length, start + 3)), text: emoji, subtext: null, position: 'free', style: 'sticker',
      size: 'l', anim: 'pop', color: null, x: 50, y: 45,
    };
    let index = 0;
    st.commit(d => { d.edits.overlays = [...d.edits.overlays, o].sort((a, b) => a.start - b.start); index = d.edits.overlays.indexOf(o); });
    selected.set({ kind: 'overlay', index });
  }
  const edit = (i: number, patch: Partial<Overlay>) => st.commit(d => { Object.assign(d.edits.overlays[i], patch); });

  $: stickers = $doc.edits.overlays.map((o, i) => ({ o, i })).filter(x => x.o.style === 'sticker');
  $: sel = $selected?.kind === 'overlay' ? $selected.index : -1;
</script>

<div class="p-sec">
  <h3 class="p-h">Stickers</h3>
  <p class="p-note">Tap one to put it on the picture at {clock($time)} for 3 seconds. Drag it on the preview to place it.</p>
  {#each SETS as [name, list]}
    <span class="set">{name}</span>
    <div class="grid">
      {#each list as e}<button class="emo" on:click={() => add(e)} aria-label="Add {e}">{e}</button>{/each}
    </div>
  {/each}
</div>

{#if stickers.length}
  <div class="p-sec">
    <h3 class="p-h">On this video</h3>
    <ol class="list">
      {#each stickers as { o, i }}
        <!-- svelte-ignore a11y-click-events-have-key-events a11y-no-noninteractive-element-interactions -->
        <li class:cur={sel === i} on:click={() => selected.set({ kind: 'overlay', index: i })}>
          <div class="li-main">
            <span class="big">{o.text}</span>
            <button class="linkish mono" on:click|stopPropagation={() => { selected.set({ kind: 'overlay', index: i }); st.seek(o.start + 0.05); }}>{clock(o.start)} – {clock(o.end)}</button>
            <button class="btn xs ghost danger" on:click|stopPropagation={() => { st.commit(d => { d.edits.overlays.splice(i, 1); }); selected.set(null); }} aria-label="Remove sticker">✕</button>
          </div>
          {#if sel === i}
            <div class="seg-ctl small" role="radiogroup" aria-label="Size">
              {#each SIZES as [v, l]}<button role="radio" aria-checked={(o.size ?? 'm') === v} class:on={(o.size ?? 'm') === v} on:click={() => edit(i, { size: v })}>{l}</button>{/each}
            </div>
            <div class="seg-ctl small" role="radiogroup" aria-label="Entrance">
              {#each ANIMS as [v, l]}<button role="radio" aria-checked={(o.anim ?? 'pop') === v} class:on={(o.anim ?? 'pop') === v} on:click={() => edit(i, { anim: v })}>{l}</button>{/each}
            </div>
            <div class="row tight">
              <button class="btn xs" on:click={() => edit(i, { start: Math.min(round($time), o.end - 0.5) })}>Start at playhead</button>
              <button class="btn xs" on:click={() => edit(i, { end: Math.max(round($time), o.start + 0.5) })}>End at playhead</button>
            </div>
          {/if}
        </li>
      {/each}
    </ol>
  </div>
{/if}

<style>
  .set { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--st-muted); }
  .grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 0.3rem; }
  .emo { aspect-ratio: 1; border-radius: 9px; background: var(--st-raise); font-size: 1.35rem; display: grid; place-items: center; transition: transform 120ms; }
  .emo:hover { transform: scale(1.12); background: #2a2d38; }
  .big { font-size: 1.3rem; line-height: 1; }
  .linkish { font-size: 0.76rem; color: var(--st-text); text-decoration: underline dotted; margin-right: auto; }
</style>
