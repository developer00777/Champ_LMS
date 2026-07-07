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
    <p class="loading-text">Loading Champ LMS...</p>
  </div>
{:else if $isLoggedIn}
  <nav class="nav">
    <a href="/" class="logo">CHAMP<span>LMS</span></a>
    <div class="nav-links">
      <a href="/" class:active={$page.url.pathname === '/'}>
        <span class="nav-icon">🏠</span> Home
      </a>
      <a href="/my-learning" class:active={$page.url.pathname === '/my-learning'}>
        <span class="nav-icon">📚</span> My Learning
      </a>
      <a href="/leaderboard" class:active={$page.url.pathname === '/leaderboard'}>
        <span class="nav-icon">🏆</span> Leaderboard
      </a>
      {#if $isAdmin}
        <a href="/admin" class:active={$page.url.pathname.startsWith('/admin')}>
          <span class="nav-icon">⚙️</span> Admin
        </a>
      {/if}
    </div>
    <div class="nav-user">
      <div class="user-stats">
        <span class="stat points">
          <span class="stat-icon">⭐</span>
          {$auth.user?.points ?? 0}
        </span>
        <span class="stat streak">
          <span class="stat-icon">🔥</span>
          {$auth.user?.streak_days ?? 0}
        </span>
      </div>
      <button class="btn-signout" on:click={() => auth.logout()}>Sign Out</button>
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
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    gap: 1rem;
  }
  
  .spinner {
    width: 48px;
    height: 48px;
    border: 3px solid var(--surface2);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  
  @keyframes spin { 
    to { transform: rotate(360deg); } 
  }
  
  .loading-text {
    color: var(--muted);
    font-size: 0.9rem;
  }

  .nav {
    display: flex;
    align-items: center;
    gap: 2rem;
    padding: 0 2rem;
    height: 64px;
    background: rgba(10, 10, 15, 0.95);
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
  }
  
  .logo {
    font-size: 1.4rem;
    font-weight: 900;
    letter-spacing: -0.02em;
    color: var(--text);
  }
  
  .logo span { 
    color: var(--accent); 
  }
  
  .nav-links { 
    display: flex; 
    gap: 0.5rem; 
    flex: 1;
  }
  
  .nav-links a {
    font-size: 0.9rem;
    color: var(--muted);
    transition: all 0.2s ease;
    padding: 0.5rem 0.75rem;
    border-radius: 6px;
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  
  .nav-links a:hover, 
  .nav-links a.active { 
    color: var(--text);
    background: var(--surface);
  }
  
  .nav-icon {
    font-size: 1rem;
  }
  
  .nav-user { 
    display: flex; 
    align-items: center; 
    gap: 1.25rem; 
    margin-left: auto; 
  }
  
  .user-stats {
    display: flex;
    gap: 1rem;
  }
  
  .stat {
    font-size: 0.85rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  
  .stat-icon {
    font-size: 0.9rem;
  }
  
  .points { 
    color: var(--gold); 
  }
  
  .streak { 
    color: #ff6b35; 
  }
  
  .btn-signout {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 0.4rem 1rem;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 500;
    transition: all 0.2s ease;
  }
  
  .btn-signout:hover {
    background: var(--surface2);
    color: var(--text);
    border-color: var(--muted);
  }
  
  .main { 
    padding: 1.5rem 2rem 4rem; 
    max-width: 1400px; 
    margin: 0 auto; 
  }
  
  @media (max-width: 768px) {
    .nav {
      padding: 0 1rem;
      gap: 1rem;
    }
    
    .logo {
      font-size: 1.1rem;
    }
    
    .nav-links a {
      padding: 0.4rem 0.5rem;
      font-size: 0.8rem;
    }
    
    .nav-icon {
      display: none;
    }
    
    .stat {
      font-size: 0.75rem;
    }
    
    .btn-signout {
      padding: 0.3rem 0.7rem;
      font-size: 0.75rem;
    }
    
    .main {
      padding: 1rem 1rem 3rem;
    }
  }
</style>
