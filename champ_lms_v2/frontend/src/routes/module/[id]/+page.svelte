<script lang="ts">
  import { page } from '$app/stores';
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { api, type ModuleDetail } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import Thumb from '$lib/components/Thumb.svelte';
  import { tilt } from '$lib/actions/auto-motion';

  let module: ModuleDetail | null = null;
  let loading = true;
  let error = '';

  $: id = $page.params.id;

  onMount(async () => {
    try {
      module = await api.module(id);
      // Canvas courses have their own player.
      if (module.layout === 'canvas') { goto(`/course/${id}`, { replaceState: true }); return; }
    } catch (e: any) {
      error = e.message;
    } finally {
      loading = false;
    }
  });

  function formatDuration(secs: number | null) {
    if (!secs) return '';
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  }

  $: hasImage = !!module?.thumbnail_url && module.thumbnail_url !== '/placeholder-thumb.svg';
  $: totalSecs = module ? module.episodes.reduce((a, e) => a + (e.duration_seconds ?? 0), 0) : 0;
  const TONES = ['sky', 'lilac', 'mint', 'butter', 'peach'];
</script>

<svelte:head>
  <title>{module?.title ?? 'Module'} — Champ LMS</title>
</svelte:head>

{#if loading}
  <div class="sk-hero">
    <div class="sk-copy">
      <div class="ui-skeleton" style="height:22px;width:30%;border-radius:99px"></div>
      <div class="ui-skeleton" style="height:44px;width:85%;border-radius:12px"></div>
      <div class="ui-skeleton" style="height:16px;width:70%;border-radius:8px"></div>
      <div class="ui-skeleton" style="height:48px;width:45%;border-radius:99px;margin-top:auto"></div>
    </div>
    <div class="ui-skeleton" style="border-radius:24px;min-height:280px"></div>
  </div>
  {#each Array(4) as _}<div class="ui-skeleton" style="height:104px;border-radius:24px;margin-bottom:0.7rem"></div>{/each}
{:else if error}
  <div class="state ui-rise">
    <span class="state-ico danger"><Icon name="alert" size={28} /></span>
    <h2>Couldn't open this module</h2>
    <p>{error}</p>
    <a href="/" class="btn-ghost"><Icon name="arrowLeft" size={16} /> Back to home</a>
  </div>
{:else if module}
  <div class="module-page">
    <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: module.title }]} />

    <article class="hero ui-rise" style="--i:1">
      <div class="copy">
        <div class="chips">
          {#if module.category}<span class="ui-pill sky cat">{module.category}</span>{/if}
          <span class="ui-pill"><Icon name="film" size={14} /> {module.episodes.length} episode{module.episodes.length === 1 ? '' : 's'}</span>
          {#if totalSecs}<span class="ui-pill"><Icon name="clock" size={14} /> {Math.max(1, Math.round(totalSecs / 60))} min</span>{/if}
        </div>
        <h1>{module.title}</h1>
        {#if module.description}
          <p class="desc">{module.description}</p>
        {/if}
        {#if module.tags?.length}
          <div class="tags">
            {#each module.tags as tag, n}
              <span class="tag" style="--i:{n}"><Icon name="hash" size={12} />{tag}</span>
            {/each}
          </div>
        {/if}
        {#if module.episodes.length}
          <div class="actions">
            <a href="/watch/{module.episodes[0].id}?module={module.id}" class="btn-primary play-btn">
              <span class="play-ico"><Icon name="play" size={13} stroke={0} /></span> Play episode 1
            </a>
          </div>
        {/if}
      </div>
      <div class="art" use:tilt={{ max: 5 }}>
        {#if hasImage}
          <Thumb src={module.thumbnail_url} eager />
        {:else}
          <span class="art-fallback"><Icon name="film" size={54} stroke={1.4} /></span>
        {/if}
      </div>
    </article>

    <section class="episodes">
      <div class="sec-head ui-rise" style="--i:2">
        <h2>Episodes</h2>
        <span class="count">{module.episodes.length}</span>
      </div>
      <div class="episode-list">
        {#each module.episodes as ep, n}
          <a href="/watch/{ep.id}?module={module.id}" class="ep-card ui-rise" style="--i:{Math.min(n + 3, 10)}" class:disabled={ep.status !== 'ready'}>
            <div class="ep-thumb {TONES[n % TONES.length]}">
              {#if ep.thumbnail_url}
                <Thumb src={ep.thumbnail_url} alt={ep.title} />
              {:else}
                <div class="ep-thumb-placeholder">{ep.sequence_order}</div>
              {/if}
              <span class="t-play" aria-hidden="true"><Icon name="play" size={15} stroke={0} /></span>
              {#if ep.status === 'processing'}
                <span class="status-badge"><span class="spin"></span> Processing</span>
              {/if}
              {#if ep.duration_seconds}<span class="dur">{formatDuration(ep.duration_seconds)}</span>{/if}
            </div>
            <div class="ep-info">
              <span class="ep-num">Episode {ep.sequence_order}</span>
              <p class="ep-title">{ep.title}</p>
              {#if ep.description}
                <p class="ep-desc">{ep.description}</p>
              {/if}
            </div>
            <span class="ui-round ink go" aria-hidden="true"><Icon name="play" size={15} stroke={0} /></span>
          </a>
        {/each}
      </div>
    </section>
  </div>
{/if}

<style>
  .module-page { max-width: 1080px; margin: 0 auto; }

  /* ---------- hero ---------- */
  .hero, .sk-hero {
    display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr); align-items: center; gap: 1.25rem;
    padding: 0.75rem; border-radius: 32px; background: var(--surface); box-shadow: var(--shadow-sm);
    margin-bottom: 2rem;
  }
  .sk-copy { display: flex; flex-direction: column; gap: 0.9rem; padding: 1.8rem 1.4rem; min-height: 280px; }
  .copy { display: flex; flex-direction: column; align-items: flex-start; gap: 0.8rem; padding: 1.8rem 1.4rem 1.5rem 1.6rem; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .cat { text-transform: capitalize; }
  h1 { font-size: clamp(1.7rem, 1.1rem + 1.8vw, 2.6rem); font-weight: 700; letter-spacing: -0.035em; line-height: 1.06; }
  .desc { color: var(--muted); font-size: 0.98rem; line-height: 1.6; max-width: 52ch; }
  .tags { display: flex; flex-wrap: wrap; gap: 0.35rem; }
  .tag {
    display: inline-flex; align-items: center; gap: 0.2rem;
    padding: 0.25rem 0.6rem; border-radius: 99px; background: var(--surface2);
    font-size: 0.76rem; font-weight: 500; color: var(--text-secondary);
    animation: pop 420ms var(--ease-out) backwards; animation-delay: calc(300ms + var(--i) * 50ms);
    transition: background-color var(--dur-2), translate var(--dur-2) var(--ease-out);
  }
  .tag:hover { background: var(--surface3); translate: 0 -1px; }
  .actions { margin-top: auto; padding-top: 0.6rem; }
  .play-ico {
    width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
    background: var(--on-accent); color: var(--accent); margin-left: -0.6rem;
    transition: transform var(--dur-3) var(--ease-out);
  }
  .play-ico :global(svg) { fill: currentColor; translate: 1px 0; }
  .play-btn:hover .play-ico { transform: scale(1.15) rotate(-8deg); }
  /* 16:9 like the video, so the thumbnail is shown whole, not cropped to the copy's height. */
  .art { position: relative; overflow: hidden; border-radius: 24px; aspect-ratio: 16 / 9; background: var(--tile-lilac); }
  .hero:hover .art :global(.thumb-media) { scale: 1.05; }
  .art-fallback { position: absolute; inset: 0; display: grid; place-items: center; color: var(--tile-ink); opacity: 0.55; }

  /* ---------- episodes ---------- */
  .sec-head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 1rem; }
  .sec-head h2 { font-size: 1.45rem; letter-spacing: -0.025em; }
  .count {
    min-width: 28px; height: 26px; padding: 0 8px; border-radius: 99px; display: inline-grid; place-items: center;
    background: var(--accent); color: var(--on-accent); font-size: 0.8rem; font-weight: 700;
    animation: pop 420ms var(--ease-out) 300ms backwards;
  }
  .episode-list { display: flex; flex-direction: column; gap: 0.7rem; }
  .ep-card {
    display: flex; align-items: center; gap: 1.1rem;
    background: var(--surface); border-radius: 24px; box-shadow: var(--shadow-sm);
    padding: 0.6rem 1rem 0.6rem 0.6rem; color: var(--text);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .ep-card:hover { translate: 4px 0; box-shadow: var(--shadow); }
  .ep-card.disabled { opacity: 0.55; pointer-events: none; }
  .ep-thumb {
    width: 180px; flex-shrink: 0; aspect-ratio: 16/9;
    border-radius: 18px; overflow: hidden; position: relative; color: var(--tile-ink);
  }
  .sky { background: var(--tile-sky); } .lilac { background: var(--tile-lilac); } .mint { background: var(--tile-mint); }
  .butter { background: var(--tile-butter); } .peach { background: var(--tile-peach); }
  .ep-card:hover .ep-thumb :global(.thumb-media) { scale: 1.08; }
  .ep-thumb-placeholder {
    width: 100%; height: 100%; display: grid; place-items: center;
    font-size: 1.8rem; font-weight: 700; letter-spacing: -0.03em; opacity: 0.7;
  }
  .t-play {
    position: absolute; inset: 0; margin: auto; width: 38px; height: 38px; border-radius: 50%;
    display: grid; place-items: center; background: var(--surface); color: var(--text);
    opacity: 0; scale: 0.6; transition: opacity var(--dur-2) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .t-play :global(svg), .go :global(svg) { fill: currentColor; translate: 1px 0; }
  .ep-card:hover .t-play { opacity: 1; scale: 1; }
  .status-badge {
    position: absolute; top: 8px; left: 8px; display: inline-flex; align-items: center; gap: 0.35rem;
    background: rgba(10, 10, 12, 0.75); color: #f4f4f6; font-size: 0.68rem; font-weight: 600;
    padding: 0.2rem 0.5rem; border-radius: 99px;
  }
  .spin { width: 9px; height: 9px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.35); border-top-color: #fff; animation: spin 0.9s linear infinite; }
  @keyframes spin { to { rotate: 360deg; } }
  .dur {
    position: absolute; right: 8px; bottom: 8px; padding: 0.1rem 0.45rem; border-radius: 6px;
    background: rgba(10, 10, 12, 0.72); color: #f4f4f6; font-size: 0.7rem; font-weight: 600; font-variant-numeric: tabular-nums;
  }
  .ep-info { flex: 1; min-width: 0; }
  .ep-num { font-size: 0.72rem; color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.07em; }
  .ep-title { font-weight: 600; font-size: 1.02rem; margin: 0.2rem 0; }
  .ep-desc {
    font-size: 0.84rem; color: var(--muted); line-height: 1.45;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .go { width: 40px; height: 40px; flex-shrink: 0; transition: transform var(--dur-3) var(--ease-out), background-color var(--dur-2); }
  .ep-card:hover .go { transform: scale(1.1) rotate(-8deg); }

  /* ---------- states ---------- */
  .state { display: flex; flex-direction: column; align-items: center; gap: 0.75rem; text-align: center; padding: 3rem 1.5rem; border-radius: 32px; background: var(--surface); }
  .state h2 { font-size: 1.35rem; }
  .state p { color: var(--muted); margin-bottom: 0.5rem; }
  .state-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; animation: pop 520ms var(--ease-out); }
  .state-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }

  @media (max-width: 820px) {
    .hero, .sk-hero { grid-template-columns: 1fr; }
    .art { order: -1; }
    .copy { padding: 1.1rem 0.9rem 1rem; }
  }
  @media (max-width: 560px) {
    .ep-thumb { width: 120px; }
    .go { display: none; }
    .ep-desc { -webkit-line-clamp: 1; line-clamp: 1; }
  }
</style>
