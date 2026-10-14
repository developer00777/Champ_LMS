<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type ZoomSession } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';

  let sessions: ZoomSession[] = [];
  let loading = true;
  let building: string | null = null;

  // Manual session form
  let showForm = false;
  let topic = '';
  let summary = '';
  let transcript = '';
  let submitting = false;
  let formError = '';

  onMount(() => loadSessions());

  async function loadSessions() {
    loading = true;
    try { sessions = await api.zoomSessions(); }
    finally { loading = false; }
  }

  async function buildModule(sessionId: string) {
    building = sessionId;
    try {
      await api.buildModule(sessionId);
      await loadSessions();
    } catch (e: any) {
      alert(e.message);
    } finally {
      building = null;
    }
  }

  async function submitManual() {
    if (!topic || !transcript) { formError = 'Topic and transcript required'; return; }
    submitting = true; formError = '';
    try {
      await api.addZoomSession({ topic, summary, transcript });
      showForm = false; topic = ''; summary = ''; transcript = '';
      await loadSessions();
    } catch (e: any) { formError = e.message; }
    finally { submitting = false; }
  }
</script>

<svelte:head><title>Zoom → Module Builder — Admin</title></svelte:head>

<div class="page">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Zoom → Module Builder' }]} />
  <div class="header">
    <div>
      <h1 class="ui-rise" style="--i:1">
        Zoom → Module Builder
        <span class="title-mark" aria-hidden="true"><Icon name="video" size={23} /></span>
      </h1>
      <p class="sub ui-rise" style="--i:2">Claude AI converts Zoom transcripts into structured learning modules with episodes and quizzes.</p>
    </div>
    <button class="btn-primary toggle ui-rise" style="--i:3" class:open={showForm} on:click={() => showForm = !showForm}>
      <span class="plus"><Icon name="plus" size={16} stroke={2.2} /></span>
      {showForm ? 'Cancel' : 'Add Manual Session'}
    </button>
  </div>

  {#if showForm}
    <div class="form-card">
      <div class="f-head">
        <span class="f-ico"><Icon name="mic" size={18} /></span>
        <div>
          <h2>Add Zoom Session Manually</h2>
          <p class="hint">Paste the transcript from Zoom's AI Companion or recording.</p>
        </div>
      </div>
      <label><span class="lbl">Meeting Topic *</span>
        <input bind:value={topic} placeholder="e.g. Q3 Sales Strategy" />
      </label>
      <label><span class="lbl">AI Summary (optional)</span>
        <textarea bind:value={summary} rows="3" placeholder="Brief summary of the meeting..."></textarea>
      </label>
      <label><span class="lbl">Full Transcript *</span>
        <textarea bind:value={transcript} rows="8" placeholder="Paste the full meeting transcript here..."></textarea>
      </label>
      {#if formError}{#key formError}<p class="error"><Icon name="alert" size={15} /> {formError}</p>{/key}{/if}
      <div class="form-actions">
        <button class="btn-ghost" on:click={() => showForm = false}>Cancel</button>
        <button class="btn-primary" on:click={submitManual} disabled={submitting}>
          {#if submitting}<span class="spin" aria-hidden="true"></span> Processing...{:else}<Icon name="sparkles" size={16} /> Submit &amp; Build Module{/if}
        </button>
      </div>
    </div>
  {/if}

  {#if loading}
    <div class="sessions">
      {#each Array(3) as _}<div class="ui-skeleton" style="height:84px;border-radius:24px"></div>{/each}
    </div>
  {:else if sessions.length === 0}
    <div class="empty ui-rise">
      <span class="e-ico"><Icon name="video" size={28} /></span>
      <h2>No Zoom sessions yet.</h2>
      <p>Sessions appear here when Zoom webhooks fire or you add them manually.</p>
    </div>
  {:else}
    <div class="sessions">
      {#each sessions as s, n}
        <div class="session-card ui-rise" style="--i:{Math.min(n, 10) + 3}" class:ready={s.processed && s.module_id}>
          <span class="s-ico" aria-hidden="true"><Icon name={s.processed && s.module_id ? 'checkCircle' : 'video'} size={20} /></span>
          <div class="session-info">
            <p class="topic">{s.topic || 'Untitled Session'}</p>
            <p class="date"><Icon name="calendar" size={13} /> {new Date(s.created_at).toLocaleDateString()}</p>
          </div>
          <div class="session-status">
            {#if s.processed && s.module_id}
              <span class="badge-done"><Icon name="check" size={14} /> Module Ready</span>
              <a href="/module/{s.module_id}" class="btn-ghost">View Module <Icon name="arrowRight" size={15} /></a>
            {:else if building === s.id}
              <span class="building"><span class="spin" aria-hidden="true"></span> Building with Claude AI...</span>
            {:else}
              <button
                class="btn-primary build"
                on:click={() => buildModule(s.id)}
                disabled={building !== null}
              >
                <Icon name="sparkles" size={16} /> Build Module
              </button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { max-width: 900px; margin: 0 auto; }
  .header { display: flex; align-items: flex-end; justify-content: space-between; gap: 1.25rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
  h1 {
    font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.05;
    display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
  }
  .title-mark {
    display: inline-grid; place-items: center; width: 46px; height: 46px; border-radius: 50%;
    background: var(--tile-sky); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .sub { color: var(--muted); font-size: 0.95rem; margin-top: 0.6rem; max-width: 60ch; }
  .plus { display: grid; transition: rotate var(--dur-3) var(--ease-out); }
  .toggle.open .plus { rotate: 45deg; }
  .toggle:hover .plus { rotate: 90deg; }
  .toggle.open:hover .plus { rotate: 135deg; }

  .form-card {
    background: var(--surface); border-radius: 30px; padding: 1.6rem; margin-bottom: 1.5rem; box-shadow: var(--shadow-md);
    display: flex; flex-direction: column; gap: 1rem;
    transform-origin: top center; animation: drop 420ms var(--ease-out);
  }
  @keyframes drop { from { opacity: 0; translate: 0 -10px; scale: 0.98; } }
  .f-head { display: flex; align-items: center; gap: 0.8rem; }
  .f-ico { width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-lilac); color: var(--tile-ink); flex: none; }
  h2 { font-size: 1.15rem; font-weight: 700; letter-spacing: -0.02em; }
  .hint { font-size: 0.84rem; color: var(--muted); }
  label { display: flex; flex-direction: column; gap: 0.4rem; }
  .lbl { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
  input, textarea {
    background: var(--surface2); border: 1px solid transparent;
    color: var(--text); border-radius: 16px; padding: 0.8rem 1rem;
    font-size: 0.92rem; resize: vertical; font-family: inherit;
  }
  input { height: 48px; }
  input:hover, textarea:hover { background: var(--surface3); }
  .form-actions { display: flex; gap: 0.6rem; justify-content: flex-end; flex-wrap: wrap; }
  .error {
    display: flex; align-items: center; gap: 0.45rem; padding: 0.6rem 0.85rem; border-radius: 14px; font-size: 0.85rem; font-weight: 600;
    background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); animation: shake 420ms var(--ease-out);
  }
  @keyframes shake { 20%, 60% { translate: -5px 0; } 40%, 80% { translate: 5px 0; } }

  .empty {
    display: flex; flex-direction: column; align-items: center; gap: 0.5rem; text-align: center;
    padding: 2.75rem 1rem; border-radius: 30px; background: var(--surface); color: var(--muted);
  }
  .empty h2 { color: var(--text); }
  .e-ico {
    width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; margin-bottom: 0.4rem;
    background: var(--tile-sky); color: var(--tile-ink); animation: float 4s var(--ease-in-out) infinite;
  }

  .sessions { display: flex; flex-direction: column; gap: 0.7rem; }
  .session-card {
    display: flex; align-items: center; gap: 1rem;
    background: var(--surface); border-radius: 24px; padding: 0.9rem 1rem 0.9rem 0.9rem; box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .session-card:hover { translate: 4px 0; box-shadow: var(--shadow); }
  .s-ico {
    width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; flex: none;
    background: var(--tile-sky); color: var(--tile-ink);
    transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .ready .s-ico { background: var(--tile-mint); }
  .session-card:hover .s-ico { rotate: -12deg; scale: 1.08; }
  .session-info { flex: 1; min-width: 0; }
  .topic { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .date { display: flex; align-items: center; gap: 0.3rem; font-size: 0.78rem; color: var(--muted); margin-top: 0.2rem; }
  .session-status { display: flex; align-items: center; gap: 0.6rem; flex-shrink: 0; }
  .badge-done {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 30px; padding: 0 0.8rem; border-radius: 99px;
    background: var(--tile-mint); color: var(--tile-ink); font-size: 0.8rem; font-weight: 600;
  }
  .building { display: inline-flex; align-items: center; gap: 0.5rem; color: var(--text-secondary); font-size: 0.86rem; font-weight: 600; }
  .build :global(.icon) { transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out); }
  .build:hover:not(:disabled) :global(.icon) { rotate: 20deg; scale: 1.15; }
  .spin {
    width: 16px; height: 16px; border-radius: 50%; flex: none;
    border: 2px solid color-mix(in srgb, currentColor 25%, transparent); border-top-color: currentColor;
    animation: spin 800ms linear infinite;
  }
  @keyframes spin { to { rotate: 360deg; } }

  @media (max-width: 680px) {
    .session-card { flex-wrap: wrap; }
    .session-status { width: 100%; justify-content: flex-end; }
  }
</style>
