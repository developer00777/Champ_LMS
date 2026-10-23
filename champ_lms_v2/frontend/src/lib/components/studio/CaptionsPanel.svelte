<script lang="ts">
  // Captions: how they look (preset, font, colours, placement), and what they
  // say. Fixing a word, find and replace and filler clean-up edit the
  // transcript lines in the doc, so they undo like any edit and Save stores
  // them as the transcript. A video without one can get it here: transcribed
  // in the browser from the file, or read from a .vtt or .srt file.
  import { api, type TranscriptSegment } from '$lib/api/client';
  import { autoTranscribe, clock, parseCaptions } from '$lib/utils/transcribe';
  import { stripFillers, type CaptionFont, type CaptionPreset, type CaptionStyle } from '$lib/utils/video-edits';
  import { useStudio } from './studio';

  export let localFile: File | null = null;

  const st = useStudio();
  const { doc, ep, ccOn, time } = st;
  // Captions show in the preview while this panel is open.
  ccOn.set(true);

  const PRESETS: { id: CaptionPreset; name: string; about: string }[] = [
    { id: 'classic', name: 'Classic', about: 'A quiet dark box. Easy on long videos.' },
    { id: 'pop', name: 'Pop', about: 'The word being said lights up, OpusClip style.' },
    { id: 'karaoke', name: 'Karaoke', about: 'Words fill in as they are said.' },
    { id: 'bold', name: 'Bold', about: 'Big outlined capitals that read on any picture.' },
    { id: 'minimal', name: 'Minimal', about: 'Just the text, with a soft shadow.' },
  ];
  const FONTS: [CaptionFont, string][] = [['sans', 'Sans'], ['display', 'Heavy'], ['rounded', 'Rounded'], ['serif', 'Serif'], ['mono', 'Mono']];
  const POSITIONS = [['bottom', 'Bottom'], ['middle', 'Middle'], ['top', 'Top']] as const;
  const SIZES = [['s', 'Small'], ['m', 'Medium'], ['l', 'Large']] as const;
  const SWATCHES = ['#ffffff', '#ffd23f', '#7ef0a8', '#6ea8ff', '#ff8fb1', '#ff3b45'];

  $: c = $doc.edits.captions;
  const set = (patch: Partial<CaptionStyle>, key?: string) => st.commit(d => { d.edits.captions = { ...d.edits.captions, ...patch }; }, key);

  // ---- the words ---------------------------------------------------------------
  $: segs = $doc.segments;
  $: kept = segs.map((s, i) => ({ s, i })).filter(({ s }) => s.end > $doc.start && s.start < $doc.end);
  let query = '';
  let replaceWith = '';
  $: q = query.trim().toLowerCase();
  $: shown = q ? kept.filter(({ s }) => s.text.toLowerCase().includes(q)) : kept;
  $: nowLine = kept.find(({ s }) => $time >= s.start && $time < Math.max(s.end, s.start + 0.5))?.i ?? -1;
  $: changedLines = segs.filter((s, i) => s.text !== $ep.transcript_segments[i]?.text).length;

  function editLine(i: number, text: string) {
    st.commit(d => { d.segments[i].text = text; }, `cap-${i}`);
  }

  function escapeRe(x: string) { return x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function replaceAll() {
    if (!query.trim()) return;
    const re = new RegExp(escapeRe(query.trim()), 'gi');
    let n = 0;
    st.commit(d => {
      for (const s of d.segments) {
        const next = s.text.replace(re, () => { n++; return replaceWith; });
        s.text = next.replace(/\s{2,}/g, ' ').trim();
      }
    });
    st.say(n ? `Replaced ${n} time${n === 1 ? '' : 's'}.` : 'Nothing to replace.', n ? 'ok' : 'bad');
  }

  function cleanFillers() {
    let n = 0;
    st.commit(d => {
      for (const s of d.segments) {
        const next = stripFillers(s.text);
        if (next !== s.text && next) { s.text = next; n++; }
      }
    });
    st.say(n ? `Cleaned ${n} line${n === 1 ? '' : 's'}: um, uh and repeated words are gone from the captions.` : 'No filler words found.', n ? 'ok' : 'bad');
  }

  // ---- where they come from ------------------------------------------------------
  let busy = '';
  let progress = '';
  let filePick: HTMLInputElement;
  let capPick: HTMLInputElement;

  async function transcribe(file: File) {
    busy = 'transcribe';
    progress = 'Reading the sound…';
    try {
      const out = await autoTranscribe($ep.id, file, (done, total) => (progress = `Transcribing ${done} of ${total}…`));
      st.adoptSegments(out);
      st.say(`Transcribed: ${out.length} lines. Captions, AI and cutting by transcript use them now.`);
    } catch (e: any) { st.say(e.message, 'bad'); }
    finally { busy = ''; progress = ''; }
  }
  function onVideoFile(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    (e.target as HTMLInputElement).value = '';
    if (f) transcribe(f);
  }
  async function onCaptionFile(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    (e.target as HTMLInputElement).value = '';
    if (!f) return;
    busy = 'file';
    try {
      const lines = parseCaptions(await f.text()).sort((a, b) => a.start - b.start);
      if (!lines.length) throw new Error('No captions found in that file. Use a .vtt or .srt file.');
      // A caption file covers the whole video, so it is timed from its start.
      await api.saveTranscript($ep.id, lines, 'manual', 'source');
      st.adoptSegments(lines);
      st.say(`Read ${lines.length} caption lines from ${f.name}.`);
    } catch (err: any) { st.say(err.message, 'bad'); }
    finally { busy = ''; }
  }

  // The kept part's captions as an .srt, in the time learners hear them.
  function srtTime(x: number) {
    const ms = Math.max(0, Math.round(x * 1000));
    const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000), s = Math.floor((ms % 60000) / 1000);
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(ms % 1000).padStart(3, '0')}`;
  }
  function exportSrt() {
    const from = $doc.start;
    const body = kept.map(({ s }, n) => `${n + 1}\n${srtTime(s.start - from)} --> ${srtTime(Math.max(s.end, s.start + 0.5) - from)}\n${s.text}\n`).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([body], { type: 'application/x-subrip' }));
    a.download = `${$ep.title.replace(/[^\w\- ]+/g, '').trim() || 'captions'}.srt`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
</script>

{#if !segs.length}
  <div class="p-sec warn">
    <h3 class="p-h">No captions yet</h3>
    <p class="p-note">Captions are the transcript, timed to the video. Make one here; captions, the AI tools and cutting by transcript all use it.</p>
    {#if busy === 'transcribe'}
      <p class="p-note"><span class="spin"></span> {progress}</p>
    {:else}
      <div class="row">
        {#if localFile}<button class="btn sm hot" on:click={() => localFile && transcribe(localFile)} disabled={!!busy}>Transcribe {localFile.name}</button>{/if}
        <button class="btn sm {localFile ? '' : 'hot'}" on:click={() => filePick.click()} disabled={!!busy}>Transcribe from the video file…</button>
        <button class="btn sm" on:click={() => capPick.click()} disabled={!!busy}>Upload .vtt or .srt…</button>
      </div>
      <p class="p-note">Transcribing reads the sound in this browser, so pick the same video file that was uploaded. Keep this tab open until it finishes.</p>
    {/if}
  </div>
{/if}
<input bind:this={filePick} type="file" accept="video/*,audio/*" hidden on:change={onVideoFile} />
<input bind:this={capPick} type="file" accept=".vtt,.srt,text/vtt" hidden on:change={onCaptionFile} />

<div class="p-sec">
  <h3 class="p-h">Caption style</h3>
  <div class="presets">
    {#each PRESETS as p}
      <button class="preset" class:on={c.preset === p.id} on:click={() => set({ preset: p.id })} aria-pressed={c.preset === p.id}>
        <span class="sample pre-{p.id}" style="--cc:{c.color}; --hi:{c.highlight}">
          {#if p.id === 'pop'}<span>Close</span> <span class="now">every</span> <span>call</span>
          {:else if p.id === 'karaoke'}<span class="said">Close</span> <span class="now">every</span> <span class="dim">call</span>
          {:else if p.id === 'classic'}<span class="box">Close every call</span>
          {:else}Close every call{/if}
        </span>
        <b>{p.name}</b>
        <span class="about">{p.about}</span>
      </button>
    {/each}
  </div>
</div>

<div class="p-sec">
  <h3 class="p-h">Font and colour</h3>
  <div class="field">Font
    <div class="seg-ctl small" role="radiogroup" aria-label="Caption font">
      {#each FONTS as [v, l]}
        <button role="radio" aria-checked={c.font === v} class:on={c.font === v} class="f-{v}" on:click={() => set({ font: v })}>{l}</button>
      {/each}
    </div>
  </div>
  <div class="field">Text colour
    <div class="swatches">
      {#each SWATCHES as sw}<button class="sw" class:on={c.color === sw} style="background:{sw}" on:click={() => set({ color: sw })} aria-label="Text colour {sw}"></button>{/each}
      <input type="color" value={c.color} on:input={e => set({ color: e.currentTarget.value }, 'cap-color')} aria-label="Any text colour" />
    </div>
  </div>
  {#if c.preset === 'pop' || c.preset === 'karaoke'}
    <div class="field">Word being said
      <div class="swatches">
        {#each SWATCHES.slice(1) as sw}<button class="sw" class:on={c.highlight === sw} style="background:{sw}" on:click={() => set({ highlight: sw })} aria-label="Highlight colour {sw}"></button>{/each}
        <input type="color" value={c.highlight} on:input={e => set({ highlight: e.currentTarget.value }, 'cap-hi')} aria-label="Any highlight colour" />
      </div>
    </div>
  {/if}
  <label class="toggle">
    <input type="checkbox" checked={c.uppercase} on:change={e => set({ uppercase: e.currentTarget.checked })} />
    <span><b>All capitals</b></span>
  </label>
</div>

<div class="p-sec">
  <h3 class="p-h">Placement</h3>
  <div class="field">Position
    <div class="seg-ctl" role="radiogroup" aria-label="Caption position">
      {#each POSITIONS as [v, l]}
        <button role="radio" aria-checked={c.position === v} class:on={c.position === v} on:click={() => set({ position: v })}>{l}</button>
      {/each}
    </div>
  </div>
  <div class="field">Size
    <div class="seg-ctl" role="radiogroup" aria-label="Caption size">
      {#each SIZES as [v, l]}
        <button role="radio" aria-checked={c.size === v} class:on={c.size === v} on:click={() => set({ size: v })}>{l}</button>
      {/each}
    </div>
  </div>
  <label class="toggle">
    <input type="checkbox" checked={c.default_on} on:change={e => set({ default_on: e.currentTarget.checked })} />
    <span><b>Captions on by default</b><span>Learners who never touched CC see captions from the start. Their own choice still wins.</span></span>
  </label>
</div>

{#if segs.length}
  <div class="p-sec">
    <div class="p-hrow">
      <h3 class="p-h">Edit the words</h3>
      {#if changedLines}<span class="pill">{changedLines} changed · saved with Save</span>{/if}
    </div>
    <p class="p-note">Fix a misheard word right in its line. Only the text changes; the timing stays.</p>
    <div class="fr">
      <input type="search" placeholder="Find…" bind:value={query} aria-label="Find in the captions" />
      <input type="text" placeholder="Replace with…" bind:value={replaceWith} aria-label="Replace with" />
      <button class="btn sm" on:click={replaceAll} disabled={!query.trim()}>Replace all</button>
    </div>
    <div class="row">
      <button class="btn sm" on:click={cleanFillers}>Remove filler words</button>
      <button class="btn sm ghost" on:click={exportSrt} disabled={!kept.length}>Download .srt</button>
      <button class="btn sm ghost" on:click={() => capPick.click()} disabled={!!busy}>Replace from a file…</button>
    </div>
    <ol class="lines">
      {#each shown as { s, i } (i)}
        <li class:now={i === nowLine}>
          <button class="t mono" on:click={() => st.seek(s.start + 0.01)}>{clock(s.start)}</button>
          <input type="text" value={s.text} on:input={e => editLine(i, e.currentTarget.value)} on:focus={() => st.seek(s.start + 0.01)} aria-label="Caption at {clock(s.start)}" />
        </li>
      {/each}
      {#if !shown.length}<li class="none">{q ? 'No line has that.' : 'No captions inside the kept part.'}</li>{/if}
    </ol>
  </div>
{/if}

<style>
  .warn { border-color: rgba(245,197,24,.45); }
  .p-hrow { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
  .pill { font-size: 0.68rem; font-weight: 700; padding: 2px 7px; border-radius: 99px; background: rgba(110,168,255,.18); color: #cfe0ff; }
  .presets { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; }
  .preset { display: grid; gap: 0.3rem; text-align: left; padding: 0.5rem; border-radius: 10px; border: 1px solid var(--st-line); background: var(--st-raise); color: var(--st-text); }
  .preset.on { border-color: var(--st-hot); box-shadow: 0 0 0 1px var(--st-hot); }
  .preset b { font-size: 0.8rem; }
  .about { font-size: 0.7rem; color: var(--st-muted); line-height: 1.35; }
  .sample { display: grid; place-items: center; height: 54px; border-radius: 7px; font-size: 0.8rem; text-align: center;
    background: linear-gradient(135deg, #3a4a5c, #1d2633 60%, #45392d); color: var(--cc, #fff); }
  .box { background: rgba(8,8,12,.75); padding: 0.15em 0.55em; border-radius: 5px; font-weight: 500; font-size: 0.74rem; }
  .pre-bold, .pre-pop, .pre-karaoke { font-weight: 900; -webkit-text-stroke: 0.05em #000; paint-order: stroke fill; display: block; line-height: 54px; }
  .pre-bold { text-transform: uppercase; font-size: 0.78rem; }
  .pre-pop .now { background: var(--hi, #ffd23f); color: #111; -webkit-text-stroke: 0; padding: 0 0.15em; border-radius: 0.2em; display: inline-block; transform: rotate(-2deg) scale(1.08); }
  .pre-karaoke .dim { color: color-mix(in srgb, var(--cc, #fff) 50%, #6b6b75); }
  .pre-karaoke .now { color: var(--hi, #7ef0a8); }
  .pre-minimal { text-shadow: 0 1px 3px #000; }
  .f-display { font-family: 'Arial Black', Impact, sans-serif; }
  .f-serif { font-family: Georgia, serif; }
  .f-rounded { font-family: ui-rounded, 'Nunito', 'Arial Rounded MT Bold', sans-serif; }
  .f-mono { font-family: ui-monospace, Consolas, monospace; }
  .swatches { display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; }
  .sw { width: 24px; height: 24px; border-radius: 50%; border: 2px solid var(--st-line); }
  .sw.on { border-color: #fff; box-shadow: 0 0 0 2px var(--st-hot); }
  .swatches input[type='color'] { width: 30px; height: 26px; padding: 0; border: 1px solid var(--st-line); border-radius: 6px; background: none; }
  .toggle { display: grid; grid-template-columns: auto 1fr; gap: 0.6rem; align-items: start; font-size: 0.8rem; cursor: pointer; }
  .toggle input { margin-top: 0.2rem; accent-color: var(--st-hot); }
  .toggle span { display: grid; gap: 0.15rem; }
  .toggle span span { color: var(--st-muted); font-size: 0.74rem; line-height: 1.4; }
  .fr { display: grid; grid-template-columns: 1fr 1fr auto; gap: 0.35rem; }
  .lines { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; max-height: 420px; overflow: auto; }
  .lines li { display: grid; grid-template-columns: auto 1fr; gap: 0.4rem; align-items: center; padding: 0.15rem 0.25rem; border-radius: 6px; }
  .lines li.now { background: rgba(110,168,255,.14); }
  .lines li.none { font-size: 0.76rem; color: var(--st-muted); padding: 0.4rem; }
  .lines li input { width: 100%; background: transparent; border-color: transparent; }
  .lines li input:hover, .lines li input:focus { border-color: var(--st-line); background: var(--st-deep); }
  .t { font-size: 0.7rem; color: var(--st-muted); }
  .t:hover { color: var(--st-text); }
  .spin { display: inline-block; width: 12px; height: 12px; border-radius: 50%; border: 2px solid rgba(255,255,255,.2); border-top-color: #fff; animation: spin .9s linear infinite; vertical-align: -2px; }
  @keyframes spin { to { rotate: 360deg; } }
</style>
