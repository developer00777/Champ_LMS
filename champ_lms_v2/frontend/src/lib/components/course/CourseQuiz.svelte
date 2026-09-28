<script lang="ts">
  import { api, type CourseItemView, type AttemptResult } from '$lib/api/client';
  import { handleReward, gamification } from '$lib/stores/gamification';
  import { icons } from './icons';

  export let courseId: string;
  export let item: CourseItemView;
  export let nextTitle: string | null = null;
  export let onDone: () => void;
  export let onNext: () => void;

  type Q = { question: string; options: string[] };
  let questions: Q[] = [];
  let step = -1; // -1 intro, 0..n-1 question, n result
  let answers: (number | null)[] = [];
  let result: (AttemptResult & { feedback?: any[] }) | null = null;
  let busy = false;
  let error = '';

  async function start() {
    busy = true; error = '';
    try {
      const q = await api.courseQuiz(courseId, item.ref_id);
      questions = q.questions; answers = questions.map(() => null); result = null; step = 0;
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  async function submit() {
    busy = true; error = '';
    try {
      const r: any = await api.submitAttempt(item.ref_id, answers.map(a => a ?? -1));
      result = r; step = questions.length;
      if (r.rewards) { handleReward(r.rewards); gamification.rehydrate(); }
      onDone();
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }
</script>

<div class="box">
  {#if step === -1}
    <span class="ico">{@html icons.quiz}</span>
    <h2>{item.title}</h2>
    <p class="muted">
      {item.question_count} questions written from episode{(item.source_episode_numbers?.length ?? 0) === 1 ? '' : 's'}
      {item.source_episode_numbers?.join(', ') || 'in this course'}. Pass mark {item.pass_threshold}%.
      Retake it as often as you like; no approval needed.
      {#if item.must_pass}You need to pass it to unlock what comes next.{/if}
    </p>
    {#if item.best_score != null}<span class="pill" class:ok={item.passed}>Best so far: {item.best_score}%</span>{/if}
    <button class="btn primary" on:click={start} disabled={busy}>{item.attempts ? 'Take it again' : 'Start quiz'}</button>
  {:else if step < questions.length}
    {@const q = questions[step]}
    <div class="top"><span class="eyebrow">{item.title} · question {step + 1} of {questions.length}</span><span class="src">{@html icons.sparkle} AI-written</span></div>
    <h2>{q.question}</h2>
    <div class="opts">
      {#each q.options as o, oi}
        <button class="opt" class:picked={answers[step] === oi} on:click={() => (answers[step] = oi)}>
          <span class="letter">{'ABCDEFGH'[oi]}</span>{o}
        </button>
      {/each}
    </div>
    <div class="nav">
      <button class="btn" on:click={() => (step -= 1)} disabled={step === 0}>Back</button>
      {#if step + 1 < questions.length}
        <button class="btn primary" on:click={() => (step += 1)} disabled={answers[step] == null}>Next question</button>
      {:else}
        <button class="btn primary" on:click={submit} disabled={answers.some(a => a == null) || busy}>{busy ? 'Scoring…' : 'See my score'}</button>
      {/if}
    </div>
  {:else if result}
    <span class="eyebrow">Your score</span>
    <span class="score">{result.score}%</span>
    <span class="pill" class:ok={result.passed}>{result.passed ? 'Passed' : 'Not passed yet'} · pass mark {result.pass_threshold}%</span>
    {#if result.feedback}
      <ol class="fb">
        {#each result.feedback as f}
          <li class:right={f.correct}>
            <b>{f.question}</b>
            {#if f.correct}<span class="ok">Correct: {f.correct_answer}</span>
            {:else}<span class="miss">You chose {f.your_answer ?? 'nothing'}. The answer is {f.correct_answer}.</span>{/if}
            {#if f.explanation}<span class="muted">{f.explanation}</span>{/if}
          </li>
        {/each}
      </ol>
    {/if}
    <div class="nav">
      <button class="btn" on:click={start}>Retake</button>
      {#if nextTitle && result.passed}<button class="btn primary" on:click={onNext}>Continue to {nextTitle}</button>{/if}
    </div>
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
</div>

<style>
  .box { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 1.4rem; display: grid; gap: 0.9rem; justify-items: start; }
  .ico { display: grid; place-items: center; width: 46px; height: 46px; border-radius: 12px; font-size: 1.35rem; color: #b596ff; background: rgba(181, 150, 255, 0.14); }
  h2 { font-size: 1.25rem; font-weight: 700; line-height: 1.3; }
  .muted { color: var(--muted); font-size: 0.9rem; line-height: 1.55; max-width: 65ch; }
  .top { display: flex; justify-content: space-between; gap: 1rem; width: 100%; flex-wrap: wrap; }
  .eyebrow { font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  .src { display: inline-flex; gap: 0.3rem; align-items: center; font-size: 0.75rem; color: var(--muted); }
  .opts { display: grid; gap: 0.5rem; width: 100%; }
  .opt { display: flex; gap: 0.8rem; align-items: center; width: 100%; text-align: left; padding: 0.8rem 0.9rem; border-radius: 10px; border: 1px solid var(--border-hover); background: var(--bg); font-size: 0.92rem; }
  .opt:hover { border-color: var(--text-secondary); }
  .opt.picked { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(229, 9, 20, 0.2); }
  .letter { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; border: 1.5px solid var(--border-hover); font-size: 0.72rem; flex: none; }
  .nav { display: flex; gap: 0.5rem; justify-content: flex-end; width: 100%; flex-wrap: wrap; }
  .btn { height: 38px; padding: 0 1.1rem; border-radius: 8px; font-weight: 600; font-size: 0.88rem; border: 1px solid var(--border-hover); background: var(--surface2); color: var(--text); }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .pill { display: inline-flex; height: 24px; align-items: center; padding: 0 10px; border-radius: 99px; font-size: 0.76rem; font-weight: 600; background: rgba(240, 165, 64, 0.14); color: #f0a540; }
  .pill.ok { background: rgba(46, 204, 113, 0.14); color: #2ecc71; }
  .score { font-size: 3.2rem; font-weight: 800; line-height: 1; font-variant-numeric: tabular-nums; }
  .fb { margin: 0; padding-left: 1.2rem; display: grid; gap: 0.6rem; width: 100%; }
  .fb li { display: grid; gap: 0.15rem; font-size: 0.88rem; }
  .fb .ok { color: #2ecc71; }
  .fb .miss { color: #f0a540; }
  .error { color: #ff6b6b; }
</style>
