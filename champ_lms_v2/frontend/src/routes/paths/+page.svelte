<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type PathSummary, type PathDetail, type PathNode } from '$lib/api/client';
  import { auth } from '$lib/stores/auth';
  import SkillTrail from '$lib/components/SkillTrail.svelte';

  let paths: PathSummary[] = [];
  let selectedPath: PathDetail | null = null;
  let loading = true;
  let error = '';

  onMount(async () => {
    try {
      paths = await api.paths();
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  });

  async function openPath(p: PathSummary) {
    loading = true;
    try {
      selectedPath = await api.path(p.id);
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  function onNodeClick(node: PathNode) {
    if (node.module_id && node.status !== 'locked') {
      window.location.href = `/module/${node.module_id}`;
    }
  }

  $: myDept = $auth.user?.department;
  $: deptPaths = paths.filter(p => p.department === myDept);
  $: otherPaths = paths.filter(p => p.department !== myDept);
</script>

<svelte:head><title>Learning Paths — Champ LMS</title></svelte:head>

{#if selectedPath}
  <div class="path-detail-view">
    <button class="back-btn" on:click={() => (selectedPath = null)}>← All Paths</button>
    <SkillTrail path={selectedPath} onNodeClick={onNodeClick} />
  </div>
{:else if loading}
  <div class="loading-state">Loading paths...</div>
{:else if error}
  <div class="error-state">{error}</div>
{:else}
  <div class="paths-page">
    <h1>Learning Paths</h1>
    <p class="subtitle">Competency-gated skill tracks. Master each checkpoint to unlock the next.</p>

    {#if deptPaths.length}
      <section>
        <h2>Your Department — {myDept}</h2>
        <div class="path-grid">
          {#each deptPaths as p}
            <button class="path-card" on:click={() => openPath(p)}>
              <span class="path-variant">{p.variant === 'ridge' ? '🏔️' : '🥾'}</span>
              <div class="path-info">
                <h3>{p.title}</h3>
                <p>{p.description ?? ''}</p>
                <span class="path-meta">{p.total_nodes} checkpoints · {p.path_type}</span>
              </div>
            </button>
          {/each}
        </div>
      </section>
    {/if}

    {#if otherPaths.length}
      <section>
        <h2>Other Tracks</h2>
        <div class="path-grid">
          {#each otherPaths as p}
            <button class="path-card" on:click={() => openPath(p)}>
              <span class="path-variant">{p.variant === 'ridge' ? '🏔️' : '🥾'}</span>
              <div class="path-info">
                <h3>{p.title}</h3>
                <p>{p.description ?? ''}</p>
                <span class="path-meta">{p.total_nodes} checkpoints · {p.path_type}</span>
              </div>
            </button>
          {/each}
        </div>
      </section>
    {/if}
  </div>
{/if}

<style>
  .paths-page { max-width: 900px; margin: 0 auto; }
  h1 { font-size: 1.8rem; font-weight: 800; margin-bottom: 0.25rem; }
  .subtitle { color: var(--muted); margin-bottom: 2rem; }
  h2 { font-size: 1.1rem; font-weight: 700; margin-bottom: 1rem; color: var(--text-secondary); }
  section { margin-bottom: 2.5rem; }
  .path-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 1rem; }
  .path-card {
    display: flex; align-items: flex-start; gap: 1rem;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: 1.25rem;
    text-align: left; cursor: pointer; transition: all 0.2s;
  }
  .path-card:hover { border-color: var(--accent); background: var(--surface2); transform: translateY(-1px); }
  .path-variant { font-size: 1.8rem; }
  .path-info { flex: 1; }
  .path-info h3 { font-size: 1rem; font-weight: 700; margin-bottom: 0.25rem; }
  .path-info p { font-size: 0.85rem; color: var(--muted); margin-bottom: 0.5rem; }
  .path-meta { font-size: 0.75rem; color: var(--muted); text-transform: capitalize; }
  .back-btn {
    background: var(--surface); border: 1px solid var(--border);
    color: var(--text); padding: 0.5rem 1rem; border-radius: 6px;
    font-size: 0.85rem; margin-bottom: 1rem; cursor: pointer;
  }
  .back-btn:hover { background: var(--surface2); }
  .loading-state, .error-state { text-align: center; padding: 4rem; color: var(--muted); }
</style>
