<script lang="ts">
  // A video/course thumbnail that never crops the picture. It fills its
  // positioned parent: the whole image is shown (contain), and any space a
  // non-16:9 upload leaves is filled with a blurred copy of the same image
  // rather than bars or a hard crop. For a true 16:9 thumbnail in a 16:9 box
  // the two layers line up exactly and it looks like a plain cover image.
  //
  // Parents zoom it on hover via `:global(.thumb-media)`.
  import { createEventDispatcher } from 'svelte';

  export let src: string;
  export let alt = '';
  export let eager = false;

  const dispatch = createEventDispatcher<{ error: void }>();
</script>

<span class="thumb-media">
  <img class="backdrop" {src} alt="" aria-hidden="true" loading={eager ? 'eager' : 'lazy'} decoding="async" />
  <img class="picture" {src} {alt} loading={eager ? 'eager' : 'lazy'} decoding="async" on:error={() => dispatch('error')} />
</span>

<style>
  .thumb-media {
    position: absolute; inset: 0; display: block; overflow: hidden; border-radius: inherit;
    transition: scale 700ms var(--ease-out);
  }
  img { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  .backdrop {
    object-fit: cover;
    filter: blur(18px) saturate(1.2) brightness(0.82);
    scale: 1.2;
  }
  .picture { object-fit: contain; }
</style>
