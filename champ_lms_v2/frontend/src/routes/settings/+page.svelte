<script lang="ts">
  import { api } from '$lib/api/client';
  import { auth } from '$lib/stores/auth';
  import Avatar from '$lib/components/Avatar.svelte';

  // Local mirror of the picture so the page updates the instant an upload
  // lands, rather than waiting for the auth store to round-trip.
  let avatarUrl: string | null = null;
  let name = '';
  let hydrated = false;

  // Fill the form once the auth store has a user. Guarded so a later store
  // update (points, streak) can't stomp on what the admin is mid-typing.
  $: if (!hydrated && $auth.user) {
    name = $auth.user.full_name ?? '';
    avatarUrl = $auth.user.avatar_url ?? null;
    hydrated = true;
  }

  let fileInput: HTMLInputElement;
  let uploading = false;
  let savingName = false;
  let error = '';
  let notice = '';

  async function pick(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    error = ''; notice = '';
    uploading = true;
    try {
      const r = await api.uploadAvatar(file);
      avatarUrl = r.avatar_url;
      await auth.refresh();
      notice = 'Profile picture updated.';
    } catch (e: any) {
      error = e.message;
    } finally {
      uploading = false;
      // Clear the input so picking the same file again still fires a change.
      if (fileInput) fileInput.value = '';
    }
  }

  async function removePicture() {
    error = ''; notice = '';
    uploading = true;
    try {
      await api.deleteAvatar();
      avatarUrl = null;
      await auth.refresh();
      notice = 'Profile picture removed.';
    } catch (e: any) {
      error = e.message;
    } finally {
      uploading = false;
    }
  }

  async function saveName() {
    const trimmed = name.trim();
    if (!trimmed) { error = 'Name cannot be empty'; return; }
    error = ''; notice = '';
    savingName = true;
    try {
      await api.updateProfile({ full_name: trimmed });
      await auth.refresh();
      notice = 'Name saved.';
    } catch (e: any) {
      error = e.message;
    } finally {
      savingName = false;
    }
  }
</script>

<svelte:head><title>Settings — Champ LMS</title></svelte:head>

<div class="wrap">
  <header>
    <h1>Settings</h1>
    <p class="sub">Your profile picture appears in the top bar, on the leaderboard and anywhere your name shows up.</p>
  </header>

  {#if error}<p class="error">{error}</p>{/if}
  {#if notice}<p class="notice">{notice}</p>{/if}

  <section class="card">
    <h2>Profile picture</h2>
    <div class="pic-row">
      <Avatar src={avatarUrl} name={$auth.user?.full_name} size={96} />
      <div class="pic-actions">
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          bind:this={fileInput}
          on:change={pick}
          hidden
        />
        <button class="btn primary" disabled={uploading} on:click={() => fileInput?.click()}>
          {uploading ? 'Uploading…' : avatarUrl ? 'Change picture' : 'Upload picture'}
        </button>
        {#if avatarUrl}
          <button class="btn ghost" disabled={uploading} on:click={removePicture}>Remove</button>
        {/if}
        <p class="hint">JPEG, PNG, WebP or GIF · up to 5MB. Without one, your initials are shown.</p>
      </div>
    </div>
  </section>

  <section class="card">
    <h2>Your details</h2>
    <div class="fields">
      <label>
        Full name
        <input bind:value={name} placeholder="Your name" />
      </label>
      <label>
        Employee code
        <input value={$auth.user?.employee_code ?? 'Not assigned'} readonly />
        <span class="hint">Set by your administrator.</span>
      </label>
      <label>
        Work email
        <input value={$auth.user?.email ?? ''} readonly />
        <span class="hint">Managed by your administrator.</span>
      </label>
      <label>
        Department &amp; team
        <input
          value={[$auth.user?.department, $auth.user?.team].filter(Boolean).join(' · ') || 'Not assigned'}
          readonly
        />
        <span class="hint">Managed by your administrator.</span>
      </label>
    </div>
    <button class="btn primary" disabled={savingName} on:click={saveName}>
      {savingName ? 'Saving…' : 'Save name'}
    </button>
  </section>

  <section class="card">
    <h2>Password</h2>
    <p class="hint">Choose a password only you know.</p>
    <a class="btn ghost" href="/auth/change-password">Change password</a>
  </section>
</div>

<style>
  .wrap { max-width: 720px; margin: 0 auto; padding-bottom: 4rem; }
  header { margin-bottom: 1.5rem; }
  h1 { font-size: 1.6rem; font-weight: 800; margin-bottom: 0.3rem; }
  h2 { font-size: 1.02rem; font-weight: 700; margin-bottom: 1rem; }
  .sub { color: var(--muted); font-size: 0.87rem; max-width: 60ch; }
  .card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.35rem; margin-bottom: 1.25rem;
  }
  .pic-row { display: flex; gap: 1.4rem; align-items: center; flex-wrap: wrap; }
  .pic-actions { display: flex; gap: 0.6rem; align-items: center; flex-wrap: wrap; }
  .fields {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem; margin-bottom: 1.1rem;
  }
  label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.82rem; color: var(--muted); }
  input {
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 0.55rem 0.7rem; font-size: 0.9rem; outline: none; width: 100%;
  }
  input:focus { border-color: var(--accent); }
  input[readonly] { color: var(--muted); cursor: default; }
  .hint { font-size: 0.74rem; color: var(--muted); flex-basis: 100%; margin: 0; }
  .btn {
    border: 1px solid var(--border); background: var(--surface2); color: var(--text);
    border-radius: 6px; padding: 0.5rem 0.95rem; font-size: 0.85rem; font-weight: 600;
    cursor: pointer; text-decoration: none; display: inline-block;
  }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn.ghost { background: transparent; }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .error { color: var(--accent); font-size: 0.85rem; margin-bottom: 1rem; }
  .notice { color: var(--success); font-size: 0.85rem; margin-bottom: 1rem; }
</style>
