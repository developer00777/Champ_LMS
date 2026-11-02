<script lang="ts">
  // Transitions: what plays where a cut joins two stretches, as playback
  // jumps over it. One style for every cut, previewed on any of them.
  import { clock } from '$lib/utils/transcribe';
  import type { Transition } from '$lib/utils/video-edits';
  import { useStudio } from './studio';

  const st = useStudio();
  const { doc } = st;

  const STYLES: [Transition, string, string][] = [
    ['none', 'None', 'A straight cut.'],
    ['fade', 'Fade', 'Dips through black.'],
    ['flash', 'Flash', 'A quick white flash.'],
    ['blur', 'Blur', 'Blurs out and back in.'],
    ['zoom', 'Zoom', 'Punches in across the cut.'],
    ['shake', 'Shake', 'A short jolt.'],
  ];
  $: cur = $doc.edits.look.transition;
  $: cuts = $doc.edits.cuts.filter(c => c.end > $doc.start && c.start < $doc.end);
  const set = (v: Transition) => st.commit(d => { d.edits.look = { ...d.edits.look, transition: v }; });
</script>

<div class="p-sec">
  <h3 class="p-h">Transition at cuts</h3>
  <div class="grid">
    {#each STYLES as [v, l, about]}
      <button class="card tr-{v}" class:on={cur === v} on:click={() => set(v)} aria-pressed={cur === v} title={about}>
        <span class="demo"><i class="a"></i><i class="b"></i><i class="fx"></i></span>
        <b>{l}</b>
      </button>
    {/each}
  </div>
  <p class="p-note">{STYLES.find(s => s[0] === cur)?.[2]} Splits are separate episodes, so transitions play at cuts inside a part.</p>
</div>

<div class="p-sec">
  <h3 class="p-h">Cuts in this video</h3>
  {#if cuts.length}
    <ol class="list">
      {#each cuts as c, n}
        <li><div class="li-main">
          <span class="mono">{clock(c.start)} → {clock(c.end)}</span>
          <button class="btn xs" on:click={() => st.playRange(Math.max(0, c.start - 2), Math.min(st.length, c.end + 2), `cut ${n + 1}`)}>▶ Preview</button>
        </div></li>
      {/each}
    </ol>
  {:else}
    <p class="p-note">No cuts yet. Cut a stretch (Cuts, or I, O then C) and the transition plays where it joins.</p>
  {/if}
</div>

<style>
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.45rem; }
  .card { display: grid; gap: 0.3rem; padding: 0.4rem; border-radius: 10px; border: 1px solid var(--st-line); background: var(--st-raise); color: var(--st-text); font-size: 0.72rem; }
  .card.on { border-color: var(--st-hot); box-shadow: 0 0 0 1px var(--st-hot); }
  .demo { position: relative; aspect-ratio: 16/9; border-radius: 6px; overflow: hidden; display: block; }
  .demo i { position: absolute; inset: 0; }
  .demo .a { background: linear-gradient(135deg, #3a6ea5, #6fb1d6); }
  .demo .b { background: linear-gradient(135deg, #f3b562, #e0603e); animation: swap 2.4s steps(1) infinite; }
  @keyframes swap { 0%, 49% { opacity: 0; } 50%, 100% { opacity: 1; } }
  .tr-fade .fx { background: #000; animation: dip 2.4s ease-in-out infinite; }
  .tr-flash .fx { background: #fff; animation: dip 2.4s ease-in-out infinite; }
  .tr-blur .fx { backdrop-filter: blur(6px); animation: dip 2.4s ease-in-out infinite; }
  .tr-zoom .demo { animation: punch 2.4s ease-in-out infinite; }
  .tr-shake .demo { animation: jolt 2.4s linear infinite; }
  @keyframes dip { 0%, 40%, 62%, 100% { opacity: 0; } 50% { opacity: 1; } }
  @keyframes punch { 0%, 42%, 62%, 100% { scale: 1; } 50% { scale: 1.12; } }
  @keyframes jolt { 0%, 47%, 56%, 100% { translate: 0 0; } 49% { translate: -3px 2px; } 51% { translate: 3px -2px; } 53% { translate: -2px -1px; } }
</style>
