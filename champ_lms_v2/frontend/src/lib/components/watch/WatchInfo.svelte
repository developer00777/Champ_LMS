<script lang="ts">
  // Title block under the player: the same on every watch page.
  export let title: string;
  /** Small line above the title, e.g. "Episode 3 · Sales onboarding". */
  export let eyebrow = '';
  /** Short facts shown as pills after the title. */
  export let facts: string[] = [];
</script>

<header class="winfo">
  {#if eyebrow}<span class="eyebrow">{eyebrow}</span>{/if}
  <h1>{title}</h1>
  {#if facts.length}
    <div class="facts">{#each facts as f, i}<span class="ui-pill fact" class:mint={f === 'Watched'} style="--i:{i}">{f}</span>{/each}</div>
  {/if}
</header>

<style>
  .winfo { display: grid; gap: 0.4rem; }
  .eyebrow { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  h1 { font-size: clamp(1.3rem, 1.1rem + 0.8vw, 1.6rem); font-weight: 700; letter-spacing: -0.025em; line-height: 1.2; }
  .facts { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.2rem; }
  /* .ui-pill (app.css), slightly smaller under a title. */
  .fact {
    height: 30px; padding: 0 0.8rem; font-size: 0.8rem; font-variant-numeric: tabular-nums;
    animation: pop 420ms var(--ease-out) backwards; animation-delay: calc(100ms + var(--i) * 50ms);
  }
</style>
