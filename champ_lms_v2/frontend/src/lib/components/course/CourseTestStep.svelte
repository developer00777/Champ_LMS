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
  .box {
    background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-sm); padding: 1.6rem;
    display: grid; gap: 0.9rem; justify-items: start; animation: rise 480ms var(--ease-out) backwards;
  }
  .ico {
    display: grid; place-items: center; width: 52px; height: 52px; border-radius: 50%; font-size: 1.35rem;
    color: var(--tile-ink); background: var(--tile-butter); rotate: -8deg; animation: pop 560ms var(--ease-out) 200ms backwards;
  }
  .ico.ok { background: var(--tile-mint); }
  .ico.warn { background: var(--tile-peach); }
  /* A gentle pulse while the request waits on the admin. */
  .ico.warn::after {
    content: ''; position: absolute; inset: 0; border-radius: inherit; animation: pulse-ring 1.8s var(--ease-out) infinite;
  }
  .ico { position: relative; }
  h2 { font-size: 1.4rem; font-weight: 700; letter-spacing: -0.02em; }
  .facts { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .pill {
    display: inline-flex; gap: 0.3rem; align-items: center; height: 30px; padding: 0 12px; border-radius: 99px; font-size: 0.78rem; font-weight: 600;
    background: var(--surface2); color: var(--text-secondary);
    animation: pop 420ms var(--ease-out) backwards;
  }
  .pill:nth-child(2) { animation-delay: 60ms; } .pill:nth-child(3) { animation-delay: 120ms; }
  .pill:nth-child(4) { animation-delay: 180ms; } .pill:nth-child(5) { animation-delay: 240ms; }
  .pill.ok { background: var(--tile-mint); color: var(--tile-ink); }
  .muted { color: var(--muted); font-size: 0.92rem; line-height: 1.6; max-width: 65ch; }
  .muted a { color: var(--text); text-decoration: underline; font-weight: 600; }
  .lockline {
    display: flex; gap: 0.5rem; align-items: center; color: var(--tile-ink); font-size: 0.86rem; font-weight: 500;
    background: var(--tile-butter); padding: 0.5rem 0.9rem; border-radius: 99px;
  }
  .btn {
    display: inline-flex; align-items: center; height: 44px; padding: 0 1.3rem; border-radius: 999px; font-weight: 600; font-size: 0.9rem;
    background: var(--surface2); color: var(--text);
    transition: background-color var(--dur-2), translate var(--dur-2) var(--ease-out), box-shadow var(--dur-2);
  }
  .btn:hover:not(:disabled) { background: var(--surface3); translate: 0 -1px; }
  .btn.primary { background: var(--accent); color: var(--on-accent); }
  .btn.primary:hover:not(:disabled) { background: var(--accent-hover); box-shadow: var(--shadow); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .error { color: var(--danger); animation: wiggle 420ms var(--ease-out); }
</style>
