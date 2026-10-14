<script lang="ts">
  // svelte's tick renamed: this page has its own countdown `tick()`.
  import { onMount, onDestroy, tick as nextRender } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { api, type TestPaper } from '$lib/api/client';
  import { ExamLockdown, type ProctorEvent } from '$lib/utils/exam-lockdown';
  import Icon from '$lib/components/Icon.svelte';

  const id = $page.params.id;
  // Set when the test was opened from a course, so the result can lead back there.
  const courseParam = $page.url.searchParams.get('course');

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

  // The card (and its Previous/Next) is rebuilt per question by {#key}, so
  // a keyboard user's focus would drop to <body>; put it back on the same
  // button, or on Previous once Next is gone on the last question.
  let prevBtn: HTMLButtonElement | null = null;
  let nextBtn: HTMLButtonElement | null = null;
  async function step(by: 1 | -1) {
    goTo(current + by);
    await nextRender();
    (by === 1 ? nextBtn ?? prevBtn : prevBtn?.disabled ? nextBtn : prevBtn)?.focus();
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
  // floor, not round: 199 of 200 must not read "100%".
  $: answeredPct = total ? Math.floor((answeredCount / total) * 100) : 0;
  // First question still open (and not timed out), for the submit bar's jump link.
  $: firstUnanswered = paper
    ? paper.questions.findIndex((item) =>
        !expired[item.id] &&
        (item.question_type === 'written'
          ? !(textAnswers[item.id] ?? '').trim()
          : answers[item.id] === null),
      )
    : -1;
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
      goto(`/tests/result/${res.attempt_id}${courseParam ? `?course=${courseParam}` : ''}`);
    } catch (e: any) {
      error = e.message;
      submitting = false;
    }
  }
</script>

<svelte:head><title>{paper ? `${paper.title} — Test` : 'Test'} — Champ LMS</title></svelte:head>

<div class="page">
  {#if loading}
    <div class="ui-skeleton" style="height:96px;border-radius:28px;margin-bottom:1rem"></div>
    <div class="ui-skeleton" style="height:380px;border-radius:30px"></div>
  {:else if error && !paper}
    <div class="blocked ui-rise">
      <span class="blocked-ico"><Icon name="lock" size={26} /></span>
      <h1>Can't start this test</h1>
      <p>{error}</p>
      <a href={courseParam ? `/course/${courseParam}` : '/tests'} class="btn-primary">
        <Icon name="arrowLeft" size={16} /> {courseParam ? 'Back to course' : 'Back to tests'}
      </a>
    </div>
  {:else if paper}
    {#if paper.proctoring_enabled}
      <div class="proctor-bar" role="status">
        <span class="p-ico" aria-hidden="true"><Icon name="shield" size={18} /><span class="dot-live"></span></span>
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
      <div class="warn-banner" role="alert"><Icon name="alert" size={17} /> <span>{warning}</span></div>
    {/if}

    <header class="bar">
      <div class="bar-copy">
        <h1>{paper.title}</h1>
        <p class="sub">
          <span class="chip">Attempt {paper.attempt_number}{paper.max_attempts ? ` of ${paper.max_attempts}` : ''}</span>
          <span class="chip"><Icon name="target" size={13} /> pass mark {paper.pass_threshold}%</span>
          <span class="chip"><Icon name="star" size={13} /> {paper.total_marks} marks</span>
        </p>
      </div>
      {#if clock}
        <div class="clock" class:urgent={secondsLeft !== null && secondsLeft < 60}>
          <Icon name="clock" size={18} /> {clock}
        </div>
      {/if}
    </header>

    <!-- Navigator: answered count + bar, then one tile per question. -->
    <section class="navi" aria-label="Question navigator">
      <div class="navi-head">
        <span class="navi-pct">{answeredPct}<small>%</small></span>
        <span class="navi-count"><b>{answeredCount}</b> of {total} answered</span>
        <span class="legend" aria-hidden="true">
          <span><i class="lg done"></i> Answered</span>
          <span><i class="lg now"></i> Current</span>
          <span><i class="lg todo"></i> Not answered</span>
        </span>
      </div>
      <div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax={total} aria-valuenow={answeredCount}
           aria-label="Questions answered">
        <div class="progress-fill" style="width:{answeredPct}%"></div>
      </div>

      <div class="dots">
        {#each paper.questions as item, i}
          {@const done = item.question_type === 'written'
            ? (textAnswers[item.id] ?? '').trim().length > 0
            : answers[item.id] !== null}
          <button class="dot"
                  class:done
                  class:now={i === current}
                  class:expired={expired[item.id]}
                  aria-current={i === current ? 'step' : undefined}
                  aria-label="Question {i + 1}{done ? ', answered' : ', not answered'}{expired[item.id] ? ', time up' : ''}"
                  on:click={() => goTo(i)}>
            {i + 1}
            {#if expired[item.id]}<span class="d-flag lock"><Icon name="lock" size={9} stroke={2.4} /></span>
            {:else if done}<span class="d-flag"><Icon name="check" size={9} stroke={3} /></span>{/if}
          </button>
        {/each}
      </div>
    </section>

    {#if error}<p class="error"><Icon name="alert" size={15} /> {error}</p>{/if}

    {#if q}
      <!-- A short, quiet fade between questions; nothing moves while answering. -->
      {#key current}
        <div class="q-card" class:written={q.question_type === 'written'}>
          <span class="q-track" aria-hidden="true"><span style="width:{((current + 1) / total) * 100}%"></span></span>
          <div class="q-meta">
            <span class="q-badge" aria-hidden="true">{current + 1}</span>
            <span class="q-num">
              <b>Question {current + 1}</b>
              <em>of {total}{q.question_type === 'written' ? ' · written answer' : ''}</em>
            </span>
            <span class="q-meta-right">
              {#if q.topic}<span class="chip topic"><Icon name="hash" size={12} /> {q.topic}</span>{/if}
              <span class="chip marks"><Icon name="star" size={12} /> {q.marks} mark{q.marks === 1 ? '' : 's'}</span>
              {#if qClock}
                <span class="q-clock" class:urgent={qSecondsLeft !== null && qSecondsLeft <= 15}>
                  <Icon name="clock" size={14} /> {qClock}
                </span>
              {/if}
            </span>
          </div>
          <h2 class="q-text">{q.question}</h2>

          {#if locked}
            <p class="locked-note"><Icon name="lock" size={15} /> Time for this question has run out — your answer is locked.</p>
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
            <p class="opts-hint">Choose one answer</p>
            <div class="opts" role="radiogroup" aria-label="Answers">
              {#each q.options as opt, oi}
                <button class="opt" class:sel={answers[q.id] === oi} disabled={locked}
                        role="radio" aria-checked={answers[q.id] === oi}
                        on:click={() => choose(q.id, oi)}>
                  <span class="key">{String.fromCharCode(65 + oi)}</span>
                  <span class="opt-text">{opt}</span>
                  <span class="tick" aria-hidden="true"><Icon name="check" size={14} stroke={2.6} /></span>
                </button>
              {/each}
            </div>
          {/if}

          <div class="nav">
            <button class="btn-ghost prev" bind:this={prevBtn} disabled={current === 0} on:click={() => step(-1)}>
              <Icon name="chevronLeft" size={16} /> Previous
            </button>
            <span class="nav-pos"><b>{current + 1}</b> / {total}</span>
            {#if current < total - 1}
              <button class="btn-primary next" bind:this={nextBtn} on:click={() => step(1)}>
                Next <Icon name="chevronRight" size={16} />
              </button>
            {:else}
              <span class="nav-end"><Icon name="flag" size={14} /> Last question</span>
            {/if}
          </div>
        </div>
      {/key}
    {/if}

    <div class="submit-bar" class:ready={allAnswered}>
      <span class="sb-ico" aria-hidden="true"><Icon name={allAnswered ? 'checkCircle' : 'alert'} size={20} /></span>
      <div class="sb-copy">
        {#if allAnswered}
          <b>All {total} questions answered</b>
          <span>Check anything you're unsure of, then submit when you're ready.</span>
        {:else}
          <b>{total - answeredCount} question{total - answeredCount === 1 ? '' : 's'} not answered yet</b>
          <span>
            Unanswered questions are marked as skipped.
            {#if firstUnanswered >= 0 && firstUnanswered !== current}
              <button class="sb-jump" on:click={() => goTo(firstUnanswered)}>Go to question {firstUnanswered + 1}</button>
            {/if}
          </span>
        {/if}
      </div>
      <button class="btn-primary sb-go" disabled={submitting} on:click={submit}>
        {#if submitting}<span class="spin" aria-hidden="true"></span> Submitting…{:else}<Icon name="send" size={16} /> Submit test{/if}
      </button>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 780px; margin: 0 auto; padding-bottom: 1.5rem; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.3rem;
    font-size: 0.76rem; font-weight: 500; color: var(--text-secondary); background: var(--surface2);
    border-radius: 999px; padding: 0.22rem 0.65rem;
  }

  /* --- header --- */
  .bar { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.1rem; }
  .bar-copy { min-width: 0; flex: 1; }
  h1 { font-size: clamp(1.5rem, 1.1rem + 1.2vw, 2.1rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.1; margin-bottom: 0.6rem; }
  .sub { display: flex; flex-wrap: wrap; gap: 0.35rem; }
  .clock {
    display: inline-flex; align-items: center; gap: 0.45rem;
    font-size: 1.15rem; font-weight: 700; font-variant-numeric: tabular-nums;
    background: var(--surface); box-shadow: var(--shadow-sm); border-radius: 999px; padding: 0.55rem 1.1rem;
    transition: background-color var(--dur-3), color var(--dur-3);
  }
  .clock.urgent { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, var(--surface)); }
  .clock.urgent :global(.icon) { animation: pulse-ring 1.4s var(--ease-out) infinite; border-radius: 50%; }

  /* --- proctoring notice + warnings --- */
  .proctor-bar { display: flex; align-items: center; gap: 0.8rem; margin-bottom: 1rem;
                 background: var(--tile-butter); color: var(--tile-ink); border-radius: 22px; padding: 0.75rem 1rem; }
  .p-ico { position: relative; flex: none; width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); }
  .proctor-copy { display: flex; flex-direction: column; gap: 0.15rem; flex: 1; }
  .proctor-copy strong { font-size: 0.88rem; }
  .proctor-copy span { font-size: 0.78rem; opacity: 0.75; line-height: 1.45; }
  .dot-live { position: absolute; top: 2px; right: 2px; width: 9px; height: 9px; border-radius: 50%; background: var(--warn);
              box-shadow: 0 0 0 2px var(--tile-butter); animation: pulse 2s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
  .flag-count { flex-shrink: 0; font-size: 0.74rem; font-weight: 700; color: var(--tile-ink);
                background: var(--tile-inner); border-radius: 999px; padding: 0.2rem 0.6rem; }
  .warn-banner { display: flex; align-items: flex-start; gap: 0.55rem;
                 background: color-mix(in srgb, var(--danger) 13%, var(--surface)); color: var(--text);
                 box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--danger) 55%, transparent);
                 border-radius: 18px; padding: 0.7rem 0.95rem; font-size: 0.84rem; margin-bottom: 1rem; line-height: 1.45;
                 animation: rise 280ms var(--ease-out); }
  .warn-banner :global(.icon) { color: var(--danger); flex: none; margin-top: 1px; }

  /* --- progress --- */
  /* --- navigator: progress + question tiles in one panel --- */
  .navi {
    background: var(--surface); border-radius: 22px; padding: 1rem 1.1rem 1.05rem; margin-bottom: 1rem;
    box-shadow: var(--shadow-sm), 0 0 0 1px var(--border);
  }
  .navi-head { display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap; margin-bottom: 0.6rem; }
  .navi-pct { font-size: 1.5rem; font-weight: 800; letter-spacing: -0.03em; line-height: 1; font-variant-numeric: tabular-nums; }
  .navi-pct small { font-size: 0.6em; font-weight: 700; color: var(--muted); margin-left: 1px; }
  .navi-count { font-size: 0.8rem; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
  .navi-count b { color: var(--text); }
  .legend { margin-left: auto; display: flex; gap: 0.75rem; flex-wrap: wrap; font-size: 0.7rem; font-weight: 600; color: var(--muted); }
  .legend > span { display: inline-flex; align-items: center; gap: 0.3rem; }
  .lg { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
  .lg.done { background: var(--success); }
  .lg.now { background: var(--accent); }
  .lg.todo { background: var(--surface); box-shadow: inset 0 0 0 1.5px var(--border-hover); }

  .progress { height: 10px; background: var(--surface2); border-radius: 999px; overflow: hidden; box-shadow: inset 0 0 0 1px var(--border); }
  .progress-fill {
    height: 100%; border-radius: 999px; transition: width var(--dur-3) var(--ease-out);
    background: linear-gradient(90deg, color-mix(in srgb, var(--success) 75%, var(--accent)), var(--success));
  }
  .error { display: flex; align-items: center; gap: 0.4rem; color: var(--danger); font-size: 0.86rem; margin-bottom: 0.75rem; }

  /* Tiles: outlined = not answered, green = answered (with a tick),
     ink + ring = where you are, faded + lock = time ran out. */
  .dots { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.9rem; }
  .dot {
    position: relative; width: 38px; height: 38px; border-radius: 12px; font-size: 0.82rem; font-weight: 700;
    background: var(--surface); color: var(--text-secondary); cursor: pointer; font-variant-numeric: tabular-nums;
    box-shadow: inset 0 0 0 1.5px var(--border-hover);
    transition: background-color var(--dur-2), color var(--dur-2), box-shadow var(--dur-2), translate var(--dur-2) var(--ease-out);
  }
  .dot:hover { translate: 0 -2px; color: var(--text); box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--text) 40%, transparent); }
  .dot:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .dot.done {
    background: color-mix(in srgb, var(--success) 14%, var(--surface)); color: var(--success);
    box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--success) 45%, transparent);
  }
  .dot.now {
    background: var(--accent); color: var(--on-accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
    translate: 0 -2px;
  }
  .dot.expired { opacity: 0.5; background: var(--surface2); color: var(--muted); box-shadow: inset 0 0 0 1.5px var(--border); }
  .d-flag {
    position: absolute; top: -5px; right: -5px; width: 16px; height: 16px; border-radius: 50%;
    display: grid; place-items: center; background: var(--success); color: var(--on-accent);
    box-shadow: 0 0 0 2px var(--surface); animation: pop 260ms var(--ease-out);
  }
  .d-flag.lock { background: var(--muted); }

  /* --- question card --- */
  /* Card: a thin position track on the top edge, a header row (number badge,
     "Question n of m", topic / marks / timer), the question, then answers. */
  .q-card {
    position: relative; overflow: hidden;
    background: var(--surface); border-radius: 26px; padding: 1.6rem 1.7rem 1.4rem;
    box-shadow: var(--shadow-sm), 0 0 0 1px var(--border);
    animation: fade 220ms var(--ease-out);
  }
  .q-track { position: absolute; left: 0; right: 0; top: 0; height: 4px; background: var(--surface2); }
  .q-track span { display: block; height: 100%; background: var(--accent); border-radius: 0 99px 99px 0; transition: width var(--dur-3) var(--ease-out); }
  .q-meta { display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap; margin-bottom: 1.1rem; }
  .q-badge {
    flex: none; width: 40px; height: 40px; border-radius: 13px; display: grid; place-items: center;
    background: var(--accent); color: var(--on-accent); font-size: 1rem; font-weight: 800; font-variant-numeric: tabular-nums;
    animation: pop 360ms var(--ease-out);
  }
  .q-num { display: flex; flex-direction: column; line-height: 1.25; }
  .q-num b { font-size: 0.92rem; font-weight: 700; color: var(--text); }
  .q-num em { font-style: normal; font-size: 0.74rem; color: var(--muted); font-weight: 500; }
  .q-meta-right { display: flex; align-items: center; gap: 0.4rem; margin-left: auto; flex-wrap: wrap; }
  .chip.topic { text-transform: capitalize; }
  .chip.marks { background: var(--tile-butter); color: var(--tile-ink); font-weight: 700; }
  .q-clock { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.78rem; font-weight: 700; font-variant-numeric: tabular-nums;
             padding: 0.22rem 0.65rem; border-radius: 99px; background: var(--tile-sky); color: var(--tile-ink); }
  .q-clock.urgent { color: var(--danger); background: color-mix(in srgb, var(--danger) 14%, transparent); animation: pulse-urgent 1s var(--ease-in-out) infinite; }
  @keyframes pulse-urgent { 50% { opacity: 0.6; } }
  .q-text {
    font-size: clamp(1.08rem, 1rem + 0.35vw, 1.25rem); font-weight: 650; line-height: 1.5; letter-spacing: -0.015em;
    color: var(--text); margin-bottom: 1.2rem; padding-top: 1.05rem; border-top: 1px solid var(--border);
  }
  .locked-note { display: flex; align-items: center; gap: 0.4rem; font-size: 0.82rem; color: var(--danger); margin-bottom: 0.9rem; }
  .opts-hint { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.55rem; }

  /* Written answers stay selectable and editable even under lockdown — you
     must be able to fix your own prose. */
  .answer { width: 100%; background: var(--surface2); border: 1.5px solid transparent;
            color: var(--text); border-radius: 18px; padding: 0.9rem 1rem;
            font-family: inherit; font-size: 0.95rem; line-height: 1.6; resize: vertical;
            -webkit-user-select: text; user-select: text;
            transition: border-color var(--dur-2), background-color var(--dur-2); }
  .answer:focus { outline: none; border-color: var(--accent); background: var(--surface); }
  .answer:disabled { opacity: 0.55; cursor: not-allowed; }
  .words { font-size: 0.76rem; color: var(--muted); margin-top: 0.45rem; }

  /* Options: outlined rows on the card. Hover darkens the outline; the chosen
     one gets an ink outline, a light tint, a filled letter key and a tick. */
  .opts { display: flex; flex-direction: column; gap: 0.5rem; }
  .opt { display: flex; align-items: center; gap: 0.85rem; text-align: left; width: 100%;
         background: var(--surface); color: var(--text);
         border-radius: 16px; padding: 0.8rem 0.9rem 0.8rem 0.8rem; font-size: 0.95rem; font-weight: 500; cursor: pointer;
         font-family: inherit; line-height: 1.5; box-shadow: inset 0 0 0 1.5px var(--border-hover);
         transition: background-color var(--dur-2), box-shadow var(--dur-2), translate var(--dur-2) var(--ease-out); }
  .opt:hover:not(:disabled) { background: var(--surface2); box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--text) 38%, transparent); }
  .opt:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .opt:disabled { opacity: 0.55; cursor: not-allowed; }
  .opt.sel { box-shadow: inset 0 0 0 2px var(--accent); background: color-mix(in srgb, var(--accent) 6%, var(--surface)); }
  .key { flex-shrink: 0; width: 32px; height: 32px; border-radius: 10px; background: var(--surface2);
         box-shadow: inset 0 0 0 1px var(--border);
         display: grid; place-items: center; font-size: 0.8rem; font-weight: 800; color: var(--text-secondary);
         transition: background-color var(--dur-2), color var(--dur-2); }
  .opt:hover:not(:disabled) .key { background: var(--surface3); color: var(--text); }
  .opt.sel .key { background: var(--accent); color: var(--on-accent); box-shadow: none; animation: pop 260ms var(--ease-out); }
  .opt-text { flex: 1; }
  .opt.sel .opt-text { font-weight: 600; }
  .tick { flex: none; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
          background: var(--accent); color: var(--on-accent); opacity: 0; scale: 0.5;
          transition: opacity var(--dur-2), scale var(--dur-2) var(--ease-out); }
  .opt.sel .tick { opacity: 1; scale: 1; }

  .nav {
    display: flex; align-items: center; justify-content: space-between; gap: 0.6rem;
    margin-top: 1.4rem; padding-top: 1.1rem; border-top: 1px solid var(--border);
  }
  .nav-pos { font-size: 0.8rem; color: var(--muted); font-variant-numeric: tabular-nums; }
  .nav-pos b { color: var(--text); }
  .nav-end { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.8rem; font-weight: 600; color: var(--muted); }
  .nav button:disabled { opacity: 0.4; cursor: not-allowed; }
  .nav :global(.icon) { transition: translate var(--dur-2) var(--ease-out); }
  .nav button:hover:not(:disabled) :global(.icon) { translate: -2px 0; }
  .nav .next:hover :global(.icon) { translate: 2px 0; }

  /* Submit bar: status icon + what happens next, and the submit button.
     Amber while questions are open, green once everything is answered. */
  .submit-bar {
    --sb: var(--warn);
    margin-top: 1.25rem; display: flex; align-items: center; gap: 0.9rem; flex-wrap: wrap;
    padding: 0.85rem 0.9rem 0.85rem 0.95rem; border-radius: 22px;
    background: color-mix(in srgb, var(--sb) 8%, var(--surface));
    box-shadow: var(--shadow-sm), 0 0 0 1px color-mix(in srgb, var(--sb) 30%, var(--border));
    transition: background-color var(--dur-3), box-shadow var(--dur-3);
  }
  .submit-bar.ready { --sb: var(--success); }
  .sb-ico {
    flex: none; width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center;
    background: color-mix(in srgb, var(--sb) 16%, transparent); color: var(--sb);
  }
  .submit-bar.ready .sb-ico { animation: pop 420ms var(--ease-out); }
  .sb-copy { flex: 1; min-width: 200px; display: flex; flex-direction: column; gap: 0.12rem; }
  .sb-copy b { font-size: 0.92rem; font-weight: 700; color: var(--text); }
  .sb-copy > span { font-size: 0.8rem; color: var(--text-secondary); line-height: 1.45; }
  .sb-jump {
    display: inline; padding: 0; margin-left: 0.2rem; background: none; font-size: inherit; font-weight: 700; color: var(--text);
    text-decoration: underline; text-underline-offset: 3px; text-decoration-color: color-mix(in srgb, var(--text) 35%, transparent);
  }
  .sb-jump:hover { text-decoration-color: currentColor; }
  .sb-go { flex: none; height: 46px; padding: 0 1.3rem; }
  .sb-go:disabled { opacity: 0.6; cursor: progress; }
  .spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid currentColor; border-right-color: transparent; animation: spin 700ms linear infinite; }
  @keyframes spin { to { rotate: 360deg; } }

  .blocked { display: flex; flex-direction: column; align-items: center; gap: 0.6rem; text-align: center; padding: 3.5rem 1rem; background: var(--surface); border-radius: 32px; }
  .blocked-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-peach); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }
  .blocked h1 { font-size: 1.35rem; margin-bottom: 0; }
  .blocked p { color: var(--muted); font-size: 0.9rem; margin-bottom: 0.8rem; }

  @media (max-width: 760px) {
    .q-card { padding: 1.3rem 1.1rem 1.1rem; border-radius: 22px; }
    .q-meta-right { margin-left: 0; width: 100%; }
    .nav-pos { display: none; }
    .navi { padding: 0.9rem; }
    .legend { margin-left: 0; width: 100%; }
    .dot { width: 34px; height: 34px; border-radius: 10px; }
    .sb-go { width: 100%; justify-content: center; }
  }
</style>
