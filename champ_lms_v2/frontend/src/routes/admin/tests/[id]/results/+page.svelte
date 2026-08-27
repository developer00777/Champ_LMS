<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, type TestResults, type AiAnalysis, type CohortCoaching } from '$lib/api/client';
  import Avatar from '$lib/components/Avatar.svelte';

  const id = $page.params.id;
  let data: TestResults | null = null;
  let loading = true;
  let error = '';
  let expanded: Record<string, boolean> = {};
  let analyzing: Record<string, boolean> = {};
  // Integrity timelines are opened per attempt — the event list is long and
  // only wanted when an admin is actually investigating one result.
  let timelineOpen: Record<string, boolean> = {};

  const RISK_LABELS: Record<string, string> = {
    clean: 'No issues',
    minor: 'Minor flags',
    suspicious: 'Needs review',
    high_risk: 'High risk',
  };

  function toggleTimeline(attemptId: string) {
    timelineOpen[attemptId] = !timelineOpen[attemptId];
    timelineOpen = timelineOpen;
  }

  function clockAt(seconds: number): string {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  /** Human label for an event kind, so admins don't read raw enum names. */
  function eventLabel(kind: string): string {
    const labels: Record<string, string> = {
      tab_hidden: 'Left the exam tab',
      tab_visible: 'Returned to the exam',
      window_blur: 'Window lost focus',
      window_focus: 'Window regained focus',
      copy_attempt: 'Tried to copy text',
      paste_attempt: 'Tried to paste into an answer',
      context_menu: 'Right-clicked',
      devtools_open: 'Developer tools',
      shortcut_blocked: 'Blocked shortcut',
      fullscreen_exit: 'Exited fullscreen',
      answer_burst: 'Answer appeared at once',
      multi_session: 'Exam open in another tab',
    };
    return labels[kind] ?? kind;
  }

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

  // --- cohort coaching -----------------------------------------------------
  // What to do about the results, for the whole group and per person, so the
  // admin can act on this page instead of just reading it.
  let coaching: CohortCoaching | null = null;
  let coachBusy = false;
  let coachError = '';
  let copied = '';

  async function coach() {
    coachBusy = true; coachError = '';
    try {
      coaching = await api.coachTestCohort(id);
    } catch (e: any) { coachError = e.message; }
    finally { coachBusy = false; }
  }

  async function copyMessage(userId: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      copied = userId;
      setTimeout(() => { if (copied === userId) copied = ''; }, 2000);
    } catch { /* clipboard blocked — the text is on screen to copy by hand */ }
  }

  $: cohortRanked = data
    ? Object.entries(data.cohort_topic_stats).sort((a, b) => a[1].accuracy - b[1].accuracy)
    : [];

  // --- extra attempts ------------------------------------------------------
  // Someone who has used up their attempts can be given more, one person at a
  // time. Keyed by user rather than attempt: the grant belongs to the person,
  // and they may have several rows on this page.
  let grantOpen: Record<string, boolean> = {};
  let grantCount: Record<string, number> = {};
  let grantReason: Record<string, string> = {};
  let grantBusy: Record<string, boolean> = {};

  function toggleGrant(userId: string) {
    grantOpen[userId] = !grantOpen[userId];
    if (grantCount[userId] == null) grantCount[userId] = 1;
    grantOpen = grantOpen; grantCount = grantCount;
  }

  /** Apply a new allowance to every row belonging to this person. */
  function applyAllowance(userId: string, allowed: number | null, extra: number) {
    if (!data) return;
    for (const row of data.attempts) {
      if (row.user_id !== userId) continue;
      row.attempts_allowed = allowed;
      row.extra_attempts_granted = extra;
      row.attempts_left = allowed === null ? null : Math.max(0, allowed - row.attempts_used);
      row.attempts_exhausted = allowed !== null && row.attempts_used >= allowed;
    }
    data = data;
  }

  async function grant(userId: string) {
    grantBusy[userId] = true; grantBusy = grantBusy; error = '';
    try {
      const r = await api.grantExtraAttempts(id, {
        user_id: userId,
        extra_attempts: grantCount[userId] || 1,
        reason: grantReason[userId]?.trim() || null,
      });
      applyAllowance(userId, r.allowed, r.granted_extra);
      if (data) {
        data.grants = [
          { grant_id: r.grant_id, user_id: r.user_id, full_name: r.full_name,
            extra_attempts: r.extra_attempts, reason: r.reason,
            granted_by: '', granted_at: r.granted_at },
          ...data.grants,
        ];
        data = data;
      }
      grantOpen[userId] = false; grantOpen = grantOpen;
      grantReason[userId] = ''; grantReason = grantReason;
    } catch (e: any) { error = e.message; }
    finally { grantBusy[userId] = false; grantBusy = grantBusy; }
  }

  async function revokeGrant(grantId: string, userId: string) {
    grantBusy[userId] = true; grantBusy = grantBusy; error = '';
    try {
      const r = await api.revokeAttemptGrant(id, grantId);
      if (data) {
        data.grants = data.grants.filter((g) => g.grant_id !== grantId);
        const stillGranted = data.grants
          .filter((g) => g.user_id === userId)
          .reduce((sum, g) => sum + g.extra_attempts, 0);
        applyAllowance(userId, r.allowed, stillGranted);
      }
    } catch (e: any) { error = e.message; }
    finally { grantBusy[userId] = false; grantBusy = grantBusy; }
  }
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

    {#if data.attempts.length > 0}
      <div class="panel coach-panel">
        <div class="coach-head">
          <div>
            <h2>🤖 What to suggest</h2>
            <p class="panel-sub">
              AI coaching across everyone's latest attempt: what the group should
              work on, plus a ready-to-send note for each person who needs one.
            </p>
          </div>
          <button class="btn primary" disabled={coachBusy} on:click={coach}>
            {coachBusy ? 'Thinking…' : coaching ? 'Regenerate' : 'Get coaching plan'}
          </button>
        </div>

        {#if coachError}<p class="error">{coachError}</p>{/if}

        {#if coaching}
          {@const g = coaching.guidance}
          <p class="coach-summary">{g.cohort_summary}</p>

          {#if g.weakest_topics?.length}
            <h3 class="coach-h3">Weakest areas</h3>
            <div class="weak-list">
              {#each g.weakest_topics as w}
                <div class="weak">
                  <div class="weak-top"><b>{w.topic}</b><span class="acc">{w.accuracy}%</span></div>
                  <p class="why">{w.why_it_matters}</p>
                </div>
              {/each}
            </div>
          {/if}

          {#if g.group_actions?.length}
            <h3 class="coach-h3">Run this for the group</h3>
            <ul class="recs">{#each g.group_actions as a}<li>{a}</li>{/each}</ul>
          {/if}

          {#if g.per_learner?.length}
            <h3 class="coach-h3">Person by person</h3>
            <div class="learners">
              {#each g.per_learner as l (l.user_id)}
                <div class="learner">
                  <div class="learner-top">
                    <b>{l.full_name}</b>
                    <span class="learner-score">{l.score}%</span>
                  </div>
                  <p class="focus"><b>Focus:</b> {l.focus}</p>
                  <blockquote>{l.message_to_learner}</blockquote>
                  <button class="btn small" on:click={() => copyMessage(l.user_id, l.message_to_learner)}>
                    {copied === l.user_id ? 'Copied ✓' : 'Copy message'}
                  </button>
                </div>
              {/each}
            </div>
          {/if}
        {/if}
      </div>
    {/if}

    {#if data.attempts.length === 0}
      <div class="empty">
        <div class="empty-icon">📊</div>
        <h2>No attempts yet</h2>
        <p>Once learners take this test, their scores, answers and AI recommendations appear here.</p>
      </div>
    {:else}
    {#if data.grants.length > 0}
      <h2 class="section">Extra attempts granted</h2>
      <div class="grants">
        {#each data.grants as g (g.grant_id)}
          <div class="grant-row">
            <div>
              <b>{g.full_name || 'Unknown'}</b>
              <span class="muted"> +{g.extra_attempts} attempt{g.extra_attempts === 1 ? '' : 's'}</span>
              {#if g.reason}<span class="muted tiny"> · “{g.reason}”</span>{/if}
              <span class="muted tiny"> · {new Date(g.granted_at).toLocaleString()}</span>
            </div>
            <button class="btn tiny-btn" disabled={grantBusy[g.user_id]}
                    on:click={() => revokeGrant(g.grant_id, g.user_id)}>
              Revoke
            </button>
          </div>
        {/each}
      </div>
    {/if}

      <h2 class="section">Individual results</h2>
      <div class="rows">
        {#each data.attempts as a (a.attempt_id)}
          <div class="row-card">
            <div class="row-head">
              <div class="who">
                <Avatar src={a.avatar_url} name={a.full_name} size={40} />
                <div class="who-text">
                  <b>
                    {a.full_name || a.email || 'Unknown'}
                    {#if a.employee_code}<span class="code">{a.employee_code}</span>{/if}
                  </b>
                  <span class="muted">{a.email}{a.department ? ` · ${a.department}` : ''}</span>
                  <span class="muted tiny">{new Date(a.submitted_at).toLocaleString()}</span>
                </div>
              </div>
              <div class="score-box">
                <span class="score" class:pass={a.passed} class:fail={!a.passed}>{a.score}%</span>
                <span class="muted tiny">
                  {a.correct_count}/{a.total_questions} correct · {a.marks_earned}/{a.marks_total} marks
                </span>
                <span class="verdict" class:pass={a.passed}>{a.passed ? 'PASSED' : 'FAILED'}</span>
                {#if a.proctoring}
                  <span class="risk risk-{a.proctoring.risk_level}"
                        title={`Integrity risk ${a.proctoring.risk_score}/100`}>
                    {RISK_LABELS[a.proctoring.risk_level] ?? a.proctoring.risk_level}
                  </span>
                {:else}
                  <span class="risk risk-none" title="This attempt was not proctored">
                    Not proctored
                  </span>
                {/if}
                {#if a.attempts_allowed !== null}
                  <span class="attempts" class:spent={a.attempts_exhausted}>
                    {a.attempts_used}/{a.attempts_allowed} attempts
                    {#if a.extra_attempts_granted > 0}
                      <span class="granted" title="Extra attempts granted by an admin">
                        +{a.extra_attempts_granted}
                      </span>
                    {/if}
                  </span>
                {/if}
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
              {#if a.attempts_allowed !== null}
                <button
                  class="btn"
                  class:primary={a.attempts_exhausted}
                  disabled={grantBusy[a.user_id]}
                  on:click={() => toggleGrant(a.user_id)}
                >
                  {grantOpen[a.user_id] ? 'Cancel' : '+ Grant attempt'}
                </button>
              {/if}
            </div>

            {#if grantOpen[a.user_id]}
              <div class="grant-box">
                <p class="grant-lead">
                  {a.full_name || a.email || 'This person'} has used
                  <b>{a.attempts_used} of {a.attempts_allowed}</b> attempts.
                  Extra attempts apply to them only.
                </p>
                <div class="grant-fields">
                  <label>
                    Extra attempts
                    <input type="number" min="1" max="20" bind:value={grantCount[a.user_id]} />
                  </label>
                  <label class="grow">
                    Reason (optional, kept on the record)
                    <input bind:value={grantReason[a.user_id]}
                           placeholder="e.g. Browser crashed mid-exam" />
                  </label>
                </div>
                <button class="btn primary" disabled={grantBusy[a.user_id]}
                        on:click={() => grant(a.user_id)}>
                  {grantBusy[a.user_id] ? 'Granting…' : 'Grant'}
                </button>
              </div>
            {/if}

            {#if a.proctoring && (a.proctoring.findings.length || a.proctoring.risk_score > 0 || a.proctoring.telemetry_missing)}
              {@const pr = a.proctoring}
              <div class="integrity risk-border-{pr.risk_level}">
                <div class="integrity-head">
                  <span class="integrity-title">🛡 Proctoring review</span>
                  <span class="integrity-score">{pr.risk_score}/100</span>
                  {#if pr.verdict_by === 'rules'}
                    <span class="tag">rules only (AI review unavailable)</span>
                  {/if}
                  {#if pr.telemetry_missing}
                    <span class="tag danger">no telemetry received</span>
                  {/if}
                </div>
                {#if pr.summary}<p class="integrity-summary">{pr.summary}</p>{/if}
                {#if pr.findings.length}
                  <ul class="integrity-findings">
                    {#each pr.findings as f}<li>{f}</li>{/each}
                  </ul>
                {/if}
                <p class="integrity-meta">
                  {pr.event_count} event(s) recorded · {pr.away_seconds}s away in total
                  {#if pr.longest_away_seconds}· longest absence {pr.longest_away_seconds}s{/if}
                </p>
                {#if pr.event_count}
                  <button class="btn small" on:click={() => toggleTimeline(a.attempt_id)}>
                    {timelineOpen[a.attempt_id] ? 'Hide' : 'Show'} timeline
                  </button>
                {/if}
                {#if timelineOpen[a.attempt_id] && pr.events?.length}
                  <ol class="timeline">
                    {#each pr.events as e}
                      <li>
                        <span class="t-at">{clockAt(e.at_seconds)}</span>
                        <span class="t-kind">{eventLabel(e.kind)}</span>
                        {#if e.duration_seconds}<span class="t-dur">{e.duration_seconds}s</span>{/if}
                        {#if e.detail}<span class="t-detail">{e.detail}</span>{/if}
                      </li>
                    {/each}
                  </ol>
                {/if}
              </div>
            {/if}

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

  .coach-panel { border-left: 3px solid var(--accent); }
  .coach-head { display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; flex-wrap: wrap; }
  .coach-summary { font-size: 0.87rem; line-height: 1.65; margin: 0.9rem 0 0.25rem; }
  .coach-h3 { font-size: 0.82rem; font-weight: 700; text-transform: uppercase;
              letter-spacing: 0.05em; color: var(--muted); margin: 1.1rem 0 0.55rem; }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn.small { padding: 0.28rem 0.6rem; font-size: 0.74rem; }
  .learners { display: flex; flex-direction: column; gap: 0.7rem; }
  .learner { background: var(--surface2); border-radius: 8px; padding: 0.8rem 0.95rem; }
  .learner-top { display: flex; justify-content: space-between; align-items: baseline; gap: 0.75rem; font-size: 0.9rem; }
  .learner-score { font-weight: 800; color: var(--muted); font-variant-numeric: tabular-nums; }
  .focus { font-size: 0.79rem; color: var(--muted); margin: 0.35rem 0 0.5rem; }
  .learner blockquote {
    margin: 0 0 0.6rem; padding: 0.55rem 0.75rem; font-size: 0.81rem; line-height: 1.6;
    background: var(--surface); border-left: 2px solid var(--border); border-radius: 0 6px 6px 0;
  }

  .rows { display: flex; flex-direction: column; gap: 0.9rem; }
  .row-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.15rem; }
  .row-head { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
  .attempts { font-size: 0.72rem; color: var(--muted); border: 1px solid var(--border);
              border-radius: 999px; padding: 0.15rem 0.55rem; }
  .attempts.spent { color: #ffc107; border-color: #ffc107; }
  .granted { color: var(--success); font-weight: 700; }
  .grant-box { margin-top: 0.8rem; padding: 0.9rem; border: 1px solid var(--border);
               border-radius: 10px; background: var(--surface2); }
  .grant-lead { font-size: 0.83rem; color: var(--muted); margin-bottom: 0.7rem; }
  .grant-fields { display: flex; gap: 0.8rem; flex-wrap: wrap; margin-bottom: 0.7rem; }
  .grant-fields label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.78rem; }
  .grant-fields .grow { flex: 1; min-width: 220px; }
  .grants { display: flex; flex-direction: column; gap: 0.5rem; margin-bottom: 1.5rem; }
  .grant-row { display: flex; justify-content: space-between; align-items: center; gap: 1rem;
               padding: 0.6rem 0.9rem; border: 1px solid var(--border); border-radius: 10px;
               font-size: 0.85rem; flex-wrap: wrap; }
  .tiny-btn { font-size: 0.75rem; padding: 0.25rem 0.6rem; }
  .who { display: flex; align-items: center; gap: 0.7rem; }
  .who-text { display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; }
  .who .code {
    font-size: 0.68rem; font-weight: 700; color: var(--muted);
    background: var(--surface2); border-radius: 999px; padding: 0.1rem 0.45rem;
    margin-left: 0.4rem; letter-spacing: 0.03em;
  }
  .who b { font-size: 0.98rem; }
  .muted { color: var(--muted); font-size: 0.79rem; }
  .tiny { font-size: 0.72rem; }
  /* --- proctoring verdict ------------------------------------------------ */
  .risk { font-size: 0.66rem; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase;
          border-radius: 999px; padding: 0.1rem 0.5rem; border: 1px solid; margin-top: 0.1rem; }
  .risk-clean { color: var(--success); border-color: var(--success); }
  .risk-minor { color: #c9a227; border-color: #c9a227; }
  .risk-suspicious { color: #e08a3c; border-color: #e08a3c; }
  .risk-high_risk { color: #fff; background: #c0392b; border-color: #c0392b; }
  .risk-none { color: var(--muted); border-color: var(--border); }

  .integrity { margin-top: 0.9rem; background: var(--surface2); border: 1px solid var(--border);
               border-left-width: 3px; border-radius: 8px; padding: 0.85rem 1rem; }
  .risk-border-clean { border-left-color: var(--success); }
  .risk-border-minor { border-left-color: #c9a227; }
  .risk-border-suspicious { border-left-color: #e08a3c; }
  .risk-border-high_risk { border-left-color: #c0392b; }
  .integrity-head { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.45rem; }
  .integrity-title { font-size: 0.8rem; font-weight: 800; }
  .integrity-score { font-size: 0.75rem; font-weight: 800; color: var(--muted);
                     font-variant-numeric: tabular-nums; }
  .tag.danger { color: #c0392b; border-color: #c0392b; }
  .integrity-summary { font-size: 0.82rem; line-height: 1.55; margin-bottom: 0.5rem; }
  .integrity-findings { margin: 0 0 0.5rem 1.1rem; font-size: 0.79rem; line-height: 1.6; color: var(--text); }
  .integrity-meta { font-size: 0.72rem; color: var(--muted); margin-bottom: 0.5rem; }
  .btn.small { padding: 0.3rem 0.7rem; font-size: 0.74rem; }

  .timeline { margin: 0.6rem 0 0; padding: 0; list-style: none; display: flex;
              flex-direction: column; gap: 0.2rem; max-height: 320px; overflow-y: auto; }
  .timeline li { display: flex; align-items: baseline; gap: 0.55rem; font-size: 0.74rem;
                 padding: 0.28rem 0.4rem; border-radius: 4px; background: var(--surface); flex-wrap: wrap; }
  .t-at { font-variant-numeric: tabular-nums; color: var(--muted); font-weight: 700; flex-shrink: 0; }
  .t-kind { font-weight: 600; }
  .t-dur { color: #e08a3c; font-weight: 700; }
  .t-detail { color: var(--muted); }

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
