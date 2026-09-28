<script lang="ts">
  import { onDestroy } from 'svelte';
  import { api, type CourseItemView } from '$lib/api/client';
  import { icons } from './icons';

  export let courseId: string;
  export let item: CourseItemView;
  export let onChanged: () => void;

  let busy = false;
  let error = '';

  // While waiting on the admin, check every 15 seconds so "Start" appears
  // without a reload once they approve.
  let poll: ReturnType<typeof setInterval> | null = null;
  $: {
    if (item.state === 'pending' && !poll) poll = setInterval(onChanged, 15_000);
    if (item.state !== 'pending' && poll) { clearInterval(poll); poll = null; }
  }
  onDestroy(() => poll && clearInterval(poll));

  async function ask() {
    busy = true; error = '';
    try { await api.requestCourseTest(courseId, item.ref_id); onChanged(); }
    catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  function ago(iso?: string | null) {
    if (!iso) return '';
    const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m} min ago`;
    if (m < 1440) return `${Math.round(m / 60)} h ago`;
    return `${Math.round(m / 1440)} d ago`;
  }
  $: s = item.state;
  $: plural = (n: number) => `${n} attempt${n === 1 ? '' : 's'}`;
</script>

<div class="box">
  <span class="ico" class:ok={s === 'approved'} class:warn={s === 'pending'}>
    {@html s === 'approved' ? icons.check : s === 'pending' ? icons.clock : s === 'not_allowed' ? icons.lock : icons.test}
  </span>
  <h2>
    {#if s === 'approved'}Approved: {item.title}{:else if s === 'pending'}Waiting for your admin{:else if s === 'denied'}Request declined{:else}{item.title}{/if}
  </h2>
  <div class="facts">
    <span class="pill">{item.question_count} questions</span>
    {#if item.duration_minutes}<span class="pill">{item.duration_minutes} min</span>{/if}
    <span class="pill">Pass {item.pass_threshold}%</span>
    {#if item.proctoring_enabled}<span class="pill">{@html icons.shield} Proctored</span>{/if}
    {#if item.passed}<span class="pill ok">Passed · best {item.best_score}%</span>{/if}
  </div>

  {#if s === 'not_allowed'}
    <p class="muted">Your admin hasn't opened this test to you. You can still watch the whole course.</p>
  {:else if s === 'approved'}
    <p class="muted">
      Your admin approved {plural(item.attempts_left ?? 0)}{#if item.note}: “{item.note}”{:else}.{/if}
      The timer starts when you press start.
    </p>
    <a class="btn primary" href="/tests/{item.ref_id}?course={courseId}">Start test</a>
  {:else if s === 'pending'}
    <p class="muted">Your request went to your admin {ago(item.requested_at)}. You'll be able to start as soon as they approve it. Keep watching meanwhile.</p>
  {:else if s === 'denied'}
    <p class="muted">{item.reason ? `Your admin said: “${item.reason}”` : 'Your admin declined this request.'}</p>
    <button class="btn" on:click={ask} disabled={busy}>Ask again</button>
  {:else}
    {#if s === 'used'}
      <p class="muted">
        You've used your approved attempts. Last score {item.last_score}%.
        {#if item.last_attempt_id}<a href="/tests/result/{item.last_attempt_id}">See the result</a>.{/if}
        {#if !item.passed}Ask your admin for another go when you're ready.{/if}
      </p>
    {:else}
      <p class="muted">Your admin approves each attempt. Send a request and they'll get a pop-up to let you in and set how many tries you get.</p>
    {/if}
    {#if !item.unlocked}
      <p class="lockline">{@html icons.lock} Watch every episode first. This test opens once they're all watched.</p>
    {/if}
    {#if s !== 'used' || !item.passed}
      <button class="btn primary" on:click={ask} disabled={busy || !item.unlocked}>
        {s === 'used' ? 'Ask for another attempt' : 'Request to take this test'}
      </button>
    {/if}
  {/if}
  {#if error}<p class="error">{error}</p>{/if}
</div>

<style>
  .box { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 1.4rem; display: grid; gap: 0.85rem; justify-items: start; }
  .ico { display: grid; place-items: center; width: 46px; height: 46px; border-radius: 12px; font-size: 1.35rem; color: #f5c518; background: rgba(245, 197, 24, 0.13); }
  .ico.ok { color: #2ecc71; background: rgba(46, 204, 113, 0.14); }
  .ico.warn { color: #f0a540; background: rgba(240, 165, 64, 0.14); }
  h2 { font-size: 1.25rem; font-weight: 700; }
  .facts { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .pill { display: inline-flex; gap: 0.3rem; align-items: center; height: 24px; padding: 0 10px; border-radius: 99px; font-size: 0.76rem; font-weight: 600; background: var(--surface3); color: var(--text-secondary); }
  .pill.ok { background: rgba(46, 204, 113, 0.14); color: #2ecc71; }
  .muted { color: var(--muted); font-size: 0.9rem; line-height: 1.55; max-width: 65ch; }
  .muted a { color: var(--text); text-decoration: underline; }
  .lockline { display: flex; gap: 0.4rem; align-items: center; color: #f0a540; font-size: 0.86rem; }
  .btn { display: inline-flex; align-items: center; height: 38px; padding: 0 1.1rem; border-radius: 8px; font-weight: 600; font-size: 0.88rem; border: 1px solid var(--border-hover); background: var(--surface2); color: var(--text); }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .error { color: #ff6b6b; }
</style>
