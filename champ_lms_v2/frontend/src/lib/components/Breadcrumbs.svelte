<script lang="ts">
  /**
   * Where a nested page sits: "Admin › Courses › Sales onboarding". Every
   * item but the last links back up; the last is the current page. Top-level
   * pages don't need one, the nav tabs already say where you are.
   */
  import Icon from './Icon.svelte';

  export let items: { label: string; href?: string }[] = [];
</script>

{#if items.length}
  <nav class="crumbs" aria-label="Breadcrumb">
    <ol>
      {#each items as item, i}
        {@const last = i === items.length - 1}
        <li>
          {#if item.href && !last}
            <a href={item.href}>
              {#if i === 0}<Icon name="arrowLeft" size={14} />{/if}{item.label}
            </a>
          {:else}
            <span aria-current={last ? 'page' : undefined}>{item.label}</span>
          {/if}
          {#if !last}<Icon name="chevronRight" size={13} />{/if}
        </li>
      {/each}
    </ol>
  </nav>
{/if}

<style>
  .crumbs { margin-bottom: 0.6rem; min-width: 0; }
  ol { display: flex; align-items: center; flex-wrap: wrap; gap: 0.15rem 0.35rem; list-style: none; padding: 0; margin: 0; }
  li { display: inline-flex; align-items: center; gap: 0.35rem; min-width: 0; font-size: 0.85rem; font-weight: 600; color: var(--muted); }
  li :global(.icon) { flex: none; opacity: 0.7; }
  a { display: inline-flex; align-items: center; gap: 0.3rem; color: var(--muted); border-radius: 6px; }
  a:hover { color: var(--text); }
  a:hover :global(.icon) { translate: -3px 0; transition: translate var(--dur-2) var(--ease-out); }
  span[aria-current] { color: var(--text); max-width: 42ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
