<script lang="ts">
  import { moduleHref, type Module } from '$lib/api/client';
  import Icon from './Icon.svelte';
  import { tilt } from '$lib/actions/auto-motion';
  export let module: Module | null = null;
  /** Show the upload shortcut on the empty state (admins only). */
  export let canUpload = false;

  $: hasImage = !!module?.thumbnail_url && module.thumbnail_url !== '/placeholder-thumb.svg';
</script>

{#if module}
  <!-- Text sits on a solid surface, image on its own side: readable in both
       themes without a dark overlay. -->
  <article class="hero ui-rise">
    <div class="copy">
      <span class="eyebrow"><span class="dot"></span> Featured for you</span>
      {#if module.category}<span class="badge badge-category">{module.category}</span>{/if}
      <h2>{module.title}</h2>
      <p class="desc">{module.description || 'Start learning with this module.'}</p>
      <div class="actions">
        <a href={moduleHref(module)} class="btn-primary play-btn">
          <span class="play-ico"><Icon name="play" size={14} stroke={0} /></span> Start learning
        </a>
        <a href={moduleHref(module)} class="btn-ghost">Details</a>
      </div>
    </div>
    <a class="art" href={moduleHref(module)} tabindex="-1" aria-hidden="true" use:tilt={{ max: 5 }}>
      {#if hasImage}
        <img src={module.thumbnail_url} alt="" loading="lazy" />
      {:else}
        <span class="art-fallback"><Icon name="film" size={54} stroke={1.4} /></span>
      {/if}
      {#if module.total_episodes > 1}<span class="eps">{module.total_episodes} episodes</span>{/if}
    </a>
  </article>
{:else}
  <article class="hero empty ui-rise">
    <div class="copy">
      <span class="eyebrow"><span class="dot"></span> Getting started</span>
      <h2>Welcome to Champ LMS</h2>
      <p class="desc">Your learning plan appears here as soon as courses are published.</p>
      {#if canUpload}
        <div class="actions">
          <a href="/admin/upload" class="btn-primary">Upload the first video <Icon name="arrowRight" size={17} /></a>
        </div>
      {/if}
    </div>
  </article>
{/if}

<style>
  .hero {
    display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
    gap: 1.25rem; align-items: stretch;
    padding: 0.75rem;
    background: var(--surface); border-radius: 32px; box-shadow: var(--shadow-sm);
    margin-bottom: 2.75rem;
  }
  .copy { display: flex; flex-direction: column; align-items: flex-start; gap: 0.75rem; padding: 1.9rem 1.4rem 1.6rem 1.6rem; }
  .eyebrow { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.8rem; font-weight: 600; color: var(--muted); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--path); animation: pulse-ring 1.6s var(--ease-out) infinite; }
  h2 { font-size: clamp(1.6rem, 1.1rem + 1.6vw, 2.4rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.08; }
  .desc {
    color: var(--muted); font-size: 0.98rem; line-height: 1.6; max-width: 46ch;
    display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  }
  .actions { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-top: auto; padding-top: 0.6rem; }
  .play-ico {
    width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center;
    background: var(--on-accent); color: var(--accent); margin-left: -0.6rem;
    transition: transform var(--dur-3) var(--ease-out);
  }
  .play-ico :global(svg) { fill: currentColor; translate: 1px 0; }
  .play-btn:hover .play-ico { transform: scale(1.15) rotate(-8deg); }

  .art {
    position: relative; display: block; overflow: hidden;
    border-radius: 24px; min-height: 280px; background: var(--tile-sky);
  }
  .art img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transition: transform 900ms var(--ease-out); }
  .hero:hover .art img { transform: scale(1.05); }
  .art-fallback { position: absolute; inset: 0; display: grid; place-items: center; color: var(--tile-ink); opacity: 0.55; }
  .eps {
    position: absolute; left: 14px; bottom: 14px;
    padding: 0.35rem 0.8rem; border-radius: 99px;
    background: var(--surface); color: var(--text); font-size: 0.78rem; font-weight: 600;
  }
  .hero.empty { grid-template-columns: 1fr; background: var(--tile-mint); color: var(--tile-ink); }
  .hero.empty .desc, .hero.empty .eyebrow { color: color-mix(in srgb, var(--tile-ink) 70%, transparent); }

  @media (max-width: 820px) {
    .hero { grid-template-columns: 1fr; }
    .art { order: -1; min-height: 200px; }
    .copy { padding: 1.1rem 0.9rem 1rem; }
  }
</style>
