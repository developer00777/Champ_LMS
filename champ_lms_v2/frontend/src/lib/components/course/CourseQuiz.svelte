<script lang="ts">
  import { api, type CourseItemView, type AttemptResult } from '$lib/api/client';
  import { handleReward, gamification } from '$lib/stores/gamification';
  import { icons } from './icons';
  import { countUp } from '$lib/actions/motion';

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
    <div class="steps" aria-hidden="true">
      {#each questions as _, qi}<i class:on={qi <= step} class:ans={answers[qi] != null}></i>{/each}
    </div>
    {#key step}
      <div class="qwrap">
        <h2>{q.question}</h2>
        <div class="opts">
          {#each q.options as o, oi}
            <button class="opt" style="--i:{oi}" class:picked={answers[step] === oi} on:click={() => (answers[step] = oi)}>
              <span class="letter">{'ABCDEFGH'[oi]}</span>{o}
            </button>
          {/each}
        </div>
      </div>
    {/key}
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
    <span class="score"><span use:countUp={result.score}></span>%</span>
    <span class="pill" class:ok={result.passed}>{result.passed ? 'Passed' : 'Not passed yet'} · pass mark {result.pass_threshold}%</span>
    {#if result.feedback}
      <ol class="fb">
        {#each result.feedback as f, fi}
          <li class:right={f.correct} style="--i:{Math.min(fi + 1, 10)}">
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
  .box {
    background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-sm); padding: 1.6rem;
    display: grid; gap: 0.95rem; justify-items: start; animation: rise 480ms var(--ease-out) backwards;
  }
  .ico {
    display: grid; place-items: center; width: 52px; height: 52px; border-radius: 50%; font-size: 1.35rem;
    color: var(--tile-ink); background: var(--tile-lilac); rotate: -8deg; animation: pop 560ms var(--ease-out) 200ms backwards;
  }
  h2 { font-size: 1.4rem; font-weight: 700; line-height: 1.3; letter-spacing: -0.02em; }
  .muted { color: var(--muted); font-size: 0.92rem; line-height: 1.6; max-width: 65ch; }
  .top { display: flex; justify-content: space-between; gap: 1rem; width: 100%; flex-wrap: wrap; }
  .eyebrow { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  .src { display: inline-flex; gap: 0.3rem; align-items: center; font-size: 0.75rem; font-weight: 600; color: var(--tile-ink); background: var(--tile-lilac); border-radius: 99px; padding: 0.2rem 0.6rem; }
  .steps { display: flex; gap: 4px; width: 100%; }
  .steps i { flex: 1; height: 5px; border-radius: 99px; background: var(--surface3); transition: background-color var(--dur-3) var(--ease-out); }
  .steps i.ans { background: color-mix(in srgb, var(--accent) 45%, var(--surface3)); }
  .steps i.on { background: var(--accent); }
  .qwrap { display: grid; gap: 0.95rem; width: 100%; animation: q-in 380ms var(--ease-out) backwards; }
  @keyframes q-in { from { opacity: 0; translate: 18px 0; } }
  .opts { display: grid; gap: 0.5rem; width: 100%; }
  .opt {
    display: flex; gap: 0.8rem; align-items: center; width: 100%; text-align: left; padding: 0.6rem 0.9rem 0.6rem 0.6rem;
    border-radius: 18px; background: var(--surface2); font-size: 0.94rem;
    animation: rise 380ms var(--ease-out) backwards; animation-delay: calc(80ms + var(--i) * 50ms);
    transition: background-color var(--dur-2) var(--ease-out), translate var(--dur-2) var(--ease-out), box-shadow var(--dur-2);
  }
  .opt:hover { background: var(--surface3); translate: 3px 0; }
  .opt.picked { background: var(--tile-lilac); color: var(--tile-ink); box-shadow: inset 0 0 0 2px var(--accent); }
  .letter {
    display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; background: var(--surface);
    font-size: 0.78rem; font-weight: 700; flex: none; transition: background-color var(--dur-2), color var(--dur-2);
  }
  .opt.picked .letter { background: var(--accent); color: var(--on-accent); animation: pop 360ms var(--ease-out); }
  .nav { display: flex; gap: 0.5rem; justify-content: flex-end; width: 100%; flex-wrap: wrap; }
  .btn {
    display: inline-flex; align-items: center; height: 42px; padding: 0 1.2rem; border-radius: 999px; font-weight: 600; font-size: 0.88rem;
    background: var(--surface2); color: var(--text);
    transition: background-color var(--dur-2), translate var(--dur-2) var(--ease-out);
  }
  .btn:hover:not(:disabled) { background: var(--surface3); translate: 0 -1px; }
  .btn.primary { background: var(--accent); color: var(--on-accent); }
  .btn.primary:hover:not(:disabled) { background: var(--accent-hover); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .pill { display: inline-flex; height: 30px; align-items: center; padding: 0 12px; border-radius: 99px; font-size: 0.78rem; font-weight: 600; background: var(--tile-butter); color: var(--tile-ink); animation: pop 420ms var(--ease-out) 200ms backwards; }
  .pill.ok { background: var(--tile-mint); }
  .score { font-size: 3.6rem; font-weight: 700; letter-spacing: -0.04em; line-height: 1; font-variant-numeric: tabular-nums; animation: pop 600ms var(--ease-out) backwards; }
  .fb { margin: 0; padding: 0; list-style: none; display: grid; gap: 0.5rem; width: 100%; }
  .fb li {
    display: grid; gap: 0.2rem; font-size: 0.88rem; padding: 0.75rem 0.95rem; border-radius: 18px;
    background: color-mix(in srgb, var(--warn) 12%, var(--surface));
    animation: rise 420ms var(--ease-out) backwards; animation-delay: calc(var(--i) * 60ms);
  }
  .fb li.right { background: var(--tile-mint); color: var(--tile-ink); }
  .fb li.right .muted { color: inherit; opacity: 0.72; }
  .fb .ok { color: inherit; font-weight: 600; }
  .fb .miss { color: var(--text); font-weight: 500; }
  .error { color: var(--danger); animation: wiggle 420ms var(--ease-out); }
</style>
