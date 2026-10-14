<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, type AttemptDetail, type AiAnalysis, type BreakdownRow } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import { countUp, reveal } from '$lib/actions/motion';

  const attemptId = $page.params.attemptId;
  // Course tests are retaken through an approval in the course, not from here.
  const courseParam = $page.url.searchParams.get('course');

  let data: AttemptDetail | null = null;
  let analysis: AiAnalysis | null = null;
  let loading = true;
  let analyzing = false;
  let error = '';

  onMount(async () => {
    try {
      data = await api.testAttempt(attemptId);
      analysis = data.ai_analysis;
      // * generate on first view so the learner immediately sees where to improve
      if (!analysis) loadAnalysis();
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  });

  async function loadAnalysis() {
    analyzing = true;
    try {
      const r = await api.attemptAnalysis(attemptId);
      analysis = r.ai_analysis;
    } catch (e: any) { error = e.message; }
    finally { analyzing = false; }
  }

  $: topicsRanked = data
    ? Object.entries(data.topic_stats).sort((a, b) => a[1].accuracy - b[1].accuracy)
    : [];
  $: scorePct = data ? Math.max(0, Math.min(100, data.score)) : 0;
  $: passMark = data?.pass_threshold != null ? Math.max(0, Math.min(100, data.pass_threshold)) : null;
  // Points above (+) or below (−) the pass mark, for the line under the gauge.
  $: margin = passMark !== null ? Math.round(scorePct - passMark) : 0;

  // Written rows have no options (older attempts may predate question_type).
  const isWritten = (b: BreakdownRow) => b.question_type === 'written' || (b.question_type !== 'mcq' && !b.options?.length);

  /** The verdict pill for one reviewed question. */
  function verdict(b: BreakdownRow): { label: string; tone: 'good' | 'part' | 'bad' | 'pending'; icon: string } {
    if (!isWritten(b)) {
      return b.correct ? { label: 'Correct', tone: 'good', icon: 'check' } : { label: 'Incorrect', tone: 'bad', icon: 'close' };
    }
    if (b.graded_by === 'ungraded') return { label: 'Not graded yet', tone: 'pending', icon: 'clock' };
    if (b.graded_by === 'skipped') return { label: 'Left blank', tone: 'bad', icon: 'close' };
    const got = b.awarded ?? 0;
    if (b.correct || (b.marks > 0 && got >= b.marks)) return { label: 'Correct', tone: 'good', icon: 'check' };
    if (got > 0) return { label: 'Partly correct', tone: 'part', icon: 'checkCircle' };
    return { label: 'Incorrect', tone: 'bad', icon: 'close' };
  }
</script>

<svelte:head><title>Test result — Champ LMS</title></svelte:head>

<div class="page">
  <Breadcrumbs items={data
    ? [{ label: 'Tests', href: '/tests' }, { label: data.test_title }, { label: 'Result' }]
    : [{ label: 'Tests', href: '/tests' }, { label: 'Result' }]} />

  {#if loading}
    <div class="ui-skeleton" style="height:230px;border-radius:32px;margin-bottom:1.25rem"></div>
    <div class="ui-skeleton" style="height:260px;border-radius:28px"></div>
  {:else if error && !data}
    <div class="state ui-rise">
      <span class="state-ico danger"><Icon name="alert" size={26} /></span>
      <p>{error}</p>
    </div>
  {:else if data}
    <section class="hero ui-rise" class:pass={data.passed}>
      <div class="ring" style="--p:{scorePct}">
        <svg viewBox="0 0 120 120" aria-hidden="true">
          <circle class="track" cx="60" cy="60" r="52" />
          <circle class="arc" cx="60" cy="60" r="52" pathLength="100" style="stroke-dasharray:{scorePct} 100" />
        </svg>
        <span class="pct">
          <!-- One inline run so the % sits on the number's baseline.
               countUp rounds, so fractional scores are shown as-is. -->
          <span class="num">{#if Number.isInteger(data.score)}<b use:countUp={data.score}></b>{:else}<b>{data.score}</b>{/if}<i>%</i></span>
          <span class="pct-lbl">Your score</span>
        </span>
      </div>

      <div class="hero-meta">
        <div class="hero-top">
          <span class="verdict">
            <Icon name={data.passed ? 'checkCircle' : 'xCircle'} size={15} />
            {data.passed ? 'Passed' : 'Not passed'}
          </span>
          <span class="when"><Icon name="calendar" size={13} /> {new Date(data.submitted_at).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
        </div>
        <h1>{data.test_title}</h1>

        {#if passMark !== null}
          <div class="gauge" aria-hidden="true">
            <span class="g-fill" style="--p:{scorePct}%"></span>
            <i class="g-mark" class:near-start={passMark < 12} class:near-end={passMark > 88} style="left:{passMark}%"><span>Pass {passMark}%</span></i>
          </div>
          <!-- The pass mark is the test's current one, but `passed` was decided
               when the attempt was made; if an admin has changed it since,
               skip the line rather than contradict the verdict. -->
          {#if (margin >= 0) === data.passed}
          <p class="gap-note">
            {#if margin >= 0}
              <Icon name="trend" size={14} /> <b>{margin}%</b>&nbsp;above the pass mark
            {:else}
              <Icon name="target" size={14} /> <b>{-margin}%</b>&nbsp;short of the pass mark
            {/if}
          </p>
          {/if}
        {/if}

        <div class="tiles">
          <div class="tile">
            <span class="t-ico good"><Icon name="check" size={15} /></span>
            <b>{data.correct_count}<small>/{data.total_questions}</small></b>
            <span>Correct</span>
          </div>
          <div class="tile">
            <span class="t-ico star"><Icon name="star" size={15} /></span>
            <b>{data.marks_earned}<small>/{data.marks_total}</small></b>
            <span>Marks</span>
          </div>
          {#if passMark !== null}
            <div class="tile">
              <span class="t-ico aim"><Icon name="target" size={15} /></span>
              <b>{passMark}<small>%</small></b>
              <span>Pass mark</span>
            </div>
          {/if}
        </div>
      </div>
    </section>

    {#if error}<p class="error"><Icon name="alert" size={15} /> {error}</p>{/if}

    <!-- AI areas of improvement -->
    <section class="ai-panel ui-rise" style="--i:2">
      <div class="ai-head">
        <span class="ai-mark"><Icon name="sparkles" size={20} /></span>
        <h2>Your areas of improvement</h2>
        {#if analysis?.generated_by === 'fallback'}
          <span class="tag">rule-based</span>
        {/if}
      </div>

      {#if analyzing && !analysis}
        <p class="thinking"><span class="dots"><i></i><i></i><i></i></span> Analysing your answers…</p>
        <div class="ui-skeleton" style="height:14px;width:90%;border-radius:7px;margin-top:0.8rem"></div>
        <div class="ui-skeleton" style="height:14px;width:70%;border-radius:7px;margin-top:0.5rem"></div>
      {:else if analysis}
        <p class="ai-summary">{analysis.summary}</p>

        {#if analysis.weak_areas?.length}
          <div class="weak-list">
            {#each analysis.weak_areas as w, n}
              <div class="weak ui-rise" style="--i:{3 + n}">
                <div class="weak-top">
                  <b>{w.topic}</b>
                  <span class="acc">{w.accuracy}%</span>
                </div>
                <p class="why">{w.why}</p>
                <p class="action"><Icon name="arrowRight" size={14} /> {w.action}</p>
              </div>
            {/each}
          </div>
        {/if}

        {#if analysis.strengths?.length}
          <div class="strengths">
            <span class="lbl">Strong areas</span>
            <div class="chips">{#each analysis.strengths as s}<span class="ui-pill mint"><Icon name="check" size={13} /> {s}</span>{/each}</div>
          </div>
        {/if}

        {#if analysis.recommendations?.length}
          <div class="recs-block">
            <span class="lbl">What to do next</span>
            <ul class="recs">{#each analysis.recommendations as r}<li><span class="li-dot"></span>{r}</li>{/each}</ul>
          </div>
        {/if}

        {#if analysis.suggested_focus}
          <p class="focus"><Icon name="target" size={15} /> Suggested focus: <b>{analysis.suggested_focus}</b></p>
        {/if}
      {:else}
        <button class="btn-primary" on:click={loadAnalysis}><Icon name="sparkles" size={16} /> Generate insight</button>
      {/if}
    </section>

    {#if topicsRanked.length}
      <section class="panel" use:reveal>
        <h2><Icon name="chart" size={20} /> Accuracy by topic</h2>
        {#each topicsRanked as [topic, s], n}
          <div class="bar-row">
            <span class="bar-label">{topic}</span>
            <div class="bar"><div class="fill" class:low={s.accuracy < 50}
                                  class:mid={s.accuracy >= 50 && s.accuracy < 80}
                                  style="width:{s.accuracy}%;animation-delay:{200 + n * 80}ms"></div></div>
            <span class="bar-val">{s.accuracy}% <em>({s.correct}/{s.total})</em></span>
          </div>
        {/each}
      </section>
    {/if}

    <h2 class="section"><Icon name="list" size={22} /> Every question reviewed</h2>
    <div class="answers">
      {#each data.breakdown as b, i}
        {@const v = verdict(b)}
        {@const written = isWritten(b)}
        <article class="ans" class:wrong={v.tone === 'bad'} use:reveal={{ delay: (i % 3) * 60 }}>
          <div class="ans-head">
            <span class="idx">{i + 1}</span>
            <span class="ui-pill mark {v.tone}"><Icon name={v.icon} size={13} /> {v.label}</span>
            {#if written}<span class="chip"><Icon name="edit" size={12} /> Written</span>{/if}
            {#if b.topic}<span class="chip">{b.topic}</span>{/if}
            <span class="marks" title="Marks for this question">
              <b>{b.awarded ?? (b.correct ? b.marks : 0)}</b>/{b.marks} mark{b.marks === 1 ? '' : 's'}
            </span>
          </div>
          <p class="q">{b.question}</p>

          {#if written}
            <!-- Written answer: what the learner typed, the grader's feedback and
                 the reference answer, as returned in the attempt breakdown. -->
            <div class="written">
              <div class="w-block yours" class:empty={!b.your_answer}>
                <span class="w-lbl"><Icon name="user" size={13} /> Your answer</span>
                {#if b.your_answer}
                  <p class="w-text">{b.your_answer}</p>
                {:else}
                  <p class="w-text muted">You left this answer blank.</p>
                {/if}
              </div>

              {#if b.ai_feedback && b.graded_by !== 'skipped'}
                <div class="w-block feedback" class:pending={b.graded_by === 'ungraded'}>
                  <span class="w-lbl">
                    <Icon name={b.graded_by === 'ungraded' ? 'clock' : 'sparkles'} size={13} />
                    {b.graded_by === 'ungraded' ? 'Grading' : 'Feedback'}
                  </span>
                  <p class="w-text">{b.ai_feedback}</p>
                </div>
              {/if}

              {#if b.correct_answer}
                <div class="w-block reference">
                  <span class="w-lbl"><Icon name="checkCircle" size={13} /> Reference answer</span>
                  <p class="w-text">{b.correct_answer}</p>
                </div>
              {/if}
            </div>
          {:else}
            <div class="opts">
              {#each b.options as opt, oi}
                <div class="opt"
                     class:correct={oi === b.correct_index}
                     class:yours-wrong={oi === b.your_index && !b.correct}>
                  <span class="key">{String.fromCharCode(65 + oi)}</span>
                  <span class="opt-text">{opt}</span>
                  {#if oi === b.correct_index}<span class="pill good">Correct answer</span>{/if}
                  {#if oi === b.your_index && !b.correct}<span class="pill bad">Your answer</span>{/if}
                  {#if oi === b.your_index && b.correct}<span class="pill good">Your answer</span>{/if}
                </div>
              {/each}
            </div>

            {#if b.your_index === null}
              <p class="skipped"><Icon name="info" size={14} /> You skipped this question.</p>
            {/if}
          {/if}
          {#if b.explanation}
            <p class="expl"><b>Why:</b> {b.explanation}</p>
          {/if}
        </article>
      {/each}
    </div>

    <div class="footer-actions">
      {#if courseParam}
        <a href="/course/{courseParam}" class="btn-primary">Back to course <Icon name="arrowRight" size={16} /></a>
      {:else}
        <a href="/tests" class="btn-ghost"><Icon name="arrowLeft" size={16} /> Back to tests</a>
        <a href="/tests/{data.test_id}" class="btn-primary"><Icon name="refresh" size={16} /> Retake test</a>
      {/if}
    </div>
  {/if}
</div>

<style>
  .page { max-width: 880px; margin: 0 auto; }
  .error { display: flex; align-items: center; gap: 0.4rem; color: var(--danger); font-size: 0.86rem; margin-bottom: 1rem; }
  .section { display: flex; align-items: center; gap: 0.5rem; font-size: 1.45rem; letter-spacing: -0.025em; margin: 2rem 0 1rem; }

  /* ---------- hero ---------- */
  /* A surface card washed with the result colour from the left: ring |
     verdict, title, pass-mark gauge, stat tiles. */
  .hero {
    --c: var(--danger);
    position: relative; overflow: hidden;
    display: flex; align-items: center; gap: 1.8rem; flex-wrap: wrap;
    background:
      radial-gradient(120% 140% at 0% 50%, color-mix(in srgb, var(--c) 16%, transparent), transparent 60%),
      var(--surface);
    box-shadow: var(--shadow-sm), 0 0 0 1px color-mix(in srgb, var(--c) 22%, var(--border));
    border-radius: 30px; padding: 1.5rem 1.7rem; margin-bottom: 1.25rem; color: var(--text);
  }
  .hero.pass { --c: var(--success); }

  .ring {
    position: relative; width: 156px; height: 156px; flex: none; border-radius: 50%;
    background: var(--surface); box-shadow: var(--shadow), inset 0 0 0 1px var(--border);
  }
  .ring svg { position: absolute; inset: 0; width: 100%; height: 100%; rotate: -90deg; }
  .ring circle { fill: none; stroke-width: 9; }
  .track { stroke: color-mix(in srgb, var(--c) 14%, var(--surface3)); }
  .arc { stroke: var(--c); stroke-linecap: round; animation: draw 1.3s var(--ease-out) 250ms backwards; }
  @keyframes draw { from { stroke-dasharray: 0 100; } }
  .pct { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.3rem; }
  .num { white-space: nowrap; line-height: 1; font-variant-numeric: tabular-nums; }
  .num b { font-size: 2.7rem; font-weight: 800; letter-spacing: -0.045em; color: var(--text); }
  .num i { font-style: normal; font-size: 1.15rem; font-weight: 700; color: var(--c); margin-left: 2px; }
  .pct-lbl { font-size: 0.66rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }

  .hero-meta { flex: 1; min-width: 260px; display: flex; flex-direction: column; align-items: stretch; gap: 0.6rem; }
  .hero-top { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
  .verdict {
    display: inline-flex; align-items: center; gap: 0.35rem; height: 30px; padding: 0 0.8rem; border-radius: 99px;
    background: var(--c); color: var(--on-accent); font-size: 0.82rem; font-weight: 700;
    animation: pop 500ms var(--ease-out) 700ms backwards;
  }
  .when { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.76rem; color: var(--muted); }
  .hero-meta h1 { font-size: clamp(1.35rem, 1rem + 1.1vw, 1.9rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.15; }

  /* Score vs pass mark: the tick and its label sit on the bar. */
  .gauge { position: relative; height: 10px; margin: 1.35rem 0 0; border-radius: 99px; background: var(--surface3); }
  .g-fill {
    position: absolute; left: 0; top: 0; bottom: 0; width: var(--p); border-radius: inherit; background: var(--c);
    transform-origin: left; animation: grow-x 1.1s var(--ease-out) 300ms backwards;
  }
  @keyframes grow-x { from { transform: scaleX(0); } }
  .g-mark { position: absolute; top: -5px; bottom: -5px; width: 3px; margin-left: -1.5px; border-radius: 2px; background: var(--text); }
  .g-mark span {
    position: absolute; bottom: calc(100% + 4px); left: 50%; translate: -50% 0; white-space: nowrap;
    font-style: normal; font-size: 0.68rem; font-weight: 700; color: var(--text-secondary);
  }
  /* Keep the label inside the card when the pass mark is near either end. */
  .g-mark.near-start span { translate: -4px 0; left: 0; }
  .g-mark.near-end span { translate: calc(-100% + 4px) 0; left: 100%; }
  .gap-note { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.82rem; color: var(--text-secondary); }
  .gap-note b { color: var(--c); }

  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 0.5rem; margin-top: 0.2rem; }
  .tile {
    display: grid; grid-template-columns: auto 1fr; grid-template-rows: auto auto; column-gap: 0.6rem; align-items: center;
    padding: 0.6rem 0.75rem; border-radius: 16px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--border);
  }
  .t-ico { grid-row: 1 / 3; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; color: var(--tile-ink); }
  .t-ico.good { background: var(--tile-mint); }
  .t-ico.star { background: var(--tile-butter); }
  .t-ico.aim { background: var(--tile-sky); }
  .tile b { font-size: 1.15rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .tile b small { font-size: 0.72em; font-weight: 600; color: var(--muted); }
  .tile > span:last-child { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }

  /* ---------- AI panel ---------- */
  .ai-panel { background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-sm); padding: 1.4rem 1.5rem; margin-bottom: 1.25rem; }
  .ai-head { display: flex; align-items: center; gap: 0.65rem; margin-bottom: 0.9rem; flex-wrap: wrap; }
  .ai-mark { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-lilac); color: var(--tile-ink); animation: float 4s var(--ease-in-out) infinite; }
  .ai-head h2 { font-size: 1.2rem; font-weight: 700; letter-spacing: -0.02em; }
  .tag { font-size: 0.7rem; color: var(--muted); background: var(--surface2); border-radius: 999px; padding: 0.15rem 0.55rem; }
  .thinking { display: flex; align-items: center; gap: 0.6rem; font-size: 0.88rem; color: var(--muted); }
  .dots { display: inline-flex; gap: 4px; }
  .dots i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; animation: blink 1.2s var(--ease-in-out) infinite; }
  .dots i:nth-child(2) { animation-delay: 150ms; } .dots i:nth-child(3) { animation-delay: 300ms; }
  @keyframes blink { 0%, 80%, 100% { opacity: 0.25; scale: 0.8; } 40% { opacity: 1; scale: 1; } }
  .ai-summary { font-size: 0.95rem; line-height: 1.65; margin-bottom: 1.1rem; }
  .weak-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.65rem; margin-bottom: 1.1rem; }
  .weak { background: var(--tile-peach); color: var(--tile-ink); border-radius: 22px; padding: 0.95rem 1.05rem; transition: translate var(--dur-3) var(--ease-out); }
  .weak:hover { translate: 0 -3px; }
  .weak-top { display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.92rem; }
  .acc { font-weight: 700; padding: 0.05rem 0.5rem; border-radius: 99px; background: var(--tile-inner); font-variant-numeric: tabular-nums; }
  .why { font-size: 0.82rem; opacity: 0.75; margin-top: 0.35rem; line-height: 1.55; }
  .action { display: flex; gap: 0.35rem; font-size: 0.84rem; font-weight: 600; margin-top: 0.5rem; line-height: 1.5; }
  .action :global(.icon) { flex: none; margin-top: 3px; }
  .lbl { font-size: 0.74rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; display: block; margin-bottom: 0.5rem; }
  .strengths { margin-bottom: 1.1rem; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.35rem; }
  .chip { font-size: 0.74rem; color: var(--text-secondary); background: var(--surface2); border-radius: 999px; padding: 0.2rem 0.6rem; }
  .recs { list-style: none; display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.88rem; line-height: 1.6; }
  .recs li { display: flex; gap: 0.6rem; align-items: flex-start; }
  .li-dot { flex: none; width: 8px; height: 8px; border-radius: 50%; margin-top: 0.5rem; background: var(--brand); }
  .focus { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; font-size: 0.86rem; color: var(--muted); margin-top: 1rem; padding: 0.6rem 0.85rem; border-radius: 16px; background: var(--tile-butter); color: var(--tile-ink); }
  .focus b { font-weight: 700; }

  /* ---------- topic bars ---------- */
  .panel { background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-sm); padding: 1.35rem 1.5rem; margin-bottom: 1.25rem; }
  .panel h2 { display: flex; align-items: center; gap: 0.5rem; font-size: 1.15rem; font-weight: 700; margin-bottom: 1rem; }
  .bar-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.65rem; font-size: 0.84rem; }
  .bar-label { flex: 0 0 32%; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-transform: capitalize; }
  .bar { flex: 1; height: 10px; background: var(--surface2); border-radius: 999px; overflow: hidden; }
  .fill { height: 100%; background: var(--success); border-radius: 999px; transform-origin: left; animation: grow 900ms var(--ease-out) backwards; }
  @keyframes grow { from { transform: scaleX(0); } }
  .fill.mid { background: var(--warn); }
  .fill.low { background: var(--danger); }
  .bar-val { flex: 0 0 92px; text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
  .bar-val em { color: var(--muted); font-style: normal; font-size: 0.74rem; font-weight: 500; }

  /* ---------- answers ---------- */
  .answers { display: flex; flex-direction: column; gap: 0.85rem; }
  .ans { background: var(--surface); border-radius: 26px; box-shadow: var(--shadow-sm); padding: 1.15rem 1.3rem; transition: box-shadow var(--dur-3) var(--ease-out); }
  .ans:hover { box-shadow: var(--shadow); }
  .ans-head { display: flex; align-items: center; gap: 0.55rem; margin-bottom: 0.65rem; flex-wrap: wrap; }
  .idx { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; background: var(--surface2); font-size: 0.8rem; font-weight: 700; }
  .mark { font-weight: 700; animation: pop 420ms var(--ease-out) backwards; }
  .mark.bad { background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); }
  .mark.good { background: var(--tile-mint); color: var(--tile-ink); }
  .mark.part { background: var(--tile-butter); color: var(--tile-ink); }
  .mark.pending { background: var(--surface2); color: var(--text-secondary); }
  .chip { display: inline-flex; align-items: center; gap: 0.3rem; }
  .marks { margin-left: auto; font-size: 0.8rem; color: var(--muted); font-variant-numeric: tabular-nums; }
  .marks b { color: var(--text); font-weight: 700; }

  /* ---------- written answers ---------- */
  .written { display: flex; flex-direction: column; gap: 0.5rem; }
  .w-block {
    border-radius: 16px; padding: 0.75rem 0.9rem; background: var(--surface2);
    transition: translate var(--dur-2) var(--ease-out);
  }
  .w-block:hover { translate: 2px 0; }
  .w-block.yours { box-shadow: inset 0 0 0 1.5px var(--surface3); }
  .w-block.empty { background: color-mix(in srgb, var(--danger) 8%, var(--surface2)); }
  .w-block.feedback { background: var(--tile-lilac); color: var(--tile-ink); }
  .w-block.feedback.pending { background: var(--surface2); color: var(--text); }
  .w-block.reference { background: color-mix(in srgb, var(--success) 12%, var(--surface2)); box-shadow: inset 0 0 0 1.5px var(--success); }
  .w-lbl {
    display: inline-flex; align-items: center; gap: 0.35rem; margin-bottom: 0.3rem;
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.75;
  }
  .w-text { font-size: 0.9rem; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
  .w-text.muted { color: var(--muted); font-style: italic; }
  .q { font-size: 0.98rem; font-weight: 600; line-height: 1.55; margin-bottom: 0.85rem; }

  .opts { display: flex; flex-direction: column; gap: 0.4rem; }
  .opt { display: flex; align-items: center; gap: 0.65rem; background: var(--surface2);
         border-radius: 16px; padding: 0.65rem 0.8rem; font-size: 0.88rem; line-height: 1.5;
         box-shadow: inset 0 0 0 1.5px transparent; transition: translate var(--dur-2) var(--ease-out); }
  .opt:hover { translate: 2px 0; }
  .opt.correct { background: color-mix(in srgb, var(--success) 12%, var(--surface2)); box-shadow: inset 0 0 0 1.5px var(--success); }
  .opt.yours-wrong { background: color-mix(in srgb, var(--danger) 10%, var(--surface2)); box-shadow: inset 0 0 0 1.5px var(--danger); }
  .key { flex-shrink: 0; width: 26px; height: 26px; border-radius: 50%; background: var(--surface);
         display: grid; place-items: center; font-size: 0.72rem; font-weight: 700; color: var(--muted); }
  .opt.correct .key { background: var(--success); color: var(--on-accent); }
  .opt.yours-wrong .key { background: var(--danger); color: var(--on-accent); }
  .opt-text { flex: 1; }
  .pill { font-size: 0.68rem; font-weight: 700; border-radius: 999px; padding: 0.15rem 0.55rem; white-space: nowrap; }
  .pill.good { color: var(--success); background: var(--surface); }
  .pill.bad { color: var(--danger); background: var(--surface); }

  .skipped { display: flex; align-items: center; gap: 0.35rem; font-size: 0.8rem; color: var(--warn); margin-top: 0.65rem; }
  .expl { font-size: 0.84rem; color: var(--text-secondary); margin-top: 0.75rem; line-height: 1.6;
          background: var(--tile-sky); color: var(--tile-ink); border-radius: 16px; padding: 0.7rem 0.9rem; }
  .expl b { font-weight: 700; }

  .footer-actions { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-top: 2rem; }

  .state { display: flex; flex-direction: column; align-items: center; gap: 0.7rem; text-align: center; padding: 3rem 1rem; background: var(--surface); border-radius: 32px; }
  .state p { color: var(--muted); }
  .state-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; animation: pop 520ms var(--ease-out); }
  .state-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }

  @media (max-width: 600px) {
    .hero { gap: 1.1rem; padding: 1.2rem; justify-content: center; }
    .ring { width: 128px; height: 128px; }
    .num b { font-size: 2.2rem; }
    .hero-meta { min-width: 0; flex-basis: 100%; }
    .hero-top { justify-content: center; }
    .hero-meta h1 { text-align: center; }
    .bar-label { flex: 0 0 26%; }
  }
</style>
