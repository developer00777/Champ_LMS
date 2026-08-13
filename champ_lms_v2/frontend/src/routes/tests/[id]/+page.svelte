<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { api, type TestPaper } from '$lib/api/client';

  const id = $page.params.id;

  let paper: TestPaper | null = null;
  let loading = true;
  let error = '';
  let submitting = false;

  let answers: Record<string, number | null> = {};
  let current = 0;
  let secondsLeft: number | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let autoSubmitted = false;

  onMount(async () => {
    try {
      paper = await api.takeTest(id);
      for (const q of paper.questions) answers[q.id] = null;
      answers = answers;
      if (paper.duration_minutes) {
        secondsLeft = paper.duration_minutes * 60;
        timer = setInterval(tick, 1000);
      }
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  });

  onDestroy(() => { if (timer) clearInterval(timer); });

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

  $: answeredCount = Object.values(answers).filter((v) => v !== null).length;
  $: total = paper?.questions.length ?? 0;
  $: allAnswered = total > 0 && answeredCount === total;
  $: clock = secondsLeft === null ? null
    : `${String(Math.floor(secondsLeft / 60)).padStart(2, '0')}:${String(secondsLeft % 60).padStart(2, '0')}`;

  function choose(qid: string, oi: number) {
    answers[qid] = oi;
    answers = answers;
  }

  async function submit() {
    if (!paper || submitting) return;
    submitting = true; error = '';
    if (timer) clearInterval(timer);
    try {
      const res = await api.submitTest(id, answers);
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
    <div class="bar">
      <div>
        <h1>{paper.title}</h1>
        <p class="sub">
          Attempt {paper.attempt_number}{paper.max_attempts ? ` of ${paper.max_attempts}` : ''}
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
      {#each paper.questions as q, i}
        <button class="dot" class:done={answers[q.id] !== null} class:now={i === current}
                on:click={() => (current = i)} title={`Question ${i + 1}`}>{i + 1}</button>
      {/each}
    </div>

    {#each paper.questions as q, i}
      {#if i === current}
        <div class="q-card">
          <div class="q-meta">
            <span>Question {i + 1} of {total}</span>
            <span>{q.marks} mark{q.marks === 1 ? '' : 's'}{q.topic ? ` · ${q.topic}` : ''}</span>
          </div>
          <h2 class="q-text">{q.question}</h2>

          <div class="opts">
            {#each q.options as opt, oi}
              <button class="opt" class:sel={answers[q.id] === oi} on:click={() => choose(q.id, oi)}>
                <span class="key">{String.fromCharCode(65 + oi)}</span>
                <span class="opt-text">{opt}</span>
              </button>
            {/each}
          </div>

          <div class="nav">
            <button class="btn" disabled={current === 0} on:click={() => (current -= 1)}>← Previous</button>
            {#if current < total - 1}
              <button class="btn" on:click={() => (current += 1)}>Next →</button>
            {/if}
          </div>
        </div>
      {/if}
    {/each}

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

  .progress { height: 5px; background: var(--surface2); border-radius: 999px; overflow: hidden; margin: 1.15rem 0 0.4rem; }
  .progress-fill { height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.25s; }
  .count { font-size: 0.75rem; color: var(--muted); margin-bottom: 1rem; }
  .error { color: var(--accent); font-size: 0.85rem; margin-bottom: 0.75rem; }

  .dots { display: flex; flex-wrap: wrap; gap: 0.3rem; margin-bottom: 1.15rem; }
  .dot { width: 30px; height: 30px; border-radius: 6px; font-size: 0.76rem; font-weight: 700;
         background: var(--surface2); border: 1px solid var(--border); color: var(--muted); cursor: pointer; }
  .dot.done { color: var(--text); border-color: var(--success); }
  .dot.now { background: var(--accent); border-color: var(--accent); color: #fff; }

  .q-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1.5rem; }
  .q-meta { display: flex; justify-content: space-between; font-size: 0.73rem; color: var(--muted); margin-bottom: 0.75rem; gap: 0.75rem; flex-wrap: wrap; }
  .q-text { font-size: 1.06rem; font-weight: 600; line-height: 1.55; margin-bottom: 1.25rem; }

  .opts { display: flex; flex-direction: column; gap: 0.55rem; }
  .opt { display: flex; align-items: flex-start; gap: 0.7rem; text-align: left; width: 100%;
         background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 8px; padding: 0.8rem 0.9rem; font-size: 0.9rem; cursor: pointer;
         font-family: inherit; line-height: 1.5; }
  .opt:hover { border-color: var(--accent); }
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
</style>
