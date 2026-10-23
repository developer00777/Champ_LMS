<script lang="ts">
  // AI clipping, in the spirit of OpusClip: the AI reads the transcript and
  // suggests the strongest moments, chapters, an opening hook and cuts.
  // Every suggestion is applied by the admin, undoable, and saved with Save.
  import { api, type StudioHighlight } from '$lib/api/client';
  import { clock } from '$lib/utils/transcribe';
  import { mergeCuts, type Chapter, type Overlay } from '$lib/utils/video-edits';
  import { MIN_PART, clockShort, deadAir, round, useStudio } from './studio';

  const st = useStudio();
  const { doc, ep, tighten, tab } = st;

  $: d = $doc;
  $: segs = $ep.transcript_segments;
  $: hasTranscript = segs.length >= 3;
  let scope: 'kept' | 'all' = 'kept';
  $: range = scope === 'kept' ? { start: d.start, end: d.end } : {};

  let busy = '';
  let highlights: StudioHighlight[] | null = null;
  let chapters: Chapter[] | null = null;
  let hook: { title: string; subtitle: string } | null = null;

  async function run<T>(label: string, fn: () => Promise<T>): Promise<T | null> {
    busy = label;
    try { return await fn(); }
    catch (e: any) { st.say(e.message, 'bad'); return null; }
    finally { busy = ''; }
  }

  const findHighlights = () => run('highlights', async () => {
    const r = await api.studioAi($ep.id, { task: 'highlights', count: 6, ...range });
    highlights = r.suggestions;
    if (!highlights.length) st.say('The AI found no clear standalone moments. Try the whole video.', 'bad');
  });
  const findChapters = () => run('chapters', async () => {
    chapters = (await api.studioAi($ep.id, { task: 'chapters', count: 6, ...range })).suggestions;
  });
  const writeHook = () => run('hook', async () => {
    hook = (await api.studioAi($ep.id, { task: 'hook', ...range })).hook;
  });
  const findTighten = () => run('tighten', async () => {
    tighten.set((await api.studioAi($ep.id, { task: 'tighten', start: d.start, end: d.end })).suggestions);
    tab.set('cuts');
  });

  // ---- applying a highlight -------------------------------------------------
  function keepOnly(h: StudioHighlight) {
    st.commit(dd => { dd.start = h.start; dd.end = Math.max(h.end, h.start + MIN_PART); dd.splits = []; });
    st.say(`Trimmed to "${h.title}". Undo with Ctrl+Z.`);
  }
  function splitOut(h: StudioHighlight) {
    st.commit(dd => {
      for (const x of [h.start, h.end]) {
        const v = round(x);
        if (v > dd.start + MIN_PART && v < dd.end - MIN_PART && !dd.splits.some(s => Math.abs(s - v) < MIN_PART)) dd.splits.push(v);
      }
    });
    st.say(`Split around "${h.title}", so it plays as its own part.`);
  }
  function asChapter(h: StudioHighlight) {
    st.commit(dd => { dd.edits.chapters = [...dd.edits.chapters, { start: h.start, title: h.title }].sort((a, b) => a.start - b.start); });
    st.say(`Chapter "${h.title}" added.`);
  }
  function asTitle(h: StudioHighlight) {
    st.commit(dd => {
      dd.edits.overlays = [...dd.edits.overlays, { start: h.start, end: Math.min(h.end, h.start + 4.5), text: h.title, subtext: null, position: 'lower-third', style: 'label' }];
    });
    st.say(`Title card added at ${clock(h.start)}.`);
  }
  function useChapters() {
    if (!chapters) return;
    const list = chapters;
    st.commit(dd => { dd.edits.chapters = list.map(c => ({ ...c })); });
    st.say(`${list.length} chapters set. Learners see them on the scrub bar.`);
    chapters = null;
  }
  function useHook() {
    if (!hook) return;
    const h = hook;
    st.commit(dd => {
      dd.edits.overlays = [
        ...dd.edits.overlays.filter(o => !(o.style === 'title' && o.start <= dd.start + 0.5)),
        { start: dd.start, end: dd.start + 4.5, text: h.title, subtext: h.subtitle || null, position: 'center', style: 'title' } as Overlay,
      ].sort((a, b) => a.start - b.start);
      dd.edits.look.fade_in = true;
    });
    st.say('Hook added to the opening, with a fade in.');
    hook = null;
  }

  // ---- one-click polish -------------------------------------------------------
  async function polish() {
    const done: string[] = [];
    const ch = await run('polish', () => api.studioAi($ep.id, { task: 'chapters', count: 6, start: d.start, end: d.end }));
    const hk = await run('polish', () => api.studioAi($ep.id, { task: 'hook', start: d.start, end: d.end }));
    const gaps = deadAir(segs, d.start, d.end, 2.5);
    st.commit(dd => {
      if (ch?.suggestions.length) { dd.edits.chapters = ch.suggestions; done.push(`${ch.suggestions.length} chapters`); }
      if (hk) {
        dd.edits.overlays = [
          ...dd.edits.overlays.filter(o => !(o.style === 'title' && o.start <= dd.start + 0.5)),
          { start: dd.start, end: dd.start + 4.5, text: hk.hook.title, subtext: hk.hook.subtitle || null, position: 'center', style: 'title' } as Overlay,
        ].sort((a, b) => a.start - b.start);
        done.push('an opening hook');
      }
      if (gaps.length) {
        dd.edits.cuts = mergeCuts([...dd.edits.cuts, ...gaps]);
        done.push(`${gaps.length} silence${gaps.length === 1 ? '' : 's'} cut (${clockShort(gaps.reduce((a, g) => a + g.end - g.start, 0))})`);
      }
      dd.edits.captions = { ...dd.edits.captions, preset: 'pop', default_on: true };
      dd.edits.look = { ...dd.edits.look, fade_in: true, fade_out: true };
      done.push('word-by-word captions on by default', 'fades');
    });
    st.say(`Polished: ${done.join(', ')}. Undo with Ctrl+Z.`);
  }

  const tone = (s: number) => (s >= 80 ? 'hi' : s >= 60 ? 'mid' : 'lo');
</script>

<div class="p-sec hero">
  <h3 class="p-h">✦ AI editor</h3>
  <p class="p-note">The AI reads this video's transcript and suggests edits. Nothing changes until you apply a suggestion, and every one can be undone.</p>
  {#if !hasTranscript}
    <p class="p-bad">This video has no transcript yet. Add or generate one from its Transcript tab, then come back.</p>
  {/if}
  <div class="seg-ctl" role="radiogroup" aria-label="What the AI reads">
    <button role="radio" aria-checked={scope === 'kept'} class:on={scope === 'kept'} on:click={() => (scope = 'kept')}>Kept part</button>
    <button role="radio" aria-checked={scope === 'all'} class:on={scope === 'all'} on:click={() => (scope = 'all')}>Whole video</button>
  </div>
  <button class="btn ai wide" on:click={polish} disabled={!!busy || !hasTranscript}>
    {busy === 'polish' ? 'Polishing…' : '✦ One-click polish'}
  </button>
  <p class="p-note">Chapters, an opening hook, silences cut, word-by-word captions and fades, in one step.</p>
</div>

<div class="p-sec">
  <div class="p-hrow"><h3 class="p-h">Highlights</h3>
    <button class="btn sm ai" on:click={findHighlights} disabled={!!busy || !hasTranscript}>{busy === 'highlights' ? 'Finding…' : highlights ? 'Find again' : 'Find highlights'}</button></div>
  <p class="p-note">The strongest standalone moments, scored for how useful they are on their own. Keep one as the whole episode, or split it out as its own part.</p>
  {#if highlights?.length}
    <ol class="hl">
      {#each highlights as h}
        <li>
          <span class="score {tone(h.score)}" style="--p:{h.score}%"><b>{h.score}</b></span>
          <div class="hl-b">
            <b>{h.title}</b>
            <span class="mono muted">{clock(h.start)} – {clock(h.end)} · {clockShort(h.end - h.start)}</span>
            <span class="why">{h.reason}</span>
            <div class="row tight">
              <button class="btn xs" on:click={() => st.playRange(h.start, h.end, `"${h.title}"`)}>▶ Play</button>
              <button class="btn xs" on:click={() => keepOnly(h)} title="Trim this episode to just this moment">Keep only this</button>
              <button class="btn xs" on:click={() => splitOut(h)} title="Split at its start and end so it is its own part">Split it out</button>
              <button class="btn xs ghost" on:click={() => asChapter(h)}>Chapter</button>
              <button class="btn xs ghost" on:click={() => asTitle(h)}>Title card</button>
            </div>
          </div>
        </li>
      {/each}
    </ol>
  {/if}
</div>

<div class="p-sec">
  <div class="p-hrow"><h3 class="p-h">Chapters</h3>
    <button class="btn sm ai" on:click={findChapters} disabled={!!busy || !hasTranscript}>{busy === 'chapters' ? 'Writing…' : 'Suggest chapters'}</button></div>
  {#if chapters?.length}
    <ol class="list">
      {#each chapters as c}
        <li><div class="li-main"><button class="linkish mono" on:click={() => st.seek(c.start)}>{clock(c.start)}</button><span>{c.title}</span></div></li>
      {/each}
    </ol>
    <div class="row"><button class="btn sm hot" on:click={useChapters}>Use these {chapters.length} chapters</button><button class="btn sm ghost" on:click={() => (chapters = null)}>Dismiss</button></div>
    {#if d.edits.chapters.length}<p class="p-note">Replaces the {d.edits.chapters.length} chapter{d.edits.chapters.length === 1 ? '' : 's'} there now.</p>{/if}
  {/if}
</div>

<div class="p-sec">
  <div class="p-hrow"><h3 class="p-h">Opening hook</h3>
    <button class="btn sm ai" on:click={writeHook} disabled={!!busy || !hasTranscript}>{busy === 'hook' ? 'Writing…' : 'Write a hook'}</button></div>
  <p class="p-note">A title over the first seconds that says what the learner will be able to do.</p>
  {#if hook}
    <label class="field">Title<input type="text" bind:value={hook.title} maxlength="120" /></label>
    <label class="field">Subtitle<input type="text" bind:value={hook.subtitle} maxlength="160" /></label>
    <div class="row"><button class="btn sm hot" on:click={useHook}>Add to the opening</button><button class="btn sm ghost" on:click={() => (hook = null)}>Dismiss</button></div>
  {/if}
</div>

<div class="p-sec">
  <div class="p-hrow"><h3 class="p-h">Tighten</h3>
    <button class="btn sm ai" on:click={findTighten} disabled={!!busy || !hasTranscript}>{busy === 'tighten' ? 'Reading…' : 'Find cuts'}</button></div>
  <p class="p-note">False starts, repeats and setup chatter. The suggestions open in Cuts.</p>
</div>

<style>
  .hero { background: linear-gradient(160deg, rgba(180,139,255,.16), rgba(110,168,255,.08)); border-color: rgba(180,139,255,.35); }
  .wide { width: 100%; justify-content: center; height: 38px; font-size: 0.86rem; }
  .p-hrow { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
  .hl { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.5rem; }
  .hl li { display: grid; grid-template-columns: 44px 1fr; gap: 0.6rem; padding: 0.6rem; border: 1px solid var(--st-line); border-radius: 10px; background: var(--st-raise); }
  .hl-b { display: grid; gap: 0.25rem; min-width: 0; }
  .hl-b b { font-size: 0.86rem; }
  .why { font-size: 0.76rem; color: var(--st-muted); line-height: 1.4; }
  .score { width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; background: conic-gradient(var(--c) var(--p), rgba(255,255,255,.1) 0); }
  .score b { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--st-panel); font-size: 0.82rem; font-variant-numeric: tabular-nums; }
  .score.hi { --c: #4fd17f; } .score.mid { --c: #ffd23f; } .score.lo { --c: #ff8a8f; }
  .linkish { font-size: 0.78rem; color: var(--st-text); text-decoration: underline dotted; }
</style>
