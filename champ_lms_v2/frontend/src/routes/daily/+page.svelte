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
  import Icon from '$lib/components/Icon.svelte';
  import Select from '$lib/components/Select.svelte';
  import { countUp } from '$lib/actions/motion';

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
      <p class="eyebrow ui-rise">{new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
      <h1 class="ui-rise" style="--i:1">
        Today
        <span class="title-mark" aria-hidden="true"><Icon name="flame" size={24} /></span>
      </h1>
      <p class="sub ui-rise" style="--i:2">Your daily challenges, streak, and team recognition.</p>
    </div>
    {#if streak}
      <div class="streak-card ui-rise" style="--i:3" class:cold={!streak.active_today}>
        <span class="flame"><Icon name="flame" size={24} /></span>
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

  {#if error}<p class="error ui-rise"><Icon name="alert" size={15} /> {error}</p>{/if}

  {#if loading}
    <div class="streak-stats">{#each Array(3) as _}<div class="ui-skeleton" style="height:104px;border-radius:24px"></div>{/each}</div>
    <div class="cols">
      <div class="ui-skeleton" style="height:420px;border-radius:30px"></div>
      <div class="ui-skeleton" style="height:420px;border-radius:30px"></div>
    </div>
  {:else}
    <!-- Streak detail ------------------------------------------------------ -->
    {#if streak}
      <div class="streak-stats">
        <div class="stat peach ui-rise" style="--i:3">
          <span class="s-ico"><Icon name="flame" size={17} /></span>
          <b use:countUp={streak.streak_days}></b><span>current streak</span>
        </div>
        <div class="stat butter ui-rise" style="--i:4">
          <span class="s-ico"><Icon name="trophy" size={17} /></span>
          <b use:countUp={streak.longest_streak}></b><span>personal best</span>
        </div>
        <div class="stat sky ui-rise" style="--i:5" title="A freeze covers one missed day so your streak survives">
          <span class="s-ico"><Icon name="shield" size={17} /></span>
          <b use:countUp={streak.streak_freezes}></b><span>freezes left</span>
        </div>
      </div>
    {/if}

    <div class="cols">
      <!-- Daily challenges --------------------------------------------------- -->
      <section class="panel ui-rise" style="--i:5">
        <div class="panel-head">
          <div>
            <h2><Icon name="target" size={21} /> Daily challenges</h2>
            <p class="panel-sub">
              A fresh set every day, the same for everyone. Verified challenges
              unlock once you've actually done the work.
            </p>
          </div>
          {#if challenges}
            <span class="tally" class:full={allDone}>{challenges.completed} / {challenges.total}</span>
          {/if}
        </div>

        {#if challenges}
          <div class="progress"><div class="fill" style="width:{progressPct}%"></div></div>
          {#if allDone}
            <p class="all-done"><Icon name="sparkles" size={16} /> All done for today — come back tomorrow for a new set.</p>
          {/if}
          {#if claimNote}<p class="claim-note"><Icon name="zap" size={15} /> {claimNote}</p>{/if}

          {#if challenges.challenges.length === 0}
            <p class="empty"><Icon name="info" size={16} /> No challenges are set up yet. An admin can add some.</p>
          {:else}
            <div class="ch-list">
              {#each challenges.challenges as ch, n (ch.id)}
                <div class="ch ui-rise" style="--i:{6 + Math.min(n, 6)}" class:done={ch.completed_today}>
                  <span class="ch-ico" aria-hidden="true">
                    <Icon name={ch.completed_today ? 'check' : ch.kind === 'watch_episode' ? 'play' : ch.kind === 'pass_quiz' || ch.kind === 'pass_test' ? 'clipboard' : 'flag'} size={17} />
                  </span>
                  <div class="ch-main">
                    <div class="ch-top">
                      <b>{ch.title}</b>
                      <span class="kind" class:auto={ch.auto_verified}>
                        {KIND_LABELS[ch.kind] ?? ch.kind}
                      </span>
                      {#if ch.always_on}<span class="kind pin">Pinned</span>{/if}
                    </div>
                    {#if ch.description}<p class="ch-desc">{ch.description}</p>{/if}
                    <span class="reward"><Icon name="zap" size={13} /> +{ch.reward_xp} XP</span>
                  </div>

                  <div class="ch-action">
                    {#if ch.completed_today}
                      <span class="badge-done">
                        <Icon name="check" size={14} /> Done{ch.verified ? '' : ' (self-reported)'}
                      </span>
                    {:else if ch.claimable}
                      <button class="btn-primary sm" disabled={claiming[ch.id]}
                              on:click={() => claim(ch.id)}>
                        {claiming[ch.id] ? 'Claiming…' : ch.auto_verified ? 'Collect' : 'Mark done'}
                      </button>
                    {:else}
                      <span class="locked" title="Finish the activity and this unlocks">
                        <Icon name="lock" size={13} /> Not yet
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
      <section class="panel ui-rise" style="--i:6">
        <div class="panel-head">
          <div>
            <h2><Icon name="heart" size={21} /> Kudos</h2>
            <p class="panel-sub">Recognise someone who helped you. They earn XP for it.</p>
          </div>
          <button class="btn-primary sm" class:ghost={showCompose} on:click={() => (showCompose = !showCompose)}>
            {#if showCompose}<Icon name="close" size={15} /> Cancel{:else}<Icon name="gift" size={15} /> Give kudos{/if}
          </button>
        </div>

        {#if sentNote}<p class="claim-note"><Icon name="checkCircle" size={15} /> {sentNote}</p>{/if}

        {#if showCompose}
          <div class="compose">
            {#if sendError}<p class="error">{sendError}</p>{/if}
            <!-- svelte-ignore a11y-label-has-associated-control -->
            <label>
              Who?
              <Select
                bind:value={toUserId}
                tone="raised"
                placeholder="Choose a colleague…"
                options={recipients.map(r => ({ value: r.id, label: r.full_name, hint: r.employee_code || undefined }))}
              />
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
              <button class="btn-primary sm" disabled={!toUserId || !message.trim() || sending}
                      on:click={send}>
                {#if sending}Sending…{:else}<Icon name="send" size={15} /> Send kudos{/if}
              </button>
            </div>
          </div>
        {/if}

        <div class="tabs" role="tablist" aria-label="Filter kudos">
          <button class="tab" role="tab" aria-selected={kudosFilter === 'all'} class:on={kudosFilter === 'all'}
                  on:click={() => switchFilter('all')}>Everyone</button>
          <button class="tab" role="tab" aria-selected={kudosFilter === 'mine'} class:on={kudosFilter === 'mine'}
                  on:click={() => switchFilter('mine')}>For me</button>
        </div>

        {#if kudos.length === 0}
          <p class="empty">
            <Icon name="message" size={16} />
            {kudosFilter === 'mine'
              ? 'No kudos for you yet — it’ll show up here.'
              : 'No kudos yet. Be the first to recognise someone.'}
          </p>
        {:else}
          <div class="kudos-list">
            {#each kudos as k, n (k.id)}
              <div class="kudos ui-rise" style="--i:{Math.min(n, 8)}">
                <span class="k-emoji">{k.emoji}</span>
                <div class="k-body">
                  <div class="k-who">
                    <Avatar src={k.from_avatar_url} name={k.from_name} size={24} />
                    <b>{k.from_name ?? 'Someone'}</b>
                    <span class="muted arrow"><Icon name="arrowRight" size={13} /></span>
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
    </div>
  {/if}
</div>

<style>
  .head { display: flex; justify-content: space-between; align-items: flex-end;
          gap: 1.5rem; flex-wrap: wrap; margin: 0 0 1.25rem; }
  .eyebrow { color: var(--muted); font-size: 0.95rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; display: flex; align-items: center; gap: 0.6rem; }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-peach); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .sub { color: var(--muted); font-size: 0.95rem; margin-top: 0.6rem; }
  .error { display: flex; align-items: center; gap: 0.4rem; color: var(--danger); font-size: 0.86rem; margin-bottom: 0.75rem; }
  .empty { display: flex; align-items: center; gap: 0.5rem; color: var(--muted); font-size: 0.88rem; padding: 1.2rem 1rem; border-radius: 18px; background: var(--surface2); }

  .peach { background: var(--tile-peach); } .butter { background: var(--tile-butter); } .sky { background: var(--tile-sky); }

  .streak-card { display: flex; align-items: center; gap: 0.75rem; background: var(--tile-peach); color: var(--tile-ink);
                 border-radius: 999px; padding: 0.5rem 1.3rem 0.5rem 0.5rem;
                 transition: translate var(--dur-3) var(--ease-out); }
  .streak-card:hover { translate: 0 -2px; }
  .streak-card.cold { background: var(--surface2); color: var(--text); }
  .flame { width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); }
  .streak-card:not(.cold) .flame :global(.icon) { animation: flicker 2.4s var(--ease-in-out) infinite; color: var(--brand); }
  .streak-card.cold .flame { color: var(--muted); }
  @keyframes flicker { 0%, 100% { scale: 1; } 45% { scale: 1.14; } 60% { scale: 0.95; } }
  .streak-text { display: flex; flex-direction: column; }
  .streak-text b { font-size: 1.05rem; }
  .streak-text span { font-size: 0.76rem; opacity: 0.72; }

  .streak-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.9rem; margin-bottom: 1.6rem; }
  .stat { border-radius: 24px; color: var(--tile-ink); padding: 1rem 1.15rem; display: flex; flex-direction: column; gap: 0.1rem;
          transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out); }
  .stat:hover { translate: 0 -3px; box-shadow: var(--shadow); }
  .s-ico { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); margin-bottom: 0.45rem; transition: rotate var(--dur-3) var(--ease-out); }
  .stat:hover .s-ico { rotate: -14deg; }
  .stat b { font-size: 2rem; font-weight: 700; letter-spacing: -0.03em; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .stat:hover b { animation: pop 420ms var(--ease-out); }
  .stat > span:last-child { font-size: 0.8rem; opacity: 0.72; }

  .cols { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr); gap: 1.4rem; align-items: start; }

  .panel { background: var(--surface); border-radius: 30px; box-shadow: var(--shadow-sm); padding: 1.4rem 1.45rem; }
  .panel-head { display: flex; justify-content: space-between; align-items: flex-start;
                gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .panel-head h2 { display: flex; align-items: center; gap: 0.45rem; font-size: 1.3rem; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 0.3rem; }
  .panel-sub { font-size: 0.82rem; color: var(--muted); line-height: 1.5; max-width: 52ch; }
  .tally { font-size: 0.9rem; font-weight: 700; padding: 0.35rem 0.8rem; border-radius: 99px; background: var(--surface2);
           font-variant-numeric: tabular-nums; }
  .tally.full { background: var(--tile-mint); color: var(--tile-ink); animation: pop 500ms var(--ease-out); }

  .progress { height: 8px; background: var(--surface2); border-radius: 999px; overflow: hidden; margin-bottom: 1rem; }
  .fill { height: 100%; background: var(--brand); border-radius: 999px; transition: width var(--dur-3) var(--ease-out);
          transform-origin: left; animation: grow 1s var(--ease-out) 300ms backwards; }
  @keyframes grow { from { transform: scaleX(0); } }
  .all-done, .claim-note { display: flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.8rem;
                           padding: 0.55rem 0.85rem; border-radius: 16px; background: var(--tile-mint); color: var(--tile-ink); animation: rise 320ms var(--ease-out); }

  .ch-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .ch { display: flex; align-items: center; gap: 0.9rem;
        background: var(--surface2); border-radius: 22px; padding: 0.85rem 1rem 0.85rem 0.85rem;
        transition: translate var(--dur-3) var(--ease-out), background-color var(--dur-2); }
  .ch:hover { translate: 3px 0; }
  .ch.done { opacity: 0.75; }
  .ch-ico { flex: none; width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-lilac); color: var(--tile-ink); transition: rotate var(--dur-3) var(--ease-out); }
  .ch:hover .ch-ico { rotate: -12deg; }
  .ch.done .ch-ico { background: var(--tile-mint); }
  .ch-main { flex: 1; min-width: 0; }
  .ch-top { display: flex; align-items: center; gap: 0.45rem; flex-wrap: wrap; margin-bottom: 0.2rem; }
  .ch-top b { font-size: 0.95rem; font-weight: 600; }
  .kind { font-size: 0.66rem; font-weight: 700; text-transform: uppercase;
          letter-spacing: 0.05em; color: var(--muted); background: var(--surface);
          border-radius: 999px; padding: 0.12rem 0.5rem; }
  .kind.auto { color: var(--tile-ink); background: var(--tile-mint); }
  .kind.pin { color: var(--tile-ink); background: var(--tile-butter); }
  .ch-desc { font-size: 0.8rem; color: var(--muted); line-height: 1.5; margin-bottom: 0.3rem; }
  .reward { display: inline-flex; align-items: center; gap: 0.2rem; font-size: 0.76rem; font-weight: 700; color: var(--text-secondary); }
  .ch-action { flex-shrink: 0; }
  .badge-done { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.78rem; font-weight: 700; color: var(--success); }
  .locked { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.78rem; color: var(--muted); padding: 0.3rem 0.7rem; border-radius: 99px; background: var(--surface); }
  .sm { padding: 0.5rem 1rem; font-size: 0.84rem; }
  .sm:disabled { opacity: 0.5; cursor: not-allowed; }
  .sm.ghost { background: var(--surface2); color: var(--text); }

  .compose { background: var(--surface2); border-radius: 22px; padding: 1rem 1.1rem; margin-bottom: 1rem;
             display: flex; flex-direction: column; gap: 0.8rem; animation: rise 300ms var(--ease-out); }
  .compose label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.8rem; font-weight: 600; }
  .compose textarea {
    background: var(--surface); border: 1.5px solid transparent; color: var(--text);
    border-radius: 14px; padding: 0.6rem 0.8rem; font-family: inherit;
    font-size: 0.88rem; font-weight: 400; transition: border-color var(--dur-2); }
  .compose textarea { resize: vertical; line-height: 1.55; }
  .compose textarea:focus { outline: none; border-color: var(--accent); }
  .emoji-row { display: flex; gap: 0.35rem; flex-wrap: wrap; }
  .emoji { width: 42px; height: 42px; background: var(--surface); border-radius: 50%; font-size: 1.1rem; cursor: pointer;
           box-shadow: inset 0 0 0 1.5px transparent; transition: scale var(--dur-2) var(--ease-out), box-shadow var(--dur-2); }
  .emoji:hover { scale: 1.12; }
  .emoji.sel { box-shadow: inset 0 0 0 2px var(--accent); animation: pop 300ms var(--ease-out); }
  .compose-foot { display: flex; justify-content: space-between; align-items: center; gap: 0.7rem; }

  .tabs { display: inline-flex; gap: 0.25rem; padding: 0.3rem; border-radius: 999px; background: var(--surface2); margin-bottom: 1rem; }
  .tab { height: 34px; padding: 0 1rem; border-radius: 999px; font-size: 0.82rem; font-weight: 600; color: var(--muted); background: transparent; cursor: pointer;
         transition: background-color var(--dur-2), color var(--dur-2); }
  .tab:hover { color: var(--text); }
  .tab.on { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); }

  .kudos-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .kudos { display: flex; gap: 0.8rem; background: var(--surface2); border-radius: 22px; padding: 0.85rem 1rem;
           transition: translate var(--dur-3) var(--ease-out); }
  .kudos:hover { translate: 0 -2px; }
  .k-emoji { flex-shrink: 0; width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; background: var(--surface); font-size: 1.2rem; transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out); }
  .kudos:hover .k-emoji { rotate: -12deg; scale: 1.1; }
  .k-body { flex: 1; min-width: 0; }
  .k-who { display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap; font-size: 0.84rem; margin-bottom: 0.3rem; }
  .arrow { display: inline-grid; }
  .mult { font-size: 0.66rem; font-weight: 700; color: var(--tile-ink); background: var(--tile-butter); border-radius: 999px; padding: 0.08rem 0.45rem; }
  .k-msg { font-size: 0.9rem; line-height: 1.55; margin-bottom: 0.25rem; overflow-wrap: anywhere; }
  .muted { color: var(--muted); }
  .tiny { font-size: 0.72rem; }

  @media (max-width: 1000px) {
    .cols { grid-template-columns: 1fr; }
  }
  @media (max-width: 640px) {
    .streak-stats { grid-template-columns: 1fr; }
    .ch { flex-wrap: wrap; }
    .ch-action { width: 100%; padding-left: 3.1rem; }
  }
</style>
