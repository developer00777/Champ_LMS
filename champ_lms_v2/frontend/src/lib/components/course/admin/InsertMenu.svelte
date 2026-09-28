<script lang="ts">
  import type { CourseItemKind } from '$lib/api/client';
  import { icons } from '../icons';

  export let onPick: (kind: CourseItemKind) => void;

  const OPTIONS: { kind: CourseItemKind; title: string; hint: string }[] = [
    { kind: 'video', title: 'Videos', hint: 'Pick one or many files. Each becomes an episode.' },
    { kind: 'quiz', title: 'AI quiz', hint: 'Written from the episodes just above it.' },
    { kind: 'test', title: 'Test', hint: 'Upload a PDF or Word paper, write it, or let AI write it.' },
    { kind: 'notes', title: 'Notes', hint: 'A reading page, with an optional PDF.' },
  ];
</script>

<div class="ins-menu" role="menu">
  {#each OPTIONS as o}
    <button role="menuitem" on:click={() => onPick(o.kind)}>
      <span class="c-ico k-{o.kind}">{@html icons[o.kind]}</span>
      <span><b>{o.title}</b><small>{o.hint}</small></span>
    </button>
  {/each}
</div>
