<script lang="ts">
  import { auth } from '$lib/stores/auth';

  let email = '';
  let password = '';
  let loading = false;
  let error = '';

  // * No sign-up here: Champ LMS is internal and admins provision every
  // * account, so this page only signs people in.
  async function submit() {
    loading = true; error = '';
    try {
      await auth.login(email, password);
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
    <h1>Sign In</h1>

    <form on:submit|preventDefault={submit}>
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
        {loading ? 'Loading...' : 'Sign In'}
      </button>
    </form>

    <p class="toggle">
      Need an account? Ask your administrator — accounts are created internally.
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
