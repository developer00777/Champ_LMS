<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, type TestResults, type TestResultRow, type AiAnalysis, type CohortCoaching } from '$lib/api/client';
  import Avatar from '$lib/components/Avatar.svelte';
  import { buildTestReport } from '$lib/reports/model';
  import { downloadResultsCsv } from '$lib/reports/csv';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import { countUp, reveal } from '$lib/actions/motion';
  import SortHeader from '$lib/components/SortHeader.svelte';
  import { sortRows, NO_SORT, type SortAccessors } from '$lib/utils/table-sort';

  const id = $page.params.id;
  let data: TestResults | null = null;
  let loading = true;
  let error = '';
  let expanded: Record<string, boolean> = {};
  let analyzing: Record<string, boolean> = {};
  // Integrity timelines are opened per attempt — the event list is long and
  // only wanted when an admin is actually investigating one result.
  let timelineOpen: Record<string, boolean> = {};

  // Mirrors STAFF_ROLES on the backend: these accounts administer the platform,
  // so their attempts are shown but never counted.
  const STAFF_ROLES = ['admin', 'ld_lead'];
  const isStaff = (role: string | null) => STAFF_ROLES.includes(role ?? '');

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
  // guidance is AI-written JSON: treat every key as possibly missing.
  const guide = (c: CohortCoaching): Partial<CohortCoaching['guidance']> => c.guidance ?? {};
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

  // --- downloadable report -------------------------------------------------
  // Both exports read the same derived analysis, so the spreadsheet and the
  // board PDF can never disagree. A coaching plan generated above is folded in
  // when it exists, rather than telling a second, separate story.
  let reportBusy = '';
  let reportError = '';

  function download(kind: 'csv' | 'pdf') {
    if (!data) return;
    reportBusy = kind;
    reportError = '';
    const model = buildTestReport(data, coaching);
    if (model.attemptCount === 0) {
      reportBusy = '';
      reportError =
        'Every attempt on this test was made by an admin account, so there is nothing to report yet.';
      return;
    }
    const run = kind === 'csv'
      ? Promise.resolve(downloadResultsCsv(model))
      // jsPDF is ~350KB - loaded only when an admin actually asks for the PDF.
      : import('$lib/reports/pdf').then((mod) => mod.downloadResultsPdf(model));
    run
      .catch((e: any) => { reportError = e?.message ?? 'Could not build the report.'; })
      .finally(() => { reportBusy = ''; });
  }

  // --- presentation only ---------------------------------------------------
  // Score spread over the counted (non-staff) attempts, for the bar chart.
  $: counted = data ? data.attempts.filter((a) => !isStaff(a.role)) : [];
  $: spread = [
    { label: '90–100%', tone: 'mint', n: counted.filter((a) => a.score >= 90).length },
    { label: '70–89%', tone: 'sky', n: counted.filter((a) => a.score >= 70 && a.score < 90).length },
    { label: '50–69%', tone: 'butter', n: counted.filter((a) => a.score >= 50 && a.score < 70).length },
    { label: 'Under 50%', tone: 'peach', n: counted.filter((a) => a.score < 50).length },
  ];
  $: spreadMax = Math.max(1, ...spread.map((s) => s.n));
  const RISK_ICON: Record<string, string> = { clean: 'checkCircle', minor: 'info', suspicious: 'alert', high_risk: 'xCircle' };

  // Individual results are cards, so the sort controls sit above them rather
  // than in a table header. Unproctored attempts have no risk and sort last.
  const RESULT_SORT: SortAccessors<TestResultRow> = {
    name: (a) => a.full_name || a.email,
    score: (a) => a.score,
    submitted: (a) => new Date(a.submitted_at),
    risk: (a) => a.proctoring?.risk_score,
  };
  const SORT_FIELDS = [
    { field: 'name', label: 'Name' },
    { field: 'score', label: 'Score' },
    { field: 'submitted', label: 'Submitted' },
    { field: 'risk', label: 'Integrity risk' },
  ];
  let resultSort = NO_SORT;
  $: sortedAttempts = sortRows(data?.attempts ?? [], resultSort, RESULT_SORT);
</script>

<svelte:head><title>{data?.title ? `${data.title} results` : 'Results'} — Champ LMS</title></svelte:head>

<div class="page">
  <Breadcrumbs items={[
    { label: 'Admin', href: '/admin' },
    { label: 'Test Series', href: '/admin/tests' },
    { label: data?.title || 'Test', href: `/admin/tests/${id}` },
    { label: 'Results' },
  ]} />

  {#if loading}
    <div class="ui-skeleton" style="height:90px;border-radius:24px;margin-bottom:1.25rem"></div>
    <div class="kpis">{#each Array(3) as _}<div class="ui-skeleton" style="height:112px;border-radius:24px"></div>{/each}</div>
    <div class="ui-skeleton" style="height:220px;border-radius:28px;margin-bottom:1.25rem"></div>
    {#each Array(3) as _}<div class="ui-skeleton" style="height:130px;border-radius:24px;margin-bottom:0.9rem"></div>{/each}
  {:else if error && !data}
    <div class="state ui-rise">
      <span class="state-ico danger"><Icon name="alert" size={26} /></span>
      <h2>Couldn't load results</h2>
      <p>{error}</p>
      <button class="btn-primary" on:click={load}><Icon name="refresh" size={16} /> Try again</button>
    </div>
  {:else if data}
    <header class="head">
      <p class="eyebrow ui-rise" style="--i:1">Results · pass mark {data.pass_threshold}% · {data.total_questions} questions</p>
      <h1 class="ui-rise" style="--i:2">
        <span class="title-text">{data.title}</span>
        <span class="title-mark" aria-hidden="true"><Icon name="chart" size={22} /></span>
      </h1>
    </header>
    {#if error}<p class="note bad" role="alert"><Icon name="alert" size={16} /> {error}</p>{/if}

    <div class="kpis">
      <div class="kpi sky ui-rise" style="--i:3">
        <span class="k-ico"><Icon name="users" size={18} /></span>
        <b use:countUp={data.attempt_count}></b><span>attempts</span>
      </div>
      <div class="kpi lilac ui-rise" style="--i:4">
        <span class="k-ico"><Icon name="target" size={18} /></span>
        {#if data.average_score != null}<b><span use:countUp={data.average_score}></span><i>%</i></b>{:else}<b>—</b>{/if}
        <span>average score</span>
      </div>
      <div class="kpi mint ui-rise" style="--i:5">
        <span class="k-ico"><Icon name="checkCircle" size={18} /></span>
        {#if data.pass_rate != null}<b><span use:countUp={data.pass_rate}></span><i>%</i></b>{:else}<b>—</b>{/if}
        <span>pass rate</span>
      </div>
    </div>

    {#if data.excluded_staff_count > 0}
      <p class="staff-note ui-rise" style="--i:6">
        <Icon name="info" size={15} />
        <span>
          {data.excluded_staff_count} attempt{data.excluded_staff_count === 1 ? '' : 's'} by admin
          or L&amp;D lead account{data.excluded_staff_count === 1 ? '' : 's'} {data.excluded_staff_count === 1 ? 'is' : 'are'}
          listed below but left out of these figures, the topic accuracy and the downloads.
        </span>
      </p>
    {/if}

    {#if data.attempts.length > 0}
      <section class="panel report-panel ui-rise" style="--i:6">
        <div class="report-head">
          <span class="p-ico butter"><Icon name="download" size={19} /></span>
          <div class="p-copy">
            <h2>Download the report</h2>
            <p class="panel-sub">
              The whole analysis — bands, topic accuracy, per-person scores and the
              recommended focus — as a spreadsheet, or as the leadership-board deck
              you can circulate as-is.
            </p>
          </div>
          <div class="report-actions">
            <button class="btn-ghost" disabled={reportBusy === 'csv'} on:click={() => download('csv')}>
              {#if reportBusy === 'csv'}<span class="spin"></span> Building…{:else}<Icon name="file" size={16} /> Analysis (CSV){/if}
            </button>
            <button class="btn-primary" disabled={reportBusy === 'pdf'} on:click={() => download('pdf')}>
              {#if reportBusy === 'pdf'}<span class="spin light"></span> Building…{:else}<Icon name="download" size={16} /> Leadership board (PDF){/if}
            </button>
          </div>
        </div>
        <p class="report-note">
          PDF: landscape A4 with bookmarks and clickable page navigation — cover board,
          four-tier roster, and key points for improvisation. Attempts made by admin and
          L&amp;D lead accounts are left out, matching the figures above.
          {#if coaching}Includes the AI coaching plan generated above.{/if}
        </p>
        {#if reportError}<p class="note bad"><Icon name="alert" size={16} /> {reportError}</p>{/if}
      </section>
    {/if}

    {#if counted.length > 0 || cohortRanked.length}
      <div class="two">
        {#if counted.length > 0}
          <section class="panel" use:reveal>
            <h2>Score spread</h2>
            <p class="panel-sub">Counted attempts by score band.</p>
            <div class="spread">
              {#each spread as s, i}
                <div class="col">
                  <span class="col-n">{s.n}</span>
                  <div class="col-track">
                    <div class="col-fill {s.tone}" style="height:{(s.n / spreadMax) * 100}%; --d:{i * 90}ms"></div>
                  </div>
                  <span class="col-l">{s.label}</span>
                </div>
              {/each}
            </div>
          </section>
        {/if}

        {#if cohortRanked.length}
          <section class="panel" use:reveal={{ delay: 80 }}>
            <h2>Where the team struggles</h2>
            <p class="panel-sub">Accuracy across every attempt, weakest first — use this to target training.</p>
            {#each cohortRanked as [topic, s], i}
              <div class="bar-row">
                <span class="bar-label" title={topic}>{topic}</span>
                <div class="bar"><div class="fill" class:low={s.accuracy < 50} class:mid={s.accuracy >= 50 && s.accuracy < 80}
                                      style="width:{s.accuracy}%; --d:{Math.min(i, 10) * 70}ms"></div></div>
                <span class="bar-val">{s.accuracy}% <em>({s.correct}/{s.total})</em></span>
              </div>
            {/each}
          </section>
        {/if}
      </div>
    {/if}

    {#if data.attempts.length > 0}
      <section class="panel coach-panel" use:reveal>
        <div class="coach-head">
          <span class="p-ico lilac"><Icon name="sparkles" size={19} /></span>
          <div class="p-copy">
            <h2>What to suggest</h2>
            <p class="panel-sub">
              AI coaching across everyone's latest attempt: what the group should
              work on, plus a ready-to-send note for each person who needs one.
            </p>
          </div>
          <button class="btn-primary" disabled={coachBusy} on:click={coach}>
            {#if coachBusy}<span class="spin light"></span> Thinking…{:else}<Icon name="sparkles" size={16} /> {coaching ? 'Regenerate' : 'Get coaching plan'}{/if}
          </button>
        </div>

        {#if coachError}<p class="note bad"><Icon name="alert" size={16} /> {coachError}</p>{/if}

        {#if coaching}
          {@const g = guide(coaching)}
          <!-- guidance is AI-written JSON: any key can be missing. -->
          <div class="coach-body">
            {#if g.cohort_summary}<p class="coach-summary">{g.cohort_summary}</p>{/if}

            {#if g.weakest_topics?.length}
              <h3 class="coach-h3">Weakest areas</h3>
              <div class="weak-list">
                {#each g.weakest_topics as w, i}
                  <div class="weak ui-rise" style="--i:{Math.min(i, 8)}">
                    <div class="weak-top"><b>{w.topic}</b><span class="acc">{w.accuracy}%</span></div>
                    <p class="why">{w.why_it_matters}</p>
                  </div>
                {/each}
              </div>
            {/if}

            {#if g.group_actions?.length}
              <h3 class="coach-h3">Run this for the group</h3>
              <ul class="recs">{#each g.group_actions as a}<li><Icon name="check" size={15} /><span>{a}</span></li>{/each}</ul>
            {/if}

            {#if g.per_learner?.length}
              <h3 class="coach-h3">Person by person</h3>
              <div class="learners">
                {#each g.per_learner as l, i (`${l.user_id ?? ''}-${i}`)}
                  <div class="learner ui-rise" style="--i:{Math.min(i, 8)}">
                    <div class="learner-top">
                      <b>{l.full_name}</b>
                      <span class="learner-score">{l.score}%</span>
                    </div>
                    <p class="focus"><b>Focus:</b> {l.focus}</p>
                    <blockquote><Icon name="message" size={15} /><span>{l.message_to_learner}</span></blockquote>
                    <button class="btn-ghost small" class:copied={copied === l.user_id} on:click={() => copyMessage(l.user_id, l.message_to_learner)}>
                      <Icon name={copied === l.user_id ? 'check' : 'copy'} size={14} />
                      {copied === l.user_id ? 'Copied ✓' : 'Copy message'}
                    </button>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {/if}
      </section>
    {/if}

    {#if data.attempts.length === 0}
      <div class="state ui-rise" style="--i:6">
        <span class="state-ico"><Icon name="chart" size={26} /></span>
        <h2>No attempts yet</h2>
        <p>Once learners take this test, their scores, answers and AI recommendations appear here.</p>
      </div>
    {:else}
      <div class="results-head">
        <h2 class="section">Individual results <span class="count">{data.attempts.length}</span></h2>
        <div class="sort-bar" role="group" aria-label="Sort results">
          <span class="sort-lbl">Sort by</span>
          {#each SORT_FIELDS as s}
            <span class="sort-chip" class:on={resultSort.key === s.field && resultSort.dir !== 'none'}>
              <SortHeader field={s.field} bind:sort={resultSort}>{s.label}</SortHeader>
            </span>
          {/each}
        </div>
      </div>
      <div class="rows">
        {#each sortedAttempts as a, n (a.attempt_id)}
          <div class="row-card" use:reveal={{ delay: (n % 4) * 60 }}>
            <div class="row-head">
              <div class="who">
                <Avatar src={a.avatar_url} name={a.full_name} size={44} />
                <div class="who-text">
                  <b>
                    {a.full_name || a.email || 'Unknown'}
                    {#if a.employee_code}<span class="code">{a.employee_code}</span>{/if}
                    {#if isStaff(a.role)}<span class="staff-tag">not counted</span>{/if}
                  </b>
                  <span class="muted">{a.email}{a.department ? ` · ${a.department}` : ''}</span>
                  <span class="muted tiny"><Icon name="calendar" size={12} /> {new Date(a.submitted_at).toLocaleString()}</span>
                </div>
              </div>
              <div class="score-box">
                <div class="ring" class:pass={a.passed} style="--p:{Math.max(0, Math.min(100, a.score))}">
                  <span class="score">{a.score}<i>%</i></span>
                </div>
                <div class="score-meta">
                  <span class="verdict" class:pass={a.passed}>
                    <Icon name={a.passed ? 'checkCircle' : 'xCircle'} size={13} /> {a.passed ? 'PASSED' : 'FAILED'}
                  </span>
                  <span class="muted tiny">
                    {a.correct_count}/{a.total_questions} correct · {a.marks_earned}/{a.marks_total} marks
                  </span>
                  {#if a.proctoring}
                    <span class="risk risk-{a.proctoring.risk_level}"
                          title={`Integrity risk ${a.proctoring.risk_score}/100`}>
                      <Icon name={RISK_ICON[a.proctoring.risk_level] ?? 'shield'} size={12} />
                      {RISK_LABELS[a.proctoring.risk_level] ?? a.proctoring.risk_level}
                    </span>
                  {:else}
                    <span class="risk risk-none" title="This attempt was not proctored">
                      Not proctored
                    </span>
                  {/if}
                </div>
              </div>
            </div>

            <div class="row-actions">
              <button class="btn-ghost small" class:on={expanded[a.attempt_id]} on:click={() => toggle(a.attempt_id)}>
                <span class="chev"><Icon name="chevronDown" size={15} /></span>
                {expanded[a.attempt_id] ? 'Hide' : 'View'} answers
              </button>
              <button class="btn-ghost small" disabled={analyzing[a.attempt_id]} on:click={() => analyze(a.attempt_id)}>
                {#if analyzing[a.attempt_id]}<span class="spin"></span>{:else}<Icon name="sparkles" size={14} />{/if}
                {analyzing[a.attempt_id]
                  ? 'Analysing…'
                  : a.has_ai_analysis ? 'Regenerate AI insight' : 'Get AI insight'}
              </button>
            </div>

            {#if a.proctoring && (a.proctoring.findings.length || a.proctoring.risk_score > 0 || a.proctoring.telemetry_missing)}
              {@const pr = a.proctoring}
              <div class="integrity tone-{pr.risk_level}">
                <div class="integrity-head">
                  <span class="integrity-title"><Icon name="shield" size={15} /> Proctoring review</span>
                  <span class="integrity-score">{pr.risk_score}/100</span>
                  {#if pr.verdict_by === 'rules'}
                    <span class="tag">rules only (AI review unavailable)</span>
                  {/if}
                  {#if pr.telemetry_missing}
                    <span class="tag danger">no telemetry received</span>
                  {/if}
                </div>
                <div class="risk-meter"><span style="width:{Math.max(0, Math.min(100, pr.risk_score))}%"></span></div>
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
                  <button class="btn-ghost small" on:click={() => toggleTimeline(a.attempt_id)}>
                    <Icon name="history" size={14} /> {timelineOpen[a.attempt_id] ? 'Hide' : 'Show'} timeline
                  </button>
                {/if}
                {#if timelineOpen[a.attempt_id] && pr.events?.length}
                  <ol class="timeline">
                    {#each pr.events as e, ti}
                      <li style="--d:{Math.min(ti, 12) * 30}ms">
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
                  <span class="ai-title"><Icon name="sparkles" size={15} /> Areas of improvement</span>
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
                        <p class="action"><Icon name="arrowRight" size={13} /> {w.action}</p>
                      </div>
                    {/each}
                  </div>
                {/if}
                {#if an?.strengths?.length}
                  <p class="strengths"><b>Strengths:</b> {an.strengths.join(', ')}</p>
                {/if}
                {#if an?.recommendations?.length}
                  <ul class="recs">{#each an.recommendations as r}<li><Icon name="check" size={15} /><span>{r}</span></li>{/each}</ul>
                {/if}
              </div>
            {/if}

            {#if expanded[a.attempt_id]}
              <div class="expand">
                <div class="topics">
                  {#each Object.entries(a.topic_stats) as [topic, s]}
                    <span class="chip" class:low={s.accuracy < 50}>{topic} {s.accuracy}%</span>
                  {/each}
                </div>
                <div class="answers">
                  {#each a.breakdown as b, i}
                    <div class="ans" class:wrong={!b.correct}>
                      <div class="ans-q">
                        <span class="idx" aria-label={b.correct ? 'Correct' : 'Wrong'}>
                          {#if b.correct}<Icon name="check" size={13} stroke={2.4} />{:else}<Icon name="close" size={13} stroke={2.4} />{/if}
                        </span>
                        <span><span class="qn">{i + 1}.</span> {b.question}</span>
                      </div>
                      <div class="ans-body">
                        <div class="ans-line">
                          <span class="lbl">Their answer</span>
                          <span class:bad={!b.correct} class:good={b.correct}>
                            {b.your_answer ?? '— skipped —'}
                          </span>
                        </div>
                        {#if b.question_type === 'written'}
                          <!-- Written answers are AI-graded: show the marks awarded,
                               the grader's feedback and the reference answer. -->
                          <div class="ans-line">
                            <span class="lbl">Marks</span>
                            <span>{b.awarded ?? 0} / {b.marks}{#if b.graded_by === 'ungraded'} · not graded yet{/if}</span>
                          </div>
                          {#if b.ai_feedback}<p class="expl">{b.ai_feedback}</p>{/if}
                          {#if b.correct_answer}
                            <div class="ans-line">
                              <span class="lbl">Reference answer</span>
                              <span class="good">{b.correct_answer}</span>
                            </div>
                          {/if}
                        {:else if !b.correct && b.correct_answer}
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
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .page { max-width: 980px; margin: 0 auto; }

  .head { margin-bottom: 1.25rem; }
  .eyebrow { color: var(--muted); font-size: 0.92rem; font-weight: 500; margin-bottom: 0.3rem; }
  h1 { font-size: clamp(1.6rem, 1.1rem + 1.6vw, 2.3rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.08; display: flex; align-items: center; gap: 0.6rem; }
  .title-text { min-width: 0; overflow-wrap: anywhere; }
  .title-mark {
    flex: none; display: inline-grid; place-items: center; width: 44px; height: 44px; border-radius: 50%;
    background: var(--tile-sky); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .section { display: flex; align-items: center; gap: 0.5rem; font-size: 1.4rem; font-weight: 700; letter-spacing: -0.02em; margin: 2rem 0 0.9rem; }
  .count { min-width: 26px; height: 24px; padding: 0 7px; border-radius: 99px; font-size: 0.78rem; display: inline-grid; place-items: center; background: var(--surface2); color: var(--text-secondary); }
  .results-head { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem 1rem; flex-wrap: wrap; margin: 2rem 0 0.9rem; }
  .results-head .section { margin: 0; }
  .sort-bar { display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap; }
  .sort-lbl { font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin-right: 0.15rem; }
  .sort-chip {
    display: inline-flex; height: 32px; border-radius: 999px;
    font-size: 0.8rem; font-weight: 600; background: var(--surface2); color: var(--text-secondary);
    transition: background-color var(--dur-2) var(--ease-out);
  }
  /* The whole pill is the click target, not just the label. */
  .sort-chip :global(.sort) { height: 100%; padding: 0 0.8rem; border-radius: inherit; }
  .sort-chip:hover { background: var(--surface3); }
  .sort-chip.on { background: color-mix(in srgb, var(--accent) 14%, var(--surface)); }

  .note {
    display: flex; align-items: flex-start; gap: 0.5rem; font-size: 0.86rem; font-weight: 500; line-height: 1.5;
    padding: 0.7rem 0.95rem; border-radius: 16px; margin: 0.6rem 0 1rem; animation: rise 360ms var(--ease-out);
  }
  .note :global(.icon) { flex: none; margin-top: 2px; }
  .note.bad { background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger); }

  /* ---------- KPIs ---------- */
  .kpis { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.9rem; margin-bottom: 1.25rem; }
  .kpi {
    display: flex; flex-direction: column; gap: 0.1rem; padding: 1rem 1.15rem 1.05rem;
    border-radius: 24px; color: var(--tile-ink);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .kpi:hover { translate: 0 -3px; box-shadow: var(--shadow); }
  .kpi b { font-size: clamp(1.7rem, 1.3rem + 1vw, 2.3rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.1; margin-top: 0.55rem; font-variant-numeric: tabular-nums; }
  .kpi b i { font-style: normal; font-size: 0.55em; opacity: 0.65; margin-left: 1px; }
  .kpi > span:last-child { font-size: 0.8rem; opacity: 0.72; font-weight: 500; }
  .kpi:hover b { animation: pop 420ms var(--ease-out); }
  .k-ico { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out); }
  .kpi:hover .k-ico { rotate: -14deg; scale: 1.1; }
  .kpi.sky { background: var(--tile-sky); } .kpi.lilac { background: var(--tile-lilac); } .kpi.mint { background: var(--tile-mint); }

  .staff-note {
    display: flex; gap: 0.5rem; align-items: flex-start;
    font-size: 0.8rem; color: var(--muted); line-height: 1.5;
    margin: -0.3rem 0 1.25rem; padding: 0.65rem 0.9rem; border-radius: 16px; background: var(--surface2);
  }
  .staff-note :global(.icon) { flex: none; margin-top: 2px; }
  .staff-tag { font-size: 0.64rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); background: var(--surface2); border-radius: 999px; padding: 0.12rem 0.5rem; margin-left: 0.3rem; }

  /* ---------- panels ---------- */
  .panel { background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-sm); padding: 1.3rem 1.4rem; margin-bottom: 1.25rem; }
  .panel h2 { font-size: 1.15rem; font-weight: 700; letter-spacing: -0.02em; }
  .panel-sub { font-size: 0.82rem; color: var(--muted); margin: 0.25rem 0 1rem; line-height: 1.5; }
  .p-ico { flex: none; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; color: var(--tile-ink); transition: rotate var(--dur-3) var(--ease-out); }
  .panel:hover .p-ico { rotate: -12deg; }
  .p-ico.butter { background: var(--tile-butter); } .p-ico.lilac { background: var(--tile-lilac); }
  .p-copy { flex: 1; min-width: 220px; }
  .p-copy .panel-sub { margin-bottom: 0; }
  .report-head, .coach-head { display: flex; gap: 0.9rem; align-items: flex-start; flex-wrap: wrap; }
  .report-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .report-actions :global(.icon), .coach-head :global(.icon) { flex: none; }
  .report-panel:hover .report-actions .btn-primary :global(.icon) { animation: nudge 900ms var(--ease-out) infinite; }
  @keyframes nudge { 0%, 100% { translate: 0 0; } 50% { translate: 0 2px; } }
  .report-note { font-size: 0.76rem; color: var(--muted); margin-top: 0.9rem; padding: 0.65rem 0.85rem; border-radius: 14px; background: var(--surface2); line-height: 1.55; }

  .two { display: grid; grid-template-columns: minmax(0, 0.8fr) minmax(0, 1.2fr); gap: 1.25rem; align-items: start; }
  .two > .panel:only-child { grid-column: 1 / -1; }

  .spread { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.6rem; align-items: end; height: 190px; }
  .col { display: flex; flex-direction: column; align-items: center; gap: 0.35rem; height: 100%; }
  .col-n { font-size: 0.95rem; font-weight: 700; font-variant-numeric: tabular-nums; }
  .col-track { flex: 1; width: 100%; display: flex; align-items: flex-end; border-radius: 14px; background: var(--surface2); overflow: hidden; }
  .col-fill { width: 100%; min-height: 4px; border-radius: 14px; transform-origin: bottom; animation: grow-y 900ms var(--ease-out) var(--d, 0ms) backwards; transition: filter var(--dur-2); }
  .col:hover .col-fill { filter: saturate(1.4) brightness(0.96); }
  .col-fill.mint { background: var(--tile-mint); } .col-fill.sky { background: var(--tile-sky); }
  .col-fill.butter { background: var(--tile-butter); } .col-fill.peach { background: var(--tile-peach); }
  .col-l { font-size: 0.72rem; color: var(--muted); white-space: nowrap; }
  @keyframes grow-y { from { transform: scaleY(0); } }

  .bar-row { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.6rem; font-size: 0.82rem; padding: 0.2rem 0.3rem; border-radius: 10px; transition: background-color var(--dur-2); }
  .bar-row:hover { background: var(--surface2); }
  .bar-label { flex: 0 0 34%; color: var(--text-secondary); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar { flex: 1; height: 10px; background: var(--surface2); border-radius: 999px; overflow: hidden; }
  .bar-row:hover .bar { background: var(--surface3); }
  .fill { height: 100%; background: var(--success); border-radius: 999px; transform-origin: left; animation: grow-x 1s var(--ease-out) var(--d, 0ms) backwards; }
  .fill.mid { background: var(--warn); }
  .fill.low { background: var(--danger); }
  @keyframes grow-x { from { transform: scaleX(0); } }
  .bar-val { flex: 0 0 96px; text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
  .bar-val em { color: var(--muted); font-style: normal; font-size: 0.72rem; font-weight: 400; }

  /* ---------- coaching ---------- */
  .coach-body { animation: rise 420ms var(--ease-out); }
  .coach-summary { font-size: 0.92rem; line-height: 1.65; margin: 1rem 0 0.25rem; }
  .coach-h3 { font-size: 0.76rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); margin: 1.2rem 0 0.6rem; }
  .learners { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.7rem; }
  .learner { background: var(--surface2); border-radius: 20px; padding: 0.9rem 1rem; display: flex; flex-direction: column; transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3); }
  .learner:hover { translate: 0 -2px; box-shadow: var(--shadow); }
  .learner-top { display: flex; justify-content: space-between; align-items: baseline; gap: 0.75rem; font-size: 0.94rem; }
  .learner-score { font-weight: 700; font-variant-numeric: tabular-nums; padding: 0.1rem 0.55rem; border-radius: 99px; background: var(--surface); }
  .focus { font-size: 0.8rem; color: var(--muted); margin: 0.4rem 0 0.55rem; }
  .learner blockquote {
    display: flex; gap: 0.5rem; align-items: flex-start;
    margin: 0 0 0.7rem; padding: 0.65rem 0.8rem; font-size: 0.83rem; line-height: 1.6;
    background: var(--surface); border-radius: 14px; flex: 1;
  }
  .learner blockquote :global(.icon) { flex: none; margin-top: 3px; color: var(--muted); }
  .small { height: 34px; padding: 0 0.85rem; font-size: 0.8rem; align-self: flex-start; }
  .small :global(.icon) { flex: none; }
  .copied { background: color-mix(in srgb, var(--success) 15%, transparent); color: var(--success); }
  .copied :global(.icon) { animation: pop 360ms var(--ease-out); }

  /* ---------- attempt rows ---------- */
  .rows { display: flex; flex-direction: column; gap: 0.9rem; }
  .row-card { background: var(--surface); border-radius: 24px; box-shadow: var(--shadow-sm); padding: 1.1rem 1.2rem; transition: box-shadow var(--dur-3) var(--ease-out); }
  .row-card:hover { box-shadow: var(--shadow); }
  .row-head { display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap; align-items: center; }
  .who { display: flex; align-items: center; gap: 0.75rem; min-width: 0; }
  .who-text { display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; }
  .who .code { font-size: 0.68rem; font-weight: 700; color: var(--tile-ink); background: var(--tile-sky); border-radius: 999px; padding: 0.1rem 0.5rem; margin-left: 0.4rem; letter-spacing: 0.03em; }
  .who b { font-size: 1rem; font-weight: 600; }
  .muted { color: var(--muted); font-size: 0.8rem; }
  .tiny { font-size: 0.73rem; display: inline-flex; align-items: center; gap: 0.3rem; }

  .score-box { display: flex; align-items: center; gap: 0.85rem; }
  .ring {
    --c: var(--danger);
    width: 68px; height: 68px; border-radius: 50%; flex: none; display: grid; place-items: center;
    background: conic-gradient(var(--c) calc(var(--p) * 1%), var(--surface2) 0);
    animation: pop 520ms var(--ease-out) backwards;
    transition: scale var(--dur-3) var(--ease-out);
  }
  .ring.pass { --c: var(--success); }
  .row-card:hover .ring { scale: 1.06; }
  .score { width: 54px; height: 54px; border-radius: 50%; background: var(--surface); display: grid; place-items: center; font-size: 1.05rem; font-weight: 700; font-variant-numeric: tabular-nums; }
  .score i { font-style: normal; font-size: 0.7em; opacity: 0.6; }
  .score-meta { display: flex; flex-direction: column; align-items: flex-start; gap: 0.3rem; }
  .verdict { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.06em; color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); border-radius: 999px; padding: 0.15rem 0.55rem; }
  .verdict.pass { color: var(--success); background: color-mix(in srgb, var(--success) 13%, transparent); }

  /* --- proctoring verdict ------------------------------------------------ */
  .risk { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.66rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; border-radius: 999px; padding: 0.15rem 0.55rem; }
  .risk-clean { color: var(--success); background: color-mix(in srgb, var(--success) 13%, transparent); }
  .risk-minor { color: var(--warn); background: color-mix(in srgb, var(--warn) 14%, transparent); }
  .risk-suspicious { color: var(--caution); background: color-mix(in srgb, var(--caution) 15%, transparent); }
  .risk-high_risk { color: var(--on-accent); background: var(--danger); }
  .risk-high_risk :global(.icon) { animation: wiggle 900ms var(--ease-out) 600ms 2 backwards; }
  .risk-none { color: var(--muted); background: var(--surface2); }

  .row-actions { display: flex; gap: 0.5rem; margin-top: 0.9rem; flex-wrap: wrap; }
  .chev { display: inline-grid; transition: rotate var(--dur-3) var(--ease-out); }
  .on .chev { rotate: 180deg; }
  .spin { width: 13px; height: 13px; border-radius: 50%; flex: none; border: 2px solid var(--surface3); border-top-color: var(--text); animation: spin 800ms linear infinite; }
  .spin.light { border-color: color-mix(in srgb, var(--on-accent) 35%, transparent); border-top-color: var(--on-accent); }
  @keyframes spin { to { rotate: 360deg; } }

  .integrity { --tone: var(--muted); margin-top: 0.9rem; border-radius: 18px; padding: 0.9rem 1rem; background: color-mix(in srgb, var(--tone) 9%, var(--surface2)); animation: rise 380ms var(--ease-out); }
  .tone-clean { --tone: var(--success); } .tone-minor { --tone: var(--warn); }
  .tone-suspicious { --tone: var(--caution); } .tone-high_risk { --tone: var(--danger); }
  .integrity-head { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.5rem; }
  .integrity-title { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.84rem; font-weight: 700; }
  .integrity-title :global(.icon) { color: var(--tone); }
  .integrity-score { font-size: 0.78rem; font-weight: 700; color: var(--tone); font-variant-numeric: tabular-nums; }
  .risk-meter { height: 6px; border-radius: 99px; background: var(--surface3); overflow: hidden; margin-bottom: 0.6rem; }
  .risk-meter span { display: block; height: 100%; border-radius: inherit; background: var(--tone); transform-origin: left; animation: grow-x 900ms var(--ease-out) 200ms backwards; }
  .integrity-summary { font-size: 0.85rem; line-height: 1.55; margin-bottom: 0.5rem; }
  .integrity-findings { margin: 0 0 0.5rem 1.1rem; font-size: 0.81rem; line-height: 1.6; color: var(--text); }
  .integrity-meta { font-size: 0.74rem; color: var(--muted); margin-bottom: 0.55rem; }
  .tag { font-size: 0.68rem; font-weight: 600; color: var(--muted); background: var(--surface); border-radius: 999px; padding: 0.14rem 0.55rem; }
  .tag.danger { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }

  .timeline { margin: 0.65rem 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 0.25rem; max-height: 320px; overflow-y: auto; }
  .timeline li { display: flex; align-items: baseline; gap: 0.6rem; font-size: 0.77rem; padding: 0.4rem 0.6rem; border-radius: 10px; background: var(--surface); flex-wrap: wrap; animation: rise 300ms var(--ease-out) var(--d, 0ms) backwards; }
  .t-at { font-variant-numeric: tabular-nums; color: var(--muted); font-weight: 700; flex-shrink: 0; }
  .t-kind { font-weight: 600; }
  .t-dur { color: var(--caution); font-weight: 700; }
  .t-detail { color: var(--muted); }

  .ai { margin-top: 1rem; background: var(--tile-lilac); color: var(--tile-ink); border-radius: 20px; padding: 1rem 1.1rem; animation: rise 380ms var(--ease-out); }
  .ai-head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.5rem; flex-wrap: wrap; }
  .ai-title { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.88rem; font-weight: 700; }
  .ai .tag { background: var(--tile-inner); color: var(--tile-ink); }
  .ai-summary { font-size: 0.88rem; line-height: 1.6; margin-bottom: 0.85rem; }
  .weak-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.6rem; }
  .weak { background: var(--surface2); border-radius: 16px; padding: 0.7rem 0.85rem; transition: translate var(--dur-3) var(--ease-out); }
  .ai .weak { background: var(--tile-inner); }
  .weak:hover { translate: 0 -2px; }
  .weak-top { display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.86rem; }
  .acc { color: var(--danger); font-weight: 700; font-variant-numeric: tabular-nums; }
  .why { font-size: 0.8rem; opacity: 0.75; margin-top: 0.25rem; line-height: 1.5; }
  .action { display: flex; gap: 0.3rem; align-items: flex-start; font-size: 0.81rem; margin-top: 0.35rem; font-weight: 600; }
  .action :global(.icon) { flex: none; margin-top: 3px; }
  .strengths { font-size: 0.82rem; margin-top: 0.8rem; opacity: 0.85; }
  .recs { list-style: none; margin: 0.6rem 0 0; padding: 0; display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.84rem; line-height: 1.55; }
  .recs li { display: flex; gap: 0.5rem; align-items: flex-start; }
  .recs :global(.icon) { flex: none; margin-top: 3px; color: var(--success); }
  .ai .recs :global(.icon) { color: currentColor; }

  .expand { animation: rise 380ms var(--ease-out); }
  .topics { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 1rem; }
  .chip { font-size: 0.74rem; font-weight: 600; color: var(--text-secondary); background: var(--surface2); border-radius: 999px; padding: 0.2rem 0.6rem; }
  .chip.low { color: var(--danger); background: color-mix(in srgb, var(--danger) 11%, transparent); }
  .chip.tiny { font-size: 0.68rem; display: inline-block; margin-top: 0.35rem; }

  .answers { margin-top: 0.85rem; display: flex; flex-direction: column; gap: 0.55rem; }
  .ans { border-radius: 16px; padding: 0.8rem 0.95rem; background: color-mix(in srgb, var(--success) 6%, var(--surface2)); }
  .ans.wrong { background: color-mix(in srgb, var(--danger) 7%, var(--surface2)); }
  .ans-q { font-size: 0.88rem; font-weight: 600; display: flex; gap: 0.55rem; align-items: flex-start; }
  .idx { flex: none; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--success); color: var(--on-accent); margin-top: 1px; }
  .ans.wrong .idx { background: var(--danger); }
  .qn { color: var(--muted); }
  .ans-body { margin-top: 0.5rem; padding-left: 1.75rem; }
  .ans-line { display: flex; gap: 0.6rem; font-size: 0.83rem; margin-bottom: 0.2rem; flex-wrap: wrap; }
  .lbl { color: var(--muted); flex: 0 0 110px; }
  .good { color: var(--success); font-weight: 600; }
  .bad { color: var(--danger); font-weight: 600; }
  .expl { font-size: 0.79rem; color: var(--muted); margin-top: 0.4rem; line-height: 1.55; }

  /* ---------- states ---------- */
  .state { display: flex; flex-direction: column; align-items: center; gap: 0.7rem; text-align: center; padding: 3rem 1.5rem; border-radius: 28px; background: var(--surface); }
  .state h2 { font-size: 1.25rem; }
  .state p { color: var(--muted); max-width: 46ch; }
  .state-ico { width: 60px; height: 60px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }
  .state-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }

  @media (max-width: 860px) {
    .two { grid-template-columns: 1fr; }
  }
  @media (max-width: 640px) {
    .kpis { grid-template-columns: 1fr 1fr; }
    .kpis > :last-child { grid-column: 1 / -1; }
    .panel { padding: 1.1rem; border-radius: 24px; }
    .bar-label { flex: 0 0 28%; }
    .bar-val { flex-basis: 78px; }
    .ans-body { padding-left: 0; }
    .lbl { flex-basis: 100%; }
  }
</style>
