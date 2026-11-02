<script lang="ts">
  // The tab strip under the player on every watch page.
  export let tabs: { id: string; label: string }[] = [];
  export let active: string;
</script>

<div class="wtabs" role="tablist">
  {#each tabs as t (t.id)}
    <button role="tab" aria-selected={active === t.id} class:on={active === t.id} on:click={() => (active = t.id)}>{t.label}</button>
  {/each}
</div>

<style>
  .wtabs {
    display: flex; gap: 0.25rem; padding: 0.3rem; border-radius: var(--radius-pill); background: var(--surface2);
    width: fit-content; max-width: 100%; overflow-x: auto; scrollbar-width: none;
  }
  .wtabs::-webkit-scrollbar { display: none; }
  button {
    flex: none; height: 36px; padding: 0 1rem; border-radius: var(--radius-pill); font-weight: 600; font-size: 0.85rem; color: var(--muted);
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2), box-shadow var(--dur-2);
  }
  button:hover { color: var(--text); }
  button.on { color: var(--text); background: var(--surface); box-shadow: var(--shadow-sm); }
</style>
