<script lang="ts">
  // The guided tour and the feature check, drawn over the studio (steps and
  // checks are in tour.ts). The tour spotlights one tool at a time; "Show
  // me" makes the edit and checks it works. The feature check lists every
  // check with its result, can run them all, copy a report, and put the
  // video's edits back to how they were before the tour. The studio stays
  // usable underneath throughout.
  import { onDestroy, onMount, tick } from 'svelte';
  import { get } from 'svelte/store';
  import { STEPS, type Ctx, type Result } from './tour';
  import { useStudio } from './studio';

  export let root: HTMLElement;
  export let mode: 'tour' | 'check';
  export let results: Record<string, Result> = {};
  // The edits as they were before the tour's first change; null once kept or undone.
  export let snapshot: string | null = null;
  export let onClose: () => void;

  const st = useStudio();
  const { doc } = st;
  const ctx: Ctx = { st, root };
  const RUNNABLE = STEPS.filter(s => s.run);

  let i = 0;
  $: step = STEPS[i];
  let running = '';
  let runAllAt = -1;

  // ---- running a check ----------------------------------------------------------
  async function run(id: string): Promise<Result | null> {
    const s = STEPS.find(x => x.id === id);
    if (!s?.run || running) return null;
    if (!snapshot) snapshot = JSON.stringify(get(doc));
    running = id;
    if (s.tab !== undefined) st.tab.set(s.tab);
    st.selected.set(null);
    st.mark.set({ in: null, out: null });
    results = { ...results, [id]: { status: 'running', note: 'Checking…' } };
    let r: Result;
    try { r = await s.run(ctx); }
    catch (e: any) { r = { status: 'fail', note: `Something went wrong: ${e?.message ?? e}` }; }
    st.pause();
    results = { ...results, [id]: r };
    running = '';
    return r;
  }

  async function runAll() {
    for (let n = 0; n < RUNNABLE.length; n++) {
      runAllAt = n;
      await run(RUNNABLE[n].id);
      await tick();
    }
    runAllAt = -1;
    st.tab.set(null);
    const f = RUNNABLE.filter(s => results[s.id]?.status === 'fail').length;
    st.say(f ? `${f} check${f === 1 ? '' : 's'} failed. See the list.` : 'Every check that could run passed.', f ? 'bad' : 'ok');
  }

  // ---- the tour -------------------------------------------------------------------
  let base = 0;
  async function go(n: number) {
    i = Math.max(0, Math.min(STEPS.length - 1, n));
    st.pause();
    const s = STEPS[i];
    if (s.tab !== undefined) st.tab.set(s.tab);
    base = s.baseline?.(ctx) ?? 0;
    await tick();
    if (s.target) root.querySelector(s.target)?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }
  // A step that needs the person (a voice-over) passes once they've done it.
  $: if (mode === 'tour' && step.watch && results[step.id]?.status !== 'pass' && ($doc, step.watch(ctx, base))) {
    results = { ...results, [step.id]: { status: 'pass', note: 'You recorded a voice-over: it is on the Audio row.' } };
  }

  // ---- spotlight --------------------------------------------------------------------
  let rect: DOMRect | null = null;
  let card: HTMLDivElement;
  let cardW = 360, cardH = 220;
  let raf = 0;
  function measure() {
    const sel = mode === 'tour' ? step.target : runAllAt >= 0 ? RUNNABLE[runAllAt]?.target : null;
    const el = sel ? root.querySelector(sel) : null;
    rect = el ? el.getBoundingClientRect() : null;
    raf = requestAnimationFrame(measure);
  }
  onMount(() => { raf = requestAnimationFrame(measure); go(0); });
  onDestroy(() => cancelAnimationFrame(raf));

  $: place = position(rect, cardW, cardH);
  function position(r: DOMRect | null, w: number, h: number): { x: number; y: number } {
    const vw = innerWidth, vh = innerHeight, m = 12;
    if (!r) return { x: (vw - w) / 2, y: (vh - h) / 2 };
    const cx = Math.min(vw - w - m, Math.max(m, r.left + r.width / 2 - w / 2));
    const cy = Math.min(vh - h - m, Math.max(m, r.top + r.height / 2 - h / 2));
    const options = [
      { x: cx, y: r.bottom + 14 },
      { x: cx, y: r.top - h - 14 },
      { x: r.right + 14, y: cy },
      { x: r.left - w - 14, y: cy },
    ];
    const fits = options.find(o => o.x >= m && o.y >= m && o.x + w <= vw - m && o.y + h <= vh - m);
    // A big target (the preview): sit inside it, at the bottom.
    return fits ?? { x: cx, y: Math.min(vh - h - m, Math.max(m, r.bottom - h - 16)) };
  }

  // ---- the check list ------------------------------------------------------------
  $: counts = RUNNABLE.reduce((a, s) => { const k = results[s.id]?.status ?? 'idle'; a[k] = (a[k] ?? 0) + 1; return a; }, {} as Record<string, number>);

  function undoTour() {
    if (!snapshot) return;
    const s = JSON.parse(snapshot);
    st.commit(d => { d.start = s.start; d.end = s.end; d.splits = s.splits; d.edits = s.edits; d.segments = s.segments; });
    snapshot = null;
    st.selected.set(null);
    st.ccOn.set(false);
    st.say("Back to how it was before the tour. (Ctrl+Z brings the tour's edits back.)");
  }
  function keep() {
    snapshot = null;
    st.say("Kept the tour's edits. Save to give them to learners, or undo them one by one.");
  }

  async function copyReport() {
    const icon = (s?: string) => (s === 'pass' ? '✓' : s === 'fail' ? '✗' : s === 'skip' ? '–' : '·');
    const ep = get(st.ep);
    const lines = [
      `Video studio feature check: ${ep.title} (${ep.id})`,
      `${new Date().toLocaleString()} · ${navigator.userAgent}`,
      '',
      ...RUNNABLE.map(s => `${icon(results[s.id]?.status)} ${s.title}: ${results[s.id]?.note ?? 'not checked'}`),
    ];
    try { await navigator.clipboard.writeText(lines.join('\n')); st.say('Report copied. Paste it into a message or ticket.'); }
    catch { st.say("The browser wouldn't copy. Select the list and copy it instead.", 'bad'); }
  }

  const ICON: Record<string, string> = { pass: '✓', fail: '✗', skip: '–', running: '…', idle: '·' };
  $: r = results[step.id];
</script>

{#if mode === 'tour' || runAllAt >= 0}
  {#if rect}
    <div class="spot" style="left:{rect.left - 6}px; top:{rect.top - 6}px; width:{rect.width + 12}px; height:{rect.height + 12}px"></div>
  {:else if mode === 'tour'}
    <div class="dim"></div>
  {/if}
{/if}

{#if mode === 'tour'}
  <div class="card" bind:this={card} bind:clientWidth={cardW} bind:clientHeight={cardH} style="left:{place.x}px; top:{place.y}px" role="dialog" aria-label="Studio tour">
    <div class="head">
      <span class="count">Step {i + 1} of {STEPS.length}</span>
      <button class="x" on:click={onClose} aria-label="Leave the tour" title="Leave the tour">✕</button>
    </div>
    <div class="dots" aria-hidden="true">
      {#each STEPS as s, n}<button class="d {results[s.id]?.status ?? ''}" class:now={n === i} on:click={() => go(n)} tabindex="-1" aria-label={s.title}></button>{/each}
    </div>
    <h3>{step.title}</h3>
    <p>{step.body}</p>
    {#if r}
      <div class="res {r.status}" role="status"><b>{ICON[r.status]}</b><span>{r.note}</span></div>
    {/if}
    <div class="btns">
      <button class="b ghost" on:click={() => go(i - 1)} disabled={i === 0 || !!running}>Back</button>
      {#if step.run}
        <button class="b try" on:click={() => run(step.id)} disabled={!!running}>{running === step.id ? 'Checking…' : r ? 'Check again' : 'Show me'}</button>
      {/if}
      {#if i < STEPS.length - 1}
        <button class="b next" on:click={() => go(i + 1)} disabled={!!running}>Next</button>
      {:else}
        <button class="b next" on:click={() => (mode = 'check')} disabled={!!running}>See the results</button>
      {/if}
    </div>
    <button class="link" on:click={() => (mode = 'check')}>Feature check: run every check at once</button>
  </div>
{:else}
  <div class="panel" role="dialog" aria-label="Feature check">
    <div class="head">
      <h3>Feature check</h3>
      <button class="x" on:click={onClose} aria-label="Close the feature check">✕</button>
    </div>
    <p class="sum">
      <span class="pass">✓ {counts.pass ?? 0} working</span>
      <span class="fail">✗ {counts.fail ?? 0} failed</span>
      <span class="skip">– {counts.skip ?? 0} couldn't run</span>
      <span>· {(counts.idle ?? 0) + (counts.running ?? 0)} not checked</span>
    </p>
    <ol class="list">
      {#each RUNNABLE as s, n}
        {@const res = results[s.id]}
        <li class={res?.status ?? 'idle'} class:now={runAllAt === n}>
          <b class="ic">{ICON[res?.status ?? 'idle']}</b>
          <div class="txt">
            <button class="name" on:click={() => { mode = 'tour'; go(STEPS.indexOf(s)); }} title="Open this step of the tour">{s.title}</button>
            <span class="note">{res?.note ?? 'Not checked yet.'}</span>
          </div>
          <button class="b sm" on:click={() => run(s.id)} disabled={!!running}>{res ? 'Again' : 'Check'}</button>
        </li>
      {/each}
    </ol>
    <div class="btns">
      <button class="b try" on:click={runAll} disabled={!!running}>{runAllAt >= 0 ? `Checking ${runAllAt + 1} of ${RUNNABLE.length}…` : 'Run all checks'}</button>
      <button class="b ghost" on:click={copyReport} disabled={!!running || !Object.keys(results).length}>Copy report</button>
      <button class="b ghost" on:click={() => { mode = 'tour'; go(0); }} disabled={!!running}>Take the tour</button>
    </div>
    {#if snapshot && !running}
      <div class="sandbox">
        <span>The checks made sample edits to this video. They aren't saved.</span>
        <div class="row">
          <button class="b next" on:click={undoTour} title="Put the edits back to how they were before the tour started">Undo the tour's edits</button>
          <button class="b ghost" on:click={keep}>Keep them</button>
        </div>
      </div>
    {/if}
    <p class="hint">Checks play the preview, so leave it alone while they run. A check that can't run here (no transcript, no microphone, AI switched off) says why.</p>
  </div>
{/if}

<style>
  .spot { position: fixed; z-index: 40; border-radius: 14px; pointer-events: none; transition: left 220ms, top 220ms, width 220ms, height 220ms;
    box-shadow: 0 0 0 3px var(--st-mint), 0 0 0 9999px rgba(0,0,0,.45); }
  .dim { position: fixed; inset: 0; z-index: 40; background: rgba(0,0,0,.45); pointer-events: none; }
  .card { position: fixed; z-index: 41; width: min(360px, calc(100vw - 24px)); display: grid; gap: 0.55rem; padding: 0.9rem 1rem 0.8rem;
    border-radius: 16px; background: #fff; color: #15151a; box-shadow: 0 20px 50px rgba(0,0,0,.5); transition: left 220ms, top 220ms; }
  .head { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
  .count { font-size: 0.7rem; font-weight: 800; letter-spacing: 0.06em; text-transform: uppercase; color: #6b6b78; }
  .x { width: 26px; height: 26px; border-radius: 99px; display: grid; place-items: center; color: inherit; opacity: 0.6; }
  .x:hover { opacity: 1; background: rgba(0,0,0,.08); }
  .dots { display: flex; gap: 4px; flex-wrap: wrap; }
  .d { width: 8px; height: 8px; border-radius: 99px; background: #d9d9e0; padding: 0; }
  .d.pass { background: #12b886; } .d.fail { background: #ff3b45; } .d.skip { background: #f5b400; }
  .d.now { outline: 2px solid #15151a; outline-offset: 1px; }
  h3 { font-size: 1.02rem; font-weight: 800; margin: 0; }
  .card p { font-size: 0.84rem; line-height: 1.5; color: #3b3b45; margin: 0; }
  .res { display: grid; grid-template-columns: auto 1fr; gap: 0.5rem; align-items: start; padding: 0.5rem 0.6rem; border-radius: 10px; font-size: 0.8rem; line-height: 1.4; }
  .res.pass { background: #e6fff5; color: #04392a; } .res.fail { background: #ffe8ea; color: #6a0710; }
  .res.skip { background: #fff6dc; color: #5a4300; } .res.running { background: #eef1ff; color: #23306b; }
  .btns { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .b { height: 32px; padding: 0 0.85rem; border-radius: 99px; font-weight: 700; font-size: 0.8rem; border: 1px solid transparent; }
  .b:disabled { opacity: 0.45; cursor: not-allowed; }
  .b.ghost { background: transparent; border-color: #d4d4dc; color: inherit; }
  .b.try { background: #15151a; color: #fff; }
  .b.next { background: var(--st-mint); color: #04261b; margin-left: auto; }
  .b.sm { height: 26px; padding: 0 0.6rem; font-size: 0.72rem; background: var(--st-raise); color: var(--st-text); }
  .link { font-size: 0.74rem; color: #3b3b45; text-decoration: underline; justify-self: start; }

  /* The list scrolls; the heading, counts and buttons stay in view. */
  .panel { position: fixed; z-index: 41; right: 14px; top: 64px; width: min(400px, calc(100vw - 28px)); max-height: calc(100vh - 80px); overflow: hidden;
    display: flex; flex-direction: column; gap: 0.6rem; padding: 0.9rem; border-radius: 16px; background: var(--st-panel); border: 1px solid var(--st-line); box-shadow: 0 24px 60px rgba(0,0,0,.6); }
  .panel > * { flex: none; }
  .panel > .list { flex: 1 1 auto; min-height: 0; overflow-y: auto; }
  .panel h3 { font-size: 1rem; }
  .panel .x { color: var(--st-text); }
  .panel .x:hover { background: var(--st-raise); }
  .sum { display: flex; flex-wrap: wrap; gap: 0.4rem 0.8rem; font-size: 0.76rem; color: var(--st-muted); margin: 0; }
  .sum .pass { color: #2ee6a6; } .sum .fail { color: #ff7a82; } .sum .skip { color: #f5c518; }
  .list { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.3rem; }
  .list li { display: grid; grid-template-columns: 22px 1fr auto; gap: 0.5rem; align-items: start; padding: 0.45rem 0.5rem; border-radius: 10px; background: var(--st-raise); border: 1px solid transparent; }
  .list li.now { border-color: var(--st-mint); }
  .ic { width: 22px; height: 22px; border-radius: 99px; display: grid; place-items: center; font-size: 0.78rem; background: var(--st-deep); color: var(--st-muted); }
  .list li.pass .ic { background: #0f3d2e; color: #2ee6a6; }
  .list li.fail .ic { background: #4a1418; color: #ff7a82; }
  .list li.skip .ic { background: #3d3410; color: #f5c518; }
  .txt { display: grid; gap: 0.1rem; min-width: 0; }
  .name { font-weight: 700; font-size: 0.82rem; color: var(--st-text); text-align: left; padding: 0; }
  .name:hover { text-decoration: underline; }
  .note { font-size: 0.72rem; color: var(--st-muted); line-height: 1.4; }
  .list li.fail .note { color: #ffb3b8; }
  .panel .b.ghost { border-color: var(--st-line); color: var(--st-text); }
  .panel .b.try { background: #fff; color: #000; }
  .sandbox { display: grid; gap: 0.45rem; padding: 0.6rem; border-radius: 12px; background: rgba(46,230,166,.08); border: 1px solid rgba(46,230,166,.35); font-size: 0.78rem; }
  .sandbox .row { display: flex; gap: 0.4rem; }
  .sandbox .b.next { margin-left: 0; }
  .hint { font-size: 0.7rem; color: var(--st-muted); margin: 0; line-height: 1.4; }
</style>
