<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api,
    type DailyChallengeSet,
    type StreakDetail,
    type KudosItem,
    type KudosRecipient,
  } from '$lib/api/client';
  import Avatar from '$lib/components/Avatar.svelte';
  import { gamification } from '$lib/stores/gamification';

  let challenges: DailyChallengeSet | null = null;
  let streak: StreakDetail | null = null;
  let kudos: KudosItem[] = [];
  let recipients: KudosRecipient[] = [];
  let loading = true;
  let error = '';

  // Per-challenge busy flag, so one claim doesn't disable every button.
  let claiming: Record<string, boolean> = {};
  let claimNote = '';

  // --- kudos composer ------------------------------------------------------
  let showCompose = false;
  let toUserId = '';
  let message = '';
  let emoji = '🎉';
  let sending = false;
  let sendError = '';
  let sentNote = '';
  let kudosFilter: 'all' | 'mine' = 'all';

  const EMOJI = ['🎉', '🚀', '💡', '🙌', '🏆', '❤️', '🔥', '🧠'];

  const KIND_LABELS: Record<string, string> = {
    watch_episode: 'Watch',
    pass_quiz: 'Quiz',
    pass_test: 'Test',
    self_report: 'Self-reported',
  };

  onMount(load);

  async function load() {
    loading = true;
    try {
      // Fetched together: the page is useless with only some of it, and three
      // sequential round-trips is a visibly slower first paint.
      [challenges, streak, kudos, recipients] = await Promise.all([
        api.dailyChallenges(),
        api.streakDetail(),
        api.kudosWall({ limit: 20 }),
        api.kudosRecipients(),
      ]);
      error = '';
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function reloadKudos() {
    try {
      kudos = await api.kudosWall({ limit: 20, mine: kudosFilter === 'mine' });
    } catch (e: any) {
      sendError = e.message;
    }
  }

  async function claim(id: string) {
    if (claiming[id]) return;
    claiming[id] = true; claiming = claiming;
    claimNote = ''; error = '';
    try {
      const res = await api.completeDailyChallenge(id);
      claimNote = `+${res.awarded_xp} XP${res.verified ? ' · verified' : ''}`;
      // Refresh both: the claim moves the streak and the XP bar too.
      const [set, st] = await Promise.all([api.dailyChallenges(), api.streakDetail()]);
      challenges = set; streak = st;
      gamification.rehydrate();
    } catch (e: any) {
      error = e.message;
    } finally {
      claiming[id] = false; claiming = claiming;
    }
  }

  async function send() {
    if (!toUserId || !message.trim() || sending) return;
    sending = true; sendError = ''; sentNote = '';
    try {
      const res = await api.sendKudos({
        to_user_id: toUserId,
        message: message.trim(),
        emoji,
      });
      sentNote = `Sent to ${res.to_name}. ${res.kudos_left_today} left today.`;
      message = ''; toUserId = ''; showCompose = false;
      await reloadKudos();
      gamification.rehydrate();
    } catch (e: any) {
      sendError = e.message;
    } finally {
      sending = false;
    }
  }

  function switchFilter(next: 'all' | 'mine') {
    kudosFilter = next;
    reloadKudos();
  }

  function when(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  }

  $: progressPct =
    challenges && challenges.total > 0
      ? (challenges.completed / challenges.total) * 100
      : 0;
  $: allDone = !!challenges && challenges.total > 0 && challenges.completed === challenges.total;
</script>

<svelte:head><title>Today · Champ LMS</title></svelte:head>

<div class="page">
  <header class="head">
    <div>
      <h1>Today</h1>
      <p class="sub">Your daily challenges, streak, and team recognition.</p>
    </div>
    {#if streak}
      <div class="streak-card" class:cold={!streak.active_today}>
        <span class="flame">{streak.active_today ? '🔥' : '🕯'}</span>
        <div class="streak-text">
          <b>{streak.streak_days} day{streak.streak_days === 1 ? '' : 's'}</b>
          <span>
            {#if streak.active_today}
              Active today
            {:else}
              Learn something to keep it alive
            {/if}
          </span>
        </div>
      </div>
    {/if}
  </header>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <div class="skeleton big"></div>
  {:else}
    <!-- Streak detail ------------------------------------------------------ -->
    {#if streak}
      <div class="streak-stats">
        <div class="stat">
          <b>{streak.streak_days}</b><span>current streak</span>
        </div>
        <div class="stat">
          <b>{streak.longest_streak}</b><span>personal best</span>
        </div>
        <div class="stat" title="A freeze covers one missed day so your streak survives">
          <b>{streak.streak_freezes}</b><span>freezes left</span>
        </div>
      </div>
    {/if}

    <!-- Daily challenges --------------------------------------------------- -->
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Daily challenges</h2>
          <p class="panel-sub">
            A fresh set every day, the same for everyone. Verified challenges
            unlock once you've actually done the work.
          </p>
        </div>
        {#if challenges}
          <span class="tally">{challenges.completed} / {challenges.total}</span>
        {/if}
      </div>

      {#if challenges}
        <div class="progress"><div class="fill" style="width:{progressPct}%"></div></div>
        {#if allDone}
          <p class="all-done">🎉 All done for today — come back tomorrow for a new set.</p>
        {/if}
        {#if claimNote}<p class="claim-note">{claimNote}</p>{/if}

        {#if challenges.challenges.length === 0}
          <p class="empty">No challenges are set up yet. An admin can add some.</p>
        {:else}
          <div class="ch-list">
            {#each challenges.challenges as ch (ch.id)}
              <div class="ch" class:done={ch.completed_today}>
                <div class="ch-main">
                  <div class="ch-top">
                    <b>{ch.title}</b>
                    <span class="kind" class:auto={ch.auto_verified}>
                      {KIND_LABELS[ch.kind] ?? ch.kind}
                    </span>
                    {#if ch.always_on}<span class="kind pin">Pinned</span>{/if}
                  </div>
                  {#if ch.description}<p class="ch-desc">{ch.description}</p>{/if}
                  <span class="reward">+{ch.reward_xp} XP</span>
                </div>

                <div class="ch-action">
                  {#if ch.completed_today}
                    <span class="badge-done">
                      ✓ Done{ch.verified ? '' : ' (self-reported)'}
                    </span>
                  {:else if ch.claimable}
                    <button class="btn primary" disabled={claiming[ch.id]}
                            on:click={() => claim(ch.id)}>
                      {claiming[ch.id] ? 'Claiming…' : ch.auto_verified ? 'Collect' : 'Mark done'}
                    </button>
                  {:else}
                    <span class="locked" title="Finish the activity and this unlocks">
                      Not yet
                    </span>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </section>

    <!-- Kudos -------------------------------------------------------------- -->
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Kudos</h2>
          <p class="panel-sub">Recognise someone who helped you. They earn XP for it.</p>
        </div>
        <button class="btn primary" on:click={() => (showCompose = !showCompose)}>
          {showCompose ? 'Cancel' : 'Give kudos'}
        </button>
      </div>

      {#if sentNote}<p class="claim-note">{sentNote}</p>{/if}

      {#if showCompose}
        <div class="compose">
          {#if sendError}<p class="error">{sendError}</p>{/if}
          <label>
            Who?
            <select bind:value={toUserId}>
              <option value="">Choose a colleague…</option>
              {#each recipients as r}
                <option value={r.id}>
                  {r.full_name}{r.employee_code ? ` · ${r.employee_code}` : ''}
                </option>
              {/each}
            </select>
          </label>

          <div class="emoji-row">
            {#each EMOJI as e}
              <button type="button" class="emoji" class:sel={emoji === e}
                      on:click={() => (emoji = e)}>{e}</button>
            {/each}
          </div>

          <label>
            What did they do?
            <textarea bind:value={message} rows="3" maxlength="280"
                      placeholder="Walked me through the new pricing deck…"></textarea>
          </label>
          <div class="compose-foot">
            <span class="muted tiny">{message.length}/280</span>
            <button class="btn primary" disabled={!toUserId || !message.trim() || sending}
                    on:click={send}>
              {sending ? 'Sending…' : 'Send kudos'}
            </button>
          </div>
        </div>
      {/if}

      <div class="tabs">
        <button class="tab" class:on={kudosFilter === 'all'}
                on:click={() => switchFilter('all')}>Everyone</button>
        <button class="tab" class:on={kudosFilter === 'mine'}
                on:click={() => switchFilter('mine')}>For me</button>
      </div>

      {#if kudos.length === 0}
        <p class="empty">
          {kudosFilter === 'mine'
            ? 'No kudos for you yet — it’ll show up here.'
            : 'No kudos yet. Be the first to recognise someone.'}
        </p>
      {:else}
        <div class="kudos-list">
          {#each kudos as k (k.id)}
            <div class="kudos">
              <span class="k-emoji">{k.emoji}</span>
              <div class="k-body">
                <div class="k-who">
                  <Avatar src={k.from_avatar_url} name={k.from_name} size={24} />
                  <b>{k.from_name ?? 'Someone'}</b>
                  <span class="muted">→</span>
                  <Avatar src={k.to_avatar_url} name={k.to_name} size={24} />
                  <b>{k.to_name ?? 'Someone'}</b>
                  {#if k.xp_multiplier > 1}
                    <span class="mult" title="Recognition from a leader counts double">
                      {k.xp_multiplier}×
                    </span>
                  {/if}
                </div>
                <p class="k-msg">{k.message}</p>
                <span class="muted tiny">{when(k.created_at)}</span>
              </div>
            </div>
          {/each}
        </div>
      {/if}
    </section>
  {/if}
</div>

<style>
  .page { max-width: 860px; margin: 0 auto; padding-bottom: 4rem; }
  .head { display: flex; justify-content: space-between; align-items: flex-start;
          gap: 1rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
  h1 { font-size: 1.5rem; font-weight: 800; margin-bottom: 0.2rem; }
  .sub { color: var(--muted); font-size: 0.84rem; }
  .error { color: #e05260; font-size: 0.85rem; margin-bottom: 0.75rem; }
  .empty { color: var(--muted); font-size: 0.85rem; padding: 1rem 0; }

  .streak-card { display: flex; align-items: center; gap: 0.6rem; background: var(--surface);
                 border: 1px solid var(--border); border-left: 3px solid #e0a852;
                 border-radius: 10px; padding: 0.65rem 0.95rem; }
  .streak-card.cold { border-left-color: var(--border); }
  .flame { font-size: 1.5rem; }
  .streak-text { display: flex; flex-direction: column; }
  .streak-text b { font-size: 0.95rem; }
  .streak-text span { font-size: 0.72rem; color: var(--muted); }

  .streak-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.7rem;
                  margin-bottom: 1.5rem; }
  .stat { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
          padding: 0.85rem 1rem; display: flex; flex-direction: column; gap: 0.1rem; }
  .stat b { font-size: 1.35rem; font-weight: 800; font-variant-numeric: tabular-nums; }
  .stat span { font-size: 0.72rem; color: var(--muted); }

  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
           padding: 1.25rem 1.35rem; margin-bottom: 1.5rem; }
  .panel-head { display: flex; justify-content: space-between; align-items: flex-start;
                gap: 1rem; flex-wrap: wrap; margin-bottom: 0.9rem; }
  .panel-head h2 { font-size: 1.05rem; font-weight: 800; margin-bottom: 0.15rem; }
  .panel-sub { font-size: 0.76rem; color: var(--muted); line-height: 1.5; max-width: 52ch; }
  .tally { font-size: 0.85rem; font-weight: 800; color: var(--muted);
           font-variant-numeric: tabular-nums; }

  .progress { height: 5px; background: var(--surface2); border-radius: 999px;
              overflow: hidden; margin-bottom: 0.9rem; }
  .fill { height: 100%; background: var(--accent); border-radius: 999px; transition: width 0.3s; }
  .all-done { font-size: 0.82rem; color: var(--success); margin-bottom: 0.7rem; }
  .claim-note { font-size: 0.8rem; color: var(--success); margin-bottom: 0.7rem; }

  .ch-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .ch { display: flex; justify-content: space-between; align-items: center; gap: 1rem;
        background: var(--surface2); border: 1px solid var(--border); border-radius: 9px;
        padding: 0.85rem 1rem; }
  .ch.done { opacity: 0.72; }
  .ch-main { flex: 1; min-width: 0; }
  .ch-top { display: flex; align-items: center; gap: 0.45rem; flex-wrap: wrap; margin-bottom: 0.2rem; }
  .ch-top b { font-size: 0.9rem; }
  .kind { font-size: 0.63rem; font-weight: 800; text-transform: uppercase;
          letter-spacing: 0.04em; border: 1px solid var(--border); color: var(--muted);
          border-radius: 999px; padding: 0.08rem 0.42rem; }
  .kind.auto { color: var(--success); border-color: var(--success); }
  .kind.pin { color: #e0a852; border-color: #e0a852; }
  .ch-desc { font-size: 0.78rem; color: var(--muted); line-height: 1.5; margin-bottom: 0.25rem; }
  .reward { font-size: 0.73rem; font-weight: 700; color: var(--accent); }
  .ch-action { flex-shrink: 0; }
  .badge-done { font-size: 0.75rem; font-weight: 700; color: var(--success); }
  .locked { font-size: 0.75rem; color: var(--muted); }

  .compose { background: var(--surface2); border: 1px solid var(--border);
             border-radius: 9px; padding: 1rem; margin-bottom: 1rem;
             display: flex; flex-direction: column; gap: 0.7rem; }
  .compose label { display: flex; flex-direction: column; gap: 0.3rem;
                   font-size: 0.78rem; font-weight: 600; }
  .compose select, .compose textarea {
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    border-radius: 7px; padding: 0.55rem 0.7rem; font-family: inherit;
    font-size: 0.85rem; font-weight: 400; }
  .compose textarea { resize: vertical; line-height: 1.55; }
  .compose select:focus, .compose textarea:focus { outline: none; border-color: var(--accent); }
  .emoji-row { display: flex; gap: 0.3rem; flex-wrap: wrap; }
  .emoji { background: var(--surface); border: 1px solid var(--border); border-radius: 7px;
           padding: 0.3rem 0.5rem; font-size: 1rem; cursor: pointer; }
  .emoji.sel { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 15%, var(--surface)); }
  .compose-foot { display: flex; justify-content: space-between; align-items: center; gap: 0.7rem; }

  .tabs { display: flex; gap: 0.4rem; margin-bottom: 0.9rem; }
  .tab { background: var(--surface2); border: 1px solid var(--border); color: var(--muted);
         border-radius: 999px; padding: 0.3rem 0.85rem; font-size: 0.76rem;
         font-weight: 700; cursor: pointer; }
  .tab.on { background: var(--accent); border-color: var(--accent); color: #fff; }

  .kudos-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .kudos { display: flex; gap: 0.7rem; background: var(--surface2);
           border: 1px solid var(--border); border-radius: 9px; padding: 0.8rem 0.95rem; }
  .k-emoji { font-size: 1.25rem; flex-shrink: 0; }
  .k-body { flex: 1; min-width: 0; }
  .k-who { display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap;
           font-size: 0.82rem; margin-bottom: 0.25rem; }
  .mult { font-size: 0.63rem; font-weight: 800; color: #e0a852;
          border: 1px solid #e0a852; border-radius: 999px; padding: 0.05rem 0.35rem; }
  .k-msg { font-size: 0.85rem; line-height: 1.55; margin-bottom: 0.2rem;
           overflow-wrap: anywhere; }
  .muted { color: var(--muted); }
  .tiny { font-size: 0.7rem; }

  .btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 7px; padding: 0.5rem 1rem; font-size: 0.82rem; font-weight: 700;
         cursor: pointer; font-family: inherit; }
  .btn:hover:not(:disabled) { border-color: var(--accent); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }

  .skeleton { border-radius: 12px; background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
              background-size: 200% 100%; animation: shimmer 1.4s infinite; }
  .skeleton.big { height: 420px; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

  @media (max-width: 640px) {
    .streak-stats { grid-template-columns: 1fr; }
    .ch { flex-direction: column; align-items: flex-start; }
  }
</style>
