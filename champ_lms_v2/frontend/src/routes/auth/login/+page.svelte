<script lang="ts">
  import { auth } from '$lib/stores/auth';
  import { api } from '$lib/api/client';

  let email = '';
  let password = '';
  let fullName = '';
  let department = '';
  let mode: 'login' | 'register' = 'login';
  let loading = false;
  let error = '';

  async function submit() {
    loading = true; error = '';
    try {
      if (mode === 'login') {
        await auth.login(email, password);
      } else {
        await api.register({ email, full_name: fullName, password, department: department || undefined });
        await auth.login(email, password);
      }
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head><title>Champ LMS — Sign In</title></svelte:head>

<div class="auth-wrap">
  <div class="auth-card">
    <div class="logo">CHAMP<span>LMS</span></div>
    <h1>{mode === 'login' ? 'Sign In' : 'Create Account'}</h1>

    <form on:submit|preventDefault={submit}>
      {#if mode === 'register'}
        <label>
          Full Name
          <input type="text" bind:value={fullName} required placeholder="Jane Smith" />
        </label>
        <label>
          Department
          <input type="text" bind:value={department} placeholder="Sales, Engineering..." />
        </label>
      {/if}

      <label>
        Email
        <input type="email" bind:value={email} required placeholder="you@company.com" autocomplete="email" />
      </label>
      <label>
        Password
        <input type="password" bind:value={password} required placeholder="••••••••" autocomplete="current-password" />
      </label>

      {#if error}<p class="error">{error}</p>{/if}

      <button type="submit" class="btn-primary" disabled={loading}>
        {loading ? 'Loading...' : mode === 'login' ? 'Sign In' : 'Create Account'}
      </button>
    </form>

    <p class="toggle">
      {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}
      <button on:click={() => { mode = mode === 'login' ? 'register' : 'login'; error = ''; }}>
        {mode === 'login' ? 'Register' : 'Sign in'}
      </button>
    </p>
  </div>
</div>

<style>
  .auth-wrap {
    min-height: 100vh; display: flex;
    align-items: center; justify-content: center;
    background: var(--bg);
    padding: 1rem;
  }
  .auth-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 2.5rem;
    width: 100%; max-width: 400px;
  }
  .logo {
    font-size: 1.5rem; font-weight: 900; color: var(--accent);
    text-align: center; margin-bottom: 1.5rem;
  }
  .logo span { color: var(--text); }
  h1 { font-size: 1.4rem; margin-bottom: 1.5rem; text-align: center; }
  form { display: flex; flex-direction: column; gap: 1rem; }
  label { display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.85rem; color: var(--muted); }
  input {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 6px;
    padding: 0.65rem 0.9rem;
    font-size: 0.95rem;
    outline: none;
    transition: border-color 0.15s;
  }
  input:focus { border-color: var(--accent); }
  .btn-primary { margin-top: 0.5rem; }
  .error { color: var(--accent); font-size: 0.85rem; text-align: center; }
  .toggle { text-align: center; font-size: 0.85rem; color: var(--muted); margin-top: 1.25rem; }
  .toggle button { color: var(--accent); font-weight: 600; background: none; border: none; cursor: pointer; }
</style>
