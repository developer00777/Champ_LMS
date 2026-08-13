<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, type AttemptDetail, type AiAnalysis } from '$lib/api/client';

  const attemptId = $page.params.attemptId;

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
</script>

<div class="page">
  <p class="breadcrumb"><a href="/tests">← Test Series</a></p>

  {#if loading}
    <div class="skeleton big"></div>
  {:else if error && !data}
    <p class="error">{error}</p>
  {:else if data}
    <div class="hero" class:pass={data.passed}>
      <div class="hero-score">
        <span class="pct">{data.score}%</span>
        <span class="verdict">{data.passed ? 'PASSED' : 'NOT PASSED'}</span>
      </div>
      <div class="hero-meta">
        <h1>{data.test_title}</h1>
        <p>
          {data.correct_count} of {data.total_questions} correct ·
          {data.marks_earned}/{data.marks_total} marks
          {#if data.pass_threshold !== null}· pass mark {data.pass_threshold}%{/if}
        </p>
        <p class="when">{new Date(data.submitted_at).toLocaleString()}</p>
      </div>
    </div>

    {#if error}<p class="error">{error}</p>{/if}

    <!-- AI areas of improvement -->
    <div class="ai-panel">
      <div class="ai-head">
        <h2>🤖 Your areas of improvement</h2>
        {#if analysis?.generated_by === 'fallback'}
          <span class="tag">rule-based</span>
        {/if}
      </div>

      {#if analyzing && !analysis}
        <p class="thinking">Analysing your answers…</p>
      {:else if analysis}
        <p class="ai-summary">{analysis.summary}</p>

        {#if analysis.weak_areas?.length}
          <div class="weak-list">
            {#each analysis.weak_areas as w}
              <div class="weak">
                <div class="weak-top">
                  <b>{w.topic}</b>
                  <span class="acc">{w.accuracy}%</span>
                </div>
                <p class="why">{w.why}</p>
                <p class="action">→ {w.action}</p>
              </div>
            {/each}
          </div>
        {/if}

        {#if analysis.strengths?.length}
          <div class="strengths">
            <span class="lbl">Strong areas</span>
            <div class="chips">{#each analysis.strengths as s}<span class="chip good">{s}</span>{/each}</div>
          </div>
        {/if}

        {#if analysis.recommendations?.length}
          <div class="recs-block">
            <span class="lbl">What to do next</span>
            <ul class="recs">{#each analysis.recommendations as r}<li>{r}</li>{/each}</ul>
          </div>
        {/if}

        {#if analysis.suggested_focus}
          <p class="focus">Suggested focus: <b>{analysis.suggested_focus}</b></p>
        {/if}
      {:else}
        <button class="btn" on:click={loadAnalysis}>Generate insight</button>
      {/if}
    </div>

    {#if topicsRanked.length}
      <div class="panel">
        <h2>Accuracy by topic</h2>
        {#each topicsRanked as [topic, s]}
          <div class="bar-row">
            <span class="bar-label">{topic}</span>
            <div class="bar"><div class="fill" class:low={s.accuracy < 50}
                                  class:mid={s.accuracy >= 50 && s.accuracy < 80}
                                  style="width:{s.accuracy}%"></div></div>
            <span class="bar-val">{s.accuracy}% <em>({s.correct}/{s.total})</em></span>
          </div>
        {/each}
      </div>
    {/if}

    <h2 class="section">Every question reviewed</h2>
    <div class="answers">
      {#each data.breakdown as b, i}
        <div class="ans" class:wrong={!b.correct}>
          <div class="ans-head">
            <span class="idx">{i + 1}</span>
            <span class="mark">{b.correct ? '✓ Correct' : '✗ Incorrect'}</span>
            {#if b.topic}<span class="chip">{b.topic}</span>{/if}
          </div>
          <p class="q">{b.question}</p>

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
            <p class="skipped">You skipped this question.</p>
          {/if}
          {#if b.explanation}
            <p class="expl"><b>Why:</b> {b.explanation}</p>
          {/if}
        </div>
      {/each}
    </div>

    <div class="footer-actions">
      <a href="/tests" class="btn">Back to tests</a>
      <a href="/tests/{data.test_id}" class="btn primary">Retake test</a>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 800px; margin: 0 auto; padding-bottom: 4rem; }
  .breadcrumb { font-size: 0.83rem; margin-bottom: 1rem; }
  .breadcrumb a { color: var(--accent); text-decoration: none; }
  .error { color: var(--accent); font-size: 0.85rem; margin-bottom: 1rem; }
  .section { font-size: 1.15rem; font-weight: 700; margin: 2rem 0 0.9rem; }

  .hero { display: flex; align-items: center; gap: 1.5rem; background: var(--surface);
          border: 1px solid var(--border); border-left: 4px solid #e05260;
          border-radius: 12px; padding: 1.5rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
  .hero.pass { border-left-color: var(--success); }
  .hero-score { display: flex; flex-direction: column; align-items: center; gap: 0.2rem; }
  .pct { font-size: 2.8rem; font-weight: 800; line-height: 1; color: #e05260; }
  .hero.pass .pct { color: var(--success); }
  .verdict { font-size: 0.66rem; font-weight: 800; letter-spacing: 0.07em; color: var(--muted); }
  .hero-meta h1 { font-size: 1.25rem; font-weight: 800; margin-bottom: 0.3rem; }
  .hero-meta p { font-size: 0.84rem; color: var(--muted); }
  .when { font-size: 0.74rem; margin-top: 0.2rem; }

  .ai-panel { background: var(--surface); border: 1px solid var(--border);
              border-left: 3px solid var(--accent); border-radius: 10px;
              padding: 1.35rem; margin-bottom: 1.25rem; }
  .ai-head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.7rem; flex-wrap: wrap; }
  .ai-head h2 { font-size: 1.05rem; font-weight: 700; }
  .tag { font-size: 0.66rem; color: var(--muted); background: var(--surface2);
         border-radius: 999px; padding: 0.12rem 0.5rem; }
  .thinking { font-size: 0.85rem; color: var(--muted); }
  .ai-summary { font-size: 0.9rem; line-height: 1.65; margin-bottom: 1rem; }
  .weak-list { display: flex; flex-direction: column; gap: 0.6rem; margin-bottom: 1rem; }
  .weak { background: var(--surface2); border-radius: 8px; padding: 0.8rem 0.95rem; }
  .weak-top { display: flex; justify-content: space-between; font-size: 0.88rem; }
  .acc { color: #e05260; font-weight: 700; }
  .why { font-size: 0.8rem; color: var(--muted); margin-top: 0.25rem; line-height: 1.55; }
  .action { font-size: 0.82rem; margin-top: 0.4rem; color: var(--accent); line-height: 1.5; }
  .lbl { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em;
         display: block; margin-bottom: 0.4rem; }
  .strengths { margin-bottom: 1rem; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.35rem; }
  .chip { font-size: 0.71rem; color: var(--muted); background: var(--surface2);
          border-radius: 999px; padding: 0.18rem 0.55rem; }
  .chip.good { color: var(--success); }
  .recs { margin: 0 0 0 1.1rem; font-size: 0.84rem; line-height: 1.75; }
  .focus { font-size: 0.82rem; color: var(--muted); margin-top: 0.9rem; }
  .focus b { color: var(--text); }

  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
           padding: 1.25rem; margin-bottom: 1.25rem; }
  .panel h2 { font-size: 1.02rem; font-weight: 700; margin-bottom: 0.9rem; }
  .bar-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.55rem; font-size: 0.8rem; }
  .bar-label { flex: 0 0 32%; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar { flex: 1; height: 8px; background: var(--surface2); border-radius: 999px; overflow: hidden; }
  .fill { height: 100%; background: var(--success); border-radius: 999px; }
  .fill.mid { background: #ffc107; }
  .fill.low { background: #e05260; }
  .bar-val { flex: 0 0 88px; text-align: right; font-variant-numeric: tabular-nums; }
  .bar-val em { color: var(--muted); font-style: normal; font-size: 0.72rem; }

  .answers { display: flex; flex-direction: column; gap: 0.85rem; }
  .ans { background: var(--surface); border: 1px solid var(--border);
         border-left: 3px solid var(--success); border-radius: 10px; padding: 1.1rem 1.25rem; }
  .ans.wrong { border-left-color: #e05260; }
  .ans-head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.55rem; flex-wrap: wrap; }
  .idx { font-size: 0.74rem; color: var(--muted); font-weight: 700; }
  .mark { font-size: 0.74rem; font-weight: 700; color: var(--success); }
  .ans.wrong .mark { color: #e05260; }
  .q { font-size: 0.93rem; font-weight: 600; line-height: 1.55; margin-bottom: 0.8rem; }

  .opts { display: flex; flex-direction: column; gap: 0.4rem; }
  .opt { display: flex; align-items: center; gap: 0.6rem; background: var(--surface2);
         border: 1px solid transparent; border-radius: 7px; padding: 0.6rem 0.75rem;
         font-size: 0.85rem; line-height: 1.5; }
  .opt.correct { border-color: var(--success); }
  .opt.yours-wrong { border-color: #e05260; }
  .key { flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%; background: var(--surface);
         display: grid; place-items: center; font-size: 0.7rem; font-weight: 700; color: var(--muted); }
  .opt-text { flex: 1; }
  .pill { font-size: 0.64rem; font-weight: 800; letter-spacing: 0.04em; border-radius: 999px;
          padding: 0.12rem 0.5rem; white-space: nowrap; }
  .pill.good { color: var(--success); border: 1px solid var(--success); }
  .pill.bad { color: #e05260; border: 1px solid #e05260; }

  .skipped { font-size: 0.78rem; color: #ffc107; margin-top: 0.6rem; }
  .expl { font-size: 0.8rem; color: var(--muted); margin-top: 0.7rem; line-height: 1.6;
          background: var(--surface2); border-radius: 6px; padding: 0.6rem 0.75rem; }
  .expl b { color: var(--text); }

  .footer-actions { display: flex; gap: 0.6rem; margin-top: 1.75rem; }
  .btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 6px; padding: 0.6rem 1.1rem; font-size: 0.87rem; font-weight: 600;
         cursor: pointer; text-decoration: none; }
  .btn:hover { border-color: var(--accent); }
  .btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }

  .skeleton { border-radius: 10px; background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
              background-size: 200% 100%; animation: shimmer 1.4s infinite; }
  .skeleton.big { height: 380px; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

  @media (max-width: 600px) {
    .hero { gap: 1rem; }
    .pct { font-size: 2.2rem; }
    .bar-label { flex: 0 0 26%; }
  }
</style>
