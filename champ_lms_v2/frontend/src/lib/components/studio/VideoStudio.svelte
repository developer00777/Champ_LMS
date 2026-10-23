<script lang="ts">
  // The video studio: one editor for any video, in a canvas course or a
  // directly uploaded (classic) module. Trim, split, cut, chapters, text,
  // caption style, look, brand and thumbnail, with AI suggestions from the
  // transcript. Nothing on Bunny changes: Save stores the edits, and the
  // learner's player applies them as the video plays.
  import { onMount } from 'svelte';
  import { api, type StudioEpisode } from '$lib/api/client';
  import StudioEditor from './StudioEditor.svelte';

  export let episodeId: string;
  // The file itself, when this session uploaded it: instant, no stream needed.
  export let localFile: File | null = null;
  export let onClose: () => void;
  // After a save or a join: the course or module should reload.
  export let onSaved: (ep: StudioEpisode) => void = () => {};

  let ep: StudioEpisode | null = null;
  let error = '';

  onMount(async () => {
    try {
      const e = await api.studio(episodeId);
      if (e.status !== 'ready' || !e.source_duration_seconds) {
        error = 'The studio opens once the video has finished processing on Bunny.';
        return;
      }
      ep = e;
    } catch (e: any) { error = e.message; }
  });

  function onKey(e: KeyboardEvent) { if (!ep && e.key === 'Escape') onClose(); }
</script>

<svelte:window on:keydown={onKey} />

{#if ep}
  <StudioEditor initial={ep} {localFile} {onClose} {onSaved} />
{:else}
  <div class="loading" role="dialog" aria-modal="true" aria-label="Video studio">
    {#if error}
      <p>{error}</p>
      <button on:click={onClose}>Close</button>
    {:else}
      <span class="ring"></span><p>Opening the studio…</p>
    {/if}
  </div>
{/if}

<style>
  .loading { position: fixed; inset: 0; z-index: 400; background: #0e0f13; color: #9a9ba8; display: grid; place-items: center; align-content: center; gap: 0.8rem; }
  .loading button { height: 32px; padding: 0 0.9rem; border-radius: 8px; background: #1e2028; color: #ececf1; font-weight: 600; }
  .ring { width: 36px; height: 36px; border-radius: 50%; border: 3px solid rgba(255,255,255,.15); border-top-color: #fff; animation: spin .9s linear infinite; }
  @keyframes spin { to { rotate: 360deg; } }
</style>
