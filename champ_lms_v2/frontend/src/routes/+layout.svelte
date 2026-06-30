<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { auth, isLoggedIn, isAdmin } from '$lib/stores/auth';
  import '../app.css';

  onMount(() => auth.init());

  $: isAuthPage = $page.url.pathname.startsWith('/auth');
  $: if (!$isLoggedIn && !isAuthPage && !$auth.loading) goto('/auth/login');
</script>

{#if $auth.loading}
  <div class="loading-screen">
    <div class="spinner"></div>
  </div>
{:else if $isLoggedIn}
  <nav class="nav">
    <a href="/" class="logo">CHAMP<span>LMS</span></a>
    <div class="nav-links">
      <a href="/" class:active={$page.url.pathname === '/'}>Home</a>
      <a href="/my-learning" class:active={$page.url.pathname === '/my-learning'}>My Learning</a>
      <a href="/leaderboard" class:active={$page.url.pathname === '/leaderboard'}>Leaderboard</a>
      {#if $isAdmin}
        <a href="/admin" class:active={$page.url.pathname.startsWith('/admin')}>Admin</a>
      {/if}
    </div>
    <div class="nav-user">
      <span class="points">{$auth.user?.points ?? 0} pts</span>
      <span class="streak">🔥 {$auth.user?.streak_days ?? 0}</span>
      <button class="btn-ghost" on:click={() => auth.logout()}>Sign Out</button>
    </div>
  </nav>
  <main class="main">
    <slot />
  </main>
{:else if isAuthPage}
  <slot />
{/if}

<style>
  .loading-screen {
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh;
  }
  .spinner {
    width: 40px; height: 40px;
    border: 3px solid var(--surface2);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .nav {
    display: flex; align-items: center; gap: 2rem;
    padding: 0.9rem 2rem;
    background: linear-gradient(to bottom, rgba(0,0,0,0.8), transparent);
    position: sticky; top: 0; z-index: 100;
    backdrop-filter: blur(8px);
  }
  .logo {
    font-size: 1.3rem; font-weight: 900; letter-spacing: 0.05em;
    color: var(--accent);
  }
  .logo span { color: var(--text); }
  .nav-links { display: flex; gap: 1.5rem; flex: 1; }
  .nav-links a { font-size: 0.9rem; color: var(--muted); transition: color 0.15s; }
  .nav-links a:hover, .nav-links a.active { color: var(--text); }
  .nav-user { display: flex; align-items: center; gap: 1rem; margin-left: auto; }
  .points, .streak { font-size: 0.85rem; font-weight: 700; color: var(--gold); }
  .main { padding: 1.5rem 2rem 4rem; max-width: 1400px; margin: 0 auto; }
</style>
