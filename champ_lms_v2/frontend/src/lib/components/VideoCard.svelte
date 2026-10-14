<script lang="ts">
  import { moduleHref, type Module } from '$lib/api/client';
  import Icon from './Icon.svelte';
  import Thumb from './Thumb.svelte';
  export let module: Module;
  export let progress: number = 0; // 0-100

  // No thumbnail: a pastel tile picked from the title, so the same course is
  // always the same colour.
  const TONES = ['sky', 'mint', 'lilac', 'butter', 'peach'];
  function tone(title: string) {
    let hash = 0;
    for (let i = 0; i < title.length; i++) hash = title.charCodeAt(i) + ((hash << 5) - hash);
    return TONES[Math.abs(hash) % TONES.length];
  }

  $: hasThumbnail = !!module.thumbnail_url && module.thumbnail_url !== '/placeholder-thumb.svg';
  let broken = false;
  // A reused card with a new module gets another go at its thumbnail.
  $: module.thumbnail_url, (broken = false);
</script>

<a href={moduleHref(module)} class="card">
  <div class="thumb-wrap tone-{tone(module.title)}">
    {#if hasThumbnail && !broken}
      <Thumb src={module.thumbnail_url} on:error={() => (broken = true)} />
    {:else}
      <span class="initial" aria-hidden="true">{module.title.trim()[0]?.toUpperCase() ?? '•'}</span>
    {/if}

    {#if module.category}<span class="cat">{module.category}</span>{/if}

    <span class="scrim" aria-hidden="true"></span>
    <span class="cta" aria-hidden="true">
      <span class="cta-ico"><Icon name={progress >= 100 ? 'refresh' : 'play'} size={13} stroke={progress >= 100 ? 2.2 : 0} /></span>
      {progress >= 100 ? 'Watch again' : progress > 0 ? 'Resume' : 'Start watching'}
    </span>

    {#if progress > 0}
      <span class="progress"><span style="--p:{progress}%"></span></span>
    {/if}
  </div>

  <!-- Title then meta pinned to the bottom; the row stretches every card to
       the tallest one, so a row stays one even height. -->
  <div class="info">
    <p class="title">{module.title}</p>
    <span class="meta">
      <span><Icon name="film" size={14} /> {module.total_episodes} episode{module.total_episodes === 1 ? '' : 's'}</span>
      <span class="end">
        {#if progress >= 100}
          <span class="state done"><Icon name="check" size={13} /> Done</span>
        {:else if progress > 0}
          <span class="state">{progress}%</span>
        {/if}
        <span class="go" aria-hidden="true"><Icon name="arrowRight" size={13} stroke={2} /></span>
      </span>
    </span>
  </div>
</a>

<style>
  .card {
    display: flex; flex-direction: column;
    width: 250px; height: 100%; flex-shrink: 0;
    padding: 0.45rem 0.45rem 0.7rem;
    background: var(--surface); border-radius: 22px; box-shadow: var(--shadow-sm);
    transition: transform var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  /* Hover: the card lifts with a hairline ring, the art zooms under a dark
     scrim and a "Start / Resume" pill rises into the middle of it. */
  .card:hover, .card:focus-visible {
    transform: translateY(-6px);
    box-shadow: var(--shadow-lg), 0 0 0 1px var(--border-hover);
  }
  .card:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }

  /* 16:9, the shape of the videos themselves, so thumbnails aren't cropped. */
  .thumb-wrap {
    position: relative; aspect-ratio: 16 / 9; border-radius: 17px; overflow: hidden;
    display: grid; place-items: center;
  }
  .tone-sky { background: var(--tile-sky); }
  .tone-mint { background: var(--tile-mint); }
  .tone-lilac { background: var(--tile-lilac); }
  .tone-butter { background: var(--tile-butter); }
  .tone-peach { background: var(--tile-peach); }
  .card:hover :global(.thumb-media), .card:focus-visible :global(.thumb-media) { scale: 1.07; }
  .initial {
    font-size: 2.8rem; font-weight: 700; color: var(--tile-ink); opacity: 0.35; letter-spacing: -0.04em;
    transition: transform var(--dur-3) var(--ease-out), opacity var(--dur-3) var(--ease-out);
  }
  .card:hover .initial, .card:focus-visible .initial { transform: scale(1.15) rotate(-6deg); opacity: 0.22; }

  .cat {
    position: absolute; left: 8px; top: 8px; z-index: 1; max-width: calc(100% - 16px);
    padding: 0.2rem 0.55rem; border-radius: 99px;
    background: color-mix(in srgb, var(--surface) 92%, transparent); color: var(--text);
    font-size: 0.66rem; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }

  .scrim {
    position: absolute; inset: 0; pointer-events: none;
    background: linear-gradient(to top, rgba(8, 8, 10, 0.62), rgba(8, 8, 10, 0.18) 55%, rgba(8, 8, 10, 0.05));
    opacity: 0; transition: opacity var(--dur-3) var(--ease-out);
  }
  .card:hover .scrim, .card:focus-visible .scrim { opacity: 1; }

  /* Frame colours, not surface: the pill sits on the dark scrim in both themes. */
  .cta {
    position: absolute; left: 50%; top: 50%;
    display: inline-flex; align-items: center; gap: 0.45rem;
    padding: 0.35rem 0.9rem 0.35rem 0.35rem; border-radius: var(--radius-pill);
    background: var(--on-frame); color: var(--frame);
    font-size: 0.78rem; font-weight: 700; white-space: nowrap;
    box-shadow: 0 10px 24px -8px rgba(0, 0, 0, 0.5);
    opacity: 0; transform: translate(-50%, -30%) scale(0.9);
    transition: opacity var(--dur-2) var(--ease-out), transform var(--dur-3) var(--ease-out);
  }
  .cta-ico {
    width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
    background: var(--brand); color: #fff;
  }
  .cta-ico :global(svg[stroke-width="0"]) { fill: currentColor; }
  .card:hover .cta, .card:focus-visible .cta { opacity: 1; transform: translate(-50%, -50%); }

  .progress { position: absolute; left: 10px; right: 10px; bottom: 10px; height: 4px; border-radius: 99px; background: color-mix(in srgb, var(--surface) 70%, transparent); overflow: hidden; }
  .progress span { display: block; height: 100%; width: var(--p); background: var(--accent); border-radius: inherit; transform-origin: left; animation: grow 900ms var(--ease-out) 200ms backwards; }
  @keyframes grow { from { transform: scaleX(0); } }

  .info { flex: 1; display: flex; flex-direction: column; gap: 0.4rem; padding: 0.65rem 0.4rem 0; }
  .title {
    font-size: 0.94rem; font-weight: 600; line-height: 1.3; color: var(--text); letter-spacing: -0.01em;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .meta {
    margin-top: auto;
    display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;
    font-size: 0.76rem; color: var(--muted);
  }
  .meta > span { display: inline-flex; align-items: center; gap: 0.3rem; }
  .meta .end { gap: 0.45rem; }
  .state { font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
  .state.done { color: var(--success); }
  .go {
    width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
    background: var(--surface2); color: var(--text);
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2) var(--ease-out), transform var(--dur-3) var(--ease-out);
  }
  .card:hover .go, .card:focus-visible .go { background: var(--accent); color: var(--on-accent); transform: rotate(-45deg); }

  @media (prefers-reduced-motion: reduce) {
    .card:hover, .card:focus-visible { transform: none; }
    .card:hover :global(.thumb-media), .card:hover .initial, .card:hover .go { transform: none; scale: none; }
    .cta, .card:hover .cta { transform: translate(-50%, -50%); }
  }

  @media (max-width: 768px) {
    .card { width: 210px; }
  }
</style>
