<script lang="ts">
  // The home page's Shorts row: tall cards that open the feed on that short.
  // Shows nothing at all until there is at least one short.
  import { onMount } from 'svelte';
  import { api, type ShortItem } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';

  export let query = '';
  let shorts: ShortItem[] = [];
  onMount(async () => {
    try { shorts = (await api.shorts()).slice(0, 12); } catch { /* the row just stays hidden */ }
  });
  $: q = query.trim().toLowerCase();
  $: shown = q ? shorts.filter(s => s.title.toLowerCase().includes(q)) : shorts;
  const compact = (n: number) => n < 1000 ? String(n) : `${(n / 1000).toFixed(1).replace(/\.0$/, '')}K`;
</script>

{#if shown.length}
  <section class="shelf" aria-label="Shorts">
    <div class="sh-head">
      <h2><span class="sh-ico"><Icon name="shorts" size={18} /></span> Shorts</h2>
      <a href="/shorts" class="all">Watch all <Icon name="arrowRight" size={14} /></a>
    </div>
    <div class="track">
      {#each shown as s (s.id)}
        <a class="card" href="/shorts?s={s.id}">
          <span class="art">
            {#if s.poster_url}
              {#if s.aspect !== '9:16'}<img class="bg" src={s.poster_url} alt="" loading="lazy" />{/if}
              <img class="poster" class:cover={s.aspect === '9:16'} src={s.poster_url} alt="" loading="lazy" />
            {:else}<span class="ph"><Icon name="shorts" size={30} stroke={1.4} /></span>{/if}
            {#if !s.seen}<span class="new">New</span>{/if}
            <span class="play"><Icon name="play" size={16} stroke={0} /></span>
          </span>
          <b>{s.title}</b>
          <small>{compact(s.view_count)} {s.view_count === 1 ? 'viewer' : 'viewers'}</small>
        </a>
      {/each}
    </div>
  </section>
{/if}

<style>
  .shelf { margin-bottom: 2rem; }
  .sh-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.9rem; }
  h2 { font-size: 1.35rem; letter-spacing: -0.025em; display: flex; align-items: center; gap: 0.55rem; }
  .sh-ico { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-peach); color: var(--tile-ink); }
  .all { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.86rem; font-weight: 600; color: var(--text-secondary); }
  .all:hover { color: var(--text); }
  .track { display: grid; grid-auto-flow: column; grid-auto-columns: 168px; gap: 0.85rem; overflow-x: auto; padding-bottom: 0.5rem; scroll-snap-type: x proximity; scrollbar-width: thin; }
  .card { display: flex; flex-direction: column; gap: 0.3rem; scroll-snap-align: start; color: var(--text); }
  .art { position: relative; display: block; aspect-ratio: 9 / 16; border-radius: 18px; overflow: hidden; background: #0b0b0d; box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out); }
  .card:hover .art { translate: 0 -3px; box-shadow: var(--shadow-md); }
  .bg { position: absolute; inset: -10%; width: 120%; height: 120%; object-fit: cover; filter: blur(18px) brightness(0.6); }
  .poster { position: relative; width: 100%; height: 100%; object-fit: contain; }
  .poster.cover { object-fit: cover; }
  .ph { position: absolute; inset: 0; display: grid; place-items: center; color: rgba(255,255,255,.4); }
  .new { position: absolute; top: 8px; left: 8px; padding: 0.15rem 0.5rem; border-radius: 99px; background: var(--brand); color: #fff; font-size: 0.68rem; font-weight: 700; }
  .play { position: absolute; right: 8px; bottom: 8px; width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: rgba(0,0,0,.55); color: #fff; opacity: 0; transition: opacity var(--dur-2); }
  .card:hover .play { opacity: 1; }
  b { font-size: 0.86rem; font-weight: 600; line-height: 1.3; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  small { font-size: 0.76rem; color: var(--muted); }
  @media (max-width: 640px) { .track { grid-auto-columns: 132px; } }
</style>
