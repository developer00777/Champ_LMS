<script lang="ts">
  import { onDestroy } from 'svelte';
  import { api } from '$lib/api/client';
  import { clock } from '$lib/utils/transcribe';
  import { useStudio } from './studio';
  import Thumb from '$lib/components/Thumb.svelte';

  const st = useStudio();
  const { doc, time, ep } = st;

  let shot: { url: string; blob: Blob; at: number } | null = null;
  let saving = false;
  onDestroy(() => { if (shot) URL.revokeObjectURL(shot.url); });

  // The frame under the playhead, with the look applied, at up to 1280 wide.
  async function grab() {
    const v = st.video();
    if (!v || !v.videoWidth) { st.say('The preview has no picture yet.', 'bad'); return; }
    const look = $doc.edits.look;
    const w = Math.min(1280, v.videoWidth), h = Math.round((w * v.videoHeight) / v.videoWidth);
    const canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.filter = `brightness(${look.brightness}%) contrast(${look.contrast}%) saturate(${look.saturation}%)`;
    // The zoomed view: the same part of the frame the player shows.
    const sw = v.videoWidth / look.zoom, sh = v.videoHeight / look.zoom;
    const sx = (look.focus_x / 100) * (v.videoWidth - sw), sy = (look.focus_y / 100) * (v.videoHeight - sh);
    try {
      ctx.drawImage(v, sx, sy, sw, sh, 0, 0, w, h);
      const blob = await new Promise<Blob | null>(res => canvas.toBlob(res, 'image/jpeg', 0.9));
      if (!blob) throw new Error('empty');
      if (shot) URL.revokeObjectURL(shot.url);
      shot = { url: URL.createObjectURL(blob), blob, at: $time };
    } catch {
      st.say("This browser won't let the page read the video's pixels. Use the thumbnail studio's upload instead.", 'bad');
    }
  }

  async function save() {
    if (!shot) return;
    saving = true;
    try {
      const s = await api.saveThumbnail('episode', $ep.id, shot.blob, 'upload');
      ep.update(e => ({ ...e, ...s }));
      st.say('Thumbnail saved.');
    } catch (e: any) { st.say(e.message, 'bad'); }
    finally { saving = false; }
  }
</script>

<div class="p-sec">
  <h3 class="p-h">Thumbnail from a frame</h3>
  <p class="p-note">Find a frame that says what the video is about, then grab it. Colour and zoom from Look are applied.</p>
  <button class="btn sm hot" on:click={grab}>Grab the frame at {clock($time)}</button>
  {#if shot}
    <img class="shot" src={shot.url} alt="Frame at {clock(shot.at)}" />
    <div class="row">
      <button class="btn sm hot" on:click={save} disabled={saving}>{saving ? 'Saving…' : 'Use as thumbnail'}</button>
      <button class="btn sm ghost" on:click={() => { if (shot) URL.revokeObjectURL(shot.url); shot = null; }}>Discard</button>
    </div>
  {/if}
</div>

<div class="p-sec">
  <h3 class="p-h">Current thumbnail</h3>
  <div class="cur">{#if $ep.thumbnail_url}<Thumb src={$ep.thumbnail_url} eager />{:else}<span class="p-note">None yet</span>{/if}</div>
  <p class="p-note">Saved straight away, separately from the video edits.</p>
</div>

<style>
  .shot { width: 100%; border-radius: 8px; border: 1px solid var(--st-line); display: block; }
  /* Thumb fills its positioned parent; without this it fills the whole studio. */
  .cur { position: relative; aspect-ratio: 16/9; border-radius: 8px; overflow: hidden; background: var(--st-deep); display: grid; place-items: center; border: 1px solid var(--st-line); }
</style>
