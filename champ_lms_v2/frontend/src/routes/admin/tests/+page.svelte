<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type AdminTestSummary } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import { countUp } from '$lib/actions/motion';

  let tests: AdminTestSummary[] = [];
  let loading = true;
  let error = '';
  let busy = '';

  onMount(load);

  async function load() {
    loading = true;
    try {
      tests = await api.adminTestList();
      error = '';
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  async function togglePublish(t: AdminTestSummary) {
    busy = t.id;
    try {
      await api.publishTestSeries(t.id, !t.is_published);
      await load();
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  async function remove(t: AdminTestSummary) {
    // * no window.confirm — a modal dialog would block the page; the button is
    // * two-step instead (click arms, second click deletes)
    if (armedDelete !== t.id) { armedDelete = t.id; return; }
    busy = t.id;
    try {
      await api.deleteTestSeries(t.id);
      armedDelete = '';
      await load();
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }
  let armedDelete = '';
</script>

<svelte:head><title>Test Series — Champ LMS</title></svelte:head>

<div class="page">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Test Series' }]} />
  <div class="head">
    <div>
      <h1 class="ui-rise" style="--i:1">
        Test Series
        <span class="title-mark" aria-hidden="true"><Icon name="clipboard" size={23} /></span>
      </h1>
      <p class="sub ui-rise" style="--i:2">Upload a question-and-answer PDF, review it, publish it, then score your team.</p>
    </div>
    <a href="/admin/tests/new" class="btn-primary new ui-rise" style="--i:3">
      <span class="plus"><Icon name="plus" size={16} stroke={2.2} /></span> New from PDF
    </a>
  </div>

  {#if error}<p class="error"><Icon name="alert" size={16} /> {error}</p>{/if}

  {#if loading}
    <div class="skeleton-list">
      {#each Array(3) as _}<div class="ui-skeleton" style="height:190px;border-radius:28px"></div>{/each}
    </div>
  {:else if tests.length === 0}
    <div class="empty ui-rise">
      <div class="empty-icon"><Icon name="file" size={30} /></div>
      <h2>No test series yet</h2>
      <p>Upload a PDF containing questions and answers to create your first interactive test.</p>
      <a href="/admin/tests/new" class="btn-primary"><Icon name="upload" size={16} /> Upload a Q&amp;A PDF</a>
    </div>
  {:else}
    <div class="grid">
      {#each tests as t, n (t.id)}
        <div class="card ui-rise" style="--i:{Math.min(n, 8) + 3}">
          <div class="card-top">
            <span class="c-ico" class:live={t.is_published} aria-hidden="true"><Icon name="clipboard" size={20} /></span>
            <div class="titles">
              <a href="/admin/tests/{t.id}" class="card-title">{t.title}</a>
              <div class="meta">
                {#if t.category}<span class="chip">{t.category}</span>{/if}
                {#if t.department}<span class="chip"><Icon name="building" size={12} /> {t.department}</span>{/if}
                <span class="chip"><Icon name="hash" size={12} /> {t.total_questions} questions</span>
                <span class="chip"><Icon name="target" size={12} /> pass {t.pass_threshold}%</span>
                {#if t.duration_minutes}<span class="chip"><Icon name="clock" size={12} /> {t.duration_minutes} min</span>{/if}
              </div>
            </div>
            <span class="status" class:live={t.is_published}>
              {#if t.is_published}<span class="dot"></span>{/if}
              {t.is_published ? 'Published' : 'Draft'}
            </span>
          </div>

          {#if !t.is_ready}
            <p class="warn">
              <Icon name="alert" size={15} />
              {t.unscorable_count} question{t.unscorable_count === 1 ? '' : 's'} missing a correct
              answer — fix before publishing.
            </p>
          {/if}

          <div class="stats">
            <div class="stat sky"><b use:countUp={t.attempt_count}></b><span>attempts</span></div>
            <div class="stat lilac">
              {#if t.average_score != null}<b><span use:countUp={t.average_score}></span>%</b>{:else}<b>—</b>{/if}
              <span>avg score</span>
            </div>
            <div class="stat mint">
              {#if t.pass_rate != null}<b><span use:countUp={t.pass_rate}></span>%</b>{:else}<b>—</b>{/if}
              <span>pass rate</span>
            </div>
          </div>

          <div class="actions">
            <a href="/admin/tests/{t.id}" class="btn"><Icon name="edit" size={15} /> Review / Edit</a>
            <a href="/admin/tests/{t.id}/results" class="btn"><Icon name="chart" size={15} /> Results</a>
            <button class="btn" disabled={busy === t.id || (!t.is_ready && !t.is_published)}
                    on:click={() => togglePublish(t)}>
              <Icon name={t.is_published ? 'eyeOff' : 'send'} size={15} />
              {t.is_published ? 'Unpublish' : 'Publish'}
            </button>
            <button class="btn danger" class:armed={armedDelete === t.id} disabled={busy === t.id} on:click={() => remove(t)}>
              <Icon name="trash" size={15} />
              {armedDelete === t.id ? 'Click again to delete' : 'Delete'}
            </button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
  h1 {
    font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.05;
    display: flex; align-items: center; gap: 0.6rem; margin: 0 0 0.55rem;
  }
  .title-mark {
    display: inline-grid; place-items: center; width: 46px; height: 46px; border-radius: 50%;
    background: var(--tile-lilac); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .sub { color: var(--muted); font-size: 0.95rem; }
  .plus { display: grid; transition: rotate var(--dur-3) var(--ease-out); }
  .new:hover .plus { rotate: 90deg; }
  .error {
    display: flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1rem; border-radius: 18px; margin-bottom: 1rem;
    background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); font-weight: 600; font-size: 0.88rem;
  }

  .grid { display: flex; flex-direction: column; gap: 1rem; }
  .card {
    background: var(--surface); border-radius: 28px; padding: 1.35rem 1.4rem; box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .card:hover { translate: 0 -3px; box-shadow: var(--shadow-md); }
  .card-top { display: flex; gap: 0.9rem; align-items: flex-start; }
  .c-ico {
    width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center; flex: none;
    background: var(--surface2); color: var(--text);
    transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .c-ico.live { background: var(--tile-lilac); color: var(--tile-ink); }
  .card:hover .c-ico { rotate: -12deg; scale: 1.08; }
  .titles { flex: 1; min-width: 0; }
  .card-title { font-size: 1.12rem; font-weight: 700; letter-spacing: -0.015em; color: var(--text); text-decoration: none; }
  .card-title:hover { text-decoration: underline; text-underline-offset: 3px; }
  .meta { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.5rem; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.25rem;
    font-size: 0.74rem; color: var(--text-secondary); background: var(--surface2); border-radius: 999px; padding: 0.22rem 0.6rem;
  }
  .status {
    display: inline-flex; align-items: center; gap: 0.35rem; height: 30px; padding: 0 0.8rem;
    font-size: 0.76rem; font-weight: 700; border-radius: 999px; white-space: nowrap;
    background: var(--surface2); color: var(--muted);
  }
  .status.live { background: var(--tile-mint); color: var(--tile-ink); }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--success); animation: pulse-ring 1.8s var(--ease-out) infinite; }
  .warn {
    display: flex; align-items: center; gap: 0.5rem;
    margin-top: 0.9rem; font-size: 0.82rem; font-weight: 500; color: var(--tile-ink); background: var(--tile-butter);
    border-radius: 14px; padding: 0.55rem 0.8rem;
  }

  .stats { display: grid; grid-template-columns: repeat(3, minmax(0, 120px)); gap: 0.5rem; margin: 1.1rem 0 0.25rem; }
  .stat { display: flex; flex-direction: column; padding: 0.6rem 0.8rem; border-radius: 18px; color: var(--tile-ink); }
  .stat b { font-size: 1.35rem; font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .stat span { font-size: 0.72rem; opacity: 0.72; }
  .stat:hover b { animation: pop 420ms var(--ease-out); }
  .sky { background: var(--tile-sky); }
  .lilac { background: var(--tile-lilac); }
  .mint { background: var(--tile-mint); }

  .actions { display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 1.1rem; }
  .btn {
    display: inline-flex; align-items: center; gap: 0.4rem; height: 38px;
    background: var(--surface2); border: 1px solid transparent; color: var(--text);
    border-radius: 999px; padding: 0 1rem; font-size: 0.84rem; font-weight: 600;
    cursor: pointer; text-decoration: none;
    transition: background-color var(--dur-2) var(--ease-out), translate var(--dur-2) var(--ease-out), color var(--dur-2);
  }
  .btn:hover:not(:disabled) { background: var(--surface3); translate: 0 -1px; }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.danger:hover:not(:disabled) { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }
  .btn.danger.armed { background: var(--danger); color: var(--on-accent); animation: shake 420ms var(--ease-out); }
  @keyframes shake { 20%, 60% { translate: -4px 0; } 40%, 80% { translate: 4px 0; } }

  .empty {
    display: flex; flex-direction: column; align-items: center; text-align: center;
    padding: 2.75rem 1rem; background: var(--surface); border-radius: 30px;
  }
  .empty-icon {
    width: 66px; height: 66px; border-radius: 50%; display: grid; place-items: center; margin-bottom: 0.9rem;
    background: var(--tile-lilac); color: var(--tile-ink); animation: float 4s var(--ease-in-out) infinite;
  }
  .empty h2 { font-size: 1.3rem; margin-bottom: 0.4rem; }
  .empty p { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.25rem; max-width: 46ch; }

  .skeleton-list { display: flex; flex-direction: column; gap: 1rem; }

  @media (max-width: 640px) {
    .card-top { flex-wrap: wrap; }
    .stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  }
</style>
