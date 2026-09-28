<script lang="ts">
  import { parseNotes } from '$lib/utils/notes-markup';

  export let source: string | null | undefined;
  $: blocks = parseNotes(source);
</script>

<div class="prose">
  {#each blocks as b}
    {#if b.type === 'h'}<h3>{b.text}</h3>
    {:else if b.type === 'ul'}<ul>{#each b.items as i}<li>{i}</li>{/each}</ul>
    {:else}<p>{b.text}</p>{/if}
  {:else}
    <p class="empty">Nothing here yet.</p>
  {/each}
</div>

<style>
  .prose { max-width: 70ch; display: grid; gap: 0.6rem; font-size: 0.95rem; line-height: 1.65; }
  h3 { font-size: 1.02rem; font-weight: 700; margin-top: 0.35rem; }
  ul { margin: 0; padding-left: 1.2rem; display: grid; gap: 0.25rem; }
  .empty { color: var(--muted); }
</style>
