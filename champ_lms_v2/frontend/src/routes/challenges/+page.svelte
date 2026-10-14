<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type ChallengeSummary, type ChallengeDetail } from '$lib/api/client';
  import { auth } from '$lib/stores/auth';
  import Icon from '$lib/components/Icon.svelte';
  import { countUp } from '$lib/actions/motion';

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

  const TYPE_ICON: Record<string, string> = { dept_race: 'flag', onboarding_sprint: 'zap' };
  const TONES = ['lilac', 'sky', 'mint', 'butter', 'peach'];
  const pctOf = (p: number, t: number) => (t ? Math.min(100, (p / t) * 100) : 0);
</script>

<svelte:head><title>Challenges — Champ LMS</title></svelte:head>

{#if detail}
  <div class="challenge-detail">
    <button class="back-btn ui-rise" on:click={() => (detail = null)}><Icon name="arrowLeft" size={16} /> All challenges</button>
    <header class="d-hero ui-rise" style="--i:1">
      <span class="d-mark" aria-hidden="true"><Icon name="users" size={24} /></span>
      <h1>{detail.title}</h1>
      <p class="desc">{detail.description}</p>
      <div class="challenge-stats">
        <span class="stat butter"><Icon name="trophy" size={16} /><b use:countUp={detail.reward_xp}></b> XP</span>
        <span class="stat peach"><Icon name="star" size={16} /><b use:countUp={detail.reward_points}></b> pts</span>
        <span class="stat sky"><Icon name="users" size={16} /> Team size <b>{detail.team_size}</b></span>
        <span class="stat mint"><Icon name="target" size={16} /><b use:countUp={detail.total_teams}></b> teams</span>
      </div>
    </header>

    {#if !detail.my_team_id}
      <div class="join-section">
        <h3 class="ui-rise" style="--i:2">Create a team</h3>
        <div class="create-row ui-rise" style="--i:3">
          <span class="in-ico"><Icon name="plus" size={18} /></span>
          <input bind:value={newTeamName} placeholder="Team name..." />
          <button class="btn-primary" on:click={createTeam} disabled={!newTeamName.trim()}>Create</button>
        </div>
        {#if detail.teams.length}
          <h3 class="ui-rise" style="--i:4">Or join a team</h3>
          <div class="teams-list">
            {#each detail.teams as t, n}
              <div class="team-row ui-rise" style="--i:{Math.min(5 + n, 12)}">
                <span class="t-av {TONES[n % TONES.length]}">{t.name.slice(0, 1).toUpperCase()}</span>
                <div class="t-info">
                  <b>{t.name}</b>
                  <span class="team-meta">{t.member_count}/{detail.team_size} members · {t.progress}/{t.target} done</span>
                </div>
                <button class="btn-ghost" on:click={() => joinTeam(t.id)} disabled={t.member_count >= detail.team_size}>
                  {#if t.member_count >= detail.team_size}<Icon name="lock" size={15} /> Full{:else}Join <Icon name="arrowRight" size={15} />{/if}
                </button>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {:else}
      <h3 class="ui-rise" style="--i:2">Teams</h3>
      <div class="teams-list">
        {#each detail.teams as t, n}
          <div class="team-row ui-rise" style="--i:{Math.min(3 + n, 12)}" class:mine={t.id === detail.my_team_id}>
            <span class="t-av {TONES[n % TONES.length]}">{t.name.slice(0, 1).toUpperCase()}</span>
            <div class="t-info">
              <b>{t.name}</b>
              {#if t.id === detail.my_team_id}<span class="my-badge">Your team</span>{/if}
              <span class="team-meta">{t.member_count}/{detail.team_size} members</span>
            </div>
            <div class="team-progress">
              <div class="progress-bar"><div class="progress-fill" class:done={t.completed} style="width: {pctOf(t.progress, t.target)}%"></div></div>
              <span class="p-txt">{t.progress}/{t.target}</span>
              {#if t.completed}<span class="done-ico"><Icon name="check" size={13} stroke={2.4} /></span>{/if}
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
{:else if loading}
  <div class="challenges-page">
    <div class="ui-skeleton" style="height:52px;width:420px;max-width:100%;border-radius:14px;margin-bottom:1.25rem"></div>
    <div class="challenge-grid">
      {#each Array(3) as _}<div class="ui-skeleton" style="height:170px;border-radius:30px"></div>{/each}
    </div>
  </div>
{:else if challenges.length === 0}
  <div class="state ui-rise">
    <span class="state-ico"><Icon name="users" size={26} /></span>
    <h2>No active challenges</h2>
    <p>No active challenges for your department.</p>
  </div>
{:else}
  <div class="challenges-page">
    <header class="head">
      <p class="eyebrow ui-rise">Team up with colleagues. First team to the finish wins together.</p>
      <h1 class="ui-rise" style="--i:1">
        Collaborative Challenges
        <span class="title-mark" aria-hidden="true"><Icon name="flag" size={24} /></span>
      </h1>
    </header>
    <div class="challenge-grid">
      {#each challenges as c, n}
        <button class="challenge-card ui-rise {TONES[n % TONES.length]}" style="--i:{Math.min(2 + n, 10)}" on:click={() => openChallenge(c)}>
          <span class="corner" aria-hidden="true"><Icon name={TYPE_ICON[c.challenge_type] ?? 'clipboard'} size={18} /></span>
          <h3>{c.title}</h3>
          <p>{c.description}</p>
          <div class="card-foot">
            <div class="card-stats">
              <span><Icon name="trophy" size={14} /> {c.reward_xp} XP</span>
              <span><Icon name="star" size={14} /> {c.reward_points} pts</span>
              <span><Icon name="users" size={14} /> {c.total_teams} teams</span>
            </div>
            {#if c.my_team_id}
              <span class="joined-badge"><Icon name="check" size={13} stroke={2.4} /> Joined</span>
            {/if}
            <span class="ui-round ink go" aria-hidden="true"><Icon name="arrowRight" size={16} /></span>
          </div>
        </button>
      {/each}
    </div>
  </div>
{/if}

<style>
  .challenge-detail { max-width: 820px; margin: 0 auto; }
  .head { margin: 0 0 1.25rem; }
  .eyebrow { color: var(--muted); font-size: 0.95rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.04; display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-peach); color: var(--tile-ink); rotate: 8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: -8deg; transition: rotate var(--dur-3) var(--ease-out); }

  /* ---------- list ---------- */
  .challenge-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1.2rem; }
  .challenge-card {
    position: relative; display: flex; flex-direction: column; align-items: flex-start; gap: 0.55rem;
    min-height: 180px; padding: 1.5rem 1.5rem 1.2rem; border-radius: 30px; color: var(--tile-ink);
    text-align: left; cursor: pointer; box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out), rotate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .challenge-card:hover { translate: 0 -4px; rotate: -1deg; box-shadow: var(--shadow-md); }
  .lilac { background: var(--tile-lilac); } .sky { background: var(--tile-sky); } .mint { background: var(--tile-mint); }
  .butter { background: var(--tile-butter); } .peach { background: var(--tile-peach); }
  .corner {
    position: absolute; top: -10px; right: -8px; width: 46px; height: 46px; border-radius: 50%;
    display: grid; place-items: center; border: 5px solid var(--bg); background: var(--surface); color: var(--text);
    transition: transform var(--dur-3) var(--ease-out);
  }
  .challenge-card:hover .corner { transform: rotate(-14deg) scale(1.08); }
  .challenge-card h3 { font-size: 1.3rem; font-weight: 600; letter-spacing: -0.02em; line-height: 1.2; padding-right: 2rem; }
  .challenge-card p {
    font-size: 0.88rem; opacity: 0.72; line-height: 1.5;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .card-foot { display: flex; align-items: center; gap: 0.6rem; width: 100%; margin-top: auto; padding-top: 0.6rem; }
  .card-stats { display: flex; flex-wrap: wrap; gap: 0.35rem; flex: 1; }
  .card-stats span {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 28px; padding: 0 0.6rem;
    border-radius: 99px; background: var(--tile-inner); font-size: 0.76rem; font-weight: 600;
  }
  .joined-badge {
    display: inline-flex; align-items: center; gap: 0.25rem; height: 28px; padding: 0 0.65rem; border-radius: 99px;
    background: var(--success); color: var(--on-accent); font-size: 0.74rem; font-weight: 700;
    animation: pop 420ms var(--ease-out) 400ms backwards;
  }
  .go { width: 38px; height: 38px; flex: none; transition: transform var(--dur-3) var(--ease-out); }
  .challenge-card:hover .go { transform: translateX(3px) rotate(-30deg); }

  /* ---------- detail ---------- */
  .back-btn {
    display: inline-flex; align-items: center; gap: 0.4rem;
    background: var(--surface); color: var(--text); height: 40px; padding: 0 1rem; border-radius: 999px;
    font-size: 0.86rem; font-weight: 600; margin-bottom: 1rem; cursor: pointer; box-shadow: var(--shadow-sm);
  }
  .back-btn:hover { background: var(--surface2); }
  .back-btn :global(.icon) { transition: translate var(--dur-2) var(--ease-out); }
  .back-btn:hover :global(.icon) { translate: -3px 0; }
  .d-hero {
    position: relative; padding: 1.8rem 1.6rem 1.5rem; border-radius: 32px; background: var(--surface);
    box-shadow: var(--shadow-sm); margin-bottom: 2rem;
  }
  .d-hero h1 { font-size: clamp(1.6rem, 1.1rem + 1.5vw, 2.3rem); margin: 0.8rem 0 0.4rem; }
  .d-mark {
    display: inline-grid; place-items: center; width: 50px; height: 50px; border-radius: 50%;
    background: var(--tile-lilac); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 250ms backwards;
  }
  .desc { color: var(--muted); margin-bottom: 1.2rem; line-height: 1.55; max-width: 60ch; }
  .challenge-stats { display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .stat {
    display: inline-flex; align-items: center; gap: 0.4rem; height: 38px; padding: 0 0.9rem;
    border-radius: 99px; color: var(--tile-ink); font-size: 0.85rem; font-weight: 500;
    transition: translate var(--dur-2) var(--ease-out);
  }
  .stat:hover { translate: 0 -2px; }
  .stat b { font-weight: 700; font-variant-numeric: tabular-nums; }
  .join-section { margin-bottom: 2rem; }
  h3 { font-size: 1.15rem; letter-spacing: -0.015em; margin: 0 0 0.8rem 0.2rem; }
  .create-row {
    display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1.8rem;
    padding: 0.35rem 0.35rem 0.35rem 1rem; border-radius: 999px; background: var(--surface); box-shadow: var(--shadow-sm);
    transition: box-shadow var(--dur-2) var(--ease-out);
  }
  .create-row:focus-within { box-shadow: 0 0 0 2px var(--accent), var(--shadow); }
  .in-ico { color: var(--muted); display: grid; }
  .create-row input { flex: 1; min-width: 0; background: none; border: none; color: var(--text); font-size: 0.95rem; height: 44px; }
  .create-row input:focus { outline: none; box-shadow: none; }
  .teams-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .team-row {
    display: flex; align-items: center; gap: 0.9rem;
    background: var(--surface); border-radius: 22px; padding: 0.7rem 0.9rem 0.7rem 0.7rem; box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .team-row:hover { translate: 3px 0; box-shadow: var(--shadow); }
  .team-row.mine { box-shadow: inset 0 0 0 2px var(--accent), var(--shadow-sm); }
  .t-av {
    flex: none; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center;
    color: var(--tile-ink); font-weight: 700; font-size: 1.05rem; transition: rotate var(--dur-3) var(--ease-out);
  }
  .team-row:hover .t-av { rotate: -10deg; }
  .t-info { flex: 1; min-width: 0; }
  .t-info b { font-weight: 600; }
  .team-meta { display: block; font-size: 0.78rem; color: var(--muted); margin-top: 0.1rem; }
  .my-badge {
    display: inline-flex; height: 20px; align-items: center; padding: 0 0.5rem; border-radius: 99px; margin-left: 0.4rem;
    background: var(--accent); color: var(--on-accent); font-size: 0.66rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
  }
  .team-progress { display: flex; align-items: center; gap: 0.55rem; min-width: 180px; }
  .progress-bar { flex: 1; height: 7px; background: var(--surface3); border-radius: 999px; overflow: hidden; }
  .progress-fill {
    height: 100%; background: var(--accent); border-radius: 999px;
    transform-origin: left; animation: grow 1s var(--ease-out) 350ms backwards; transition: width 0.4s var(--ease-out);
  }
  .progress-fill.done { background: var(--success); }
  @keyframes grow { from { transform: scaleX(0); } }
  .p-txt { font-size: 0.8rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .done-ico {
    width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center;
    background: var(--success); color: var(--on-accent); animation: pop 420ms var(--ease-out) 600ms backwards;
  }

  .state { max-width: 640px; margin: 2rem auto 0; display: flex; flex-direction: column; align-items: center; gap: 0.75rem; text-align: center; padding: 3rem 1.5rem; border-radius: 32px; background: var(--surface); }
  .state h2 { font-size: 1.35rem; }
  .state p { color: var(--muted); }
  .state-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }

  @media (max-width: 760px) {
    .challenge-grid { grid-template-columns: 1fr; }
    .team-row { flex-wrap: wrap; }
    .team-progress { width: 100%; min-width: 0; }
  }
</style>
