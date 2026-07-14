<script lang="ts">
  import type { PathDetail, PathNode } from '$lib/api/client';

  export let path: PathDetail;
  export let onNodeClick: ((node: PathNode) => void) | undefined = undefined;

  // * Geometry: serpentine path, oldest node at bottom, newest at top (port of JourneyV2)
  const W = 368;
  const BAND = 150;
  const TOP = 118;
  const STAGE = TOP + path.nodes.length * BAND + 40;

  interface Pt { x: number; y: number; node: PathNode; i: number }

  // * Compute serpentine points (port of JourneyV2 geometry)
  function computePts(nodes: PathNode[]): Pt[] {
    return nodes.map((node, i) => {
      const t = nodes.length > 1 ? i / (nodes.length - 1) : 0;
      const ltr = i % 2 === 0;
      const x = 40 + (ltr ? t : 1 - t) * 288;
      const y = TOP + (nodes.length - 1 - i) * BAND + 116 + Math.sin(i * 1.9) * 7;
      return { x, y, node, i };
    });
  }

  $: pts = computePts(path.nodes);
  $: currentIdx = path.current_node;
  $: masteredSet = new Set(path.mastered_nodes);
  $: unlockedSet = new Set(path.unlocked_nodes);

  function seg(pts: Pt[]): string {
    if (pts.length === 0) return '';
    let d = 'M' + pts[0].x.toFixed(1) + ',' + pts[0].y.toFixed(1);
    for (let i = 1; i < pts.length; i++) {
      const q = pts[i - 1];
      const p = pts[i];
      d += ' Q' + q.x.toFixed(1) + ',' + ((q.y + p.y) / 2).toFixed(1)
        + ' ' + ((q.x + p.x) / 2).toFixed(1) + ',' + ((q.y + p.y) / 2).toFixed(1)
        + ' T' + p.x.toFixed(1) + ',' + p.y.toFixed(1);
    }
    return d;
  }

  $: walked = seg(pts.filter(p => p.i <= currentIdx || masteredSet.has(p.i)));
  $: ahead = seg(pts.filter(p => p.i >= currentIdx && !masteredSet.has(p.i)));

  const isRidge = path.variant === 'ridge';
</script>

<div class="trail-screen">
  <div class="trail-topbar">
    <span class="trail-title">{path.title}</span>
    <span class="trail-meta">{path.mastered_count}/{path.total_nodes} mastered · {path.completion_percentage}%</span>
  </div>

  <div class="trail-scroll">
    {#if isRidge}
      <div class="ridge-rail">
        <span class="rail-pct">{Math.round(path.completion_percentage)}%</span>
        <span class="rail-track"><i style="height: {path.completion_percentage}%"></i></span>
        <span class="rail-cap">{isRidge ? 'altitude' : 'progress'}</span>
      </div>
    {/if}

    <div class="trail-stage" class:ridge={isRidge} style="height: {STAGE}px">
      {#if isRidge}
        <svg class="ridge-back" width="100%" height="420" viewBox="0 0 368 420" preserveAspectRatio="none">
          <path d="M0,180 L70,96 L120,150 L184,54 L240,130 L300,84 L368,168 L368,420 L0,420 Z" fill="var(--accent)" opacity="0.08" />
          <path d="M0,250 L60,170 L130,225 L200,140 L270,210 L330,165 L368,230 L368,420 L0,420 Z" fill="var(--accent)" opacity="0.13" />
          <path d="M0,330 L80,250 L160,310 L250,235 L320,300 L368,270 L368,420 L0,420 Z" fill="var(--accent)" opacity="0.19" />
        </svg>
        {#if path.nodes[path.nodes.length - 1]?.is_summit}
          <div class="summit-marker" style="top: 6px">
            <span class="summit-star">✦</span>
            <b>Summit</b>
          </div>
        {/if}
      {:else}
        {#each path.nodes as node, wi}
          <div class="terrain-band" data-alt={wi % 2} style="top: {TOP + (path.nodes.length - 1 - wi) * BAND}px; height: {BAND}px"></div>
        {/each}
      {/if}

      <svg class="trail-path" width="100%" height={STAGE} viewBox={`0 0 368 ${STAGE}`}>
        <path d={ahead} fill="none" stroke="var(--muted)" stroke-width="2" stroke-dasharray="1 8" stroke-linecap="round" opacity="0.55" />
        <path d={walked} fill="none" stroke={isRidge ? 'var(--accent)' : 'var(--gold)'} stroke-width={isRidge ? '2.5' : '3'} stroke-dasharray={isRidge ? '' : '7 6'} stroke-linecap="round" opacity="0.8" />
      </svg>

      {#each pts as p}
        <button
          class="trail-node node-{p.node.status}"
          class:is-summit={p.node.is_summit}
          class:is-current={p.i === currentIdx}
          style="left: {p.x}px; top: {p.y}px; transform: translate(-50%,-50%)"
          on:click={() => onNodeClick?.(p.node)}
          aria-label={p.node.title}
        >
          {#if p.i === currentIdx}
            <span class="here-label">You are here</span>
            <span class="here-dot">{p.i + 1}</span>
          {:else if masteredSet.has(p.i)}
            {#if p.node.is_summit}
              <span class="summit-icon">✦</span>
            {:else if p.node.node_type === 'milestone'}
              <span class="milestone-icon">⚑</span>
            {:else}
              <span class="mastered-icon">✓</span>
            {/if}
          {:else if unlockedSet.has(p.i)}
            <span class="unlocked-dot"></span>
          {:else}
            <span class="locked-dot"></span>
          {/if}
        </button>
      {/each}

      <div class="trail-base">{path.nodes[0]?.title ?? 'Trailhead'}</div>
    </div>
  </div>
</div>

<style>
  .trail-screen { display: flex; flex-direction: column; height: calc(100vh - 64px); }
  .trail-topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 2rem; border-bottom: 1px solid var(--border);
  }
  .trail-title { font-size: 1.2rem; font-weight: 800; }
  .trail-meta { font-size: 0.85rem; color: var(--gold); font-weight: 700; }
  .trail-scroll { position: relative; overflow-y: auto; overflow-x: hidden; flex: 1; }
  .trail-stage { position: relative; width: 368px; margin: 0 auto; }
  .trail-stage.ridge {
    background: linear-gradient(180deg,
      rgba(229,9,20,0.24) 0,
      rgba(229,9,20,0.13) 260px,
      rgba(229,9,20,0.06) 560px,
      transparent 900px);
    border-radius: 0 0 24px 24px;
  }
  .ridge-back { position: absolute; top: 0; left: 0; }
  .trail-path { position: absolute; top: 0; left: 0; }
  .ridge-rail {
    position: fixed; top: 80px; right: 20px; z-index: 45;
    display: flex; flex-direction: column; align-items: center; gap: 5px;
    padding: 9px 8px; border-radius: 999px;
    background: var(--surface); border: 1px solid var(--border);
  }
  .rail-pct { font-size: 0.7rem; font-weight: 800; color: var(--text); }
  .rail-track {
    position: relative; width: 5px; height: 74px; border-radius: 999px;
    background: var(--surface2); overflow: hidden; display: block;
  }
  .rail-track i {
    position: absolute; bottom: 0; left: 0; right: 0; border-radius: 999px;
    background: linear-gradient(0deg, var(--accent), var(--gold));
  }
  .rail-cap { font-size: 0.55rem; text-transform: uppercase; color: var(--muted); letter-spacing: 0.08em; }
  .summit-marker {
    position: absolute; left: 50%; transform: translateX(-50%); z-index: 5;
    display: flex; flex-direction: column; align-items: center; gap: 1px;
  }
  .summit-star { font-size: 1.3rem; color: var(--gold); text-shadow: 0 0 14px rgba(245,197,24,0.65); }
  .summit-marker b { font-size: 0.9rem; }
  .terrain-band { position: absolute; left: 0; right: 0; }
  .terrain-band[data-alt="0"] { background: rgba(229,9,20,0.05); }
  .terrain-band[data-alt="1"] { background: rgba(46,204,113,0.04); }

  .trail-node {
    position: absolute; cursor: pointer; z-index: 5;
    display: flex; align-items: center; justify-content: center;
    border: none; background: none; padding: 0;
    animation: nodeIn 0.4s cubic-bezier(0.34,1.56,0.64,1) both;
  }
  .here-label {
    position: absolute; bottom: calc(100% + 12px); left: 50%; transform: translateX(-50%);
    background: var(--accent); color: #fff; font-size: 0.6rem; font-weight: 800;
    letter-spacing: 0.07em; text-transform: uppercase; padding: 4px 8px;
    border-radius: 999px; white-space: nowrap;
    animation: bob 2.6s ease-in-out infinite;
  }
  .here-dot {
    width: 42px; height: 42px; border-radius: 999px;
    background: var(--accent); color: #fff;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem; font-weight: 800;
    border: 2px solid var(--bg);
    box-shadow: 0 0 0 3px var(--accent), 0 10px 22px -8px rgba(0,0,0,0.4);
  }
  .mastered-icon {
    width: 28px; height: 28px; border-radius: 999px;
    border: 1.5px solid var(--success); background: rgba(46,204,113,0.18);
    color: var(--success); display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 800;
    box-shadow: 0 3px 10px -3px rgba(0,0,0,0.25);
  }
  .milestone-icon {
    width: 34px; height: 34px; border-radius: 999px;
    border: 1.5px solid var(--accent);
    background: rgba(229,9,20,0.15);
    color: var(--accent); display: flex; align-items: center; justify-content: center;
    font-size: 0.9rem;
    box-shadow: 0 0 0 5px rgba(229,9,20,0.09);
  }
  .summit-icon {
    width: 34px; height: 34px; border-radius: 999px;
    border: 1.5px solid var(--gold);
    background: rgba(245,197,24,0.2);
    color: var(--gold); display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem;
    box-shadow: 0 0 0 5px rgba(245,197,24,0.12);
  }
  .unlocked-dot {
    width: 20px; height: 20px; border-radius: 999px;
    border: 1.5px solid var(--accent);
    background: var(--surface);
  }
  .locked-dot {
    width: 12px; height: 12px; border-radius: 999px;
    border: 1.5px dashed var(--muted);
    opacity: 0.5;
  }
  .trail-base {
    position: absolute; bottom: 10px; left: 0; right: 0;
    text-align: center; font-size: 0.8rem; color: var(--muted);
  }
  @keyframes nodeIn { from { opacity: 0; transform: translate(-50%,-50%) scale(0.4); } to { opacity: 1; transform: translate(-50%,-50%) scale(1); } }
  @keyframes bob { 0%, 100% { transform: translateX(-50%) translateY(0); } 50% { transform: translateX(-50%) translateY(-4px); } }
</style>
