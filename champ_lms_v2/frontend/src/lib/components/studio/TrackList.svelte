<script lang="ts">
  // The music or voice tracks on the video, for Music and Voice-over.
  import { clock } from '$lib/utils/transcribe';
  import type { AudioTrack } from '$lib/utils/video-edits';
  import { clockShort, round, useStudio } from './studio';

  export let kind: 'music' | 'voice';

  const st = useStudio();
  const { doc, time } = st;

  $: list = $doc.edits.audio.tracks.map((tr, i) => ({ tr, i })).filter(x => x.tr.kind === kind);
  const edit = (i: number, patch: Partial<AudioTrack>, key?: string) => st.commit(d => { Object.assign(d.edits.audio.tracks[i], patch); }, key);
  const remove = (i: number) => st.commit(d => { d.edits.audio.tracks.splice(i, 1); });
</script>

{#if list.length}
  <ol class="tracks">
    {#each list as { tr, i } (tr.id)}
      <li class="k-{tr.kind}">
        <div class="th">
          <span class="ic">{tr.kind === 'music' ? '♪' : '🎙'}</span>
          <input type="text" value={tr.name} maxlength="120" on:input={e => edit(i, { name: e.currentTarget.value }, `tr-name-${i}`)} aria-label="Track name" />
          <button class="btn xs ghost danger" on:click={() => remove(i)} aria-label="Remove track">✕</button>
        </div>
        <div class="row tight">
          <button class="linkish mono" on:click={() => st.seek(tr.start)}>starts {clock(tr.start)}</button>
          <span class="muted">· {clockShort(tr.duration)}{tr.loop ? ', looped' : ''}</span>
        </div>
        <label class="slider"><span>Volume<b class="mono">{tr.volume}%</b></span>
          <input type="range" min="0" max="100" value={tr.volume} on:input={e => edit(i, { volume: +e.currentTarget.value }, `tr-vol-${i}`)} /></label>
        <div class="row tight">
          <button class="btn xs" on:click={() => edit(i, { start: round($time) })}>Start at playhead</button>
          {#if tr.kind === 'music'}<button class="btn xs" class:hot={tr.loop} on:click={() => edit(i, { loop: !tr.loop })} aria-pressed={tr.loop}>Loop</button>{/if}
          <button class="btn xs" class:hot={tr.fade_in} on:click={() => edit(i, { fade_in: !tr.fade_in })} aria-pressed={tr.fade_in}>Fade in</button>
          <button class="btn xs" class:hot={tr.fade_out} on:click={() => edit(i, { fade_out: !tr.fade_out })} aria-pressed={tr.fade_out}>Fade out</button>
          <button class="btn xs ghost" on:click={() => st.playRange(tr.start, Math.min($doc.end, tr.start + Math.min(tr.duration, 20)), tr.name)}>▶ Play</button>
        </div>
      </li>
    {/each}
  </ol>
{/if}

<style>
  .tracks { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.45rem; }
  .tracks li { display: grid; gap: 0.4rem; padding: 0.55rem; border: 1px solid var(--st-line); border-radius: 10px; background: var(--st-raise); border-left: 3px solid var(--k); }
  .k-music { --k: #2ee6a6; } .k-voice { --k: #ff8fb1; }
  .th { display: grid; grid-template-columns: auto 1fr auto; gap: 0.4rem; align-items: center; }
  .ic { width: 26px; height: 26px; border-radius: 7px; display: grid; place-items: center; background: var(--st-deep); color: var(--k); }
  .linkish { font-size: 0.74rem; color: var(--st-text); text-decoration: underline dotted; }
  .slider { display: grid; gap: 0.2rem; font-size: 0.74rem; }
  .slider span { display: flex; justify-content: space-between; color: var(--st-muted); }
  .slider b { color: var(--st-text); font-weight: 600; }
  .slider input { width: 100%; accent-color: var(--k); }
</style>
