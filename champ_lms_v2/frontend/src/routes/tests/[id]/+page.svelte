<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { api, type TestPaper } from '$lib/api/client';
  import { ExamLockdown, type ProctorEvent } from '$lib/utils/exam-lockdown';

  const id = $page.params.id;

  let paper: TestPaper | null = null;
  let loading = true;
  let error = '';
  let submitting = false;

  let answers: Record<string, number | null> = {};
  let textAnswers: Record<string, string> = {};
  let current = 0;
  let secondsLeft: number | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let autoSubmitted = false;

  // --- proctoring ----------------------------------------------------------
  let lockdown: ExamLockdown | null = null;
  let detachLockdown: (() => void) | null = null;
  // The newest warning, shown as a transient banner. Kept to one at a time:
  // a stack of them during a legitimate notification storm just panics people.
  let warning = '';
  let warningTimer: ReturnType<typeof setTimeout> | null = null;
  let flagCount = 0;

  // --- per-question timers -------------------------------------------------
  // Seconds left on the question on screen. Separate from the whole-test clock:
  // a test can have either, both, or neither.
  let qSecondsLeft: number | null = null;
  let qTimer: ReturnType<typeof setInterval> | null = null;
  // Questions whose own time ran out — locked so the answer can't change after,
  // which is the only thing that makes a per-question limit mean anything.
  let expired: Record<string, boolean> = {};

  $: q = paper?.questions[current];

  onMount(async () => {
    try {
      paper = await api.takeTest(id);
      for (const item of paper.questions) {
        answers[item.id] = null;
        textAnswers[item.id] = '';
      }
      answers = answers;
      textAnswers = textAnswers;

      if (paper.proctoring_enabled) startProctoring();

      if (paper.duration_minutes) {
        secondsLeft = paper.duration_minutes * 60;
        timer = setInterval(tick, 1000);
      }
      startQuestionTimer();
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
    if (qTimer) clearInterval(qTimer);
    if (warningTimer) clearTimeout(warningTimer);
    // Always release the lockdown — otherwise copy/paste stays broken for the
    // rest of the app after the learner navigates away.
    if (detachLockdown) detachLockdown();
  });

  function startProctoring() {
    lockdown = new ExamLockdown({
      currentQuestionId: () => paper?.questions[current]?.id,
      onWarn: (message: string, _event: ProctorEvent) => {
        warning = message;
        flagCount = lockdown?.warningCount ?? 0;
        if (warningTimer) clearTimeout(warningTimer);
        warningTimer = setTimeout(() => (warning = ''), 6000);
      },
    });
    detachLockdown = lockdown.attach();
  }

  function tick() {
    if (secondsLeft === null) return;
    secondsLeft -= 1;
    if (secondsLeft <= 0) {
      secondsLeft = 0;
      if (timer) clearInterval(timer);
      // * time's up — submit whatever they have rather than losing the work
      if (!autoSubmitted) { autoSubmitted = true; submit(); }
    }
  }

  /**
   * (Re)start the clock for the question now on screen.
   *
   * A question already expired stays expired: re-visiting it must not hand back
   * more time, or the limit is trivially bypassed by navigating away and back.
   */
  function startQuestionTimer() {
    if (qTimer) { clearInterval(qTimer); qTimer = null; }
    qSecondsLeft = null;
    const item = paper?.questions[current];
    if (!item?.time_limit_seconds) return;
    if (expired[item.id]) { qSecondsLeft = 0; return; }

    qSecondsLeft = item.time_limit_seconds;
    qTimer = setInterval(() => {
      if (qSecondsLeft === null) return;
      qSecondsLeft -= 1;
      if (qSecondsLeft <= 0) {
        qSecondsLeft = 0;
        if (qTimer) { clearInterval(qTimer); qTimer = null; }
        const qid = paper?.questions[current]?.id;
        if (qid) { expired[qid] = true; expired = expired; }
        // Move them along rather than parking on a question they can no longer
        // answer; the last question just locks.
        if (paper && current < paper.questions.length - 1) goTo(current + 1);
      }
    }, 1000);
  }

  function goTo(index: number) {
    current = index;
    startQuestionTimer();
  }

  $: answeredCount = paper
    ? paper.questions.filter((item) =>
        item.question_type === 'written'
          ? (textAnswers[item.id] ?? '').trim().length > 0
          : answers[item.id] !== null,
      ).length
    : 0;
  $: total = paper?.questions.length ?? 0;
  $: allAnswered = total > 0 && answeredCount === total;
  $: clock = secondsLeft === null ? null
    : `${String(Math.floor(secondsLeft / 60)).padStart(2, '0')}:${String(secondsLeft % 60).padStart(2, '0')}`;
  $: qClock = qSecondsLeft === null ? null
    : `${String(Math.floor(qSecondsLeft / 60)).padStart(2, '0')}:${String(qSecondsLeft % 60).padStart(2, '0')}`;
  $: locked = q ? !!expired[q.id] : false;

  function choose(qid: string, oi: number) {
    if (expired[qid]) return;
    answers[qid] = oi;
    answers = answers;
  }

  function onWritten(qid: string, value: string) {
    if (expired[qid]) return;
    textAnswers[qid] = value;
    textAnswers = textAnswers;
    // Feed the burst detector: a paragraph that appears between two keystrokes
    // was not typed, however it got there.
    lockdown?.noteAnswerText(qid, value);
  }

  function wordCount(text: string): number {
    const trimmed = text.trim();
    return trimmed ? trimmed.split(/\s+/).length : 0;
  }

  async function submit() {
    if (!paper || submitting) return;
    submitting = true; error = '';
    if (timer) clearInterval(timer);
    if (qTimer) clearInterval(qTimer);
    try {
      const res = await api.submitTest(id, {
        answers,
        text_answers: textAnswers,
        // Sent only for a proctored attempt. Omitting the key entirely (rather
        // than sending []) is what tells the server this attempt was not
        // monitored, so the distinction has to survive here.
        ...(paper.proctoring_enabled && lockdown
          ? {
              proctor_events: lockdown.getEvents(),
              elapsed_seconds: lockdown.getElapsedSeconds(),
            }
          : {}),
      });
      // Release the lockdown before leaving, so the result page behaves normally.
      if (detachLockdown) { detachLockdown(); detachLockdown = null; }
      goto(`/tests/result/${res.attempt_id}`);
    } catch (e: any) {
      error = e.message;
      submitting = false;
    }
  }
</script>

<div class="page">
  {#if loading}
    <div class="skeleton big"></div>
  {:else if error && !paper}
    <div class="blocked">
      <h1>Can't start this test</h1>
      <p>{error}</p>
      <a href="/tests" class="btn">Back to tests</a>
    </div>
  {:else if paper}
    {#if paper.proctoring_enabled}
      <div class="proctor-bar" role="status">
        <span class="dot-live" aria-hidden="true"></span>
        <div class="proctor-copy">
          <strong>Proctored test</strong>
          <span>
            Copying and pasting are disabled. Switching tabs or windows is
            recorded and reviewed.
          </span>
        </div>
        {#if flagCount > 0}
          <span class="flag-count" title="Integrity events recorded on this attempt">
            {flagCount} logged
          </span>
        {/if}
      </div>
    {/if}

    {#if warning}
      <div class="warn-banner" role="alert">⚠ {warning}</div>
    {/if}

    <div class="bar">
      <div>
        <h1>{paper.title}</h1>
        <p class="sub">
          <!-- attempts_allowed already includes any extra attempts an admin
               granted this person, so a granted retake never reads "3 of 2" -->
          Attempt {paper.attempt_number}{paper.attempts_allowed ? ` of ${paper.attempts_allowed}` : ''}
          {#if paper.extra_attempts_granted > 0}
            <span class="granted-note">
              (+{paper.extra_attempts_granted} granted by an admin)
            </span>
          {/if}
          · pass mark {paper.pass_threshold}% · {paper.total_marks} marks
        </p>
      </div>
      {#if clock}
        <div class="clock" class:urgent={secondsLeft !== null && secondsLeft < 60}>⏱ {clock}</div>
      {/if}
    </div>

    <div class="progress">
      <div class="progress-fill" style="width:{total ? (answeredCount / total) * 100 : 0}%"></div>
    </div>
    <p class="count">{answeredCount} of {total} answered</p>

    {#if error}<p class="error">{error}</p>{/if}

    <div class="dots">
      {#each paper.questions as item, i}
        <button class="dot"
                class:done={item.question_type === 'written'
                  ? (textAnswers[item.id] ?? '').trim().length > 0
                  : answers[item.id] !== null}
                class:now={i === current}
                class:expired={expired[item.id]}
                on:click={() => goTo(i)} title={`Question ${i + 1}`}>{i + 1}</button>
      {/each}
    </div>

    {#if q}
      <div class="q-card">
        <div class="q-meta">
          <span>Question {current + 1} of {total}</span>
          <span class="q-meta-right">
            {#if qClock}
              <span class="q-clock" class:urgent={qSecondsLeft !== null && qSecondsLeft <= 15}>
                ⏱ {qClock}
              </span>
            {/if}
            <span>
              {q.marks} mark{q.marks === 1 ? '' : 's'}{q.topic ? ` · ${q.topic}` : ''}
            </span>
          </span>
        </div>
        <h2 class="q-text">{q.question}</h2>

        {#if locked}
          <p class="locked-note">Time for this question has run out — your answer is locked.</p>
        {/if}

        {#if q.question_type === 'written'}
          <textarea
            class="answer"
            rows="8"
            disabled={locked}
            placeholder="Type your answer here…"
            value={textAnswers[q.id] ?? ''}
            on:input={(e) => onWritten(q.id, e.currentTarget.value)}
          ></textarea>
          <p class="words">
            {wordCount(textAnswers[q.id] ?? '')} words{q.max_words ? ` · suggested limit ${q.max_words}` : ''}
          </p>
        {:else}
          <div class="opts">
            {#each q.options as opt, oi}
              <button class="opt" class:sel={answers[q.id] === oi} disabled={locked}
                      on:click={() => choose(q.id, oi)}>
                <span class="key">{String.fromCharCode(65 + oi)}</span>
                <span class="opt-text">{opt}</span>
              </button>
            {/each}
          </div>
        {/if}

        <div class="nav">
          <button class="btn" disabled={current === 0} on:click={() => goTo(current - 1)}>← Previous</button>
          {#if current < total - 1}
            <button class="btn" on:click={() => goTo(current + 1)}>Next →</button>
          {/if}
        </div>
      </div>
    {/if}

    <div class="submit-bar">
      {#if !allAnswered}
        <p class="hint">{total - answeredCount} question(s) unanswered — they'll be marked as skipped.</p>
      {/if}
      <button class="btn primary" disabled={submitting} on:click={submit}>
        {submitting ? 'Submitting…' : 'Submit test'}
      </button>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 720px; margin: 0 auto; padding-bottom: 4rem; }
  .bar { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; }
  h1 { font-size: 1.4rem; font-weight: 800; margin-bottom: 0.25rem; }
  .sub { color: var(--muted); font-size: 0.82rem; }
  .clock { font-size: 1.05rem; font-weight: 800; font-variant-numeric: tabular-nums;
           background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
           padding: 0.4rem 0.8rem; }
  .clock.urgent { color: #e05260; border-color: #e05260; }

  /* --- proctoring notice + warnings ------------------------------------- */
  .proctor-bar { display: flex; align-items: center; gap: 0.7rem; margin-bottom: 1rem;
                 background: var(--surface); border: 1px solid var(--border);
                 border-left: 3px solid #e0a852; border-radius: 8px; padding: 0.7rem 0.9rem; }
  .proctor-copy { display: flex; flex-direction: column; gap: 0.15rem; flex: 1; }
  .proctor-copy strong { font-size: 0.83rem; }
  .proctor-copy span { font-size: 0.76rem; color: var(--muted); line-height: 1.45; }
  .dot-live { width: 8px; height: 8px; border-radius: 50%; background: #e0a852; flex-shrink: 0;
              animation: pulse 2s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
  .flag-count { flex-shrink: 0; font-size: 0.72rem; font-weight: 700; color: #e0a852;
                border: 1px solid #e0a852; border-radius: 999px; padding: 0.15rem 0.5rem; }
  .warn-banner { background: color-mix(in srgb, #e05260 15%, var(--surface));
                 border: 1px solid #e05260; color: var(--text); border-radius: 8px;
                 padding: 0.65rem 0.85rem; font-size: 0.8rem; margin-bottom: 1rem; line-height: 1.45; }

  .progress { height: 5px; background: var(--surface2); border-radius: 999px; overflow: hidden; margin: 1.15rem 0 0.4rem; }
  .progress-fill { height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.25s; }
  .count { font-size: 0.75rem; color: var(--muted); margin-bottom: 1rem; }
  .error { color: var(--accent); font-size: 0.85rem; margin-bottom: 0.75rem; }

  .dots { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-bottom: 1.15rem; }
  .dot { width: 30px; height: 30px; border-radius: 6px; font-size: 0.76rem; font-weight: 700;
         background: var(--surface2); border: 1px solid var(--border); color: var(--muted); cursor: pointer; }
  .dot.done { color: var(--text); border-color: var(--success); }
  .dot.now { background: var(--accent); border-color: var(--accent); color: #fff; }
  .dot.expired { opacity: 0.45; text-decoration: line-through; }

  .q-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; }
  .q-meta { display: flex; justify-content: space-between; font-size: 0.73rem; color: var(--muted); margin-bottom: 0.75rem; gap: 0.75rem; flex-wrap: wrap; }
  .q-meta-right { display: flex; align-items: center; gap: 0.6rem; }
  .q-clock { font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text); }
  .q-clock.urgent { color: #e05260; }
  .q-text { font-size: 1.06rem; font-weight: 600; line-height: 1.55; margin-bottom: 1.25rem; }
  .locked-note { font-size: 0.78rem; color: #e05260; margin-bottom: 0.9rem; }

  /* Written answers stay selectable and editable even under lockdown — you
     must be able to fix your own prose. */
  .answer { width: 100%; background: var(--surface2); border: 1px solid var(--border);
            color: var(--text); border-radius: 8px; padding: 0.8rem 0.9rem;
            font-family: inherit; font-size: 0.9rem; line-height: 1.6; resize: vertical;
            -webkit-user-select: text; user-select: text; }
  .answer:focus { outline: none; border-color: var(--accent); }
  .answer:disabled { opacity: 0.55; cursor: not-allowed; }
  .words { font-size: 0.73rem; color: var(--muted); margin-top: 0.4rem; }

  .opts { display: flex; flex-direction: column; gap: 0.55rem; }
  .opt { display: flex; align-items: flex-start; gap: 0.7rem; text-align: left; width: 100%;
         background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 8px; padding: 0.8rem 0.9rem; font-size: 0.9rem; cursor: pointer;
         font-family: inherit; line-height: 1.5; }
  .opt:hover:not(:disabled) { border-color: var(--accent); }
  .opt:disabled { opacity: 0.55; cursor: not-allowed; }
  .opt.sel { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, var(--surface2)); }
  .key { flex-shrink: 0; width: 24px; height: 24px; border-radius: 50%; background: var(--surface);
         border: 1px solid var(--border); display: grid; place-items: center;
         font-size: 0.73rem; font-weight: 700; color: var(--muted); }
  .opt.sel .key { background: var(--accent); border-color: var(--accent); color: #fff; }
  .opt-text { flex: 1; }

  .nav { display: flex; justify-content: space-between; gap: 0.6rem; margin-top: 1.5rem; }
  .btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 6px; padding: 0.55rem 1.05rem; font-size: 0.86rem; font-weight: 600;
         cursor: pointer; text-decoration: none; display: inline-block; }
  .btn:hover:not(:disabled) { border-color: var(--accent); }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }

  .submit-bar { margin-top: 1.5rem; display: flex; flex-direction: column; gap: 0.6rem; align-items: flex-start; }
  .hint { font-size: 0.78rem; color: #ffc107; }

  .blocked { text-align: center; padding: 3rem 1rem; background: var(--surface);
             border: 1px solid var(--border); border-radius: 10px; }
  .blocked h1 { font-size: 1.2rem; margin-bottom: 0.5rem; }
  .blocked p { color: var(--muted); font-size: 0.87rem; margin-bottom: 1.25rem; }

  .skeleton { border-radius: 10px; background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
              background-size: 200% 100%; animation: shimmer 1.4s infinite; }
  .skeleton.big { height: 400px; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
  .granted-note { color: var(--success); font-weight: 600; }
</style>
