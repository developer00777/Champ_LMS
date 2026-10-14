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
  .prose { max-width: 70ch; display: grid; gap: 0.65rem; font-size: 0.97rem; line-height: 1.7; animation: fade 420ms var(--ease-out) backwards; }
  h3 { font-size: 1.12rem; font-weight: 700; letter-spacing: -0.015em; margin-top: 0.5rem; }
  ul { margin: 0; padding-left: 0; list-style: none; display: grid; gap: 0.35rem; }
  li { position: relative; padding-left: 1.3rem; }
  li::before {
    content: ''; position: absolute; left: 0.25rem; top: 0.68em; width: 7px; height: 7px; border-radius: 50%;
    background: var(--path, var(--accent));
  }
  .empty { color: var(--muted); padding: 1rem 1.1rem; border-radius: 18px; background: var(--surface2); }
</style>
