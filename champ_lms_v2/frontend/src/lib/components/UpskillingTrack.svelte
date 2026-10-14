<script lang="ts">
  /**
   * The learner's upskill track (GET /me/upselling-track) as an even grid:
   * every card is the same height, the module in progress is tinted, and the
   * totals sit above as count-up chips.
   */
  import { moduleHref, type Module, type UpskillingTrack } from '$lib/api/client';
  import Icon from './Icon.svelte';
  import { countUp, reveal } from '$lib/actions/motion';

  export let track: UpskillingTrack;
  /** Feed modules by id, for the right player link. */
  export let modulesById: Record<string, Module> = {};
  export let query = '';

  type Step = UpskillingTrack['modules'][number];

  $: q = query.trim().toLowerCase();
  $: steps = track.modules.filter((m) => !q || m.title.toLowerCase().includes(q));
  $: done = track.modules.filter((m) => m.status === 'completed' || m.status === 'mastered').length;
  $: active = track.modules.filter((m) => m.status === 'in_progress').length;
  $: upcoming = track.modules.filter((m) => m.status === 'not_started').length;
  // The first module in progress is the one to pick up next.
  $: currentId = steps.find((m) => m.status === 'in_progress')?.module_id ?? null;

  const STATUS = {
    mastered: { label: 'Mastered', tone: 'butter', icon: 'award' },
    completed: { label: 'Completed', tone: 'mint', icon: 'check' },
    in_progress: { label: 'In progress', tone: 'lilac', icon: 'play' },
    not_started: { label: 'Up next', tone: 'sky', icon: 'target' },
  } as const;

  const pct = (m: Step) => Math.max(0, Math.min(100, Math.round(m.progress || 0)));
  function href(m: Step) {
    const mod = modulesById[m.module_id];
    return mod ? moduleHref(mod) : `/module/${m.module_id}`;
  }
  function blurb(m: Step) {
    const d = m.description || modulesById[m.module_id]?.description;
    if (d) return d;
    if (m.status === 'not_started') return 'Next on your track. Start whenever you are ready.';
    if (m.status === 'in_progress') return `You are ${pct(m)}% of the way through.`;
    return 'Finished. Revisit any time to refresh it.';
  }
</script>

<section class="plan" aria-label="Learning plan for {track.track}">
  <div class="totals">
    <span class="chip sky ui-rise" style="--i:2"><Icon name="layers" size={15} /><b use:countUp={track.total_modules}></b> modules</span>
    <span class="chip lilac ui-rise" style="--i:3"><Icon name="play" size={14} /><b use:countUp={active}></b> in progress</span>
    <span class="chip mint ui-rise" style="--i:4"><Icon name="check" size={15} /><b use:countUp={done}></b> completed</span>
    <span class="chip ghost ui-rise" style="--i:5"><Icon name="target" size={15} /><b use:countUp={upcoming}></b> up next</span>
  </div>

  {#if steps.length}
    <div class="grid">
      {#each steps as m, i (m.module_id)}
        {@const s = STATUS[m.status] ?? STATUS.not_started}
        <a class="step" class:now={m.module_id === currentId} href={href(m)} use:reveal={{ delay: (i % 4) * 70 }}>
          <span class="top">
            <span class="ico {s.tone}" aria-hidden="true"><Icon name={s.icon} size={18} /></span>
            <span class="num">{String(i + 1).padStart(2, '0')}</span>
          </span>
          <h3>{m.title}</h3>
          <p>{blurb(m)}</p>
          <span class="meter" aria-label="{pct(m)}% done">
            <span class="bar"><span style="--p:{pct(m)}%"></span></span>
            <b>{pct(m)}%</b>
          </span>
          <span class="foot">
            <span class="ui-pill {s.tone}"><Icon name={s.icon} size={13} /> {m.module_id === currentId ? 'Continue' : s.label}</span>
            <span class="ui-round ink go" aria-hidden="true"><Icon name="arrowRight" size={16} /></span>
          </span>
        </a>
      {/each}
    </div>
  {:else}
    <p class="none">No modules on your track match “{query}”.</p>
  {/if}
</section>

<style>
  .totals { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.1rem; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.4rem; height: 34px; padding: 0 0.85rem;
    border-radius: 99px; font-size: 0.82rem; font-weight: 600; color: var(--tile-ink);
  }
  .chip b { font-variant-numeric: tabular-nums; }
  .chip.sky { background: var(--tile-sky); }
  .chip.lilac { background: var(--tile-lilac); }
  .chip.mint { background: var(--tile-mint); }
  .chip.ghost { background: var(--surface2); color: var(--text-secondary); }

  /* Even grid: every row stretches its cards to one height. */
  .grid {
    display: grid; gap: 1rem;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    grid-auto-rows: 1fr;
  }
  .step {
    position: relative; display: flex; flex-direction: column; gap: 0.55rem;
    min-height: 236px; height: 100%; padding: 1.15rem 1.15rem 1rem;
    border-radius: 26px; background: var(--surface); box-shadow: var(--shadow-sm); color: var(--text);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .step:hover { translate: 0 -4px; box-shadow: var(--shadow-md); }
  .step.now { background: var(--tile-lilac); color: var(--tile-ink); }
  .step.now p { color: color-mix(in srgb, var(--tile-ink) 70%, transparent); }

  .top { display: flex; align-items: center; justify-content: space-between; }
  .ico {
    width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; color: var(--tile-ink);
    transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .ico.sky { background: var(--tile-sky); }
  .ico.lilac { background: var(--tile-lilac); }
  .ico.mint { background: var(--tile-mint); }
  .ico.butter { background: var(--tile-butter); }
  .now .ico { background: var(--surface); color: var(--text); }
  .step:hover .ico { rotate: -12deg; scale: 1.08; }
  .num { font-size: 0.8rem; font-weight: 700; color: var(--muted); font-variant-numeric: tabular-nums; }
  .now .num { color: color-mix(in srgb, var(--tile-ink) 60%, transparent); }

  /* Fixed line counts keep every card's text block the same height. */
  h3 {
    font-size: 1.08rem; font-weight: 650; letter-spacing: -0.015em; line-height: 1.3;
    min-height: calc(2 * 1.3em);
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  p {
    color: var(--muted); font-size: 0.86rem; line-height: 1.45; min-height: calc(2 * 1.45em);
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }

  .meter { display: flex; align-items: center; gap: 0.6rem; margin-top: auto; }
  .meter b { font-size: 0.78rem; font-variant-numeric: tabular-nums; min-width: 3ch; text-align: right; }
  .bar { flex: 1; height: 6px; border-radius: 99px; overflow: hidden; background: var(--surface3); }
  .now .bar { background: color-mix(in srgb, var(--tile-ink) 14%, transparent); }
  .bar span {
    display: block; height: 100%; width: var(--p); border-radius: inherit; background: var(--brand);
    transform-origin: left; animation: grow 1s var(--ease-out) 300ms backwards;
  }
  .now .bar span { background: var(--tile-ink); }
  @keyframes grow { from { transform: scaleX(0); } }

  .foot { display: flex; align-items: center; justify-content: space-between; }
  .now .foot .ui-pill { background: var(--surface); color: var(--text); }
  .go { width: 36px; height: 36px; transition: transform var(--dur-3) var(--ease-out), background-color var(--dur-2); }
  .step:hover .go { transform: translateX(3px) rotate(-30deg); }

  .none { color: var(--muted); padding: 1rem 0; }
</style>
