<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { page } from '$app/stores';
  import { goto, afterNavigate } from '$app/navigation';
  import { navigating } from '$app/stores';
  import { auth, isLoggedIn, isAdmin } from '$lib/stores/auth';
  import { gamification } from '$lib/stores/gamification';
  import LevelBadge from '$lib/components/LevelBadge.svelte';
  import Avatar from '$lib/components/Avatar.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';
  import RewardModal from '$lib/components/RewardModal.svelte';
  import ApprovalPopup from '$lib/components/ApprovalPopup.svelte';
  import Tooltips from '$lib/components/Tooltips.svelte';
  import { pendingRequests, startRequestPolling, stopRequestPolling } from '$lib/stores/test-requests';
  import { countUp } from '$lib/actions/motion';
  import { autoMotion, installRipple, staggerIn } from '$lib/actions/auto-motion';
  import { motion } from '$lib/stores/motion';
  import '../app.css';

  onMount(() => {
    auth.init();
    return installRipple();
  });

  // Level, quests and the track need a signed-in user: load them once auth
  // has one (not alongside auth.init, when there may be no token yet), and
  // again whenever a different account signs in.
  let gamificationFor: string | null = null;
  $: if ($auth.user?.id && $auth.user.id !== gamificationFor) {
    gamificationFor = $auth.user.id;
    gamification.load();
  }

  // Each new page: stagger its repeated items (cards, rows, tiles) in.
  let routeEl: HTMLElement;
  afterNavigate(() => {
    tick().then(() => routeEl && staggerIn(routeEl, 120));
  });

  $: isAuthPage = $page.url.pathname.startsWith('/auth');
  // Admins get test requests as a pop-up on any screen, so poll while one is
  // signed in and stop the moment they are not.
  $: if ($isAdmin) startRequestPolling(); else stopRequestPolling();
  $: if (!$isLoggedIn && !isAuthPage && !$auth.loading) goto('/auth/login');

  type NavItem = { href: string; label: string; icon: string; match: (p: string) => boolean; admin?: boolean };
  const NAV: NavItem[] = [
    { href: '/', label: 'Home', icon: 'home', match: (p) => p === '/' },
    { href: '/my-learning', label: 'My Learning', icon: 'book', match: (p) => p === '/my-learning' },
    { href: '/paths', label: 'Paths', icon: 'route', match: (p) => p === '/paths' },
    { href: '/daily', label: 'Today', icon: 'flame', match: (p) => p === '/daily' },
    { href: '/challenges', label: 'Challenges', icon: 'flag', match: (p) => p === '/challenges' },
    { href: '/tests', label: 'Tests', icon: 'clipboard', match: (p) => p.startsWith('/tests') },
    { href: '/leaderboard', label: 'Leaderboard', icon: 'trophy', match: (p) => p === '/leaderboard' },
    { href: '/admin', label: 'Admin', icon: 'settings', match: (p) => p.startsWith('/admin'), admin: true },
  ];
  $: path = $page.url.pathname;
  $: items = NAV.filter((i) => !i.admin || $isAdmin);

  // The notch: the content panel bulges up under the active tab, and slides
  // to follow it (the reference's signature detail).
  let tabsEl: HTMLElement;
  let canvasEl: HTMLElement;
  let notchX = 0;
  let notchOn = false;
  async function placeNotch() {
    await tick();
    const a = tabsEl?.querySelector<HTMLElement>('a.active');
    if (!a || !canvasEl || !tabsEl.offsetParent) { notchOn = false; return; }
    const r = a.getBoundingClientRect();
    const c = canvasEl.getBoundingClientRect();
    notchX = r.left + r.width / 2 - c.left;
    notchOn = true;
  }
  $: if (tabsEl && canvasEl) { path; items; placeNotch(); }

  let drawerOpen = false;
  let menuOpen = false;
  $: path, (drawerOpen = false), (menuOpen = false);

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') { drawerOpen = false; menuOpen = false; }
  }
  function clickOutside(node: HTMLElement) {
    const handler = (e: MouseEvent) => { if (!node.contains(e.target as Node)) menuOpen = false; };
    document.addEventListener('click', handler, true);
    return { destroy: () => document.removeEventListener('click', handler, true) };
  }
</script>

<svelte:window on:resize={placeNotch} on:keydown={onKey} />

{#if $auth.loading}
  <div class="loading-screen">
    <div class="loader" aria-hidden="true"><span></span><span></span><span></span></div>
    <p class="loading-text">Loading Champ LMS…</p>
  </div>
{:else if $isLoggedIn}
  {#if $navigating}
    <div class="route-progress" role="progressbar" aria-label="Loading page"><span></span></div>
  {/if}
  <div class="shell">
    <header class="topbar">
      <button class="hamburger" on:click={() => (drawerOpen = true)} aria-label="Open navigation">
        <Icon name="menu" size={22} />
      </button>

      <a href="/" class="logo" aria-label="Champ LMS home">Champ<span>LMS</span></a>

      <nav class="tabs" bind:this={tabsEl} on:transitionend={placeNotch} aria-label="Main">
        {#each items as item}
          {@const active = item.match(path)}
          <a href={item.href} class:active aria-current={active ? 'page' : undefined} data-tip={item.label}>
            <span class="nav-ico" class:icon-loop={active}><Icon name={item.icon} size={21} /></span>
            <span class="tab-label">{item.label}</span>
            {#if item.admin && $pendingRequests.length}
              <span class="nav-count" title="Test requests waiting">{$pendingRequests.length}</span>
            {/if}
          </a>
        {/each}
      </nav>

      <div class="right">
        <!-- Staff carry no score: they are kept off every board, so showing them
             points and a streak would be a number that leads nowhere. -->
        {#if !$isAdmin}
          <div class="stats">
            <span class="stat" title="Points">
              <span class="stat-ico gold"><Icon name="star" size={15} /></span>
              <b use:countUp={$auth.user?.points ?? 0}></b>
            </span>
            <span class="stat" title="Day streak">
              <span class="stat-ico flame"><Icon name="flame" size={15} /></span>
              <b use:countUp={$auth.user?.streak_days ?? 0}></b>
            </span>
          </div>
        {/if}
        {#if $gamification.levelInfo}
          <a href="/my-learning" class="level-link" title="Level {$gamification.levelInfo.level}">
            <LevelBadge
              level={$gamification.levelInfo.level}
              xp={$gamification.levelInfo.xp - ($gamification.levelInfo.current_level_xp ?? 0)}
              xpToNextLevel={($gamification.levelInfo.next_level_xp ?? $gamification.levelInfo.xp + $gamification.levelInfo.xp_to_next_level) - ($gamification.levelInfo.current_level_xp ?? 0)}
              compact
              size={38}
            />
          </a>
        {/if}
        <ThemeToggle />
        <div class="profile" use:clickOutside>
          <button
            class="profile-btn"
            class:open={menuOpen}
            on:click={() => (menuOpen = !menuOpen)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <Avatar src={$auth.user?.avatar_url} name={$auth.user?.full_name} size={38} />
            <span class="profile-name">
              <b>{$auth.user?.full_name ?? 'Profile'}</b>
              <em>{$auth.user?.employee_code ?? $auth.user?.email ?? ''}</em>
            </span>
            <svg class="chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
          </button>
          {#if menuOpen}
            <div class="menu" role="menu">
              <div class="menu-head">
                <Avatar src={$auth.user?.avatar_url} name={$auth.user?.full_name} size={44} />
                <div>
                  <b>{$auth.user?.full_name ?? 'Profile'}</b>
                  <span>{$auth.user?.email ?? ''}</span>
                </div>
              </div>
              <a href="/settings" role="menuitem"><Icon name="settings" size={18} /> Settings</a>
              <button
                role="menuitemcheckbox"
                aria-checked={$motion === 'full'}
                class="motion-row"
                on:click={() => motion.set($motion === 'full' ? 'reduced' : 'full')}
              >
                <Icon name="zap" size={18} /> Animations
                <span class="switch" class:on={$motion === 'full'} aria-hidden="true"><span></span></span>
              </button>
              <button role="menuitem" class="danger" on:click={() => auth.logout()}>
                <Icon name="logout" size={18} /> Sign out
              </button>
            </div>
          {/if}
        </div>
      </div>
    </header>

    <div class="canvas" bind:this={canvasEl}>
      <svg
        class="notch"
        class:on={notchOn}
        style="--x:{notchX}px"
        width="150" height="18" viewBox="0 0 150 18" aria-hidden="true"
      ><path d="M0 18C34 18 46 0 75 0s41 18 75 18z" /></svg>

      {#if $auth.user?.must_change_password && !$page.url.pathname.startsWith('/auth')}
        <!-- Signed in with an admin-issued password: nudge, don't lock them out,
             so they can still reach their learning first. -->
        <div class="pw-banner">
          <Icon name="info" size={18} />
          <span>You're still using the password an administrator gave you.</span>
          <a href="/auth/change-password">Set your own password</a>
        </div>
      {/if}

      <main class="main" use:autoMotion>
        {#key path}
          <div class="route-view" bind:this={routeEl}><slot /></div>
        {/key}
      </main>
    </div>
  </div>

  {#if drawerOpen}
    <div class="scrim" on:click={() => (drawerOpen = false)} aria-hidden="true"></div>
    <aside class="drawer" aria-label="Navigation">
      <div class="drawer-head">
        <span class="logo">Champ<span>LMS</span></span>
        <button class="drawer-close" on:click={() => (drawerOpen = false)} aria-label="Close navigation">
          <Icon name="close" size={20} />
        </button>
      </div>
      {#each items as item, i}
        <a href={item.href} class:active={item.match(path)} style="--i:{i}">
          <span class="nav-ico" class:icon-loop={item.match(path)}><Icon name={item.icon} size={20} /></span>
          {item.label}
          {#if item.admin && $pendingRequests.length}
            <span class="nav-count">{$pendingRequests.length}</span>
          {/if}
        </a>
      {/each}
      <a href="/settings" class:active={path === '/settings'} style="--i:{items.length}">
        <Icon name="settings" size={20} /> Settings
      </a>
    </aside>
  {/if}

  <RewardModal />
  {#if $isAdmin}<ApprovalPopup />{/if}
{:else if isAuthPage}
  <slot />
{/if}

<Tooltips />

<style>
  /* ---------- loading ---------- */
  .loading-screen {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    min-height: 100vh; gap: 1.1rem; background: var(--bg);
  }
  .loader { display: flex; gap: 8px; }
  .loader span {
    width: 14px; height: 14px; border-radius: 50%;
    animation: bob 900ms var(--ease-in-out) infinite;
  }
  .loader span:nth-child(1) { background: var(--tile-sky); }
  .loader span:nth-child(2) { background: var(--tile-mint); animation-delay: 120ms; }
  .loader span:nth-child(3) { background: var(--tile-lilac); animation-delay: 240ms; }
  @keyframes bob {
    0%, 100% { transform: translateY(0); }
    50% { transform: translateY(-10px); }
  }
  .loading-text { color: var(--muted); font-size: 0.9rem; font-weight: 500; }

  /* ---------- shell ---------- */
  .shell { min-height: 100vh; background: var(--frame); display: flex; flex-direction: column; }

  /* Part of the frame, as in the reference: it scrolls away on desktop (and
     only goes sticky on small screens, where there is no notch). */
  .topbar {
    position: relative; z-index: 100;
    display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 1.5rem;
    height: 76px; padding: 0 1.75rem;
    background: var(--frame); color: var(--on-frame);
  }
  .hamburger { display: none; }

  .logo {
    font-size: 1.45rem; font-weight: 900; letter-spacing: -0.04em; color: var(--on-frame);
    display: inline-flex; align-items: baseline; gap: 0.18rem;
  }
  .logo span {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em;
    /* The frame is black in both themes, so the mark keeps one red; dark
       mode's lighter --brand left white text under 3.2:1. */
    color: #fff; background: #e50914;
    padding: 0.12rem 0.38rem; border-radius: 6px; transform: translateY(-0.35rem);
  }

  .tabs { display: flex; justify-content: center; align-items: center; gap: 0.35rem; }
  .tabs a {
    position: relative;
    display: inline-flex; align-items: center;
    height: 44px; padding: 0 0.7rem; border-radius: 999px;
    color: var(--on-frame-muted); font-size: 0.92rem; font-weight: 500;
  }
  .tabs a:hover { color: var(--on-frame); background: rgba(255, 255, 255, 0.07); }
  .tabs a.active { color: var(--on-frame); padding: 0 0.95rem 0 0.8rem; }
  /* Labels are hidden on inactive tabs and slide open on the active one. */
  .tab-label {
    display: inline-block; overflow: hidden; white-space: nowrap;
    max-width: 0; opacity: 0; margin-left: 0;
    transition: max-width var(--dur-3) var(--ease-out), opacity var(--dur-2) var(--ease-out), margin var(--dur-3) var(--ease-out);
  }
  .tabs a.active .tab-label { max-width: 140px; opacity: 1; margin-left: 0.55rem; }
  .tabs a :global(.icon) { transition: transform var(--dur-2) var(--ease-out); }
  .tabs a:hover :global(.icon) { transform: translateY(-2px); }
  /* The icon hops when its tab becomes active. */
  .tabs a.active :global(.icon) { animation: hop 560ms var(--ease-out); }
  @keyframes hop {
    0% { transform: translateY(0) scale(1); }
    35% { transform: translateY(-5px) scale(1.12); }
    65% { transform: translateY(1px) scale(0.96); }
    100% { transform: none; }
  }
  /* Live icons (app.css): the active tab's icon keeps moving, others play
     while hovered. A wrapper so it composes with the hop above. */
  .nav-ico { display: inline-flex; }
  /* Tooltip for the icon-only tabs: same bubble + arrow as Tooltips.svelte,
     kept light in both themes because it sits on the black bar. */
  .tabs a:not(.active)::after, .tabs a:not(.active)::before {
    position: absolute; left: 50%; z-index: 130;
    opacity: 0; pointer-events: none;
    transition: opacity var(--dur-2) var(--ease-out), translate var(--dur-2) var(--ease-out);
  }
  .tabs a:not(.active)::after {
    content: attr(data-tip);
    top: calc(100% + 10px); translate: -50% -4px;
    padding: 0.5rem 0.75rem; border-radius: 11px;
    background: var(--on-frame); color: var(--frame);
    box-shadow: 0 10px 28px -10px rgba(0, 0, 0, 0.45), 0 2px 6px rgba(0, 0, 0, 0.12);
    font-size: 0.78rem; font-weight: 600; line-height: 1.4; white-space: nowrap;
  }
  .tabs a:not(.active)::before {
    content: ''; top: calc(100% + 5px); width: 10px; height: 10px; margin-left: -5px;
    background: var(--on-frame); border-radius: 3px 0 0 0;
    translate: 0 -4px; rotate: 45deg;
  }
  .tabs a:not(.active):hover::after, .tabs a:not(.active):focus-visible::after { opacity: 1; translate: -50% 0; }
  .tabs a:not(.active):hover::before, .tabs a:not(.active):focus-visible::before { opacity: 1; translate: 0 0; }

  .nav-count {
    min-width: 18px; height: 18px; padding: 0 5px; margin-left: 0.35rem;
    border-radius: 999px; background: var(--brand); color: var(--on-accent);
    font-size: 0.68rem; font-weight: 700; line-height: 18px; text-align: center;
    animation: pop 420ms var(--ease-out);
  }
  .tabs .nav-count { position: absolute; top: 4px; right: 0; margin: 0; }
  .tabs a.active .nav-count { position: static; margin-left: 0.4rem; }

  .right { display: flex; align-items: center; gap: 0.75rem; justify-self: end; }
  .stats { display: flex; gap: 0.4rem; }
  .stat {
    display: inline-flex; align-items: center; gap: 0.4rem;
    height: 38px; padding: 0 0.8rem 0 0.45rem; border-radius: 999px;
    background: rgba(255, 255, 255, 0.08); font-size: 0.88rem;
  }
  .stat b { font-weight: 700; font-variant-numeric: tabular-nums; min-width: 1ch; }
  .stat-ico { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; color: #121214; }
  .stat-ico.gold { background: #fbe39a; }
  .stat-ico.flame { background: #ffc9a8; }
  .stat:hover .stat-ico { animation: pop 420ms var(--ease-out); }

  /* LevelBadge reads --text/--surface2; on the black bar they need flipping. */
  .level-link { display: flex; --text: var(--on-frame); --surface2: rgba(255, 255, 255, 0.14); }
  .level-link:hover { transform: rotate(-8deg) scale(1.05); }

  .profile { position: relative; }
  .profile-btn {
    display: flex; align-items: center; gap: 0.65rem;
    padding: 0.25rem 0.7rem 0.25rem 0.25rem; border-radius: 999px;
    color: var(--on-frame);
  }
  .profile-btn:hover, .profile-btn.open { background: rgba(255, 255, 255, 0.08); }
  .profile-name { display: flex; flex-direction: column; line-height: 1.2; text-align: left; max-width: 150px; }
  .profile-name b { font-size: 0.88rem; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .profile-name em { font-style: normal; font-size: 0.72rem; color: var(--on-frame-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chev { color: var(--on-frame-muted); transition: transform var(--dur-3) var(--ease-out); }
  .profile-btn.open .chev { transform: rotate(180deg); }

  .menu {
    position: absolute; right: 0; top: calc(100% + 10px); z-index: 120;
    width: 250px; padding: 0.5rem;
    background: var(--surface); color: var(--text);
    border: 1px solid var(--border); border-radius: 20px; box-shadow: var(--shadow-lg);
    transform-origin: top right;
    animation: menu-in 260ms var(--ease-out);
  }
  @keyframes menu-in {
    from { opacity: 0; transform: translateY(-6px) scale(0.96); }
    to { opacity: 1; transform: none; }
  }
  .menu-head { display: flex; gap: 0.7rem; align-items: center; padding: 0.6rem 0.6rem 0.8rem; border-bottom: 1px solid var(--border); margin-bottom: 0.35rem; }
  .menu-head div { display: flex; flex-direction: column; min-width: 0; }
  .menu-head b { font-size: 0.92rem; }
  .menu-head span { font-size: 0.76rem; color: var(--muted); overflow: hidden; text-overflow: ellipsis; }
  .menu a, .menu button {
    display: flex; align-items: center; gap: 0.65rem; width: 100%;
    padding: 0.65rem 0.7rem; border-radius: 12px; font-size: 0.9rem; font-weight: 500; text-align: left;
  }
  .menu a:hover, .menu button:hover { background: var(--surface2); }
  .menu a:hover :global(.icon), .menu button:hover :global(.icon) { transform: translateX(2px); transition: transform var(--dur-2) var(--ease-out); }
  .menu .danger { color: var(--danger); }
  .motion-row .switch { margin-left: auto; }
  .switch {
    position: relative; width: 38px; height: 22px; border-radius: 99px;
    background: var(--surface3); transition: background-color var(--dur-2) var(--ease-out);
  }
  .switch span {
    position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%;
    background: var(--surface); box-shadow: var(--shadow-sm);
    transition: transform 360ms var(--ease-out), width var(--dur-2) var(--ease-out);
  }
  .switch.on { background: var(--path); }
  .switch.on span { transform: translateX(16px); }
  .motion-row:active .switch span { width: 20px; }
  .motion-row:active .switch.on span { transform: translateX(12px); }

  /* Thin bar across the very top while the next page loads. */
  .route-progress {
    position: fixed; top: 0; left: 0; right: 0; z-index: 300; height: 3px; overflow: hidden;
    animation: fade 200ms var(--ease-out) 120ms backwards;
  }
  .route-progress span {
    position: absolute; top: 0; bottom: 0; left: 0; width: 40%;
    background: linear-gradient(90deg, transparent, var(--brand), var(--tile-lilac), transparent);
    animation: route-load 1.1s var(--ease-in-out) infinite;
  }
  @keyframes route-load {
    from { transform: translateX(-100%); }
    to { transform: translateX(260%); }
  }

  /* ---------- canvas ---------- */
  .canvas {
    position: relative; flex: 1;
    margin: 0 10px; border-radius: 30px 30px 0 0;
    background: var(--bg);
  }
  .notch {
    position: absolute; top: -17px; left: 0; z-index: 101;
    fill: var(--bg);
    transform: translateX(calc(var(--x) - 75px));
    transition: transform 520ms var(--ease-out), opacity var(--dur-2) var(--ease-out);
    opacity: 0; pointer-events: none;
  }
  .notch.on { opacity: 1; }

  .pw-banner {
    display: flex; align-items: center; justify-content: center; gap: 0.6rem; flex-wrap: wrap;
    margin: 1rem 1.75rem 0; padding: 0.75rem 1rem; border-radius: 16px;
    background: var(--tile-butter); color: var(--tile-ink); font-size: 0.88rem;
    animation: rise var(--dur-3) var(--ease-out) backwards;
  }
  .pw-banner a { font-weight: 700; text-decoration: underline; text-underline-offset: 3px; }

  .main { padding: 1.5rem 1.75rem 2.5rem; max-width: 1440px; margin: 0 auto; }
  .route-view { animation: page-in 520ms var(--ease-out) backwards; }
  @keyframes page-in {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: none; }
  }

  /* ---------- drawer (small screens) ---------- */
  .scrim {
    position: fixed; inset: 0; z-index: 150; background: var(--scrim);
    animation: fade var(--dur-2) var(--ease-out);
  }
  .drawer {
    position: fixed; z-index: 160; top: 0; left: 0; bottom: 0;
    width: min(300px, 86vw); padding: 1rem;
    display: flex; flex-direction: column; gap: 0.25rem;
    background: var(--frame); color: var(--on-frame);
    border-radius: 0 28px 28px 0;
    animation: drawer-in 380ms var(--ease-out);
  }
  @keyframes drawer-in { from { transform: translateX(-100%); } to { transform: none; } }
  .drawer-head { display: flex; align-items: center; justify-content: space-between; padding: 0.5rem 0.5rem 1rem; }
  .drawer-close { width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; background: rgba(255, 255, 255, 0.08); }
  .drawer a {
    display: flex; align-items: center; gap: 0.8rem;
    min-height: 48px; padding: 0 0.9rem; border-radius: 14px;
    color: var(--on-frame-muted); font-weight: 500;
    animation: rise 420ms var(--ease-out) backwards; animation-delay: calc(var(--i) * 35ms + 80ms);
  }
  .drawer a:hover { color: var(--on-frame); background: rgba(255, 255, 255, 0.07); }
  .drawer a.active { color: var(--frame); background: var(--on-frame); }
  .drawer .nav-count { margin-left: auto; }

  /* ---------- responsive ---------- */
  @media (max-width: 1180px) {
    .profile-name { display: none; }
    .stats { display: none; }
  }
  @media (max-width: 900px) {
    .topbar { position: sticky; top: 0; grid-template-columns: auto 1fr auto; height: 64px; padding: 0 0.9rem; gap: 0.6rem; }
    .hamburger {
      display: grid; place-items: center; width: 44px; height: 44px; border-radius: 50%;
      background: rgba(255, 255, 255, 0.08); color: var(--on-frame);
    }
    .tabs { display: none; }
    .logo { justify-self: start; }
    .level-link { display: none; }
    .chev { display: none; }
    .canvas { margin: 0; border-radius: 22px 22px 0 0; }
    .main { padding: 1rem 1rem 2rem; }
    .pw-banner { margin: 0.9rem 1rem 0; }
  }
</style>
