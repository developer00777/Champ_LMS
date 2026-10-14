<script lang="ts">
  /**
   * A learning path (GET /paths/{id}) drawn as a climb: Level 1 at the bottom,
   * the last level at the top. On open the view tours the route — up to the
   * last level, then back down to the learner's current level — and the
   * side panel describes whichever level is selected.
   */
  import { onDestroy, onMount, tick } from 'svelte';
  import type { PathDetail, PathNode } from '$lib/api/client';
  import { auth } from '$lib/stores/auth';
  import Icon from './Icon.svelte';
  import Thumb from './Thumb.svelte';
  import Avatar from './Avatar.svelte';
  import { countUp } from '$lib/actions/motion';

  export let path: PathDetail;
  export let onNodeClick: ((node: PathNode) => void) | undefined = undefined;

  const BAND = 136;        // vertical distance between levels
  const PAD_TOP = 170;     // room above the last level for the summit
  const PAD_BOTTOM = 120;  // room below Level 1 for the trailhead

  let stageW = 600;
  $: n = path.nodes.length;
  $: cur = n ? Math.min(Math.max(0, path.current_node ?? 0), n - 1) : 0;
  $: mastered = new Set(path.mastered_nodes ?? []);
  $: stageH = PAD_TOP + Math.max(0, n - 1) * BAND + PAD_BOTTOM;
  $: amp = Math.max(56, Math.min(170, stageW * 0.27));
  $: pts = path.nodes.map((node, i) => ({
    node, i,
    x: stageW / 2 + Math.sin(i * 1.2) * amp,
    y: stageH - PAD_BOTTOM - i * BAND,
  }));
  const isRidge = path.variant === 'ridge';
  $: done = !!path.completed_at || (n > 0 && mastered.size >= n);
  $: pct = Math.round(path.completion_percentage || 0);

  // ---------- smooth route through every level (Catmull-Rom as cubic Béziers) ----------
  function curve(p: { x: number; y: number }[]): string {
    if (!p.length) return '';
    if (p.length === 1) return `M${p[0].x},${p[0].y}`;
    let d = `M${p[0].x.toFixed(1)},${p[0].y.toFixed(1)}`;
    for (let i = 0; i < p.length - 1; i++) {
      const p0 = p[i - 1] ?? p[i], p1 = p[i], p2 = p[i + 1], p3 = p[i + 2] ?? p2;
      const c1x = p1.x + (p2.x - p0.x) / 6, c1y = p1.y + (p2.y - p0.y) / 6;
      const c2x = p2.x - (p3.x - p1.x) / 6, c2y = p2.y - (p3.y - p1.y) / 6;
      d += ` C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
    }
    return d;
  }
  $: walked = curve(pts.slice(0, (done ? n : cur + 1)));
  $: ahead = curve(pts.slice(cur));

  // ---------- level state ----------
  type Kind = 'mastered' | 'completed' | 'in_progress' | 'unlocked' | 'locked';
  const KINDS: Kind[] = ['mastered', 'completed', 'in_progress', 'unlocked', 'locked'];
  const kind = (node: PathNode, i: number): Kind =>
    mastered.has(i) ? 'mastered' : KINDS.includes(node.status as Kind) ? (node.status as Kind) : 'locked';
  const KIND: Record<Kind, { label: string; icon: string; tone: string }> = {
    mastered: { label: 'Mastered', icon: 'award', tone: 'butter' },
    completed: { label: 'Completed', icon: 'check', tone: 'mint' },
    in_progress: { label: 'In progress', icon: 'play', tone: 'lilac' },
    unlocked: { label: 'Unlocked', icon: 'unlock', tone: 'sky' },
    locked: { label: 'Locked', icon: 'lock', tone: '' },
  };
  const prog = (node: PathNode) => Math.max(0, Math.min(100, Math.round(node.progress_pct || 0)));
  function nodeIcon(node: PathNode, i: number) {
    const k = kind(node, i);
    if (node.is_summit) return 'star';
    if (k === 'mastered' || k === 'completed') return node.node_type === 'milestone' ? 'flag' : 'check';
    if (k === 'locked') return 'lock';
    return node.node_type === 'milestone' ? 'flag' : 'play';
  }

  let selected = 0;
  let selectedInit = false;
  $: if (!selectedInit && n) { selected = cur; selectedInit = true; }
  $: sel = path.nodes[selected] ?? null;
  $: selKind = sel ? kind(sel, selected) : 'locked';

  function cta(node: PathNode, k: Kind) {
    if (k === 'locked') return 'Locked';
    if (k === 'mastered' || k === 'completed') return 'Review level';
    if (k === 'in_progress') return `Continue · ${prog(node)}%`;
    return 'Start level';
  }

  // ---------- camera: tour up to the last level, then back to the current one ----------
  let scroller: HTMLElement;
  let raf = 0;
  let touring = false;
  // Each tour gets an id; stopping bumps it, so a tour paused in a sleep
  // can't carry on after the learner has taken over the camera.
  let tourId = 0;
  const reduced = () => typeof document !== 'undefined' && document.documentElement.dataset.motion === 'reduced';
  const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  /** scrollTop that centres level i in the viewport. */
  function topFor(i: number) {
    if (!scroller || !pts[i]) return 0;
    const max = scroller.scrollHeight - scroller.clientHeight;
    return Math.max(0, Math.min(max, pts[i].y - scroller.clientHeight / 2));
  }
  function glide(to: number, ms: number, alive: () => boolean = () => true) {
    return new Promise<void>((resolve) => {
      cancelAnimationFrame(raf);
      const from = scroller.scrollTop, t0 = performance.now();
      const step = (now: number) => {
        if (!alive()) return resolve();
        const t = Math.min(1, (now - t0) / ms);
        scroller.scrollTop = from + (to - from) * ease(t);
        if (t < 1) raf = requestAnimationFrame(step); else resolve();
      };
      raf = requestAnimationFrame(step);
    });
  }
  async function tour() {
    if (!scroller || !n) return;
    const id = ++tourId;
    const alive = () => id === tourId;
    if (reduced() || n < 2) { scroller.scrollTop = topFor(cur); return; }
    touring = true;
    scroller.scrollTop = scroller.scrollHeight;            // start at Level 1
    await sleep(300);
    if (alive()) await glide(topFor(n - 1), Math.min(2600, 700 + n * 140), alive);   // up to the last level
    if (alive()) await sleep(650);
    if (alive()) await glide(topFor(cur), Math.min(2000, 600 + (n - 1 - cur) * 120), alive); // back to you
    if (alive()) touring = false;
  }
  function stopTour() { tourId++; cancelAnimationFrame(raf); touring = false; }
  /** Clicking a level opens its course; a locked one is selected instead so
   *  the panel can say what unlocks it, and it gives a little shake. */
  let shaking: number | null = null;
  function openLevel(node: PathNode, i: number) {
    stopTour();
    if (kind(node, i) !== 'locked' && node.module_id) { onNodeClick?.(node); return; }
    selected = i;
    shaking = i;
    setTimeout(() => { if (shaking === i) shaking = null; }, 450);
  }
  async function focusLevel(i: number) {
    stopTour(); selected = i; await tick();
    if (reduced()) scroller.scrollTop = topFor(i); else await glide(topFor(i), 650);
  }

  // Levels pop in as the camera reaches them.
  let seen = new Set<number>();
  let io: IntersectionObserver | null = null;
  function inView(node: HTMLElement, i: number) {
    node.dataset.lvl = String(i);
    // The observer is created on mount; levels rendered before that are
    // registered there. Reduced motion shows everything at once.
    if (io) io.observe(node);
    else if (reduced()) { seen.add(i); seen = seen; }
    return { destroy: () => io?.unobserve(node) };
  }

  onMount(async () => {
    if (!reduced() && 'IntersectionObserver' in window) {
      io = new IntersectionObserver((entries) => {
        for (const e of entries) if (e.isIntersecting) seen.add(Number((e.target as HTMLElement).dataset.lvl));
        seen = seen;
      }, { root: scroller, rootMargin: '0px 0px -6% 0px', threshold: 0.2 });
    }
    await tick();
    // Register levels rendered before the observer existed.
    scroller?.querySelectorAll<HTMLElement>('[data-lvl]').forEach((el) => io?.observe(el));
    if (!io) seen = new Set(path.nodes.map((_, i) => i));
    requestAnimationFrame(() => tour());
  });
  onDestroy(() => { tourId++; cancelAnimationFrame(raf); io?.disconnect(); });

  const TONES = ['sky', 'lilac', 'mint', 'butter', 'peach'];
</script>

<div class="trail-wrap">
  <!-- ---------- header ---------- -->
  <header class="trail-head ui-rise">
    <span class="mark" aria-hidden="true"><Icon name={isRidge ? 'trend' : 'route'} size={22} /></span>
    <div class="head-txt">
      <span class="variant">{isRidge ? 'Ridge climb' : 'Trail'}{#if path.department} · {path.department}{/if}</span>
      <h1>{path.title}</h1>
      {#if path.description}<p>{path.description}</p>{/if}
    </div>
    <div class="head-stats">
      <div class="ring" style="--p:{pct}" aria-label="{pct}% mastered">
        <svg viewBox="0 0 44 44" aria-hidden="true">
          <circle class="r-track" cx="22" cy="22" r="18" />
          <circle class="r-arc" cx="22" cy="22" r="18" pathLength="100" style="stroke-dasharray:{pct} 100" />
        </svg>
        <span><b use:countUp={pct}></b>%</span>
      </div>
      <div class="chips">
        <span class="chip lilac"><Icon name="target" size={14} /> Level <b use:countUp={n ? cur + 1 : 0}></b> of {n}</span>
        <span class="chip mint"><Icon name="award" size={14} /> <b use:countUp={mastered.size}></b> mastered</span>
      </div>
    </div>
  </header>

  {#if !n}
    <div class="empty ui-rise" style="--i:1">
      <span class="empty-ico"><Icon name="route" size={26} /></span>
      <h2>No levels on this path yet</h2>
      <p>Levels appear here once your admin adds courses to the path.</p>
    </div>
  {:else}
    <div class="layout">
      <!-- ---------- the climb ---------- -->
      <div class="trail-card ui-rise" style="--i:1">
        <div class="tools">
          <button class="tool" on:click={() => focusLevel(cur)}><Icon name="target" size={15} /> My level</button>
          <button class="tool" on:click={() => { stopTour(); tour(); }} disabled={touring}>
            <Icon name="refresh" size={15} /> {touring ? 'Touring…' : 'Replay tour'}
          </button>
        </div>

        <div
          class="scroller" class:ridge={isRidge} bind:this={scroller}
          on:wheel={stopTour} on:touchstart={stopTour} on:pointerdown={stopTour}
        >
          <div class="stage" bind:clientWidth={stageW} style="height:{stageH}px">
            <!-- backdrop: peaks for a ridge climb, soft contour rings for a trail -->
            {#if isRidge}
              <svg class="peaks" viewBox="0 0 600 260" preserveAspectRatio="none" aria-hidden="true">
                <path d="M0,200 L90,110 L150,160 L250,40 L330,140 L410,80 L520,170 L600,120 L600,260 L0,260 Z" class="pk1" />
                <path d="M0,240 L70,170 L170,220 L270,130 L360,210 L450,150 L600,230 L600,260 L0,260 Z" class="pk2" />
              </svg>
            {/if}

            <div class="summit" style="top:{Math.max(18, (pts[n - 1]?.y ?? 0) - 130)}px" class:reached={done}>
              <span class="summit-star"><Icon name="star" size={20} /></span>
              <b>{done ? 'Path complete' : 'Summit'}</b>
            </div>

            <svg class="route" width={stageW} height={stageH} viewBox="0 0 {stageW} {stageH}" aria-hidden="true">
              <path d={ahead} class="ahead" />
              <path d={walked} class="walked-shadow" />
              <path d={walked} class="walked" pathLength="1" />
            </svg>

            {#each pts as p (p.i)}
              {@const k = kind(p.node, p.i)}
              {@const right = p.x < stageW / 2}
              <div
                class="lvl {k}" class:current={p.i === cur} class:sel={p.i === selected} class:seen={seen.has(p.i)}
                class:summit-lvl={p.node.is_summit} class:shake={shaking === p.i}
                style="left:{p.x}px; top:{p.y}px; --p:{prog(p.node)}"
                use:inView={p.i}
              >
                {#if p.i === cur && !done}
                  <span class="you" aria-hidden="true">
                    <Avatar src={$auth.user?.avatar_url} name={$auth.user?.full_name} size={30} />
                    <b>You</b>
                  </span>
                {/if}
                <button class="node" on:click={() => openLevel(p.node, p.i)} aria-label="Level {p.i + 1}: {p.node.title} ({KIND[k].label})">
                  {#if k === 'in_progress'}<span class="prog-ring" aria-hidden="true"></span>{/if}
                  <span class="face"><Icon name={nodeIcon(p.node, p.i)} size={p.i === cur ? 24 : 20} stroke={k === 'locked' ? 1.6 : 2.2} /></span>
                  <span class="num">{p.i + 1}</span>
                </button>
                <button class="tag" class:right on:click={() => openLevel(p.node, p.i)} tabindex="-1">
                  <small>Level {p.i + 1}</small>
                  <b>{p.node.title}</b>
                </button>
              </div>
            {/each}

            <div class="trailhead"><Icon name="flag" size={14} /> Start</div>
          </div>
        </div>
      </div>

      <!-- ---------- selected level ---------- -->
      <aside class="side">
        {#if sel}
          {#key selected}
            <div class="detail ui-rise">
              <div class="d-art {TONES[selected % TONES.length]}">
                {#if sel.thumbnail_url}
                  <Thumb src={sel.thumbnail_url} />
                {:else}
                  <Icon name={nodeIcon(sel, selected)} size={40} stroke={1.5} />
                {/if}
                <span class="d-lvl">Level {selected + 1} of {n}</span>
              </div>
              <span class="ui-pill {KIND[selKind].tone}"><Icon name={KIND[selKind].icon} size={13} /> {KIND[selKind].label}</span>
              <h2>{sel.title}</h2>
              <div class="d-facts">
                {#if sel.module_category}<span><Icon name="hash" size={13} /> {sel.module_category}</span>{/if}
                <span><Icon name="film" size={13} /> {sel.total_episodes} episode{sel.total_episodes === 1 ? '' : 's'}</span>
                {#if sel.node_type === 'milestone'}<span><Icon name="flag" size={13} /> Milestone</span>{/if}
                {#if sel.is_summit}<span><Icon name="star" size={13} /> Summit</span>{/if}
              </div>
              <div class="d-meter">
                <span class="bar"><span style="--w:{prog(sel)}%"></span></span>
                <b>{prog(sel)}%</b>
              </div>
              {#if selKind === 'locked'}
                <p class="hint"><Icon name="lock" size={14} /> Master level {selected} to unlock this one.</p>
              {:else if selKind === 'completed'}
                <p class="hint"><Icon name="info" size={14} /> Watched in full. Pass its check to master the level.</p>
              {/if}
              <button class="btn-primary cta" disabled={selKind === 'locked' || !sel.module_id} on:click={() => onNodeClick?.(sel)}>
                {#if selKind !== 'locked'}<span class="cta-ico"><Icon name="play" size={12} stroke={0} /></span>{/if}
                {cta(sel, selKind)}
              </button>
            </div>
          {/key}
        {/if}

        <div class="levels ui-rise" style="--i:2">
          <h3>All levels</h3>
          <ol>
            {#each path.nodes as node, i}
              {@const k = kind(node, i)}
              <li>
                <button class="lv-row {k}" class:on={i === selected} on:click={() => focusLevel(i)}>
                  <span class="lv-ico"><Icon name={nodeIcon(node, i)} size={13} stroke={2} /></span>
                  <span class="lv-txt"><small>Level {i + 1}{#if i === cur && !done} · you are here{/if}</small><b>{node.title}</b></span>
                  <span class="lv-pct">{prog(node)}%</span>
                </button>
              </li>
            {/each}
          </ol>
        </div>
      </aside>
    </div>
  {/if}
</div>

<style>
  /* ---------- header ---------- */
  .trail-head {
    display: flex; align-items: center; gap: 1.1rem; flex-wrap: wrap;
    padding: 1.15rem 1.3rem; margin-bottom: 1.1rem; border-radius: 30px;
    background: var(--surface); box-shadow: var(--shadow-sm);
  }
  .mark {
    flex: none; width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center;
    background: var(--tile-mint); color: var(--tile-ink); rotate: -8deg;
    animation: pop 560ms var(--ease-out) 200ms backwards;
    transition: rotate var(--dur-3) var(--ease-out);
  }
  .trail-head:hover .mark { rotate: 8deg; }
  .head-txt { flex: 1; min-width: 220px; display: flex; flex-direction: column; gap: 0.2rem; }
  .variant { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  .head-txt h1 { font-size: clamp(1.4rem, 1rem + 1.3vw, 2.1rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.1; }
  .head-txt p {
    color: var(--muted); font-size: 0.9rem; line-height: 1.5; max-width: 60ch;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .head-stats { display: flex; align-items: center; gap: 0.9rem; }
  .ring { position: relative; width: 74px; height: 74px; flex: none; }
  .ring svg { width: 100%; height: 100%; rotate: -90deg; }
  .ring circle { fill: none; stroke-width: 5; }
  .r-track { stroke: var(--surface3); }
  .r-arc { stroke: var(--success); stroke-linecap: round; animation: ring-draw 1.3s var(--ease-out) 300ms backwards; }
  @keyframes ring-draw { from { stroke-dasharray: 0 100; } }
  .ring > span { position: absolute; inset: 0; display: grid; place-items: center; grid-auto-flow: column; align-content: center; font-size: 0.8rem; font-weight: 600; color: var(--muted); }
  .ring b { font-size: 1.2rem; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
  .chips { display: flex; flex-direction: column; gap: 0.4rem; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.35rem; height: 30px; padding: 0 0.75rem;
    border-radius: 99px; font-size: 0.8rem; font-weight: 600; color: var(--tile-ink); white-space: nowrap;
  }
  .chip b { font-variant-numeric: tabular-nums; }
  .chip.lilac { background: var(--tile-lilac); }
  .chip.mint { background: var(--tile-mint); }

  /* ---------- layout ---------- */
  .layout { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: 1.25rem; align-items: start; }

  .trail-card {
    position: relative; border-radius: 32px; overflow: hidden;
    background: var(--surface); box-shadow: var(--shadow-sm);
  }
  .tools { position: absolute; top: 0.9rem; right: 0.9rem; z-index: 20; display: flex; gap: 0.4rem; }
  .tool {
    display: inline-flex; align-items: center; gap: 0.35rem; height: 36px; padding: 0 0.85rem;
    border-radius: 99px; font-size: 0.8rem; font-weight: 600;
    background: var(--surface); color: var(--text); box-shadow: var(--shadow);
    transition: translate var(--dur-2) var(--ease-out), background-color var(--dur-2);
  }
  .tool:hover:not(:disabled) { translate: 0 -2px; background: var(--surface2); }
  .tool:disabled { opacity: 0.6; cursor: default; }
  .tool:disabled :global(.icon) { animation: spin 1.1s linear infinite; }
  @keyframes spin { to { rotate: 360deg; } }

  .scroller {
    position: relative; height: max(520px, calc(100vh - 290px)); overflow-y: auto; overflow-x: hidden;
    scrollbar-width: thin;
    background:
      radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--text) 9%, transparent) 1px, transparent 0) 0 0 / 22px 22px,
      var(--bg-alt);
  }
  .scroller.ridge {
    background:
      linear-gradient(180deg, color-mix(in srgb, var(--tile-sky) 70%, transparent), transparent 520px),
      radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--text) 8%, transparent) 1px, transparent 0) 0 0 / 22px 22px,
      var(--bg-alt);
  }
  .stage { position: relative; width: 100%; }

  .peaks { position: absolute; top: 0; left: 0; width: 100%; height: 260px; }
  .pk1 { fill: color-mix(in srgb, var(--tile-lilac) 80%, transparent); }
  .pk2 { fill: color-mix(in srgb, var(--tile-mint) 85%, transparent); }

  .summit {
    position: absolute; left: 50%; translate: -50% 0; z-index: 4;
    display: flex; flex-direction: column; align-items: center; gap: 0.2rem;
    padding: 0.55rem 1rem 0.5rem; border-radius: 20px;
    background: var(--surface); box-shadow: var(--shadow);
    animation: fade 700ms var(--ease-out) 400ms backwards;
  }
  .summit b { font-size: 0.82rem; }
  .summit-star {
    width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center;
    background: var(--tile-butter); color: var(--tile-ink); animation: float 4s var(--ease-in-out) infinite;
  }
  .summit-star :global(svg) { fill: currentColor; }
  .summit.reached .summit-star { background: var(--gold); }

  /* ---------- route ---------- */
  .route { position: absolute; inset: 0; overflow: visible; pointer-events: none; }
  .route path { fill: none; stroke-linecap: round; stroke-linejoin: round; }
  .ahead { stroke: color-mix(in srgb, var(--muted) 55%, transparent); stroke-width: 4; stroke-dasharray: 0.1 14; }
  .walked-shadow { stroke: color-mix(in srgb, var(--brand) 16%, transparent); stroke-width: 18; }
  .walked {
    stroke: var(--brand); stroke-width: 6;
    stroke-dasharray: 1; stroke-dashoffset: 0;
    animation: route-draw 1.6s var(--ease-out) 250ms backwards;
  }
  @keyframes route-draw { from { stroke-dashoffset: 1; } }

  /* ---------- levels ---------- */
  .lvl { position: absolute; z-index: 6; translate: -50% -50%; }
  .lvl:not(.seen) .node, .lvl:not(.seen) .tag { opacity: 0; scale: 0.5; }
  .lvl.seen .node { animation: lvl-pop 520ms var(--ease-out) backwards; }
  .lvl.seen .tag { animation: tag-in 520ms var(--ease-out) 90ms backwards; }
  @keyframes lvl-pop { from { opacity: 0; scale: 0.4; } 70% { scale: 1.08; } to { opacity: 1; scale: 1; } }
  @keyframes tag-in { from { opacity: 0; translate: 0 8px; } }

  .node {
    position: relative; width: 68px; height: 68px; border-radius: 50%;
    display: grid; place-items: center; padding: 0;
    background: var(--surface); color: var(--text);
    box-shadow: 0 6px 0 color-mix(in srgb, var(--text) 14%, transparent), var(--shadow);
    transition: scale var(--dur-3) var(--ease-out), translate var(--dur-2) var(--ease-out), box-shadow var(--dur-2);
  }
  .node:hover { scale: 1.08; }
  /* Pressed: the coin sinks onto its edge. */
  .node:active { translate: 0 4px; box-shadow: 0 2px 0 color-mix(in srgb, var(--text) 14%, transparent), var(--shadow-sm); }
  .face { position: relative; z-index: 1; display: grid; place-items: center; }
  .num {
    position: absolute; right: -4px; bottom: -4px; z-index: 2;
    min-width: 24px; height: 24px; padding: 0 5px; border-radius: 99px;
    display: grid; place-items: center; font-size: 0.72rem; font-weight: 800;
    background: var(--accent); color: var(--on-accent); border: 2px solid var(--surface);
  }
  .mastered .node { background: var(--tile-butter); color: var(--tile-ink); }
  .completed .node { background: var(--tile-mint); color: var(--tile-ink); }
  .in_progress .node { background: var(--tile-lilac); color: var(--tile-ink); }
  .unlocked .node { background: var(--tile-sky); color: var(--tile-ink); }
  .locked .node { background: var(--surface2); color: var(--muted); box-shadow: 0 6px 0 color-mix(in srgb, var(--text) 8%, transparent); }
  .locked .num { background: var(--surface3); color: var(--muted); }
  .summit-lvl .node { width: 78px; height: 78px; }
  .summit-lvl.mastered .face :global(svg) { fill: currentColor; }

  /* Ring showing how far into the course this level is. */
  .prog-ring {
    position: absolute; inset: -7px; border-radius: 50%;
    background: conic-gradient(var(--brand) calc(var(--p) * 1%), color-mix(in srgb, var(--text) 10%, transparent) 0);
    -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 5px), #000 calc(100% - 4px));
            mask: radial-gradient(farthest-side, transparent calc(100% - 5px), #000 calc(100% - 4px));
  }

  /* The learner's own level: bigger, pulsing, with their avatar above it. */
  .current .node { width: 84px; height: 84px; }
  .lvl.seen.current .node { animation: lvl-pop 520ms var(--ease-out) backwards, here 2.2s var(--ease-out) 900ms infinite; }
  @keyframes here {
    0% { box-shadow: 0 6px 0 color-mix(in srgb, var(--text) 14%, transparent), 0 0 0 0 color-mix(in srgb, var(--brand) 45%, transparent); }
    100% { box-shadow: 0 6px 0 color-mix(in srgb, var(--text) 14%, transparent), 0 0 0 18px transparent; }
  }
  .you {
    position: absolute; left: 50%; bottom: calc(100% + 12px); translate: -50% 0; z-index: 3;
    display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.2rem 0.65rem 0.2rem 0.2rem;
    border-radius: 99px; background: var(--accent); color: var(--on-accent); box-shadow: var(--shadow-md);
    font-size: 0.75rem; white-space: nowrap;
    animation: bob 2.4s var(--ease-in-out) infinite;
  }
  .you::after {
    content: ''; position: absolute; left: 50%; top: 100%; translate: -50% -1px;
    border: 6px solid transparent; border-top-color: var(--accent);
  }
  @keyframes bob { 0%, 100% { translate: -50% 0; } 50% { translate: -50% -5px; } }

  .sel:not(.current) .node { outline: 3px solid var(--accent); outline-offset: 4px; }
  .lvl.shake .node { animation: lock-shake 420ms var(--ease-out); }
  @keyframes lock-shake { 20% { translate: -5px 0; } 40% { translate: 5px 0; } 60% { translate: -3px 0; } 80% { translate: 3px 0; } }

  .tag {
    position: absolute; top: 50%; right: calc(100% + 14px); translate: 0 -50%;
    display: flex; flex-direction: column; align-items: flex-end; text-align: right;
    width: max-content; max-width: min(220px, 34vw); padding: 0.45rem 0.75rem; border-radius: 14px;
    background: var(--surface); box-shadow: var(--shadow-sm); color: var(--text);
    transition: translate var(--dur-2) var(--ease-out), box-shadow var(--dur-2);
  }
  .tag.right { right: auto; left: calc(100% + 14px); align-items: flex-start; text-align: left; }
  .tag:hover { box-shadow: var(--shadow); }
  .tag small { font-size: 0.66rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
  .tag b {
    font-size: 0.86rem; font-weight: 600; line-height: 1.3;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .locked .tag { opacity: 0.7; }
  .current .tag, .sel .tag { box-shadow: 0 0 0 2px var(--accent), var(--shadow); }

  .trailhead {
    position: absolute; left: 50%; bottom: 26px; translate: -50% 0;
    display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.35rem 0.8rem; border-radius: 99px;
    background: var(--surface); color: var(--muted); font-size: 0.78rem; font-weight: 600; box-shadow: var(--shadow-sm);
  }

  /* ---------- side panel ---------- */
  .side { position: sticky; top: 1.25rem; display: flex; flex-direction: column; gap: 1rem; }
  .detail {
    display: flex; flex-direction: column; align-items: flex-start; gap: 0.6rem;
    padding: 0.7rem 0.7rem 1rem; border-radius: 28px; background: var(--surface); box-shadow: var(--shadow-sm);
  }
  .d-art {
    position: relative; width: 100%; aspect-ratio: 16 / 9; border-radius: 22px; overflow: hidden;
    display: grid; place-items: center; color: var(--tile-ink);
  }
  .detail:hover .d-art :global(.thumb-media) { scale: 1.05; }
  .d-art.sky { background: var(--tile-sky); } .d-art.lilac { background: var(--tile-lilac); }
  .d-art.mint { background: var(--tile-mint); } .d-art.butter { background: var(--tile-butter); }
  .d-art.peach { background: var(--tile-peach); }
  .d-lvl {
    position: absolute; left: 10px; top: 10px; padding: 0.2rem 0.6rem; border-radius: 99px;
    background: var(--surface); color: var(--text); font-size: 0.72rem; font-weight: 700;
  }
  .detail > .ui-pill { margin: 0.2rem 0.35rem 0; }
  .detail h2 {
    margin: 0 0.35rem; font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.2;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .d-facts { display: flex; flex-wrap: wrap; gap: 0.35rem; margin: 0 0.35rem; }
  .d-facts span {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 26px; padding: 0 0.6rem; border-radius: 99px;
    background: var(--surface2); color: var(--text-secondary); font-size: 0.74rem; font-weight: 600; text-transform: capitalize;
  }
  .d-meter { display: flex; align-items: center; gap: 0.6rem; width: calc(100% - 0.7rem); margin: 0.2rem 0.35rem 0; }
  .d-meter .bar { flex: 1; height: 7px; border-radius: 99px; overflow: hidden; background: var(--surface3); }
  .d-meter .bar span {
    display: block; height: 100%; width: var(--w); border-radius: inherit; background: var(--brand);
    transform-origin: left; animation: grow 900ms var(--ease-out) 150ms backwards;
  }
  @keyframes grow { from { transform: scaleX(0); } }
  .d-meter b { font-size: 0.8rem; font-variant-numeric: tabular-nums; }
  .hint { display: flex; gap: 0.4rem; align-items: flex-start; margin: 0 0.35rem; font-size: 0.8rem; color: var(--muted); line-height: 1.45; }
  .hint :global(.icon) { flex: none; margin-top: 2px; }
  .cta { margin: 0.3rem 0.35rem 0; width: calc(100% - 0.7rem); justify-content: center; }
  .cta:disabled { opacity: 0.5; cursor: not-allowed; }
  .cta-ico {
    width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center;
    background: var(--on-accent); color: var(--accent); transition: transform var(--dur-3) var(--ease-out);
  }
  .cta-ico :global(svg) { fill: currentColor; translate: 1px 0; }
  .cta:hover:not(:disabled) .cta-ico { transform: scale(1.15) rotate(-8deg); }

  .levels { padding: 0.9rem 0.6rem 0.6rem; border-radius: 28px; background: var(--bg-alt); }
  .levels h3 { font-size: 1rem; font-weight: 700; padding: 0 0.5rem 0.5rem; }
  .levels ol { list-style: none; display: flex; flex-direction: column; gap: 0.25rem; max-height: 340px; overflow-y: auto; scrollbar-width: thin; }
  .lv-row {
    width: 100%; display: flex; align-items: center; gap: 0.6rem; padding: 0.45rem 0.55rem; border-radius: 16px;
    text-align: left; color: var(--text); background: transparent;
    transition: background-color var(--dur-2), translate var(--dur-2) var(--ease-out);
  }
  .lv-row:hover { background: var(--surface); translate: 3px 0; }
  .lv-row.on { background: var(--surface); box-shadow: var(--shadow-sm); }
  .lv-ico {
    flex: none; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center;
    background: var(--surface2); color: var(--muted);
  }
  .lv-row.mastered .lv-ico { background: var(--tile-butter); color: var(--tile-ink); }
  .lv-row.completed .lv-ico { background: var(--tile-mint); color: var(--tile-ink); }
  .lv-row.in_progress .lv-ico { background: var(--tile-lilac); color: var(--tile-ink); }
  .lv-row.unlocked .lv-ico { background: var(--tile-sky); color: var(--tile-ink); }
  .lv-txt { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .lv-txt small { font-size: 0.66rem; color: var(--muted); font-weight: 600; }
  .lv-txt b { font-size: 0.84rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .lv-row.locked .lv-txt b { color: var(--muted); }
  .lv-pct { font-size: 0.74rem; font-weight: 700; color: var(--muted); font-variant-numeric: tabular-nums; }

  .empty { display: flex; flex-direction: column; align-items: center; gap: 0.7rem; text-align: center; padding: 3.5rem 1.5rem; border-radius: 32px; background: var(--surface); }
  .empty p { color: var(--muted); }
  .empty-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }

  @media (max-width: 1100px) {
    .layout { grid-template-columns: 1fr; }
    .side { position: static; display: grid; grid-template-columns: 1fr 1fr; align-items: start; }
  }
  @media (max-width: 720px) {
    .side { grid-template-columns: 1fr; }
    .scroller { height: max(480px, calc(100vh - 240px)); }
    .node { width: 58px; height: 58px; }
    .current .node { width: 70px; height: 70px; }
    .tag { max-width: 40vw; }
    .head-stats { width: 100%; }
  }
</style>
