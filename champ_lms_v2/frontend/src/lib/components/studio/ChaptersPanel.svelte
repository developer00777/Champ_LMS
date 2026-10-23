<script lang="ts">
  import { tick } from 'svelte';
  import { api } from '$lib/api/client';
  import { clock, lineAt } from '$lib/utils/transcribe';
  import { chapterIndexAt } from '$lib/utils/video-edits';
  import { round, useStudio } from './studio';

  const st = useStudio();
  const { doc, time, selected, ep } = st;
  let listEl: HTMLOListElement;
  let busy = false;

  async function add() {
    const at = round($time);
    if ($doc.edits.chapters.some(c => Math.abs(c.start - at) < 1)) { st.say('There is already a chapter here.', 'bad'); return; }
    // Name it after what is being said, so it starts as something to edit.
    const said = lineAt($doc.segments, at).split(/\s+/).slice(0, 5).join(' ');
    let index = 0;
    st.commit(d => {
      const c = { start: at, title: said || `Chapter ${d.edits.chapters.length + 1}` };
      d.edits.chapters = [...d.edits.chapters, c].sort((a, b) => a.start - b.start);
      index = d.edits.chapters.indexOf(c);
    });
    selected.set({ kind: 'chapter', index });
    await tick();
    listEl?.querySelector<HTMLInputElement>(`li[data-i="${index}"] input`)?.select();
  }

  async function suggest() {
    busy = true;
    try {
      const r = await api.studioAi($ep.id, { task: 'chapters', count: 6, start: $doc.start, end: $doc.end });
      if (!r.suggestions.length) { st.say('The AI had no chapters to suggest.', 'bad'); return; }
      st.commit(d => { d.edits.chapters = r.suggestions; });
      st.say(`${r.suggestions.length} chapters from the AI. Rename or drag any of them.`);
    } catch (e: any) { st.say(e.message, 'bad'); }
    finally { busy = false; }
  }

  $: cur = chapterIndexAt($doc.edits.chapters, $time);
  $: sel = $selected?.kind === 'chapter' ? $selected.index : -1;
  $: firstLate = $doc.edits.chapters.length > 0 && $doc.edits.chapters[0].start > $doc.start + 1;
</script>

<div class="p-sec">
  <h3 class="p-h">Chapters</h3>
  <p class="p-note">Learners see chapters on the scrub bar and can jump between them. Drag a flag on the timeline to move it.</p>
  <div class="row">
    <button class="btn sm hot" on:click={add}>+ Chapter at playhead</button>
    <button class="btn sm ai" on:click={suggest} disabled={busy || $ep.transcript_segments.length < 3}>{busy ? 'Writing…' : '✦ Suggest with AI'}</button>
  </div>
  {#if firstLate}<p class="p-note">Tip: start the first chapter where the video starts, so the opening has a name too.</p>{/if}
</div>

{#if $doc.edits.chapters.length}
  <div class="p-sec">
    <ol class="list" bind:this={listEl}>
      {#each $doc.edits.chapters as c, i}
        <li data-i={i} class:cur={sel === i || (sel < 0 && cur === i)}>
          <div class="chrow">
            <button class="linkish mono" on:click={() => { selected.set({ kind: 'chapter', index: i }); st.seek(c.start); }}>{clock(c.start)}</button>
            <input type="text" value={c.title} maxlength="120" on:focus={() => selected.set({ kind: 'chapter', index: i })}
              on:input={e => st.commit(d => { d.edits.chapters[i].title = e.currentTarget.value; }, `ch-${i}`)} aria-label="Chapter title" />
            <button class="btn xs" on:click={() => st.commit(d => { d.edits.chapters[i].start = round($time); d.edits.chapters.sort((a, b) => a.start - b.start); })} title="Move to the playhead">⇥</button>
            <button class="btn xs ghost danger" on:click={() => { st.commit(d => { d.edits.chapters.splice(i, 1); }); selected.set(null); }} aria-label="Remove chapter">✕</button>
          </div>
        </li>
      {/each}
    </ol>
    <button class="btn sm ghost danger" on:click={() => st.commit(d => { d.edits.chapters = []; })}>Remove all chapters</button>
  </div>
{/if}

<style>
  .chrow { display: grid; grid-template-columns: auto 1fr auto auto; gap: 0.4rem; align-items: center; width: 100%; }
  .linkish { font-size: 0.76rem; color: var(--st-text); text-decoration: underline dotted; }
</style>
