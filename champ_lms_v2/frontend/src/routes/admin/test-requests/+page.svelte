<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type TestRequestRow } from '$lib/api/client';
  import { openRequest, pendingRequests, refreshRequests, activeRequest } from '$lib/stores/test-requests';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';

  let tab: 'pending' | 'decided' = 'pending';
  let decided: TestRequestRow[] = [];
  let loading = true;
  let error = '';

  async function load() {
    loading = true; error = '';
    try {
      if (tab === 'pending') await refreshRequests();
      else decided = await api.testRequests('decided');
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }
  onMount(load);

  // The dialog closing usually means a decision was made: refresh the list.
  let wasOpen = false;
  $: { if (wasOpen && !$activeRequest) load(); wasOpen = !!$activeRequest; }

  $: rows = tab === 'pending' ? $pendingRequests : decided;

  function ago(iso: string | null) {
    if (!iso) return '';
    const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m} min ago`;
    if (m < 1440) return `${Math.round(m / 60)} h ago`;
    return `${Math.round(m / 1440)} d ago`;
  }
  const initials = (n: string) => n.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
  const TONES = ['sky', 'lilac', 'mint', 'butter', 'peach'];
  const tone = (id: string) => TONES[[...id].reduce((a, c) => a + c.charCodeAt(0), 0) % TONES.length];
</script>

<svelte:head><title>Test requests — Champ LMS</title></svelte:head>

<div class="page">
  <header class="head">
    <div>
      <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Test Requests' }]} />
      <h1 class="ui-rise" style="--i:1">
        Test requests
        <span class="title-mark" aria-hidden="true"><Icon name="bell" size={23} /></span>
      </h1>
      <p class="sub ui-rise" style="--i:2">
        When someone opens a course test, their request pops up on your screen and waits here.
        You decide how many attempts they get. Once those are used, they ask again.
      </p>
    </div>
    <div class="seg ui-rise" style="--i:3" role="tablist">
      <button class:on={tab === 'pending'} on:click={() => { tab = 'pending'; load(); }}>
        Waiting <span class="n" class:live={$pendingRequests.length > 0}>{$pendingRequests.length}</span>
      </button>
      <button class:on={tab === 'decided'} on:click={() => { tab = 'decided'; load(); }}>Decided</button>
    </div>
  </header>

  {#if error}<p class="error"><Icon name="alert" size={16} /> {error}</p>{/if}

  {#if loading && !rows.length}
    <div class="list">
      {#each Array(4) as _}<div class="ui-skeleton" style="height:78px;border-radius:22px"></div>{/each}
    </div>
  {:else if !rows.length}
    <div class="empty ui-rise">
      <span class="e-ico"><Icon name={tab === 'pending' ? 'bell' : 'clipboard'} size={26} /></span>
      <p>{tab === 'pending' ? 'No one is waiting. New requests pop up on your screen as they arrive.' : 'Nothing decided yet.'}</p>
    </div>
  {:else}
    {#key tab}
      <div class="list">
        {#each rows as r, n (r.id)}
          <div class="req ui-rise" style="--i:{Math.min(n, 10)}" class:waiting={r.status === 'pending'}>
            <span class="av {tone(r.id)}">{initials(r.full_name)}</span>
            <div class="body">
              <div class="t">{r.full_name} <span class="muted">wants to take</span> {r.test_title}</div>
              <div class="s">
                <span class="chip"><Icon name="users" size={13} /> {r.team ?? 'No team'}</span>
                {#if r.course_title}<span class="chip"><Icon name="layers" size={13} /> {r.course_title}</span>{/if}
                <span class="chip prog">
                  <span class="mini-bar"><span style="--p:{r.course_progress}%"></span></span>
                  watched {r.course_progress}%
                </span>
                <span class="chip"><Icon name="refresh" size={13} /> {r.previous_attempts ? `${r.previous_attempts} earlier attempts` : 'first attempt'}</span>
                <span class="chip"><Icon name="clock" size={13} /> {ago(r.created_at)}</span>
              </div>
            </div>
            <div class="acts">
              {#if r.status === 'pending'}
                <button class="btn-primary review" on:click={() => openRequest(r)}>
                  Review <Icon name="arrowRight" size={16} />
                </button>
              {:else if r.status === 'approved'}
                <span class="pill ok"><Icon name="check" size={13} /> Approved · {r.attempts_granted} attempt{r.attempts_granted === 1 ? '' : 's'}</span>
              {:else}
                <span class="pill bad" title={r.reason ?? ''}><Icon name="close" size={13} /> Denied{r.reason ? `: ${r.reason}` : ''}</span>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    {/key}
  {/if}
</div>

<style>
  .page { display: grid; gap: 1.25rem; }
  .head { display: flex; gap: 1.5rem; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; }
  h1 {
    font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.05;
    display: flex; align-items: center; gap: 0.6rem; margin: 0 0 0.6rem;
  }
  .title-mark {
    display: inline-grid; place-items: center; width: 46px; height: 46px; border-radius: 50%;
    background: var(--tile-butter); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark :global(svg) { animation: wiggle 600ms var(--ease-out); }
  .sub { color: var(--text-secondary); max-width: 62ch; font-size: 0.94rem; line-height: 1.55; }

  .seg { display: inline-flex; padding: 0.3rem; gap: 0.25rem; border-radius: 999px; background: var(--surface2); }
  .seg button {
    height: 38px; padding: 0 1.05rem; border-radius: 999px; font-weight: 600; font-size: 0.86rem; color: var(--muted);
    display: inline-flex; align-items: center; gap: 0.45rem;
  }
  .seg button:hover { color: var(--text); }
  .seg button.on { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); }
  .n {
    min-width: 22px; height: 20px; padding: 0 6px; border-radius: 99px; font-size: 0.72rem;
    display: inline-grid; place-items: center; background: var(--surface3); color: var(--text-secondary);
  }
  .n.live { background: var(--brand); color: var(--on-accent); animation: pop 360ms var(--ease-out); }

  .error {
    display: flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1rem; border-radius: 18px;
    background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); font-weight: 600; font-size: 0.88rem;
  }
  .muted { color: var(--muted); font-weight: 400; }
  .empty {
    display: flex; flex-direction: column; align-items: center; gap: 0.8rem; text-align: center;
    padding: 2.75rem 1rem; border-radius: 30px; background: var(--surface); color: var(--muted);
  }
  .e-ico {
    width: 62px; height: 62px; border-radius: 50%; display: grid; place-items: center;
    background: var(--tile-sky); color: var(--tile-ink); animation: float 4s var(--ease-in-out) infinite;
  }

  .list { display: grid; gap: 0.65rem; }
  .req {
    display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 1rem; align-items: center;
    padding: 0.9rem 1rem 0.9rem 0.9rem; background: var(--surface); border-radius: 24px; box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .req:hover { translate: 4px 0; box-shadow: var(--shadow); }
  @media (max-width: 640px) { .req { grid-template-columns: auto minmax(0, 1fr); } .acts { grid-column: 1 / -1; } }
  .av {
    position: relative; display: grid; place-items: center; width: 46px; height: 46px; border-radius: 50%;
    font-weight: 700; font-size: 0.85rem; color: var(--tile-ink);
    transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .req:hover .av { rotate: -10deg; scale: 1.06; }
  .waiting .av::after {
    content: ''; position: absolute; top: 0; right: 0; width: 11px; height: 11px; border-radius: 50%;
    background: var(--brand); border: 2px solid var(--surface); animation: pulse-ring 1.6s var(--ease-out) infinite;
  }
  .sky { background: var(--tile-sky); }
  .lilac { background: var(--tile-lilac); }
  .mint { background: var(--tile-mint); }
  .butter { background: var(--tile-butter); }
  .peach { background: var(--tile-peach); }
  .t { font-weight: 600; font-size: 0.98rem; }
  .s { display: flex; flex-wrap: wrap; gap: 0.35rem; margin-top: 0.45rem; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 24px; padding: 0 0.6rem; border-radius: 99px;
    background: var(--surface2); color: var(--text-secondary); font-size: 0.74rem; font-weight: 500;
  }
  .mini-bar { width: 38px; height: 5px; border-radius: 99px; background: var(--surface3); overflow: hidden; }
  .mini-bar span {
    display: block; height: 100%; width: var(--p); background: var(--success); border-radius: inherit;
    transform-origin: left; animation: grow 900ms var(--ease-out) 300ms backwards;
  }
  @keyframes grow { from { transform: scaleX(0); } }
  .review :global(.icon) { transition: translate var(--dur-3) var(--ease-out); }
  .review:hover :global(.icon) { translate: 3px 0; }
  .pill {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 30px; padding: 0 0.8rem; border-radius: 99px;
    font-size: 0.78rem; font-weight: 600; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .pill.ok { background: var(--tile-mint); color: var(--tile-ink); }
  .pill.bad { background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); }
</style>
