<script lang="ts">
  import { goto } from '$app/navigation';
  import { auth } from '$lib/stores/auth';
  import { api } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';

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

  // Purely visual: how far the new password is toward the minimum length.
  $: strength = Math.min(100, Math.round((newPassword.length / MIN_LENGTH) * 100));

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
  <div class="auth-card ui-rise">
    <div class="logo ui-rise" style="--i:1">Champ<span>LMS</span></div>

    {#if done}
      <div class="done">
        <span class="mark ok" aria-hidden="true"><Icon name="check" size={30} stroke={2.4} /></span>
        <h1>Password updated</h1>
        <p class="note">You're all set. Taking you to your learning…</p>
      </div>
    {:else}
      <span class="mark ui-rise" style="--i:2" aria-hidden="true"><Icon name="key" size={26} /></span>
      <h1 class="ui-rise" style="--i:2">{firstTime ? 'Set your password' : 'Change password'}</h1>
      <p class="note ui-rise" style="--i:3">
        {#if firstTime}
          You're logged in with the password an administrator gave you. Choose
          your own to finish setting up your account.
        {:else}
          Enter your current password, then the new one you'd like to use.
        {/if}
      </p>

      <form on:submit|preventDefault={submit}>
        <label class="ui-rise" style="--i:4">
          <span class="lbl">{firstTime ? 'Password you were given' : 'Current password'}</span>
          <span class="field"><Icon name="lock" size={17} /><input type="password" bind:value={currentPassword} required autocomplete="current-password" /></span>
        </label>
        <label class="ui-rise" style="--i:5">
          <span class="lbl">New password</span>
          <span class="field"><Icon name="key" size={17} /><input type="password" bind:value={newPassword} required autocomplete="new-password" /></span>
          <span class="meter" aria-hidden="true"><span class:full={strength >= 100} style="--p:{strength}%"></span></span>
        </label>
        <label class="ui-rise" style="--i:6">
          <span class="lbl">Confirm new password</span>
          <span class="field">
            <Icon name="shield" size={17} />
            <input type="password" bind:value={confirmPassword} required autocomplete="new-password" />
            {#if confirmPassword && confirmPassword === newPassword && newPassword.length >= MIN_LENGTH}
              <span class="match" aria-hidden="true"><Icon name="check" size={14} stroke={2.4} /></span>
            {/if}
          </span>
        </label>

        {#if problem}<p class="hint"><Icon name="info" size={15} /> {problem}</p>{/if}
        {#if error}{#key error}<p class="error"><Icon name="alert" size={15} /> {error}</p>{/key}{/if}

        <button type="submit" class="btn-primary submit ui-rise" style="--i:7" disabled={!canSubmit}>
          {#if loading}
            <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span> Saving…
          {:else}
            Update password <Icon name="arrowRight" size={17} />
          {/if}
        </button>
      </form>

      {#if !firstTime}
        <p class="toggle"><a href="/"><Icon name="arrowLeft" size={15} /> Back to learning</a></p>
      {/if}
    {/if}
  </div>
</div>

<style>
  .auth-wrap {
    min-height: 78vh; display: flex;
    align-items: center; justify-content: center;
    padding: 1.5rem 1rem;
  }
  .auth-card {
    background: var(--surface); border-radius: 32px; box-shadow: var(--shadow-md);
    padding: 2.4rem 2.2rem 2rem; width: 100%; max-width: 440px;
    display: flex; flex-direction: column;
  }
  .logo { font-size: 1.35rem; font-weight: 800; letter-spacing: -0.03em; margin-bottom: 1.6rem; }
  .logo span {
    margin-left: 0.3rem; padding: 0.1rem 0.45rem; border-radius: 8px; font-size: 0.7rem;
    vertical-align: 0.35em; background: #e50914; color: #fff; letter-spacing: 0.04em;
  }
  .mark {
    width: 58px; height: 58px; border-radius: 50%; display: grid; place-items: center;
    background: var(--tile-butter); color: var(--tile-ink); rotate: -8deg; margin-bottom: 1rem;
  }
  .mark.ok { background: var(--tile-mint); rotate: 0deg; animation: pop 560ms var(--ease-out); }
  h1 { font-size: 1.75rem; font-weight: 700; letter-spacing: -0.03em; margin-bottom: 0.5rem; }
  .note { color: var(--muted); font-size: 0.92rem; margin-bottom: 1.6rem; line-height: 1.55; }
  .done { display: flex; flex-direction: column; align-items: flex-start; }

  form { display: flex; flex-direction: column; gap: 1rem; }
  label { display: flex; flex-direction: column; gap: 0.4rem; }
  .lbl { font-size: 0.82rem; font-weight: 600; color: var(--text-secondary); }
  .field { position: relative; display: block; color: var(--muted); }
  .field > :global(.icon) { position: absolute; left: 1rem; top: 50%; translate: 0 -50%; pointer-events: none; transition: color var(--dur-2); }
  .field:focus-within > :global(.icon) { color: var(--text); }
  input {
    width: 100%; height: 52px; padding: 0 2.6rem 0 2.75rem;
    background: var(--surface2); border: 1px solid transparent; color: var(--text);
    border-radius: 18px; font-size: 0.95rem;
  }
  input:hover { background: var(--surface3); }
  .match {
    position: absolute; right: 0.9rem; top: 50%; translate: 0 -50%;
    width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
    background: var(--tile-mint); color: var(--tile-ink); animation: pop 380ms var(--ease-out);
  }
  .meter { height: 4px; border-radius: 99px; background: var(--surface3); overflow: hidden; margin-top: 0.15rem; }
  .meter span {
    display: block; height: 100%; width: var(--p); border-radius: inherit; background: var(--warn);
    transition: width var(--dur-3) var(--ease-out), background-color var(--dur-3);
  }
  .meter span.full { background: var(--success); }

  .submit { margin-top: 0.4rem; width: 100%; height: 52px; }
  .submit :global(.icon) { transition: translate var(--dur-3) var(--ease-out); }
  .submit:hover:not(:disabled) :global(.icon) { translate: 3px 0; }
  .dots { display: inline-flex; gap: 4px; }
  .dots i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; animation: blink 1s var(--ease-in-out) infinite; }
  .dots i:nth-child(2) { animation-delay: 150ms; }
  .dots i:nth-child(3) { animation-delay: 300ms; }
  @keyframes blink { 0%, 100% { opacity: 0.3; translate: 0 0; } 50% { opacity: 1; translate: 0 -3px; } }

  .hint, .error {
    display: flex; align-items: center; gap: 0.45rem; font-size: 0.84rem;
    padding: 0.6rem 0.85rem; border-radius: 14px; animation: rise 320ms var(--ease-out);
  }
  .hint { background: var(--surface2); color: var(--text-secondary); }
  .error { background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); animation: shake 420ms var(--ease-out); }
  @keyframes shake { 20%, 60% { translate: -5px 0; } 40%, 80% { translate: 5px 0; } }
  .toggle { font-size: 0.88rem; margin-top: 1.3rem; }
  .toggle a { display: inline-flex; align-items: center; gap: 0.35rem; color: var(--muted); font-weight: 600; }
  .toggle a:hover { color: var(--text); }
  .toggle a:hover :global(.icon) { translate: -3px 0; transition: translate var(--dur-2) var(--ease-out); }

  @media (max-width: 520px) {
    .auth-card { padding: 1.8rem 1.3rem 1.5rem; border-radius: 26px; }
  }
</style>
