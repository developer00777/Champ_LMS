<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api, type AssessmentData, type AttemptResult } from '$lib/api/client';

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
      if (result.passed) dispatch('passed');
    } catch (e: any) {
      error = e.message;
    } finally {
      submitting = false;
    }
  }
</script>

<div class="overlay" on:click|self={() => dispatch('close')}>
  <div class="modal">
    <button class="close" on:click={() => dispatch('close')}>✕</button>

    {#if result}
      <div class="result">
        <div class="score" class:passed={result.passed} class:failed={!result.passed}>
          {result.score}%
        </div>
        <p>{result.passed ? '🎉 Passed!' : 'Not quite — try again'}</p>

        <div class="feedback">
          {#each result.feedback as fb, i}
            <div class="fb-item" class:correct={fb.correct} class:wrong={!fb.correct}>
              <p class="fb-q">{i + 1}. {fb.question}</p>
              <p class="fb-a">Your answer: {fb.your_answer ?? '—'}</p>
              {#if !fb.correct}
                <p class="fb-correct">Correct: {fb.correct_answer}</p>
              {/if}
              {#if fb.explanation}
                <p class="fb-exp">{fb.explanation}</p>
              {/if}
            </div>
          {/each}
        </div>

        <button class="btn-primary" on:click={() => dispatch('close')}>Continue Learning</button>
      </div>
    {:else}
      <h2>Episode Quiz</h2>
      <p class="sub">Answer all questions to complete this episode</p>

      {#each questions as q, i}
        <div class="question">
          <p class="q-text">{i + 1}. {q.question}</p>
          <div class="options">
            {#each q.options as opt, j}
              <label class="option" class:selected={answers[i] === j}>
                <input type="radio" name="q{i}" value={j} bind:group={answers[i]} />
                {opt}
              </label>
            {/each}
          </div>
        </div>
      {/each}

      {#if error}<p class="error">{error}</p>{/if}

      <button class="btn-primary" on:click={submit} disabled={submitting}>
        {submitting ? 'Submitting...' : 'Submit Quiz'}
      </button>
    {/if}
  </div>
</div>

<style>
  .overlay {
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.8);
    display: flex; align-items: center; justify-content: center;
    z-index: 1000;
  }
  .modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2rem;
    max-width: 560px;
    width: 90%;
    max-height: 80vh;
    overflow-y: auto;
    position: relative;
  }
  .close {
    position: absolute; top: 1rem; right: 1rem;
    background: none; border: none; color: var(--muted);
    font-size: 1.1rem; cursor: pointer;
  }
  h2 { font-size: 1.3rem; margin-bottom: 0.25rem; }
  .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.5rem; }
  .question { margin-bottom: 1.5rem; }
  .q-text { font-weight: 600; margin-bottom: 0.75rem; line-height: 1.4; }
  .options { display: flex; flex-direction: column; gap: 0.5rem; }
  .option {
    display: flex; align-items: center; gap: 0.6rem;
    padding: 0.6rem 0.8rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    cursor: pointer;
    font-size: 0.9rem;
    transition: border-color 0.15s, background 0.15s;
  }
  .option.selected {
    border-color: var(--accent);
    background: rgba(229,9,20,0.1);
  }
  .option input { display: none; }
  .score {
    font-size: 3rem; font-weight: 800; text-align: center;
    margin-bottom: 0.5rem;
  }
  .score.passed { color: var(--success); }
  .score.failed { color: var(--accent); }
  .result p { text-align: center; margin-bottom: 1.5rem; }
  .feedback { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1.5rem; }
  .fb-item {
    padding: 0.75rem;
    border-radius: 6px;
    border-left: 3px solid var(--border);
  }
  .fb-item.correct { border-color: var(--success); background: rgba(46,204,113,0.08); }
  .fb-item.wrong { border-color: var(--accent); background: rgba(229,9,20,0.08); }
  .fb-q { font-weight: 600; font-size: 0.85rem; }
  .fb-a, .fb-correct, .fb-exp { font-size: 0.8rem; color: var(--muted); margin-top: 0.25rem; }
  .fb-correct { color: var(--success); }
  .error { color: var(--accent); font-size: 0.85rem; margin-bottom: 0.75rem; }
  .btn-primary { width: 100%; }
</style>
