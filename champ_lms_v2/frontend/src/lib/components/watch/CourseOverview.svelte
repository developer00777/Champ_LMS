<script lang="ts">
  /**
   * The course page the breadcrumb's course link opens: the same for a
   * series, a full course and an older module. Title, progress and a resume
   * button up top, then every episode or step, each opening the standard
   * player.
   */
  import Thumb from '$lib/components/Thumb.svelte';
  import PlaylistItem from './PlaylistItem.svelte';
  import { icons } from '$lib/components/course/icons';

  type Row = {
    key: string; title: string; sub: string; kind: 'video' | 'quiz' | 'test' | 'notes';
    thumb?: string | null; duration: string; done: boolean; locked: boolean; lockedHint?: string; progress: number;
  };

  export let title: string;
  export let badge = 'Course';
  export let description: string | null = null;
  export let meta = '';
  export let thumb: string | null = null;
  export let done = 0;
  export let total = 0;
  export let resumeLabel = 'Start';
  export let onResume: () => void;
  export let sections: { title: string; rows: Row[] }[] = [];
  export let onOpen: (key: string) => void;

  $: pct = total ? Math.round((done / total) * 100) : 0;
</script>

<section class="ov-hero ui-panel ui-rise">
  <div class="ov-art">
    {#if thumb}<Thumb src={thumb} eager />{:else}<span class="ov-art-ph">{@html icons.video}</span>{/if}
  </div>
  <div class="ov-copy">
    <span class="ui-pill lilac ov-badge">{badge}</span>
    <h1>{title}</h1>
    {#if meta}<p class="ov-meta">{meta}</p>{/if}
    {#if description}<p class="ov-desc">{description}</p>{/if}
    {#if total}
      <div class="ov-prog">
        <div class="ov-bar"><i style="width:{pct}%"></i></div>
        <span>{done} of {total} done</span>
      </div>
    {/if}
    <button class="btn-primary ov-play" on:click={onResume}>{@html icons.play} {resumeLabel}</button>
  </div>
</section>

{#each sections as s, si}
  <section class="ov-sec ui-panel ui-rise" style="--i:{Math.min(si + 2, 10)}">
    <div class="ov-sec-h">
      <h2>{s.title}</h2>
      <span>{s.rows.filter(r => r.done).length}/{s.rows.length}</span>
    </div>
    <div class="ov-rows">
      {#each s.rows as r (r.key)}
        <PlaylistItem title={r.title} sub={r.sub} kind={r.kind} thumb={r.thumb} duration={r.duration}
          done={r.done} locked={r.locked} lockedHint={r.lockedHint ?? ''} progress={r.progress}
          on:click={() => !r.locked && onOpen(r.key)} />
      {/each}
    </div>
  </section>
{/each}

<style>
  /* Panels, pill and primary button come from app.css (.ui-panel, .ui-pill,
     .btn-primary), so this page matches the rest of the app. */
  .ov-hero {
    display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 1.6rem; align-items: center;
    padding: 0.75rem; margin-bottom: 1.2rem;
  }
  @media (max-width: 860px) { .ov-hero { grid-template-columns: minmax(0, 1fr); } }
  .ov-art {
    position: relative; aspect-ratio: 16 / 9; border-radius: var(--radius-lg); overflow: hidden;
    background: var(--tile-lilac); display: grid; place-items: center; color: var(--tile-ink);
  }
  .ov-art-ph { font-size: 3rem; opacity: 0.8; }
  .ov-copy { display: grid; gap: 0.7rem; justify-items: start; padding: 1rem 1.2rem 1rem 0.4rem; }
  @media (max-width: 860px) { .ov-copy { padding: 0.4rem 0.6rem 0.8rem; } }
  .ov-badge { animation: pop 520ms var(--ease-out) 250ms backwards; }
  h1 { font-size: clamp(1.6rem, 1.2rem + 1.4vw, 2.3rem); font-weight: 700; letter-spacing: -0.035em; line-height: 1.1; }
  .ov-meta { color: var(--muted); font-size: 0.88rem; }
  .ov-desc { color: var(--text-secondary); line-height: 1.55; }
  .ov-prog { display: flex; gap: 0.7rem; align-items: center; width: 100%; font-size: 0.78rem; color: var(--muted); font-variant-numeric: tabular-nums; }
  .ov-bar { flex: 1; max-width: 260px; height: 6px; border-radius: 9px; background: var(--surface3); overflow: hidden; }
  .ov-bar i { display: block; height: 100%; border-radius: inherit; background: var(--success); }
  .ov-play { margin-top: 0.3rem; }

  .ov-sec { padding: 0.6rem; margin-bottom: 1rem; }
  .ov-sec-h { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; padding: 0.6rem 0.7rem 0.4rem; }
  .ov-sec-h h2 { font-size: 1.05rem; font-weight: 700; letter-spacing: -0.015em; }
  .ov-sec-h span {
    font-weight: 600; font-size: 0.72rem; color: var(--text-secondary); font-variant-numeric: tabular-nums;
    background: var(--surface2); border-radius: var(--radius-pill); padding: 0.1rem 0.5rem;
  }
  .ov-rows { display: grid; gap: 0.15rem; }
  .ov-rows :global(.pi) { grid-template-columns: 132px minmax(0, 1fr) auto; }
  @media (max-width: 620px) { .ov-rows :global(.pi) { grid-template-columns: 96px minmax(0, 1fr) auto; } }
</style>
