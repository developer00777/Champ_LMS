<script lang="ts">
  import { api } from '$lib/api/client';
  import { auth } from '$lib/stores/auth';
  import Avatar from '$lib/components/Avatar.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';

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
  <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: 'Settings' }]} />
  <header class="head">
    <h1 class="ui-rise" style="--i:1">
      Settings
      <span class="title-mark" aria-hidden="true"><Icon name="settings" size={24} /></span>
    </h1>
    <p class="sub ui-rise" style="--i:2">Your profile picture appears in the top bar, on the leaderboard and anywhere your name shows up.</p>
  </header>

  {#if error}
    {#key error}<p class="flash bad" role="alert"><Icon name="alert" size={17} /> {error}</p>{/key}
  {/if}
  {#if notice}
    {#key notice}<p class="flash ok" role="status"><Icon name="checkCircle" size={17} /> {notice}</p>{/key}
  {/if}

  <section class="card ui-rise" style="--i:3">
    <div class="card-head">
      <span class="c-ico lilac"><Icon name="user" size={18} /></span>
      <h2>Profile picture</h2>
    </div>
    <div class="pic-row">
      <div class="pic" class:busy={uploading}>
        <Avatar src={avatarUrl} name={$auth.user?.full_name} size={104} />
        {#if uploading}<span class="spin" aria-hidden="true"></span>{/if}
      </div>
      <div class="pic-actions">
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          bind:this={fileInput}
          on:change={pick}
          hidden
        />
        <div class="btns">
          <button class="btn-primary" disabled={uploading} on:click={() => fileInput?.click()}>
            <Icon name="upload" size={16} />
            {uploading ? 'Uploading…' : avatarUrl ? 'Change picture' : 'Upload picture'}
          </button>
          {#if avatarUrl}
            <button class="btn-ghost" disabled={uploading} on:click={removePicture}>
              <Icon name="trash" size={16} /> Remove
            </button>
          {/if}
        </div>
        <p class="hint">JPEG, PNG, WebP or GIF · up to 5MB. Without one, your initials are shown.</p>
      </div>
    </div>
  </section>

  <section class="card ui-rise" style="--i:4">
    <div class="card-head">
      <span class="c-ico sky"><Icon name="clipboard" size={18} /></span>
      <h2>Your details</h2>
    </div>
    <div class="fields">
      <label class="field">
        <span class="lbl">Full name</span>
        <input bind:value={name} placeholder="Your name" />
      </label>
      <label class="field">
        <span class="lbl">Employee code</span>
        <span class="ro"><Icon name="lock" size={14} /><input value={$auth.user?.employee_code ?? 'Not assigned'} readonly /></span>
        <span class="hint">Set by your administrator.</span>
      </label>
      <label class="field">
        <span class="lbl">Work email</span>
        <span class="ro"><Icon name="mail" size={14} /><input value={$auth.user?.email ?? ''} readonly /></span>
        <span class="hint">Managed by your administrator.</span>
      </label>
      <label class="field">
        <span class="lbl">Department &amp; team</span>
        <span class="ro"><Icon name="building" size={14} /><input
          value={[$auth.user?.department, $auth.user?.team].filter(Boolean).join(' · ') || 'Not assigned'}
          readonly
        /></span>
        <span class="hint">Managed by your administrator.</span>
      </label>
    </div>
    <button class="btn-primary" disabled={savingName} on:click={saveName}>
      <Icon name="save" size={16} /> {savingName ? 'Saving…' : 'Save name'}
    </button>
  </section>

  <section class="card row-card ui-rise" style="--i:5">
    <div class="card-head">
      <span class="c-ico butter"><Icon name="key" size={18} /></span>
      <div>
        <h2>Password</h2>
        <p class="hint">Choose a password only you know.</p>
      </div>
    </div>
    <a class="btn-ghost go-link" href="/auth/change-password">
      Change password <Icon name="arrowRight" size={16} />
    </a>
  </section>
</div>

<style>
  .wrap { max-width: 760px; margin: 0 auto; }

  .head { margin: 0 0 1.25rem; }
  h1 {
    font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02;
    display: flex; align-items: center; gap: 0.6rem;
  }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-mint); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  .title-mark :global(svg) { transition: rotate 700ms var(--ease-out); }
  h1:hover .title-mark :global(svg) { rotate: 90deg; }
  .sub { color: var(--muted); font-size: 0.95rem; max-width: 60ch; margin-top: 0.7rem; line-height: 1.5; }

  .flash {
    display: flex; align-items: center; gap: 0.55rem;
    padding: 0.75rem 1rem; border-radius: 18px; margin-bottom: 1rem;
    font-size: 0.88rem; font-weight: 600; animation: rise 380ms var(--ease-out);
  }
  .flash.bad { background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); }
  .flash.ok { background: var(--tile-mint); color: var(--tile-ink); }

  .card {
    background: var(--surface); border-radius: 28px; padding: 1.5rem;
    margin-bottom: 1.1rem; box-shadow: var(--shadow-sm);
    transition: box-shadow var(--dur-3) var(--ease-out), translate var(--dur-3) var(--ease-out);
  }
  .card:hover { box-shadow: var(--shadow); }
  .card-head { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.2rem; }
  .card-head h2 { font-size: 1.15rem; font-weight: 700; letter-spacing: -0.02em; }
  .c-ico {
    width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center;
    color: var(--tile-ink); flex: none; transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .card:hover .c-ico { rotate: -12deg; scale: 1.08; }
  .lilac { background: var(--tile-lilac); }
  .sky { background: var(--tile-sky); }
  .butter { background: var(--tile-butter); }

  .pic-row { display: flex; gap: 1.6rem; align-items: center; flex-wrap: wrap; }
  .pic {
    position: relative; padding: 6px; border-radius: 50%; background: var(--bg-alt);
    transition: scale var(--dur-3) var(--ease-out), rotate var(--dur-3) var(--ease-out);
  }
  .pic:hover { scale: 1.04; rotate: -3deg; }
  .pic.busy :global(img), .pic.busy :global(span) { opacity: 0.6; }
  .spin {
    position: absolute; inset: 0; border-radius: 50%;
    border: 3px solid transparent; border-top-color: var(--accent);
    animation: spin 900ms linear infinite;
  }
  @keyframes spin { to { rotate: 360deg; } }
  .pic-actions { display: flex; flex-direction: column; gap: 0.7rem; min-width: 0; flex: 1; }
  .btns { display: flex; gap: 0.6rem; flex-wrap: wrap; }

  .fields {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 1rem 1.1rem; margin-bottom: 1.3rem;
  }
  .field { display: flex; flex-direction: column; gap: 0.4rem; }
  .lbl { font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }
  input {
    width: 100%; height: 48px; padding: 0 1rem;
    background: var(--surface2); border: 1px solid transparent; color: var(--text);
    border-radius: 16px; font-size: 0.92rem;
  }
  input:hover:not([readonly]) { background: var(--surface3); }
  .ro { position: relative; display: block; }
  .ro :global(.icon) { position: absolute; left: 0.95rem; top: 50%; translate: 0 -50%; color: var(--muted); }
  .ro input { padding-left: 2.4rem; color: var(--muted); cursor: default; background: var(--bg-alt); }
  .ro input:focus { box-shadow: none; border-color: transparent; }
  .hint { font-size: 0.76rem; color: var(--muted); margin: 0; }

  .row-card { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
  .row-card .card-head { margin-bottom: 0; }
  .go-link :global(.icon) { transition: translate var(--dur-3) var(--ease-out); }
  .go-link:hover :global(.icon) { translate: 3px 0; }

  @media (max-width: 760px) {
    .card { padding: 1.15rem; border-radius: 24px; }
    .pic-row { flex-direction: column; align-items: flex-start; }
  }
</style>
