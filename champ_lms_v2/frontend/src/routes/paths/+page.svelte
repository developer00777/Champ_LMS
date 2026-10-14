<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, type PathSummary, type PathDetail, type PathNode } from '$lib/api/client';
  import { auth } from '$lib/stores/auth';
  import SkillTrail from '$lib/components/SkillTrail.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import { countUp } from '$lib/actions/motion';

  let paths: PathSummary[] = [];
  let selectedPath: PathDetail | null = null;
  let loading = true;
  let opening: string | null = null;
  let error = '';

  onMount(async () => {
    try {
      paths = await api.paths();
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  });

  async function openPath(p: PathSummary) {
    opening = p.id;
    error = '';
    try {
      selectedPath = await api.path(p.id);
      await tick();
      window.scrollTo({ top: 0 });
    } catch (e: any) {
      error = e.message;
    } finally {
      opening = null;
    }
  }

  function onNodeClick(node: PathNode) {
    if (node.module_id && node.status !== 'locked') goto(`/module/${node.module_id}`);
  }

  $: myDept = $auth.user?.department;
  $: deptPaths = paths.filter((p) => myDept && p.department === myDept);
  $: otherPaths = paths.filter((p) => !(myDept && p.department === myDept));
  $: totalLevels = paths.reduce((a, p) => a + (p.total_nodes || 0), 0);
  $: groups = [
    { label: myDept ? `Your department · ${myDept}` : 'Your department', list: deptPaths, mine: true },
    { label: deptPaths.length ? 'Other tracks' : 'All tracks', list: otherPaths, mine: false },
  ];

  const TONES = ['lilac', 'sky', 'mint', 'butter', 'peach'];
  // A small zig-zag of dots for each card: one per level, capped so long
  // paths still fit.
  function miniTrail(count: number) {
    const k = Math.max(2, Math.min(count || 2, 7));
    return Array.from({ length: k }, (_, i) => ({ x: 14 + (i * 172) / (k - 1), y: i % 2 ? 14 : 38 }));
  }
</script>

<svelte:head><title>Learning Paths — Champ LMS</title></svelte:head>

{#if selectedPath}
  <div class="detail-view">
    <button class="back-btn ui-rise" on:click={() => (selectedPath = null)}><Icon name="arrowLeft" size={16} /> All paths</button>
    {#key selectedPath.id}
      <SkillTrail path={selectedPath} {onNodeClick} />
    {/key}
  </div>
{:else if loading}
  <div class="ui-skeleton" style="height:18px;width:240px;border-radius:8px;margin-bottom:0.6rem"></div>
  <div class="ui-skeleton" style="height:52px;width:360px;max-width:100%;border-radius:14px;margin-bottom:1.5rem"></div>
  <div class="grid">
    {#each Array(4) as _}<div class="ui-skeleton" style="height:250px;border-radius:30px"></div>{/each}
  </div>
{:else if error && !paths.length}
  <div class="state ui-rise">
    <span class="state-ico danger"><Icon name="alert" size={28} /></span>
    <h2>Couldn't load paths</h2>
    <p>{error}</p>
    <button class="btn-primary" on:click={() => window.location.reload()}>Try again</button>
  </div>
{:else}
  <header class="head">
    <div>
      <p class="eyebrow ui-rise">Master each level to unlock the next</p>
      <h1 class="ui-rise" style="--i:1">
        Learning Paths
        <span class="title-mark" aria-hidden="true"><Icon name="route" size={24} /></span>
      </h1>
    </div>
    {#if paths.length}
      <div class="summary">
        <span class="chip mint ui-rise" style="--i:2"><Icon name="route" size={15} /><b use:countUp={paths.length}></b> path{paths.length === 1 ? '' : 's'}</span>
        <span class="chip sky ui-rise" style="--i:3"><Icon name="flag" size={15} /><b use:countUp={totalLevels}></b> levels</span>
        {#if deptPaths.length}<span class="chip lilac ui-rise" style="--i:4"><Icon name="building" size={15} /><b use:countUp={deptPaths.length}></b> for your team</span>{/if}
      </div>
    {/if}
  </header>

  {#if error}<p class="error ui-rise"><Icon name="alert" size={15} /> {error}</p>{/if}

  {#if !paths.length}
    <div class="state ui-rise" style="--i:2">
      <span class="state-ico"><Icon name="route" size={26} /></span>
      <h2>No paths yet</h2>
      <p>Skill tracks appear here once your admin publishes them.</p>
    </div>
  {/if}

  {#each groups as group, g}
    {#if group.list.length}
      <section>
        <div class="sec-head ui-rise" style="--i:{3 + g}">
          <h2>{group.label}</h2>
          <span class="count">{group.list.length}</span>
        </div>
        <div class="grid">
          {#each group.list as p, n (p.id)}
            {@const tone = TONES[(n + g * 2) % TONES.length]}
            {@const dots = miniTrail(p.total_nodes)}
            <button
              class="card ui-rise {group.mine ? tone : 'plain'}"
              class:busy={opening === p.id}
              style="--i:{Math.min(4 + n, 10)}"
              on:click={() => openPath(p)}
              disabled={!!opening}
            >
              <span class="mini" aria-hidden="true">
                <svg viewBox="0 0 200 52">
                  <polyline points={dots.map((d) => `${d.x},${d.y}`).join(' ')} />
                </svg>
                {#each dots as d, k}
                  <i style="left:{(d.x / 200) * 100}%; top:{(d.y / 52) * 100}%; --k:{k}" class:last={k === dots.length - 1}></i>
                {/each}
              </span>
              <span class="variant">
                <Icon name={p.variant === 'ridge' ? 'trend' : 'route'} size={13} />
                {p.variant === 'ridge' ? 'Ridge climb' : 'Trail'}
              </span>
              <h3>{p.title}</h3>
              <p>{p.description ?? ''}</p>
              <span class="foot">
                <span class="meta">
                  <span><Icon name="flag" size={13} /> {p.total_nodes} level{p.total_nodes === 1 ? '' : 's'}</span>
                  {#if p.path_type}<span><Icon name="hash" size={13} /> {p.path_type}</span>{/if}
                </span>
                <span class="ui-round ink go" aria-hidden="true">
                  {#if opening === p.id}<span class="spinner"></span>{:else}<Icon name="arrowRight" size={16} />{/if}
                </span>
              </span>
            </button>
          {/each}
        </div>
      </section>
    {/if}
  {/each}
{/if}

<style>
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin: 0.25rem 0 1.6rem; }
  .eyebrow { color: var(--muted); font-size: 0.95rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; display: flex; align-items: center; gap: 0.6rem; }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-mint); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .summary { display: flex; flex-wrap: wrap; gap: 0.45rem; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.4rem; height: 36px; padding: 0 0.9rem;
    border-radius: 99px; font-size: 0.84rem; font-weight: 600; color: var(--tile-ink);
  }
  .chip b { font-variant-numeric: tabular-nums; }
  .chip.mint { background: var(--tile-mint); } .chip.sky { background: var(--tile-sky); } .chip.lilac { background: var(--tile-lilac); }
  .error { display: flex; align-items: center; gap: 0.4rem; color: var(--danger); font-size: 0.86rem; margin-bottom: 1rem; }

  section { margin-bottom: 2.2rem; }
  .sec-head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 1rem; }
  .sec-head h2 { font-size: 1.35rem; letter-spacing: -0.02em; }
  .count {
    min-width: 26px; height: 24px; padding: 0 8px; border-radius: 99px; display: inline-grid; place-items: center;
    background: var(--surface2); font-size: 0.78rem; font-weight: 700; color: var(--text-secondary);
  }

  /* Even grid: every card in a row is one height. */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); grid-auto-rows: 1fr; gap: 1.1rem; }
  .card {
    position: relative; display: flex; flex-direction: column; align-items: flex-start; gap: 0.5rem;
    height: 100%; min-height: 250px; padding: 1.2rem 1.3rem 1.1rem;
    border-radius: 30px; box-shadow: var(--shadow-sm); color: var(--tile-ink); text-align: left;
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out), rotate var(--dur-3) var(--ease-out);
  }
  .card:hover:not(:disabled) { translate: 0 -5px; rotate: -0.6deg; box-shadow: var(--shadow-md); }
  .card:disabled { cursor: progress; }
  .card:disabled:not(.busy) { opacity: 0.7; }
  .card.plain { background: var(--surface); color: var(--text); }
  .lilac { background: var(--tile-lilac); } .sky { background: var(--tile-sky); }
  .mint { background: var(--tile-mint); } .butter { background: var(--tile-butter); }
  .peach { background: var(--tile-peach); }

  /* mini trail: dots pop in one by one, the last one is the summit */
  .mini { position: relative; display: block; width: 100%; height: 52px; margin-bottom: 0.3rem; }
  .mini svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; }
  .mini polyline {
    fill: none; stroke: currentColor; stroke-width: 2; stroke-dasharray: 2 6; stroke-linecap: round; opacity: 0.35;
    vector-effect: non-scaling-stroke;
  }
  .mini i {
    position: absolute; width: 14px; height: 14px; border-radius: 50%; translate: -50% -50%;
    background: var(--surface); box-shadow: 0 0 0 3px color-mix(in srgb, currentColor 18%, transparent);
    animation: dot-in 420ms var(--ease-out) calc(300ms + var(--k) * 70ms) backwards;
    transition: scale var(--dur-3) var(--ease-out);
  }
  .card.plain .mini i { background: var(--surface2); }
  .mini i.last { width: 20px; height: 20px; background: var(--accent); box-shadow: none; }
  .card:hover .mini i { scale: 1.15; transition-delay: calc(var(--k) * 40ms); }
  @keyframes dot-in { from { opacity: 0; scale: 0.2; } }

  .variant { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.7; }
  h3 {
    font-size: 1.22rem; font-weight: 650; letter-spacing: -0.02em; line-height: 1.25; min-height: calc(2 * 1.25em);
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .card p {
    font-size: 0.86rem; opacity: 0.72; line-height: 1.5; min-height: calc(2 * 1.5em);
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .foot { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; width: 100%; margin-top: auto; padding-top: 0.5rem; }
  .meta { display: flex; flex-wrap: wrap; gap: 0.35rem; }
  .meta > span {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 26px; padding: 0 0.6rem; border-radius: 99px;
    background: var(--tile-inner); font-size: 0.74rem; font-weight: 600; text-transform: capitalize;
  }
  .card.plain .meta > span { background: var(--surface2); color: var(--text-secondary); }
  .go { width: 40px; height: 40px; transition: transform var(--dur-3) var(--ease-out); }
  .card:hover .go { transform: translateX(3px) rotate(-30deg); }
  .spinner { width: 16px; height: 16px; border-radius: 50%; border: 2px solid currentColor; border-right-color: transparent; animation: spin 700ms linear infinite; }
  @keyframes spin { to { rotate: 360deg; } }

  .back-btn {
    display: inline-flex; align-items: center; gap: 0.4rem;
    background: var(--surface); color: var(--text); height: 40px; padding: 0 1rem; border-radius: 999px;
    font-size: 0.86rem; font-weight: 600; margin-bottom: 1rem; box-shadow: var(--shadow-sm);
    transition: background-color var(--dur-2);
  }
  .back-btn:hover { background: var(--surface2); }
  .back-btn :global(.icon) { transition: translate var(--dur-2) var(--ease-out); }
  .back-btn:hover :global(.icon) { translate: -3px 0; }

  .state { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; text-align: center; padding: 3.5rem 1.5rem; border-radius: 32px; background: var(--surface); }
  .state h2 { font-size: 1.35rem; }
  .state p { color: var(--muted); }
  .state-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }
  .state-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }

  @media (max-width: 760px) {
    .grid { grid-template-columns: 1fr; }
  }
</style>
