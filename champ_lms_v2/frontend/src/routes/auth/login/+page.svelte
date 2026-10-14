<script lang="ts">
  import { auth } from '$lib/stores/auth';
  import Icon from '$lib/components/Icon.svelte';
  import ThemeToggle from '$lib/components/ThemeToggle.svelte';

  let email = '';
  let password = '';
  let loading = false;
  let error = '';
  let showPw = false;
  let shake = 0;

  // * No sign-up here: Champ LMS is internal and admins provision every
  // * account, so this page only signs people in.
  async function submit() {
    loading = true; error = '';
    try {
      await auth.login(email, password);
    } catch (e: any) {
      error = e.message;
      shake++;
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head><title>Champ LMS — Log In</title></svelte:head>

<div class="auth-wrap">
  <section class="brand">
    <div class="brand-top">
      <span class="logo">Champ<span>LMS</span></span>
      <ThemeToggle />
    </div>

    <!-- Decorative only; the toggle above stays reachable. -->
    <div class="collage" aria-hidden="true">
      <div class="float t1"><Icon name="book" size={30} /><span>Courses</span></div>
      <div class="float t2"><span class="mini-ico"><Icon name="check" size={16} /></span> Completed</div>
      <div class="float t3">
        <span class="disc"><Icon name="play" size={18} stroke={0} /></span>
        <div><b>Now watching</b><span>Pick up where you left off</span></div>
      </div>
      <div class="float t4"><Icon name="flame" size={16} /> Keep your streak</div>
    </div>

    <div class="pitch">
      <h2>Your learning plan,<br />one screen.</h2>
      <p>Courses, quests and tests for everyone at Champions Group.</p>
    </div>
  </section>

  <section class="form-side">
    {#key shake}
      <div class="auth-card" class:shake={shake > 0}>
        <h1>Log in</h1>
        <p class="sub">Welcome back. Use the account your administrator set up for you.</p>

        <form on:submit|preventDefault={submit}>
          <label class="field">
            <span>Email</span>
            <span class="control">
              <Icon name="mail" size={18} />
              <input type="email" bind:value={email} required placeholder="you@company.com" autocomplete="email" />
            </span>
          </label>
          <label class="field">
            <span>Password</span>
            <span class="control">
              <Icon name="lock" size={18} />
              {#if showPw}
                <input type="text" bind:value={password} required autocomplete="current-password" />
              {:else}
                <input type="password" bind:value={password} required placeholder="••••••••" autocomplete="current-password" />
              {/if}
              <button
                type="button" class="peek" on:click={() => (showPw = !showPw)}
                aria-label={showPw ? 'Hide password' : 'Show password'}
              ><Icon name={showPw ? 'eyeOff' : 'eye'} size={18} /></button>
            </span>
          </label>

          {#if error}<p class="error" role="alert"><Icon name="alert" size={16} /> {error}</p>{/if}

          <button type="submit" class="btn-primary submit" disabled={loading}>
            {#if loading}
              <span class="dots" aria-label="Logging in"><i></i><i></i><i></i></span>
            {:else}
              Log in <Icon name="arrowRight" size={18} />
            {/if}
          </button>
        </form>

        <p class="note">Don't have an account yet? Your administrator can create one for you.</p>
      </div>
    {/key}
  </section>
</div>

<style>
  /* Exactly one screen tall on desktop, so the page itself never scrolls. */
  .auth-wrap {
    height: 100vh; height: 100dvh; display: grid;
    grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); grid-template-rows: minmax(0, 1fr);
    background: var(--frame); padding: 10px; gap: 10px;
  }

  /* ---------- brand panel ---------- */
  .brand {
    position: relative; overflow: hidden;
    display: flex; flex-direction: column; justify-content: space-between;
    padding: 2rem 2.25rem 2.5rem; color: var(--on-frame);
  }
  .brand-top { display: flex; align-items: center; justify-content: space-between; }
  .logo { font-size: 1.6rem; font-weight: 900; letter-spacing: -0.04em; display: inline-flex; align-items: baseline; gap: 0.2rem; }
  .logo span {
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em; background: #e50914; color: #fff;
    padding: 0.12rem 0.4rem; border-radius: 6px; transform: translateY(-0.4rem);
  }
  /* Takes whatever height is left (up to 340px) instead of forcing the panel taller than the screen. */
  .collage { position: relative; flex: 1 1 auto; min-height: 0; max-height: 340px; margin: 1rem 0; }
  .float {
    position: absolute; display: flex; align-items: center; gap: 0.6rem;
    border-radius: 26px; color: #121214; font-weight: 600;
    box-shadow: 0 30px 60px -30px rgba(0, 0, 0, 0.6);
    animation: enter 900ms var(--ease-out) backwards, float 6s var(--ease-in-out) infinite;
  }
  .t1 { left: 6%; top: 8%; flex-direction: column; gap: 0; padding: 1.2rem 1.6rem; background: #d5f0f9; rotate: -6deg; animation-delay: 100ms, 0s; }
  .t1 { gap: 0.5rem; }
  .t1 span { font-size: 0.95rem; font-weight: 600; }
  .t2 { left: 44%; top: 2%; padding: 0.8rem 1.2rem 0.8rem 0.8rem; background: #cbf3d4; rotate: 5deg; animation-delay: 250ms, 1.2s; }
  .mini-ico { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; background: #121214; color: #cbf3d4; }
  .t3 { left: 18%; top: 44%; padding: 1rem 1.4rem 1rem 1rem; background: #f1d7fa; rotate: -3deg; animation-delay: 400ms, 2.4s; }
  .t3 div { display: flex; flex-direction: column; }
  .t3 b { font-size: 1.05rem; }
  .t3 span { font-size: 0.8rem; font-weight: 500; opacity: 0.7; }
  .disc { width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center; background: #fdfdfb; }
  .disc :global(svg) { fill: #121214; translate: 2px 0; }
  .t4 { left: 56%; top: 70%; padding: 0.75rem 1.1rem; background: #fbebb5; rotate: 4deg; animation-delay: 550ms, 3.6s; }
  @keyframes enter { from { opacity: 0; transform: translateY(30px) scale(0.9); } }

  .pitch h2 { font-size: clamp(2rem, 1.2rem + 2.2vw, 3rem); font-weight: 700; letter-spacing: -0.035em; line-height: 1.05; animation: rise 700ms var(--ease-out) 200ms backwards; }
  .pitch p { margin-top: 0.8rem; color: var(--on-frame-muted); max-width: 36ch; animation: rise 700ms var(--ease-out) 320ms backwards; }

  /* ---------- form ---------- */
  .form-side {
    display: grid; place-items: center; padding: 2rem 1.25rem;
    background: var(--bg); border-radius: 30px;
    /* Only on a very short window does the form scroll, inside its own panel. */
    min-height: 0; overflow-x: hidden; overflow-y: auto;
  }
  .auth-card {
    width: 100%; max-width: 420px;
    animation: rise 600ms var(--ease-out) backwards;
  }
  .auth-card.shake { animation: shake 420ms var(--ease-in-out); }
  @keyframes shake {
    20% { transform: translateX(-8px); } 40% { transform: translateX(7px); }
    60% { transform: translateX(-5px); } 80% { transform: translateX(3px); }
  }
  h1 { font-size: 2.4rem; letter-spacing: -0.035em; }
  .sub { color: var(--muted); margin: 0.5rem 0 2rem; font-size: 0.95rem; }
  form { display: flex; flex-direction: column; gap: 1.1rem; }
  .field { display: flex; flex-direction: column; gap: 0.45rem; }
  .field > span:first-child { font-size: 0.85rem; font-weight: 600; color: var(--text-secondary); }
  .control {
    display: flex; align-items: center; gap: 0.65rem;
    height: 54px; padding: 0 0.6rem 0 1.05rem;
    background: var(--surface); border: 1.5px solid var(--border); border-radius: 18px; color: var(--muted);
    transition: border-color var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out);
  }
  .control:focus-within { border-color: var(--accent); box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 10%, transparent); color: var(--text); }
  .control input { flex: 1; min-width: 0; height: 100%; border: none; background: none; font-size: 0.98rem; color: var(--text); }
  .control input:focus { box-shadow: none; outline: none; }
  .peek { width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center; color: var(--muted); }
  .peek:hover { background: var(--surface2); color: var(--text); }

  .error {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.7rem 0.9rem; border-radius: 14px; font-size: 0.86rem;
    color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent);
    animation: rise 300ms var(--ease-out);
  }
  .submit { height: 54px; margin-top: 0.4rem; font-size: 1rem; }
  .submit :global(.icon) { transition: transform var(--dur-3) var(--ease-out); }
  .submit:hover :global(.icon) { transform: translateX(4px); }
  .dots { display: inline-flex; gap: 5px; }
  .dots i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; animation: dot 900ms var(--ease-in-out) infinite; }
  .dots i:nth-child(2) { animation-delay: 120ms; }
  .dots i:nth-child(3) { animation-delay: 240ms; }
  @keyframes dot { 0%, 100% { opacity: 0.3; transform: translateY(0); } 50% { opacity: 1; transform: translateY(-4px); } }
  .note { margin-top: 1.5rem; font-size: 0.85rem; color: var(--muted); }

  /* Too short for the cards to read well: drop them rather than squash them. */
  @media (max-height: 620px) {
    .collage { display: none; }
  }

  @media (max-width: 900px) {
    /* Stacked on phones: the page grows with its content like any other. */
    .auth-wrap { grid-template-columns: 1fr; grid-template-rows: auto 1fr; height: auto; min-height: 100vh; min-height: 100dvh; }
    .form-side { overflow: visible; }
    .collage { display: none; }
    .brand { padding: 1.25rem 1.25rem 1.5rem; gap: 1.25rem; }
    .pitch h2 { font-size: 1.8rem; }
  }
</style>
