<script lang="ts">
  // Header label that cycles its column through default → ascending →
  // descending. Sits inside the page's own <th> so the page's header styles apply;
  // put aria-sort={ariaSort(sort, field)} on that <th>.
  import { cycleSort, dirFor, NO_SORT, type SortState } from '$lib/utils/table-sort';

  export let field: string;
  export let sort: SortState = NO_SORT;

  $: dir = dirFor(sort, field);
  $: hint = dir === 'none' ? 'Sort ascending' : dir === 'asc' ? 'Sort descending' : 'Back to default order';
</script>

<button type="button" class="sort" class:active={dir !== 'none'} title={hint} on:click={() => (sort = cycleSort(sort, field))}>
  <slot />
  <svg class="arrows" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    {#if dir === 'asc'}
      <path d="M12 20V4M6 10l6-6 6 6" />
    {:else if dir === 'desc'}
      <path d="M12 4v16M6 14l6 6 6-6" />
    {:else}
      <path d="M8 20V4M4 8l4-4 4 4M16 4v16M12 16l4 4 4-4" />
    {/if}
  </svg>
</button>

<style>
  .sort {
    display: inline-flex; align-items: center; gap: 0.35rem; padding: 0; margin: 0;
    background: none; border: 0; cursor: pointer; white-space: nowrap;
    font: inherit; letter-spacing: inherit; text-transform: inherit; text-align: inherit; color: inherit;
    transition: color var(--dur-2) var(--ease-out);
  }
  .sort:hover, .sort.active { color: var(--text); }
  .sort:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 4px; }
  .arrows { flex: none; opacity: 0.45; transition: opacity var(--dur-2) var(--ease-out); }
  .sort:hover .arrows { opacity: 0.8; }
  .sort.active .arrows { opacity: 1; color: var(--accent); animation: pop 260ms var(--ease-out); }
</style>
