<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type LearnerTest, type MyAttempt } from '$lib/api/client';

  let tests: LearnerTest[] = [];
  let attempts: MyAttempt[] = [];
  let loading = true;
  let error = '';

  onMount(async () => {
    try {
      [tests, attempts] = await Promise.all([api.testSeries(), api.myTestAttempts()]);
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  });
</script>

<div class="page">
  <h1>Test Series</h1>
  <p class="sub">Prove what you've learned. Every test is scored instantly with feedback on where to improve.</p>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <div class="grid">{#each Array(3) as _}<div class="skeleton"></div>{/each}</div>
  {:else if tests.length === 0}
    <div class="empty">
      <div class="empty-icon">📝</div>
      <h2>No tests available</h2>
      <p>When your L&amp;D team publishes a test series, it shows up here.</p>
    </div>
  {:else}
    <div class="grid">
      {#each tests as t (t.id)}
        <div class="card">
          <div class="card-head">
            <h2>{t.title}</h2>
            {#if t.passed}<span class="badge pass">Passed</span>{/if}
          </div>
          {#if t.description}<p class="desc">{t.description}</p>{/if}

          <div class="meta">
            <span class="chip">{t.total_questions} questions</span>
            <span class="chip">{t.total_marks} marks</span>
            <span class="chip">pass {t.pass_threshold}%</span>
            {#if t.duration_minutes}<span class="chip">⏱ {t.duration_minutes} min</span>{/if}
            {#if t.category}<span class="chip">{t.category}</span>{/if}
          </div>

          {#if t.my_attempts > 0}
            <div class="prev">
              Best score <b class:pass={t.passed}>{t.my_best_score}%</b>
              · {t.my_attempts} attempt{t.my_attempts === 1 ? '' : 's'}
              {#if t.attempts_left !== null}· {t.attempts_left} left{/if}
            </div>
          {:else if t.max_attempts}
            <div class="prev">{t.max_attempts} attempt{t.max_attempts === 1 ? '' : 's'} allowed</div>
          {/if}

          {#if t.attempts_left === 0}
            <button class="btn" disabled>No attempts left</button>
          {:else}
            <a href="/tests/{t.id}" class="btn primary">
              {t.my_attempts > 0 ? 'Retake test' : 'Start test'}
            </a>
          {/if}
        </div>
      {/each}
    </div>
  {/if}

  {#if attempts.length > 0}
    <h2 class="section">Your history</h2>
    <div class="history">
      {#each attempts as a (a.attempt_id)}
        <a class="hist-row" href="/tests/result/{a.attempt_id}">
          <div>
            <b>{a.test_title}</b>
            <span class="muted">{new Date(a.submitted_at).toLocaleDateString()} · {a.correct_count}/{a.total_questions} correct</span>
          </div>
          <div class="hist-score">
            <span class="score" class:pass={a.passed} class:fail={!a.passed}>{a.score}%</span>
            <span class="arrow">›</span>
          </div>
        </a>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { max-width: 900px; margin: 0 auto; padding-bottom: 3rem; }
  h1 { font-size: 1.6rem; font-weight: 800; margin-bottom: 0.3rem; }
  .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.75rem; }
  .error { color: var(--accent); font-size: 0.85rem; margin-bottom: 1rem; }
  .section { font-size: 1.15rem; font-weight: 700; margin: 2.25rem 0 0.9rem; }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 1rem; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
          padding: 1.25rem; display: flex; flex-direction: column; gap: 0.7rem; }
  .card-head { display: flex; justify-content: space-between; gap: 0.6rem; align-items: flex-start; }
  .card h2 { font-size: 1.02rem; font-weight: 700; line-height: 1.35; }
  .badge { font-size: 0.65rem; font-weight: 800; letter-spacing: 0.05em; border-radius: 999px;
           padding: 0.15rem 0.5rem; white-space: nowrap; }
  .badge.pass { color: var(--success); border: 1px solid var(--success); }
  .desc { font-size: 0.82rem; color: var(--muted); line-height: 1.5; }
  .meta { display: flex; flex-wrap: wrap; gap: 0.35rem; }
  .chip { font-size: 0.71rem; color: var(--muted); background: var(--surface2);
          border-radius: 999px; padding: 0.18rem 0.55rem; }
  .prev { font-size: 0.79rem; color: var(--muted); }
  .prev b { color: var(--text); }
  .prev b.pass { color: var(--success); }

  .btn { margin-top: auto; background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 6px; padding: 0.55rem 1rem; font-size: 0.86rem; font-weight: 600;
         cursor: pointer; text-align: center; text-decoration: none; }
  .btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }

  .history { display: flex; flex-direction: column; gap: 0.5rem; }
  .hist-row { display: flex; justify-content: space-between; align-items: center;
              background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
              padding: 0.8rem 1rem; text-decoration: none; color: var(--text); }
  .hist-row:hover { border-color: var(--accent); }
  .hist-row b { display: block; font-size: 0.9rem; }
  .muted { color: var(--muted); font-size: 0.75rem; }
  .hist-score { display: flex; align-items: center; gap: 0.6rem; }
  .score { font-size: 1.1rem; font-weight: 800; }
  .score.pass { color: var(--success); }
  .score.fail { color: #e05260; }
  .arrow { color: var(--muted); font-size: 1.2rem; }

  .empty { text-align: center; padding: 3.5rem 1rem; background: var(--surface);
           border: 1px solid var(--border); border-radius: 10px; }
  .empty-icon { font-size: 2.5rem; margin-bottom: 0.7rem; }
  .empty h2 { font-size: 1.15rem; margin-bottom: 0.35rem; }
  .empty p { color: var(--muted); font-size: 0.87rem; }

  .skeleton { height: 200px; border-radius: 10px;
              background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
              background-size: 200% 100%; animation: shimmer 1.4s infinite; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
</style>
