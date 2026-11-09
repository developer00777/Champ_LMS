<script lang="ts">
  // The Shorts feed: one short at a time, full height, swipe or scroll (or
  // the arrow keys) to the next. ?s=<id> opens on that short, and the address
  // follows along so any short can be shared from the bar.
  import { onDestroy, onMount, tick } from 'svelte';
  import { page } from '$app/stores';
  import { replaceState } from '$app/navigation';
  import { api, moduleHref, type ShortItem } from '$lib/api/client';
  import { isAdmin } from '$lib/stores/auth';
  import Icon from '$lib/components/Icon.svelte';
  import ShortPlayer from '$lib/components/shorts/ShortPlayer.svelte';
  import { ratioLabel } from '$lib/utils/resize-video';

  const MUTE_KEY = 'champ_shorts_muted';

  let shorts: ShortItem[] = [];
  let loading = true;
  let error = '';
  let active = 0;
  let scroller: HTMLElement;
  let slots: HTMLElement[] = [];
  let players: ShortPlayer[] = [];
  let muted = false;
  let blocked = false; // autoplay with sound was refused: show "Tap to unmute"
  let pausedNow = true;
  let expanded: Record<string, boolean> = {};

  try { muted = localStorage.getItem(MUTE_KEY) === '1'; } catch { /* storage blocked */ }

  let observer: IntersectionObserver | null = null;
  onMount(async () => {
    const start = $page.url.searchParams.get('s') ?? undefined;
    try {
      shorts = await api.shorts(start);
      if (start && shorts[0]?.id !== start) {
        // A hidden or still-encoding short (an admin checking one) is fetched on its own.
        try { const one = await api.short(start); shorts = [one, ...shorts.filter(s => s.id !== one.id)]; } catch { /* gone */ }
      }
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
    await tick();
    observer = new IntersectionObserver(entries => {
      for (const en of entries) {
        if (en.isIntersecting && en.intersectionRatio >= 0.6) {
          const i = slots.indexOf(en.target as HTMLElement);
          if (i >= 0 && i !== active) setActive(i);
        }
      }
    }, { root: scroller, threshold: [0.6] });
    slots.forEach(s => s && observer!.observe(s));
    if (shorts.length) syncUrl();
  });
  onDestroy(() => observer?.disconnect());

  function setActive(i: number) { active = i; syncUrl(); }
  function syncUrl() {
    const s = shorts[active];
    if (!s) return;
    const url = new URL($page.url);
    url.searchParams.set('s', s.id);
    try { replaceState(url, {}); } catch { /* before the router is ready */ }
  }

  function go(by: number) {
    const i = Math.min(shorts.length - 1, Math.max(0, active + by));
    slots[i]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function setMuted(m: boolean) {
    muted = m; blocked = false;
    try { localStorage.setItem(MUTE_KEY, m ? '1' : '0'); } catch { /* storage blocked */ }
  }

  async function like(s: ShortItem, only = false) {
    if (only && s.liked) return;
    // Straight away on screen; the server's count settles it.
    s.liked = !s.liked; s.like_count += s.liked ? 1 : -1;
    shorts = shorts;
    try {
      const r = await api.likeShort(s.id);
      s.liked = r.liked; s.like_count = r.like_count; shorts = shorts;
    } catch {
      s.liked = !s.liked; s.like_count += s.liked ? 1 : -1; shorts = shorts;
    }
  }

  let toast = '';
  let toastTimer: ReturnType<typeof setTimeout>;
  async function share(s: ShortItem) {
    const url = `${location.origin}/shorts?s=${s.id}`;
    try {
      if (navigator.share && matchMedia('(pointer: coarse)').matches) { await navigator.share({ title: s.title, url }); return; }
      await navigator.clipboard.writeText(url);
      say('Link copied');
    } catch { say(url); }
  }
  function say(m: string) { toast = m; clearTimeout(toastTimer); toastTimer = setTimeout(() => (toast = ''), 2200); }

  function onKey(e: KeyboardEvent) {
    if ((e.target as HTMLElement).closest('input, textarea, [contenteditable]')) return;
    if (e.key === 'ArrowDown' || e.key === 'j' || e.key === 'PageDown') { e.preventDefault(); go(1); }
    else if (e.key === 'ArrowUp' || e.key === 'k' || e.key === 'PageUp') { e.preventDefault(); go(-1); }
    else if (e.key === ' ') { e.preventDefault(); players[active]?.toggle(); }
    else if (e.key === 'm') setMuted(!muted);
  }

  const compact = (n: number) => n < 1000 ? String(n) : n < 1e6 ? `${(n / 1000).toFixed(n < 1e4 ? 1 : 0).replace(/\.0$/, '')}K` : `${(n / 1e6).toFixed(1).replace(/\.0$/, '')}M`;
  // The API's times are UTC but carry no zone; read without one, a browser
  // would take them as local time.
  const ago = (iso: string) => {
    const at = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
    const d = (Date.now() - at.getTime()) / 1000;
    if (d < 3600) return `${Math.max(1, Math.round(d / 60))} min ago`;
    if (d < 86400) return `${Math.round(d / 3600)} h ago`;
    if (d < 86400 * 30) return `${Math.round(d / 86400)} d ago`;
    return at.toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  };
</script>

<svelte:head><title>{shorts[active]?.title ?? 'Shorts'} — Champ LMS</title></svelte:head>
<svelte:window on:keydown={onKey} />

<div class="feed-wrap" data-no-motion>
  {#if loading}
    <div class="center"><div class="ui-skeleton sk"></div></div>
  {:else if error}
    <div class="center"><div class="state"><span class="s-ico bad"><Icon name="alert" size={26} /></span><h2>Shorts didn't load</h2><p>{error}</p>
      <button class="btn-primary" on:click={() => location.reload()}>Try again</button></div></div>
  {:else if !shorts.length}
    <div class="center"><div class="state">
      <span class="s-ico"><Icon name="shorts" size={28} /></span>
      <h2>No shorts yet</h2>
      <p>Short videos from your trainers will show up here: quick tips, demos and course recaps you can swipe through.</p>
      {#if $isAdmin}<a class="btn-primary" href="/admin/shorts"><Icon name="plus" size={17} /> Add a short</a>{/if}
    </div></div>
  {:else}
    <div class="feed" bind:this={scroller} aria-label="Shorts" role="feed">
      {#each shorts as s, i (s.id)}
        <article class="slot" bind:this={slots[i]} aria-label={s.title} aria-posinset={i + 1} aria-setsize={shorts.length}>
          <div class="unit">
            <div class="frame">
              <ShortPlayer bind:this={players[i]} short={s} active={i === active} warm={Math.abs(i - active) <= 1} {muted}
                on:autoplaymuted={() => { muted = true; blocked = true; }}
                on:doubletap={() => like(s, true)}
                on:paused={e => { if (i === active) pausedNow = e.detail; }}>
                <!-- top: play / pause and sound, as on YouTube's desktop player -->
                <div class="top">
                  <button class="ctl" on:click={() => players[i]?.toggle()} aria-label={i === active && !pausedNow ? 'Pause' : 'Play'}>
                    {#if i === active && !pausedNow}<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>
                    {:else}<svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M8 5.5v13l10.5-6.5z"/></svg>{/if}
                  </button>
                  <button class="ctl" on:click={() => setMuted(!muted)} aria-label={muted ? 'Unmute' : 'Mute'}>
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/>{#if muted}<path d="M16 9.5l5 5M21 9.5l-5 5"/>{:else}<path d="M15.5 9a4 4 0 010 6M18 6.5a7.5 7.5 0 010 11"/>{/if}</svg>
                  </button>
                  {#if s.aspect !== '9:16' && s.width && s.height}<span class="shape">{ratioLabel(s.width, s.height)}</span>{/if}
                </div>
                {#if blocked && i === active}
                  <button class="unmute" on:click={() => setMuted(false)}>
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/><path d="M16 9.5l5 5M21 9.5l-5 5"/></svg>
                    Tap to unmute
                  </button>
                {/if}
                <!-- bottom: who, what, and the course it comes from -->
                <div class="info">
                  <p class="by"><span class="mark">C</span> <b>Champ LMS</b> <span class="when">· {ago(s.created_at)}</span></p>
                  <h2 class="title">{s.title}</h2>
                  {#if s.description}
                    <button class="desc" class:open={expanded[s.id]} on:click={() => (expanded[s.id] = !expanded[s.id])}>{s.description}</button>
                  {/if}
                  {#if s.course}
                    <a class="course" href={moduleHref(s.course)}>
                      <Icon name="play" size={13} stroke={0} />
                      <span>Watch the course · <b>{s.course.title}</b></span>
                    </a>
                  {/if}
                </div>
              </ShortPlayer>
            </div>

            <div class="rail">
              <button class="act" class:on={s.liked} on:click={() => like(s)} aria-pressed={s.liked} aria-label={s.liked ? 'Unlike' : 'Like'}>
                <span class="disc">
                  <svg viewBox="0 0 24 24" width="24" height="24" fill={s.liked ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M7 10v11H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zM7 10l4-7.5a2.3 2.3 0 0 1 3 2.4L13.4 9H19a2 2 0 0 1 2 2.3l-1.3 7.6A2.5 2.5 0 0 1 17.3 21H7"/></svg>
                </span>
                <small>{s.like_count ? compact(s.like_count) : 'Like'}</small>
              </button>
              <span class="act static" title="People who watched it">
                <span class="disc"><Icon name="eye" size={22} /></span>
                <small>{compact(s.view_count)}</small>
              </span>
              <button class="act" on:click={() => share(s)} aria-label="Share">
                <span class="disc"><Icon name="share" size={22} /></span>
                <small>Share</small>
              </button>
              {#if s.course}
                <a class="act" href={moduleHref(s.course)} aria-label="Open the course {s.course.title}">
                  <span class="disc course-disc">
                    {#if s.course.thumbnail_url}<img src={s.course.thumbnail_url} alt="" />{:else}<Icon name="layers" size={20} />{/if}
                  </span>
                  <small>Course</small>
                </a>
              {/if}
            </div>
          </div>
        </article>
      {/each}
    </div>

    <div class="nav" aria-label="Move between shorts">
      <button class="nbtn" on:click={() => go(-1)} disabled={active === 0} aria-label="Previous short"><Icon name="chevronUp" size={22} /></button>
      <button class="nbtn" on:click={() => go(1)} disabled={active >= shorts.length - 1} aria-label="Next short"><Icon name="chevronDown" size={22} /></button>
    </div>
  {/if}
  {#if toast}<div class="toast" role="status">{toast}</div>{/if}
</div>

<style>
  /* Fills the canvas under the top bar: 76px bar + the page's own padding. */
  .feed-wrap { position: relative; height: calc(100dvh - 140px); min-height: 420px; }
  .center { height: 100%; display: grid; place-items: center; }
  .sk { height: 100%; aspect-ratio: 9 / 16; border-radius: 18px; }
  .state { max-width: 440px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 0.7rem; padding: 2.5rem 1.5rem; border-radius: 30px; background: var(--surface); box-shadow: var(--shadow-sm); }
  .state p { color: var(--muted); font-size: 0.9rem; }
  .s-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-peach); color: var(--tile-ink); }
  .s-ico.bad { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }

  .feed { height: 100%; overflow-y: auto; scroll-snap-type: y mandatory; overscroll-behavior: contain; scrollbar-width: none; }
  .feed::-webkit-scrollbar { display: none; }
  .slot { height: 100%; scroll-snap-align: start; scroll-snap-stop: always; display: grid; place-items: center; padding: 6px 0; }
  .unit { height: 100%; display: flex; align-items: flex-end; gap: 14px; }
  .frame {
    position: relative; height: 100%; aspect-ratio: 9 / 16; max-width: calc(100vw - 120px);
    border-radius: 18px; overflow: hidden; background: #000; box-shadow: var(--shadow-md);
  }

  .top { position: absolute; z-index: 5; top: 0; left: 0; right: 0; display: flex; gap: 6px; align-items: center; padding: 12px; background: linear-gradient(rgba(0,0,0,.45), transparent); pointer-events: none; }
  .ctl { pointer-events: auto; width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; color: #fff; background: rgba(0,0,0,.35); }
  .ctl:hover { background: rgba(0,0,0,.6); }
  .shape { margin-left: auto; padding: 0.2rem 0.55rem; border-radius: 99px; background: rgba(0,0,0,.45); color: #fff; font-size: 0.7rem; font-weight: 700; }
  .unmute {
    position: absolute; z-index: 6; top: 62px; left: 12px; display: inline-flex; align-items: center; gap: 0.45rem;
    height: 38px; padding: 0 0.9rem; border-radius: 99px; background: #fff; color: #111; font-size: 0.84rem; font-weight: 700;
    box-shadow: 0 8px 24px rgba(0,0,0,.35); animation: rise 360ms var(--ease-out);
  }

  .info {
    position: absolute; z-index: 5; left: 0; right: 0; bottom: 0; padding: 3.5rem 1rem 1.1rem; color: #fff;
    background: linear-gradient(transparent, rgba(0,0,0,.72)); pointer-events: none;
    display: flex; flex-direction: column; gap: 0.45rem; text-shadow: 0 1px 2px rgba(0,0,0,.4);
  }
  .info > * { pointer-events: auto; }
  .by { display: flex; align-items: center; gap: 0.4rem; font-size: 0.86rem; pointer-events: none; }
  .mark { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; background: #e50914; color: #fff; font-weight: 900; font-size: 0.85rem; text-shadow: none; }
  .when { opacity: 0.75; font-size: 0.8rem; }
  .title { font-size: 1rem; font-weight: 700; line-height: 1.3; letter-spacing: -0.01em; pointer-events: none; }
  .desc { text-align: left; color: rgba(255,255,255,.88); font-size: 0.84rem; line-height: 1.4; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; }
  .desc.open { -webkit-line-clamp: 8; }
  .course {
    align-self: flex-start; display: inline-flex; align-items: center; gap: 0.45rem; max-width: 100%;
    height: 34px; padding: 0 0.8rem; border-radius: 10px; background: rgba(255,255,255,.18); color: #fff; font-size: 0.8rem;
    backdrop-filter: blur(6px);
  }
  .course span { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .course:hover { background: rgba(255,255,255,.28); }

  .rail { display: flex; flex-direction: column; gap: 16px; padding-bottom: 8px; }
  .act { display: flex; flex-direction: column; align-items: center; gap: 4px; color: var(--text); }
  .act small { font-size: 0.76rem; font-weight: 600; font-variant-numeric: tabular-nums; }
  .disc { width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; background: var(--surface2); transition: background-color var(--dur-2), scale var(--dur-2) var(--ease-out); }
  .act:not(.static):hover .disc { background: var(--surface3); }
  .act:not(.static):active .disc { scale: 0.9; }
  .act.on .disc { background: var(--accent); color: var(--on-accent); animation: pop 420ms var(--ease-out); }
  .course-disc { overflow: hidden; border-radius: 12px; }
  .course-disc img { width: 100%; height: 100%; object-fit: cover; }

  .nav { position: absolute; right: 8px; top: 50%; translate: 0 -50%; display: flex; flex-direction: column; gap: 12px; }
  .nbtn { width: 54px; height: 54px; border-radius: 50%; display: grid; place-items: center; background: var(--surface2); color: var(--text); }
  .nbtn:hover:not(:disabled) { background: var(--surface3); }
  .nbtn:disabled { opacity: 0.35; }

  .toast { position: absolute; left: 50%; bottom: 1.5rem; z-index: 20; translate: -50% 0; max-width: calc(100% - 32px); overflow-wrap: anywhere;
    padding: 0.65rem 1rem; border-radius: 12px; background: var(--accent); color: var(--on-accent); font-size: 0.86rem; font-weight: 600; box-shadow: var(--shadow-lg); }

  @media (max-width: 1100px) { .nav { display: none; } }
  /* Phones: edge to edge, the actions over the video as in the app. */
  @media (max-width: 700px) {
    .feed-wrap { height: calc(100dvh - 64px); margin: -1rem -1rem -2rem; min-height: 0; }
    .slot { padding: 0; }
    .unit { position: relative; width: 100%; }
    .frame { width: 100%; max-width: none; aspect-ratio: auto; border-radius: 0; box-shadow: none; }
    .rail { position: absolute; z-index: 6; right: 8px; bottom: 96px; gap: 14px; }
    .act { color: #fff; text-shadow: 0 1px 3px rgba(0,0,0,.6); }
    .disc { background: rgba(0,0,0,.35); width: 46px; height: 46px; }
    .act.on .disc { background: #fff; color: #111; }
    .info { padding-right: 4.5rem; }
  }
</style>
