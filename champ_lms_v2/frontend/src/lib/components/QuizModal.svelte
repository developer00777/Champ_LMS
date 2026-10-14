<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api, type AssessmentData, type AttemptResult } from '$lib/api/client';
  import { handleReward, gamification } from '$lib/stores/gamification';
  import ShareAchievement from './ShareAchievement.svelte';
  import Icon from './Icon.svelte';
  import { countUp } from '$lib/actions/motion';

  export let assessmentId: string;
  export let questions: AssessmentData['questions'];

  const dispatch = createEventDispatcher<{ close: void; passed: void }>();

  let answers: (number | null)[] = questions.map(() => null);
  let result: AttemptResult | null = null;
  let submitting = false;
  let error = '';

  async function submit() {
    if (answers.some(a => a === null)) { error = 'Please answer all questions'; return; }
    submitting = true;
    error = '';
    try {
      result = await api.submitAttempt(assessmentId, answers as number[]);
      if (result.rewards) {
        handleReward(result.rewards);
        gamification.rehydrate();
      }
      if (result.passed) dispatch('passed');
    } catch (e: any) {
      error = e.message;
    } finally {
      submitting = false;
    }
  }

  $: answered = answers.filter(a => a !== null).length;
  const LETTERS = 'ABCDEFGH';
</script>

<!-- The backdrop is a mouse shortcut only; keyboard users close with the × button.
     Escape deliberately does nothing: one stray press would throw away a half-done quiz. -->
<div class="overlay" role="presentation" on:click|self={() => dispatch('close')}>
  <div class="modal" role="dialog" aria-modal="true" aria-label="Quiz">
    <button class="close ui-round" on:click={() => dispatch('close')} aria-label="Close"><Icon name="close" size={16} /></button>

    {#if result}
      <div class="result">
        <div class="score-ring" class:passed={result.passed} class:failed={!result.passed} style="--p:{result.score}%">
          <span class="score"><b use:countUp={result.score}></b><i>%</i></span>
        </div>
        <h2 class="verdict">
          {#if result.passed}<Icon name="checkCircle" size={22} /> Passed!{:else}Not quite — try again{/if}
        </h2>

        <div class="feedback">
          {#each result.feedback as fb, i}
            <div class="fb-item ui-rise" style="--i:{Math.min(i + 1, 8)}" class:correct={fb.correct} class:wrong={!fb.correct}>
              <span class="fb-ico"><Icon name={fb.correct ? 'check' : 'close'} size={14} /></span>
              <div>
                <p class="fb-q">{i + 1}. {fb.question}</p>
                <p class="fb-a">Your answer: {fb.your_answer ?? '—'}</p>
                {#if !fb.correct}
                  <p class="fb-correct">Correct: {fb.correct_answer}</p>
                {/if}
                {#if fb.explanation}
                  <p class="fb-exp">{fb.explanation}</p>
                {/if}
              </div>
            </div>
          {/each}
        </div>

        {#if result.passed}
          <div class="share-wrap">
            <ShareAchievement type="module_mastery" refId={assessmentId} buttonText="Share this win" />
          </div>
        {/if}

        <button class="btn-primary" on:click={() => dispatch('close')}>Continue learning <Icon name="arrowRight" size={16} /></button>
      </div>
    {:else}
      <span class="mark" aria-hidden="true"><Icon name="clipboard" size={22} /></span>
      <h2>Episode Quiz</h2>
      <p class="sub">Answer all questions to complete this episode</p>
      <div class="meter" aria-hidden="true">
        <span class="bar"><span style="width:{(answered / Math.max(1, questions.length)) * 100}%"></span></span>
        <small>{answered} / {questions.length}</small>
      </div>

      {#each questions as q, i}
        <div class="question ui-rise" style="--i:{Math.min(i + 1, 8)}">
          <p class="q-text"><span class="q-num">{i + 1}</span>{q.question}</p>
          <div class="options">
            {#each q.options as opt, j}
              <label class="option" class:selected={answers[i] === j}>
                <input type="radio" name="q{i}" value={j} bind:group={answers[i]} />
                <span class="letter">{LETTERS[j] ?? j + 1}</span>
                <span class="opt-txt">{opt}</span>
              </label>
            {/each}
          </div>
        </div>
      {/each}

      {#if error}<p class="error"><Icon name="alert" size={15} /> {error}</p>{/if}

      <button class="btn-primary" on:click={submit} disabled={submitting}>
        {#if submitting}<span class="dots"><i></i><i></i><i></i></span> Submitting{:else}Submit quiz <Icon name="send" size={16} />{/if}
      </button>
    {/if}
  </div>
</div>

<style>
  .overlay {
    position: fixed; inset: 0;
    background: var(--scrim);
    display: flex; align-items: center; justify-content: center;
    z-index: 1000; padding: 1rem;
  }
  .modal {
    background: var(--surface);
    border-radius: 32px;
    box-shadow: var(--shadow-lg);
    padding: 2rem 1.75rem 1.75rem;
    max-width: 580px;
    width: 100%;
    max-height: 86vh;
    overflow-y: auto;
    position: relative;
  }
  .close { position: absolute; top: 1rem; right: 1rem; width: 38px; height: 38px; }
  .close :global(.icon) { transition: rotate var(--dur-3) var(--ease-out); }
  .close:hover :global(.icon) { rotate: 90deg; }
  .mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-lilac); color: var(--tile-ink); rotate: -8deg; margin-bottom: 0.75rem;
    animation: pop 520ms var(--ease-out) 150ms backwards;
  }
  h2 { font-size: 1.45rem; letter-spacing: -0.025em; margin-bottom: 0.25rem; }
  .sub { color: var(--muted); font-size: 0.92rem; margin-bottom: 1rem; }
  .meter { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; }
  .meter small { font-size: 0.78rem; font-weight: 600; color: var(--muted); font-variant-numeric: tabular-nums; }
  .bar { flex: 1; height: 6px; border-radius: 99px; background: var(--surface3); overflow: hidden; }
  .bar span { display: block; height: 100%; border-radius: inherit; background: var(--accent); transition: width var(--dur-3) var(--ease-out); }

  .question { margin-bottom: 1.4rem; }
  .q-text { display: flex; gap: 0.6rem; font-weight: 600; margin-bottom: 0.75rem; line-height: 1.4; }
  .q-num {
    flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center;
    background: var(--surface2); font-size: 0.78rem; font-weight: 700;
  }
  .options { display: flex; flex-direction: column; gap: 0.45rem; }
  .option {
    display: flex; align-items: center; gap: 0.7rem;
    padding: 0.55rem 0.8rem 0.55rem 0.55rem;
    background: var(--surface2);
    border-radius: 18px;
    cursor: pointer;
    font-size: 0.92rem;
    transition: background-color var(--dur-2) var(--ease-out), translate var(--dur-2) var(--ease-out), box-shadow var(--dur-2);
  }
  .option:hover { background: var(--surface3); translate: 3px 0; }
  .option.selected { background: var(--tile-lilac); color: var(--tile-ink); box-shadow: inset 0 0 0 2px var(--accent); }
  .option input { position: absolute; opacity: 0; pointer-events: none; }
  .option:focus-within { box-shadow: 0 0 0 2px var(--accent); }
  .letter {
    flex: none; width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center;
    background: var(--surface); font-size: 0.8rem; font-weight: 700;
    transition: background-color var(--dur-2), color var(--dur-2);
  }
  .option.selected .letter { background: var(--accent); color: var(--on-accent); animation: pop 360ms var(--ease-out); }

  /* ---------- result ---------- */
  .result { display: flex; flex-direction: column; align-items: stretch; }
  .score-ring {
    align-self: center; width: 132px; height: 132px; border-radius: 50%; display: grid; place-items: center;
    background: conic-gradient(var(--ring) var(--p), var(--surface3) 0);
    animation: pop 640ms var(--ease-out) backwards; margin-bottom: 0.9rem;
  }
  .score-ring.passed { --ring: var(--success); }
  .score-ring.failed { --ring: var(--danger); }
  .score {
    width: 108px; height: 108px; border-radius: 50%; display: grid; place-items: center; grid-auto-flow: column;
    background: var(--surface);
  }
  .score b { font-size: 2.3rem; font-weight: 700; letter-spacing: -0.04em; font-variant-numeric: tabular-nums; }
  .score i { font-style: normal; font-size: 1rem; font-weight: 600; color: var(--muted); align-self: center; }
  .verdict { display: flex; align-items: center; justify-content: center; gap: 0.45rem; text-align: center; margin-bottom: 1.4rem; }
  .score-ring.passed + .verdict :global(.icon) { color: var(--success); }
  .feedback { display: flex; flex-direction: column; gap: 0.55rem; margin-bottom: 1.5rem; }
  .fb-item { display: flex; gap: 0.7rem; padding: 0.8rem 0.9rem; border-radius: 18px; }
  .fb-item.correct { background: var(--tile-mint); color: var(--tile-ink); }
  .fb-item.wrong { background: color-mix(in srgb, var(--danger) 12%, var(--surface)); }
  .fb-ico {
    flex: none; width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center;
    background: var(--tile-inner);
  }
  .fb-item.correct .fb-ico { background: var(--success); color: var(--on-accent); }
  .fb-item.wrong .fb-ico { background: var(--danger); color: var(--on-accent); }
  .fb-q { font-weight: 600; font-size: 0.88rem; }
  .fb-a, .fb-correct, .fb-exp { font-size: 0.8rem; opacity: 0.8; margin-top: 0.25rem; }
  .fb-correct { font-weight: 600; opacity: 1; }
  .error {
    display: flex; align-items: center; gap: 0.4rem; color: var(--danger); font-size: 0.86rem; margin-bottom: 0.75rem;
    animation: wiggle 420ms var(--ease-out);
  }
  .share-wrap { margin: 0 0 1.25rem; }
  .btn-primary { width: 100%; justify-content: center; }
  .dots { display: inline-flex; gap: 3px; }
  .dots i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; animation: pulse-dot 900ms var(--ease-in-out) infinite; }
  .dots i:nth-child(2) { animation-delay: 150ms; }
  .dots i:nth-child(3) { animation-delay: 300ms; }
  @keyframes pulse-dot { 0%, 100% { opacity: 0.3; translate: 0 0; } 50% { opacity: 1; translate: 0 -2px; } }
</style>
