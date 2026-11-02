<script lang="ts">
  // Music: tracks mixed in under the video as it plays, and the video's own
  // volume. Files are kept in MongoDB; nothing is mixed into the video on
  // Bunny, so a track can be moved, faded or removed at any time.
  import { api } from '$lib/api/client';
  import { durationOf } from '$lib/utils/audio-mix';
  import { clock } from '$lib/utils/transcribe';
  import { playedLength } from '$lib/utils/video-edits';
  import { round, useStudio } from './studio';
  import TrackList from './TrackList.svelte';

  const st = useStudio();
  const { doc, time, ep } = st;
  let pick: HTMLInputElement;
  let busy = false;

  $: vol = $doc.edits.audio.volume;
  $: keptPlays = playedLength($doc.edits, $doc.start, $doc.end);

  async function add(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    (e.target as HTMLInputElement).value = '';
    if (!f) return;
    if (f.size > 12 * 1024 * 1024) { st.say('Music files can be up to 12 MB. Try an MP3 or M4A.', 'bad'); return; }
    busy = true;
    try {
      const duration = await durationOf(f);
      if (!duration) throw new Error("That file couldn't be read as audio.");
      const up = await api.uploadStudioAudio($ep.id, f, f.name, 'music', duration);
      st.mixer.add(up.id, f);
      // From the playhead if it's inside the kept part, otherwise from its start.
      const start = round($time >= $doc.start && $time < $doc.end - 1 ? $time : $doc.start);
      const loop = duration < playedLength($doc.edits, start, $doc.end);
      st.commit(d => {
        d.edits.audio.tracks = [...d.edits.audio.tracks, {
          id: up.id, kind: 'music', name: f.name.replace(/\.[a-z0-9]+$/i, ''), start, duration,
          volume: 35, loop, fade_in: true, fade_out: true,
        }];
      });
      st.say(`Added ${f.name} under the video from ${clock(start)}${loop ? ', looped to the end' : ''}. Save keeps it.`);
    } catch (err: any) { st.say(err.message, 'bad'); }
    finally { busy = false; }
  }
</script>

<div class="p-sec">
  <h3 class="p-h">Music</h3>
  <p class="p-note">A track under the video, starting at the playhead. It runs smoothly over cuts and speed changes, and loops if it's shorter than the {clock(keptPlays)} learners watch.</p>
  <button class="btn sm hot" on:click={() => pick.click()} disabled={busy}>{busy ? 'Adding…' : '♪ Add music…'}</button>
  <input bind:this={pick} type="file" accept="audio/*" hidden on:change={add} />
  <p class="p-note">MP3, M4A, WAV or OGG, up to 12 MB. Use music you have the rights to.</p>
  <TrackList kind="music" />
</div>

<div class="p-sec">
  <h3 class="p-h">Original sound</h3>
  <label class="slider"><span>Video volume<b class="mono">{vol}%</b></span>
    <input type="range" min="0" max="100" value={vol} on:input={e => st.commit(d => { d.edits.audio.volume = +e.currentTarget.value; }, 'own-vol')} /></label>
  <div class="row">
    <button class="btn xs" on:click={() => st.commit(d => { d.edits.audio.volume = 0; })}>Mute it</button>
    <button class="btn xs" on:click={() => st.commit(d => { d.edits.audio.volume = 30; })}>Under the music</button>
    <button class="btn xs" on:click={() => st.commit(d => { d.edits.audio.volume = 100; })}>Full</button>
  </div>
  <p class="p-note">To silence one stretch instead, use Mute in Effects.</p>
</div>

<style>
  .slider { display: grid; gap: 0.25rem; font-size: 0.76rem; }
  .slider span { display: flex; justify-content: space-between; color: var(--st-muted); }
  .slider b { color: var(--st-text); font-weight: 600; }
  .slider input { width: 100%; accent-color: var(--st-hot); }
</style>
