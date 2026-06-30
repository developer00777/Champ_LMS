<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type ZoomSession } from '$lib/api/client';

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
  <div class="breadcrumb"><a href="/admin">Admin</a> / Zoom Module Builder</div>
  <div class="header">
    <h1>Zoom → Module Builder</h1>
    <button class="btn-primary" on:click={() => showForm = !showForm}>
      {showForm ? 'Cancel' : '+ Add Manual Session'}
    </button>
  </div>
  <p class="sub">Claude AI converts Zoom transcripts into structured learning modules with episodes and quizzes.</p>

  {#if showForm}
    <div class="form-card">
      <h2>Add Zoom Session Manually</h2>
      <p class="hint">Paste the transcript from Zoom's AI Companion or recording.</p>
      <label>Meeting Topic *
        <input bind:value={topic} placeholder="e.g. Q3 Sales Strategy" />
      </label>
      <label>AI Summary (optional)
        <textarea bind:value={summary} rows="3" placeholder="Brief summary of the meeting..."></textarea>
      </label>
      <label>Full Transcript *
        <textarea bind:value={transcript} rows="8" placeholder="Paste the full meeting transcript here..."></textarea>
      </label>
      {#if formError}<p class="error">{formError}</p>{/if}
      <div class="form-actions">
        <button class="btn-ghost" on:click={() => showForm = false}>Cancel</button>
        <button class="btn-primary" on:click={submitManual} disabled={submitting}>
          {submitting ? 'Processing...' : 'Submit & Build Module'}
        </button>
      </div>
    </div>
  {/if}

  {#if loading}
    <div class="loading">Loading sessions...</div>
  {:else if sessions.length === 0}
    <div class="empty">
      <p>No Zoom sessions yet.</p>
      <p>Sessions appear here when Zoom webhooks fire or you add them manually.</p>
    </div>
  {:else}
    <div class="sessions">
      {#each sessions as s}
        <div class="session-card">
          <div class="session-info">
            <p class="topic">{s.topic || 'Untitled Session'}</p>
            <p class="date">{new Date(s.created_at).toLocaleDateString()}</p>
          </div>
          <div class="session-status">
            {#if s.processed && s.module_id}
              <span class="badge-done">✓ Module Ready</span>
              <a href="/module/{s.module_id}" class="btn-ghost">View Module</a>
            {:else if building === s.id}
              <span class="building">Building with Claude AI...</span>
            {:else}
              <button
                class="btn-primary"
                on:click={() => buildModule(s.id)}
                disabled={building !== null}
              >
                Build Module ▶
              </button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .page { max-width: 800px; margin: 0 auto; }
  .breadcrumb { font-size: 0.83rem; color: var(--muted); margin-bottom: 1rem; }
  .breadcrumb a { color: var(--accent); }
  .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; }
  h1 { font-size: 1.6rem; font-weight: 800; }
  .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }
  .form-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.75rem; margin-bottom: 2rem;
    display: flex; flex-direction: column; gap: 1rem;
  }
  h2 { font-size: 1.1rem; font-weight: 700; }
  .hint { font-size: 0.83rem; color: var(--muted); }
  label { display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.85rem; color: var(--muted); }
  input, textarea {
    background: var(--surface2); border: 1px solid var(--border);
    color: var(--text); border-radius: 6px; padding: 0.6rem 0.8rem;
    font-size: 0.9rem; resize: vertical; font-family: inherit;
  }
  .form-actions { display: flex; gap: 0.75rem; justify-content: flex-end; }
  .error { color: var(--accent); font-size: 0.85rem; }
  .loading, .empty { text-align: center; padding: 3rem; color: var(--muted); }
  .empty p { margin-bottom: 0.25rem; }
  .sessions { display: flex; flex-direction: column; gap: 0.75rem; }
  .session-card {
    display: flex; align-items: center; justify-content: space-between; gap: 1rem;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 1rem 1.25rem;
  }
  .topic { font-weight: 600; }
  .date { font-size: 0.78rem; color: var(--muted); margin-top: 0.15rem; }
  .session-status { display: flex; align-items: center; gap: 0.75rem; flex-shrink: 0; }
  .badge-done { color: var(--success); font-size: 0.85rem; font-weight: 700; }
  .building { color: var(--gold); font-size: 0.85rem; }
</style>
