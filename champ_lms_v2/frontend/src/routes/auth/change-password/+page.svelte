<script lang="ts">
  import { goto } from '$app/navigation';
  import { auth } from '$lib/stores/auth';
  import { api } from '$lib/api/client';

  const MIN_LENGTH = 8;

  let currentPassword = '';
  let newPassword = '';
  let confirmPassword = '';
  let loading = false;
  let error = '';
  let done = false;

  // Employees arrive here right after signing in with an admin-issued password.
  $: firstTime = $auth.user?.must_change_password ?? false;

  $: problem =
    newPassword.length > 0 && newPassword.length < MIN_LENGTH
      ? `Use at least ${MIN_LENGTH} characters.`
      : confirmPassword.length > 0 && newPassword !== confirmPassword
        ? "The two new passwords don't match."
        : newPassword.length > 0 && newPassword === currentPassword
          ? 'Choose something different from your current password.'
          : '';

  $: canSubmit =
    !loading && !problem &&
    currentPassword.length > 0 &&
    newPassword.length >= MIN_LENGTH &&
    newPassword === confirmPassword;

  async function submit() {
    if (!canSubmit) return;
    loading = true; error = '';
    try {
      await api.changePassword(currentPassword, newPassword);
      // Refresh the cached user so must_change_password clears and the
      // reminder banner stops showing.
      await auth.refresh();
      done = true;
      setTimeout(() => goto('/'), 1200);
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head><title>Champ LMS — Change Password</title></svelte:head>

<div class="auth-wrap">
  <div class="auth-card">
    <div class="logo">CHAMP<span>LMS</span></div>

    {#if done}
      <h1>Password updated</h1>
      <p class="note">You're all set. Taking you to your learning…</p>
    {:else}
      <h1>{firstTime ? 'Set your password' : 'Change password'}</h1>
      <p class="note">
        {#if firstTime}
          You're signed in with the password an administrator gave you. Choose
          your own to finish setting up your account.
        {:else}
          Enter your current password, then the new one you'd like to use.
        {/if}
      </p>

      <form on:submit|preventDefault={submit}>
        <label>
          {firstTime ? 'Password you were given' : 'Current password'}
          <input type="password" bind:value={currentPassword} required autocomplete="current-password" />
        </label>
        <label>
          New password
          <input type="password" bind:value={newPassword} required autocomplete="new-password" />
        </label>
        <label>
          Confirm new password
          <input type="password" bind:value={confirmPassword} required autocomplete="new-password" />
        </label>

        {#if problem}<p class="hint">{problem}</p>{/if}
        {#if error}<p class="error">{error}</p>{/if}

        <button type="submit" class="btn-primary" disabled={!canSubmit}>
          {loading ? 'Saving…' : 'Update password'}
        </button>
      </form>

      {#if !firstTime}
        <p class="toggle"><a href="/">Back to learning</a></p>
      {/if}
    {/if}
  </div>
</div>

<style>
  .auth-wrap {
    min-height: 100vh; display: flex;
    align-items: center; justify-content: center;
    background: var(--bg); padding: 1rem;
  }
  .auth-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 2.5rem; width: 100%; max-width: 420px;
  }
  .logo { font-size: 1.5rem; font-weight: 900; color: var(--accent); text-align: center; margin-bottom: 1.5rem; }
  .logo span { color: var(--text); }
  h1 { font-size: 1.35rem; margin-bottom: 0.6rem; text-align: center; }
  .note { color: var(--muted); font-size: 0.85rem; text-align: center; margin-bottom: 1.5rem; line-height: 1.5; }
  form { display: flex; flex-direction: column; gap: 1rem; }
  label { display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.85rem; color: var(--muted); }
  input {
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 0.65rem 0.9rem; font-size: 0.95rem; outline: none;
    transition: border-color 0.15s;
  }
  input:focus { border-color: var(--accent); }
  .btn-primary {
    margin-top: 0.5rem; background: var(--accent); color: #fff; font-weight: 600;
    border: none; border-radius: 6px; padding: 0.7rem; font-size: 0.95rem; cursor: pointer;
  }
  .btn-primary:disabled { opacity: 0.55; cursor: not-allowed; }
  .hint { color: var(--muted); font-size: 0.82rem; text-align: center; }
  .error { color: var(--accent); font-size: 0.85rem; text-align: center; }
  .toggle { text-align: center; font-size: 0.85rem; margin-top: 1.25rem; }
  .toggle a { color: var(--accent); }
</style>
