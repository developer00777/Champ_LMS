<script lang="ts">
  // What the player area shows before a video can play (loading, still
  // processing, or an error), sized exactly like the player.
  export let message = 'Loading video…';
  export let busy = true;
  export let hint = '';
</script>

<div class="stage-ph" role="status">
  {#if busy}<span class="ring"></span>{/if}
  <p>{message}</p>
  {#if hint}<small>{hint}</small>{/if}
</div>

<style>
  .stage-ph {
    aspect-ratio: 16 / 9; width: 100%; border-radius: var(--radius-xl); background: #0b0b0d; box-shadow: var(--shadow-md);
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.8rem;
    padding: 1rem; text-align: center; color: rgba(244, 244, 246, 0.78); font-size: 0.92rem;
  }
  small { color: rgba(244, 244, 246, 0.55); font-size: 0.8rem; }
  .ring {
    /* Same ring as the player's own loader: the stage is always dark, so no
       theme colour (--accent is near-black in light mode). */
    width: 38px; height: 38px; border-radius: 50%;
    border: 3px solid rgba(255, 255, 255, 0.15); border-top-color: #f4f4f6;
    animation: sp-spin 0.9s linear infinite;
  }
  @keyframes sp-spin { to { rotate: 360deg; } }
</style>
