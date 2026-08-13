<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, type TestResults, type AiAnalysis } from '$lib/api/client';

  const id = $page.params.id;
  let data: TestResults | null = null;
  let loading = true;
  let error = '';
  let expanded: Record<string, boolean> = {};
  let analyzing: Record<string, boolean> = {};

  onMount(load);

  async function load() {
    loading = true;
    try { data = await api.testResults(id); error = ''; }
    catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  function toggle(attemptId: string) {
    expanded[attemptId] = !expanded[attemptId];
    expanded = expanded;
  }

  async function analyze(attemptId: string) {
    analyzing[attemptId] = true; analyzing = analyzing;
    try {
      const r = await api.analyzeAttemptAdmin(attemptId);
      if (data) {
        const row = data.attempts.find((a) => a.attempt_id === attemptId);
        if (row) { row.ai_analysis = r.ai_analysis; row.has_ai_analysis = true; }
        data = data;
      }
      expanded[attemptId] = true; expanded = expanded;
    } catch (e: any) { error = e.message; }
    finally { analyzing[attemptId] = false; analyzing = analyzing; }
  }

  function analysisOf(row: { ai_analysis: AiAnalysis | null }): AiAnalysis | null {
    return row.ai_analysis;
  }

  $: cohortRanked = data
    ? Object.entries(data.cohort_topic_stats).sort((a, b) => a[1].accuracy - b[1].accuracy)
    : [];
</script>

<div class="page">
  <p class="breadcrumb"><a href="/admin/tests">← Test Series</a> · <a href="/admin/tests/{id}">Edit</a></p>

  {#if loading}
    <div class="skeleton big"></div>
  {:else if error && !data}
    <p class="error">{error}</p>
  {:else if data}
    <h1>{data.title}</h1>
    <p class="sub">Results · pass mark {data.pass_threshold}% · {data.total_questions} questions</p>
    {#if error}<p class="error">{error}</p>{/if}

    <div class="kpis">
      <div class="kpi"><b>{data.attempt_count}</b><span>attempts</span></div>
      <div class="kpi"><b>{data.average_score ?? '—'}{data.average_score != null ? '%' : ''}</b><span>average score</span></div>
      <div class="kpi"><b>{data.pass_rate ?? '—'}{data.pass_rate != null ? '%' : ''}</b><span>pass rate</span></div>
    </div>

    {#if cohortRanked.length}
      <div class="panel">
        <h2>Where the team struggles</h2>
        <p class="panel-sub">Accuracy across every attempt, weakest first — use this to target training.</p>
        {#each cohortRanked as [topic, s]}
          <div class="bar-row">
            <span class="bar-label">{topic}</span>
            <div class="bar"><div class="fill" class:low={s.accuracy < 50} class:mid={s.accuracy >= 50 && s.accuracy < 80}
                                  style="width:{s.accuracy}%"></div></div>
            <span class="bar-val">{s.accuracy}% <em>({s.correct}/{s.total})</em></span>
          </div>
        {/each}
      </div>
    {/if}

    {#if data.attempts.length === 0}
      <div class="empty">
        <div class="empty-icon">📊</div>
        <h2>No attempts yet</h2>
        <p>Once learners take this test, their scores, answers and AI recommendations appear here.</p>
      </div>
    {:else}
      <h2 class="section">Individual results</h2>
      <div class="rows">
        {#each data.attempts as a (a.attempt_id)}
          <div class="row-card">
            <div class="row-head">
              <div class="who">
                <b>{a.full_name || a.email || 'Unknown'}</b>
                <span class="muted">{a.email}{a.department ? ` · ${a.department}` : ''}</span>
                <span class="muted tiny">{new Date(a.submitted_at).toLocaleString()}</span>
              </div>
              <div class="score-box">
                <span class="score" class:pass={a.passed} class:fail={!a.passed}>{a.score}%</span>
                <span class="muted tiny">
                  {a.correct_count}/{a.total_questions} correct · {a.marks_earned}/{a.marks_total} marks
                </span>
                <span class="verdict" class:pass={a.passed}>{a.passed ? 'PASSED' : 'FAILED'}</span>
              </div>
            </div>

            <div class="row-actions">
              <button class="btn" on:click={() => toggle(a.attempt_id)}>
                {expanded[a.attempt_id] ? 'Hide' : 'View'} answers
              </button>
              <button class="btn" disabled={analyzing[a.attempt_id]} on:click={() => analyze(a.attempt_id)}>
                {analyzing[a.attempt_id]
                  ? 'Analysing…'
                  : a.has_ai_analysis ? 'Regenerate AI insight' : 'Get AI insight'}
              </button>
            </div>

            {#if analysisOf(a)}
              {@const an = analysisOf(a)}
              <div class="ai">
                <div class="ai-head">
                  <span class="ai-title">🤖 Areas of improvement</span>
                  {#if an?.generated_by === 'fallback'}
                    <span class="tag">rule-based (no AI key set)</span>
                  {/if}
                </div>
                <p class="ai-summary">{an?.summary}</p>
                {#if an?.weak_areas?.length}
                  <div class="weak-list">
                    {#each an.weak_areas as w}
                      <div class="weak">
                        <div class="weak-top"><b>{w.topic}</b><span class="acc">{w.accuracy}%</span></div>
                        <p class="why">{w.why}</p>
                        <p class="action">→ {w.action}</p>
                      </div>
                    {/each}
                  </div>
                {/if}
                {#if an?.strengths?.length}
                  <p class="strengths"><b>Strengths:</b> {an.strengths.join(', ')}</p>
                {/if}
                {#if an?.recommendations?.length}
                  <ul class="recs">{#each an.recommendations as r}<li>{r}</li>{/each}</ul>
                {/if}
              </div>
            {/if}

            {#if expanded[a.attempt_id]}
              <div class="topics">
                {#each Object.entries(a.topic_stats) as [topic, s]}
                  <span class="chip" class:low={s.accuracy < 50}>{topic} {s.accuracy}%</span>
                {/each}
              </div>
              <div class="answers">
                {#each a.breakdown as b, i}
                  <div class="ans" class:wrong={!b.correct}>
                    <div class="ans-q"><span class="idx">{i + 1}</span>{b.question}</div>
                    <div class="ans-body">
                      <div class="ans-line">
                        <span class="lbl">Their answer</span>
                        <span class:bad={!b.correct} class:good={b.correct}>
                          {b.your_answer ?? '— skipped —'}
                        </span>
                      </div>
                      {#if !b.correct}
                        <div class="ans-line">
                          <span class="lbl">Correct answer</span>
                          <span class="good">{b.correct_answer}</span>
                        </div>
                      {/if}
                      {#if b.explanation}<p class="expl">{b.explanation}</p>{/if}
                      {#if b.topic}<span class="chip tiny">{b.topic}</span>{/if}
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .page { max-width: 900px; margin: 0 auto; padding-bottom: 4rem; }
  .breadcrumb { font-size: 0.83rem; margin-bottom: 1rem; color: var(--muted); }
  .breadcrumb a { color: var(--accent); text-decoration: none; }
  h1 { font-size: 1.55rem; font-weight: 800; margin-bottom: 0.3rem; }
  .sub { color: var(--muted); font-size: 0.87rem; margin-bottom: 1.5rem; }
  .error { color: var(--accent); font-size: 0.85rem; margin-bottom: 1rem; }
  .section { font-size: 1.1rem; font-weight: 700; margin: 1.75rem 0 0.9rem; }

  .kpis { display: flex; gap: 1rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
  .kpi { flex: 1; min-width: 130px; background: var(--surface); border: 1px solid var(--border);
         border-radius: 10px; padding: 1rem 1.2rem; }
  .kpi b { display: block; font-size: 1.7rem; font-weight: 800; line-height: 1.1; }
  .kpi span { font-size: 0.74rem; color: var(--muted); }

  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
           padding: 1.25rem; margin-bottom: 1.25rem; }
  .panel h2 { font-size: 1.05rem; font-weight: 700; }
  .panel-sub { font-size: 0.78rem; color: var(--muted); margin: 0.25rem 0 1rem; }
  .bar-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.55rem; font-size: 0.8rem; }
  .bar-label { flex: 0 0 34%; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar { flex: 1; height: 8px; background: var(--surface2); border-radius: 999px; overflow: hidden; }
  .fill { height: 100%; background: var(--success); border-radius: 999px; }
  .fill.mid { background: #ffc107; }
  .fill.low { background: #e05260; }
  .bar-val { flex: 0 0 90px; text-align: right; font-variant-numeric: tabular-nums; }
  .bar-val em { color: var(--muted); font-style: normal; font-size: 0.72rem; }

  .rows { display: flex; flex-direction: column; gap: 0.9rem; }
  .row-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.15rem; }
  .row-head { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
  .who { display: flex; flex-direction: column; gap: 0.15rem; }
  .who b { font-size: 0.98rem; }
  .muted { color: var(--muted); font-size: 0.79rem; }
  .tiny { font-size: 0.72rem; }
  .score-box { display: flex; flex-direction: column; align-items: flex-end; gap: 0.15rem; }
  .score { font-size: 1.6rem; font-weight: 800; line-height: 1; }
  .score.pass { color: var(--success); }
  .score.fail { color: #e05260; }
  .verdict { font-size: 0.66rem; font-weight: 800; letter-spacing: 0.06em; color: #e05260;
             border: 1px solid currentColor; border-radius: 999px; padding: 0.1rem 0.45rem; }
  .verdict.pass { color: var(--success); }

  .row-actions { display: flex; gap: 0.5rem; margin-top: 0.9rem; flex-wrap: wrap; }
  .btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: 6px;
         padding: 0.4rem 0.85rem; font-size: 0.8rem; font-weight: 600; cursor: pointer; }
  .btn:hover:not(:disabled) { border-color: var(--accent); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .ai { margin-top: 1rem; background: var(--surface2); border: 1px solid var(--border);
        border-left: 3px solid var(--accent); border-radius: 8px; padding: 1rem; }
  .ai-head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.5rem; flex-wrap: wrap; }
  .ai-title { font-size: 0.85rem; font-weight: 700; }
  .tag { font-size: 0.66rem; color: var(--muted); background: var(--surface); border-radius: 999px; padding: 0.12rem 0.5rem; }
  .ai-summary { font-size: 0.85rem; line-height: 1.6; margin-bottom: 0.85rem; }
  .weak-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .weak { background: var(--surface); border-radius: 6px; padding: 0.65rem 0.8rem; }
  .weak-top { display: flex; justify-content: space-between; font-size: 0.83rem; }
  .acc { color: #e05260; font-weight: 700; }
  .why { font-size: 0.78rem; color: var(--muted); margin-top: 0.2rem; }
  .action { font-size: 0.79rem; margin-top: 0.3rem; color: var(--accent); }
  .strengths { font-size: 0.79rem; color: var(--muted); margin-top: 0.75rem; }
  .recs { margin: 0.6rem 0 0 1.1rem; font-size: 0.79rem; line-height: 1.7; }

  .topics { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 1rem; }
  .chip { font-size: 0.71rem; color: var(--muted); background: var(--surface2); border-radius: 999px; padding: 0.18rem 0.55rem; }
  .chip.low { color: #e05260; }
  .chip.tiny { font-size: 0.66rem; }

  .answers { margin-top: 0.85rem; display: flex; flex-direction: column; gap: 0.6rem; }
  .ans { border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 0.9rem; border-left: 3px solid var(--success); }
  .ans.wrong { border-left-color: #e05260; }
  .ans-q { font-size: 0.85rem; font-weight: 600; display: flex; gap: 0.5rem; }
  .idx { color: var(--muted); flex-shrink: 0; }
  .ans-body { margin-top: 0.5rem; padding-left: 1.35rem; }
  .ans-line { display: flex; gap: 0.6rem; font-size: 0.8rem; margin-bottom: 0.2rem; flex-wrap: wrap; }
  .lbl { color: var(--muted); flex: 0 0 105px; }
  .good { color: var(--success); }
  .bad { color: #e05260; }
  .expl { font-size: 0.76rem; color: var(--muted); margin-top: 0.4rem; line-height: 1.55; }

  .empty { text-align: center; padding: 3rem 1rem; background: var(--surface);
           border: 1px solid var(--border); border-radius: 10px; }
  .empty-icon { font-size: 2.3rem; margin-bottom: 0.6rem; }
  .empty h2 { font-size: 1.1rem; margin-bottom: 0.35rem; }
  .empty p { color: var(--muted); font-size: 0.85rem; }

  .skeleton { border-radius: 10px; background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
              background-size: 200% 100%; animation: shimmer 1.4s infinite; }
  .skeleton.big { height: 340px; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

  @media (max-width: 640px) {
    .score-box { align-items: flex-start; }
    .bar-label { flex: 0 0 28%; }
  }
</style>
