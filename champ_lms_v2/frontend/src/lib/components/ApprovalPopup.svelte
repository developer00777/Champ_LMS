<script lang="ts">
  import { api, type TestRequestRow } from '$lib/api/client';
  import { activeRequest, closeRequest, refreshRequests } from '$lib/stores/test-requests';

  let attempts = 1;
  let note = '';
  let reason = '';
  let denying = false;
  let busy = false;
  let error = '';
  let shownId: string | null = null;

  // Reset the form whenever a different request opens.
  $: if ($activeRequest && $activeRequest.id !== shownId) {
    shownId = $activeRequest.id;
    attempts = $activeRequest.attempts_per_approval || 1;
    note = ''; reason = ''; denying = false; error = '';
  }

  function ago(iso: string) {
    const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m} min ago`;
    if (m < 1440) return `${Math.round(m / 60)} h ago`;
    return `${Math.round(m / 1440)} d ago`;
  }

  async function decide(r: TestRequestRow, approve: boolean) {
    busy = true; error = '';
    try {
      if (approve) await api.approveTestRequest(r.id, attempts, note || undefined);
      else await api.denyTestRequest(r.id, reason || undefined);
      closeRequest();
      await refreshRequests();
    } catch (e: any) {
      error = e.message;
      // Someone else decided it first: drop it from the queue.
      if (e.status === 409) { closeRequest(); refreshRequests().catch(() => {}); }
    } finally { busy = false; }
  }

  function onKey(e: KeyboardEvent) { if (e.key === 'Escape' && $activeRequest && !busy) closeRequest(); }
</script>

<svelte:window on:keydown={onKey} />

{#if $activeRequest}
  {@const r = $activeRequest}
  <div class="scrim" on:click|self={() => !busy && closeRequest()} role="presentation">
    <div class="modal" role="dialog" aria-modal="true" aria-labelledby="req-title">
      <div class="eyebrow"><span class="pulse"></span>Test request · {ago(r.created_at)}</div>
      <h2 id="req-title">{r.full_name} wants to take {r.test_title}</h2>
      <dl class="facts">
        {#if r.course_title}<dt>Course</dt><dd>{r.course_title}</dd>{/if}
        <dt>Team</dt><dd>{r.team ?? '—'}{r.department ? ` · ${r.department}` : ''}</dd>
        <dt>Course progress</dt><dd>{r.course_progress}% watched</dd>
        <dt>Earlier attempts</dt><dd>{r.previous_attempts || 'None'}</dd>
        <dt>Test</dt>
        <dd>{r.question_count} questions{r.duration_minutes ? ` · ${r.duration_minutes} min` : ''}{r.pass_threshold ? ` · pass ${r.pass_threshold}%` : ''}{r.proctoring_enabled ? ' · proctored' : ''}</dd>
      </dl>

      {#if denying}
        <label class="field">
          <span>Reason {r.full_name.split(' ')[0]} will see</span>
          <textarea rows="2" bind:value={reason} placeholder="Finish the Discovery section first."></textarea>
        </label>
        {#if error}<p class="error">{error}</p>{/if}
        <div class="actions">
          <button class="btn" on:click={() => (denying = false)} disabled={busy}>Back</button>
          <button class="btn primary" on:click={() => decide(r, false)} disabled={busy}>Deny request</button>
        </div>
      {:else}
        <div class="field">
          <span>Attempts to allow</span>
          <div class="row">
            <div class="stepper">
              <button on:click={() => (attempts = Math.max(1, attempts - 1))} aria-label="Fewer attempts">−</button>
              <b>{attempts}</b>
              <button on:click={() => (attempts = Math.min(10, attempts + 1))} aria-label="More attempts">+</button>
            </div>
            <p class="hint">{r.full_name.split(' ')[0]} can sit the test this many times before asking again.</p>
          </div>
        </div>
        <label class="field">
          <span>Note to {r.full_name.split(' ')[0]} (optional)</span>
          <input type="text" bind:value={note} maxlength="500" />
        </label>
        {#if error}<p class="error">{error}</p>{/if}
        <div class="actions">
          <button class="btn" on:click={closeRequest} disabled={busy}>Decide later</button>
          <button class="btn" on:click={() => (denying = true)} disabled={busy}>Deny</button>
          <button class="btn primary" on:click={() => decide(r, true)} disabled={busy}>
            Approve {attempts} attempt{attempts === 1 ? '' : 's'}
          </button>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .scrim {
    position: fixed; inset: 0; z-index: 400;
    background: rgba(4, 4, 10, 0.6);
    display: grid; place-items: center; padding: 1rem;
  }
  .modal {
    width: min(480px, 100%); max-height: calc(100vh - 2rem); overflow: auto;
    background: var(--surface); border: 1px solid var(--border-hover);
    border-radius: 16px; box-shadow: var(--shadow-lg);
    padding: 1.4rem; display: grid; gap: 1rem;
  }
  .eyebrow {
    display: flex; align-items: center; gap: 0.5rem;
    color: var(--accent); font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase;
  }
  .pulse {
    width: 8px; height: 8px; border-radius: 50%; background: var(--accent);
    animation: pulse 1.6s infinite;
  }
  @keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(229, 9, 20, 0.6); } 70% { box-shadow: 0 0 0 8px transparent; } }
  h2 { font-size: 1.2rem; font-weight: 700; line-height: 1.3; }
  .facts {
    display: grid; grid-template-columns: auto 1fr; gap: 0.35rem 1rem;
    font-size: 0.85rem; padding: 0.8rem 0.9rem; border-radius: 10px; background: var(--surface2);
  }
  .facts dt { color: var(--muted); }
  .field { display: grid; gap: 0.4rem; font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }
  .field input, .field textarea {
    font: inherit; font-weight: 400; font-size: 0.9rem; color: var(--text);
    background: var(--bg); border: 1px solid var(--border-hover); border-radius: 8px; padding: 0.55rem 0.7rem;
  }
  .row { display: flex; align-items: center; gap: 0.9rem; flex-wrap: wrap; }
  .stepper { display: inline-flex; align-items: center; border: 1px solid var(--border-hover); border-radius: 10px; overflow: hidden; }
  .stepper button { width: 44px; height: 44px; font-size: 1.25rem; color: var(--text-secondary); }
  .stepper button:hover { background: var(--surface2); }
  .stepper b { min-width: 52px; text-align: center; font-size: 1.25rem; font-variant-numeric: tabular-nums; }
  .hint { font-weight: 400; color: var(--muted); max-width: 26ch; }
  .actions { display: flex; gap: 0.5rem; justify-content: flex-end; flex-wrap: wrap; }
  .btn {
    height: 36px; padding: 0 1rem; border-radius: 8px; font-weight: 600; font-size: 0.85rem;
    border: 1px solid var(--border-hover); background: var(--surface2); color: var(--text);
  }
  .btn:hover:not(:disabled) { background: var(--surface3); }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn.primary:hover:not(:disabled) { background: var(--accent-hover); }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .error { color: #ff6b6b; font-size: 0.85rem; }
</style>
