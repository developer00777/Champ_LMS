<script lang="ts">
  // Voice-over: record from the microphone while the preview plays, from the
  // playhead. The recording becomes a voice track starting where it began,
  // kept in MongoDB and mixed in as learners watch.
  import { onDestroy } from 'svelte';
  import { get } from 'svelte/store';
  import { api } from '$lib/api/client';
  import { clock } from '$lib/utils/transcribe';
  import { round, useStudio } from './studio';
  import TrackList from './TrackList.svelte';

  const st = useStudio();
  const { doc, time, ep, quiet } = st;

  let hush = true;
  let rec: MediaRecorder | null = null;
  let stream: MediaStream | null = null;
  let chunks: Blob[] = [];
  let startT = 0;
  let startedAt = 0;
  let elapsed = 0;
  let ticker: ReturnType<typeof setInterval> | null = null;
  let busy = false;
  let level = 0;
  let meter: { ctx: AudioContext; an: AnalyserNode } | null = null;

  async function start() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch {
      st.say("The microphone isn't available. Allow it in the browser's address bar, then try again.", 'bad');
      return;
    }
    const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'].find(t => MediaRecorder.isTypeSupported(t));
    rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    chunks = [];
    rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = finish;
    // A level meter, so it's clear the mic is picking something up.
    try {
      const ctx = new AudioContext();
      const an = ctx.createAnalyser();
      an.fftSize = 256;
      ctx.createMediaStreamSource(stream).connect(an);
      meter = { ctx, an };
    } catch { meter = null; }
    startT = round(get(time));
    startedAt = performance.now();
    elapsed = 0;
    quiet.set(hush);
    rec.start(250);
    st.play();
    ticker = setInterval(() => {
      elapsed = (performance.now() - startedAt) / 1000;
      if (meter) {
        const buf = new Uint8Array(meter.an.fftSize);
        meter.an.getByteTimeDomainData(buf);
        level = Math.min(1, Math.max(...buf.map(v => Math.abs(v - 128))) / 64);
      }
      // Past the end of what plays: nothing left to talk over.
      if (get(time) >= get(doc).end - 0.05) stop();
    }, 100);
  }

  function stop() {
    if (!rec || rec.state === 'inactive') return;
    rec.stop();
    st.pause();
  }

  async function finish() {
    const duration = (performance.now() - startedAt) / 1000;
    cleanup();
    const blob = new Blob(chunks, { type: (rec?.mimeType || 'audio/webm').split(';')[0] });
    rec = null;
    if (duration < 0.5 || !blob.size) { st.say('That recording was too short to keep.', 'bad'); return; }
    busy = true;
    try {
      const n = get(doc).edits.audio.tracks.filter(t => t.kind === 'voice').length + 1;
      const ext = blob.type.includes('ogg') ? 'ogg' : blob.type.includes('mp4') ? 'm4a' : 'webm';
      const up = await api.uploadStudioAudio(get(ep).id, blob, `voice-over-${n}.${ext}`, 'voice', round(duration));
      st.mixer.add(up.id, blob);
      st.commit(d => {
        d.edits.audio.tracks = [...d.edits.audio.tracks, {
          id: up.id, kind: 'voice', name: `Voice-over ${n}`, start: startT, duration: round(duration),
          volume: 100, loop: false, fade_in: false, fade_out: false,
        }];
      });
      st.say(`Voice-over ${n} added at ${clock(startT)} (${clock(duration)}). Save keeps it.`);
    } catch (e: any) { st.say(e.message, 'bad'); }
    finally { busy = false; }
  }

  function cleanup() {
    if (ticker) clearInterval(ticker);
    ticker = null;
    stream?.getTracks().forEach(t => t.stop());
    stream = null;
    meter?.ctx.close().catch(() => {});
    meter = null;
    level = 0;
    quiet.set(false);
  }

  onDestroy(() => {
    if (rec && rec.state !== 'inactive') { rec.onstop = null; rec.stop(); }
    cleanup();
  });

  $: recording = !!rec && rec.state === 'recording';
</script>

<div class="p-sec">
  <h3 class="p-h">Record a voice-over</h3>
  <p class="p-note">Talk over the video as it plays from the playhead ({clock($time)}). Stop when you're done; it lands on the timeline where you started.</p>
  {#if recording}
    <div class="live">
      <span class="dot"></span>
      <b class="mono">{clock(elapsed)}</b>
      <span class="lvl"><i style="width:{level * 100}%"></i></span>
      <button class="btn sm hot" on:click={stop}>■ Stop</button>
    </div>
  {:else}
    <button class="btn sm hot" on:click={start} disabled={busy}>{busy ? 'Saving the recording…' : '● Record'}</button>
    <label class="toggle"><input type="checkbox" bind:checked={hush} />
      <span><b>Hush the video while recording</b><span>So the speakers don't leak into the mic. Headphones work too.</span></span></label>
  {/if}
</div>

<div class="p-sec">
  <h3 class="p-h">Voice-overs</h3>
  {#if $doc.edits.audio.tracks.some(t => t.kind === 'voice')}
    <TrackList kind="voice" />
    <p class="p-note">Lower the video's own sound under a voice-over in Music → Original sound, or mute that stretch in Effects.</p>
  {:else}
    <p class="p-note">None yet.</p>
  {/if}
</div>

<style>
  .live { display: grid; grid-template-columns: auto auto 1fr auto; gap: 0.6rem; align-items: center; padding: 0.5rem 0.6rem; border-radius: 10px; background: rgba(255,59,69,.12); border: 1px solid rgba(255,59,69,.4); }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: #ff3b45; animation: blink 1s steps(2) infinite; }
  @keyframes blink { 50% { opacity: 0.2; } }
  .lvl { height: 6px; border-radius: 4px; background: var(--st-deep); overflow: hidden; }
  .lvl i { display: block; height: 100%; background: #2ee6a6; transition: width 90ms; }
  .toggle { display: grid; grid-template-columns: auto 1fr; gap: 0.6rem; align-items: start; font-size: 0.8rem; cursor: pointer; }
  .toggle input { margin-top: 0.2rem; accent-color: var(--st-hot); }
  .toggle span { display: grid; gap: 0.15rem; }
  .toggle span span { color: var(--st-muted); font-size: 0.74rem; }
</style>
