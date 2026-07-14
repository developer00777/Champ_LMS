<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type ChallengeSummary, type ChallengeDetail } from '$lib/api/client';
  import { auth } from '$lib/stores/auth';

  let challenges: ChallengeSummary[] = [];
  let detail: ChallengeDetail | null = null;
  let loading = true;
  let newTeamName = '';

  onMount(async () => {
    try {
      challenges = await api.challenges($auth.user?.department ?? undefined);
    } finally {
      loading = false;
    }
  });

  async function openChallenge(c: ChallengeSummary) {
    loading = true;
    try {
      detail = await api.challenge(c.id);
    } finally {
      loading = false;
    }
  }

  async function createTeam() {
    if (!detail || !newTeamName.trim()) return;
    const res = await api.createTeam(detail.id, newTeamName.trim());
    detail = await api.challenge(detail.id);
    newTeamName = '';
  }

  async function joinTeam(teamId: string) {
    if (!detail) return;
    await api.joinTeam(detail.id, teamId);
    detail = await api.challenge(detail.id);
  }
</script>

<svelte:head><title>Challenges — Champ LMS</title></svelte:head>

{#if detail}
  <div class="challenge-detail">
    <button class="back-btn" on:click={() => (detail = null)}>← All Challenges</button>
    <h1>{detail.title}</h1>
    <p class="desc">{detail.description}</p>
    <div class="challenge-stats">
      <span>🏆 {detail.reward_xp} XP</span>
      <span>⭐ {detail.reward_points} pts</span>
      <span>👥 Team size: {detail.team_size}</span>
      <span>🎯 {detail.total_teams} teams</span>
    </div>

    {#if !detail.my_team_id}
      <div class="join-section">
        <h3>Create a Team</h3>
        <div class="create-row">
          <input bind:value={newTeamName} placeholder="Team name..." />
          <button class="btn-primary" on:click={createTeam} disabled={!newTeamName.trim()}>Create</button>
        </div>
        {#if detail.teams.length}
          <h3>Or Join a Team</h3>
          <div class="teams-list">
            {#each detail.teams as t}
              <div class="team-row">
                <div>
                  <b>{t.name}</b>
                  <span class="team-meta">{t.member_count}/{detail.team_size} members · {t.progress}/{t.target} done</span>
                </div>
                <button class="btn-ghost" on:click={() => joinTeam(t.id)} disabled={t.member_count >= detail.team_size}>
                  {t.member_count >= detail.team_size ? 'Full' : 'Join'}
                </button>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {:else}
      <h3>Teams</h3>
      <div class="teams-list">
        {#each detail.teams as t}
          <div class="team-row" class:mine={t.id === detail.my_team_id}>
            <div>
              <b>{t.name}</b>
              {#if t.id === detail.my_team_id}<span class="my-badge">YOUR TEAM</span>{/if}
              <span class="team-meta">{t.member_count}/{detail.team_size} members</span>
            </div>
            <div class="team-progress">
              <div class="progress-bar"><div class="progress-fill" style="width: {Math.min(100, (t.progress / t.target) * 100)}%"></div></div>
              <span>{t.progress}/{t.target} {t.completed ? '✅' : ''}</span>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
{:else if loading}
  <div class="loading">Loading...</div>
{:else if challenges.length === 0}
  <div class="empty">No active challenges for your department.</div>
{:else}
  <div class="challenges-page">
    <h1>Collaborative Challenges</h1>
    <p class="subtitle">Team up with colleagues. First team to the finish wins together.</p>
    <div class="challenge-grid">
      {#each challenges as c}
        <button class="challenge-card" on:click={() => openChallenge(c)}>
          <div class="card-header">
            <span class="card-icon">{c.challenge_type === 'dept_race' ? '🏁' : c.challenge_type === 'onboarding_sprint' ? '🚀' : '📋'}</span>
            <h3>{c.title}</h3>
          </div>
          <p>{c.description}</p>
          <div class="card-stats">
            <span>🏆 {c.reward_xp} XP</span>
            <span>⭐ {c.reward_points} pts</span>
            <span>👥 {c.total_teams} teams</span>
          </div>
          {#if c.my_team_id}
            <span class="joined-badge">JOINED</span>
          {/if}
        </button>
      {/each}
    </div>
  </div>
{/if}

<style>
  .challenges-page, .challenge-detail { max-width: 700px; margin: 0 auto; }
  h1 { font-size: 1.6rem; font-weight: 800; margin-bottom: 0.25rem; }
  .subtitle, .desc { color: var(--muted); margin-bottom: 1.5rem; }
  .challenge-grid { display: flex; flex-direction: column; gap: 1rem; }
  .challenge-card {
    position: relative; display: flex; flex-direction: column; gap: 0.5rem;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-lg); padding: 1.25rem;
    text-align: left; cursor: pointer; transition: all 0.2s;
  }
  .challenge-card:hover { border-color: var(--accent); transform: translateY(-1px); }
  .card-header { display: flex; align-items: center; gap: 0.75rem; }
  .card-icon { font-size: 1.5rem; }
  .card-header h3 { font-size: 1rem; font-weight: 700; }
  .challenge-card p { font-size: 0.85rem; color: var(--muted); }
  .card-stats { display: flex; gap: 1rem; font-size: 0.8rem; }
  .joined-badge {
    position: absolute; top: 1rem; right: 1rem;
    background: rgba(46,204,113,0.15); color: var(--success);
    font-size: 0.65rem; font-weight: 800; padding: 0.2rem 0.5rem; border-radius: 4px;
  }
  .challenge-stats { display: flex; gap: 1.5rem; margin-bottom: 1.5rem; font-size: 0.85rem; }
  .join-section { margin-bottom: 2rem; }
  h3 { font-size: 0.95rem; margin-bottom: 0.75rem; }
  .create-row { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; }
  .create-row input {
    flex: 1; background: var(--surface); border: 1px solid var(--border);
    color: var(--text); border-radius: 6px; padding: 0.5rem 0.8rem; font-size: 0.85rem;
  }
  .teams-list { display: flex; flex-direction: column; gap: 0.5rem; }
  .team-row {
    display: flex; align-items: center; justify-content: space-between;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.85rem 1rem; gap: 1rem;
  }
  .team-row.mine { border-color: var(--accent); background: rgba(229,9,20,0.07); }
  .team-meta { display: block; font-size: 0.75rem; color: var(--muted); }
  .my-badge { font-size: 0.6rem; font-weight: 800; color: var(--accent); margin-left: 0.5rem; }
  .team-progress { display: flex; align-items: center; gap: 0.5rem; min-width: 140px; }
  .progress-bar { flex: 1; height: 6px; background: var(--surface2); border-radius: 999px; overflow: hidden; }
  .progress-fill { height: 100%; background: var(--gold); border-radius: 999px; transition: width 0.4s; }
  .back-btn { background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 0.5rem 1rem; border-radius: 6px; font-size: 0.85rem; margin-bottom: 1rem; cursor: pointer; }
  .back-btn:hover { background: var(--surface2); }
  .loading, .empty { text-align: center; padding: 4rem; color: var(--muted); }
</style>
