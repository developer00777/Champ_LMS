<script lang="ts">
  // A thumbnail preview with buttons that open the thumbnail studio.
  //
  // Saved mode (ownerId set): changes are saved by the studio and reported
  // through onChange. Pick mode (no ownerId yet): the made image is kept in
  // `picked` for the page to save once the episode exists.
  import type { ThumbnailOwner, ThumbnailState } from '$lib/api/client';
  import type { PickedThumbnail } from '$lib/thumbnails/designer';
  import ThumbnailStudio from './ThumbnailStudio.svelte';

  export let kind: ThumbnailOwner;
  export let ownerId: string | null = null;
  export let title = '';
  export let kicker = '';
  export let context = '';
  export let state: ThumbnailState | null = null;
  export let onChange: (s: ThumbnailState) => void = () => {};
  export let picked: PickedThumbnail | null = null;
  // Shown, dimmed, when there is no thumbnail yet: what learners see instead.
  export let fallbackUrl: string | null = null;
  export let fallbackNote = '';

  let open = false;

  $: url = ownerId ? state?.thumbnail_url ?? null : picked?.url ?? null;
  $: source = ownerId ? state?.thumbnail_source ?? null : picked?.source ?? null;
  $: badge = source === 'ai' ? 'AI image' : source === 'text' ? 'Text design' : source === 'upload' ? 'Uploaded' : url ? 'Earlier upload' : '';
  $: shown = url ?? fallbackUrl;
</script>

<div class="tf">
  <button type="button" class="tf-prev" class:fallback={!url && !!fallbackUrl} on:click={() => (open = true)}
    style={shown ? `background-image:url(${shown})` : ''} aria-label={url ? 'Change thumbnail' : 'Create a thumbnail'}>
    {#if !shown}
      <span class="tf-empty"><b>No thumbnail yet</b><small>Design one with text, generate it with AI, or upload</small></span>
    {/if}
    {#if badge}<span class="tf-badge">{badge}</span>{/if}
    <span class="tf-hover">{url ? 'Change' : 'Create thumbnail'}</span>
  </button>
  {#if !url && fallbackUrl && fallbackNote}<p class="tf-note">{fallbackNote}</p>{/if}
  <div class="tf-actions">
    <button type="button" class="tf-btn primary" on:click={() => (open = true)}>✦ {url ? 'Change thumbnail' : 'Create thumbnail'}</button>
    {#if !ownerId && picked}
      <button type="button" class="tf-btn" on:click={() => (picked = null)}>Remove</button>
    {/if}
  </div>
</div>

{#if open}
  <ThumbnailStudio {kind} {ownerId} {title} {kicker} {context} current={ownerId ? state : picked ? { thumbnail_url: null, thumbnail_source: null, thumbnail_design: picked.design } : null}
    onClose={() => (open = false)}
    onSaved={s => { state = s; onChange(s); }}
    onPicked={p => { if (picked) URL.revokeObjectURL(picked.url); picked = p; }} />
{/if}

<style>
  .tf { display: grid; gap: 0.5rem; }
  .tf-prev {
    position: relative; width: 100%; aspect-ratio: 16 / 9; border-radius: 10px; overflow: hidden;
    background-color: var(--surface2); background-size: cover; background-position: center;
    border: 1px solid var(--border-hover); display: grid; place-items: center; cursor: pointer; padding: 0;
  }
  .tf-prev.fallback { filter: saturate(0.6) brightness(0.7); }
  .tf-empty { display: grid; gap: 0.2rem; text-align: center; padding: 0.75rem; }
  .tf-empty b { font-size: 0.85rem; color: var(--text); }
  .tf-empty small { font-size: 0.74rem; color: var(--muted); }
  .tf-badge {
    position: absolute; right: 8px; top: 8px; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.03em;
    padding: 2px 8px; border-radius: 99px; background: rgba(0, 0, 0, 0.62); color: #fff;
  }
  .tf-hover {
    position: absolute; inset: 0; display: grid; place-items: center; background: rgba(0, 0, 0, 0.5);
    color: #fff; font-weight: 700; font-size: 0.85rem; opacity: 0; transition: opacity 0.15s;
  }
  .tf-prev:hover .tf-hover, .tf-prev:focus-visible .tf-hover { opacity: 1; }
  .tf-note { font-size: 0.74rem; color: var(--muted); line-height: 1.45; }
  .tf-actions { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .tf-btn {
    display: inline-flex; align-items: center; gap: 0.35rem; height: 30px; padding: 0 0.75rem; border-radius: 8px;
    border: 1px solid var(--border-hover); background: var(--surface2); color: var(--text); font-weight: 600; font-size: 0.78rem;
  }
  .tf-btn:hover { background: var(--surface3); }
  .tf-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .tf-btn.primary:hover { background: var(--accent-hover); }
</style>
