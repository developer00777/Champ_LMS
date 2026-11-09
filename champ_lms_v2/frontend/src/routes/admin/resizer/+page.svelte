<script lang="ts">
  import { goto } from '$app/navigation';
  import { onDestroy } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import VideoResizer from '$lib/components/shorts/VideoResizer.svelte';
  import ShortPublishForm from '$lib/components/shorts/ShortPublishForm.svelte';
  import { clock, downloadBlob } from '$lib/utils/resize-video';
  import { MAX_SHORT_SECONDS } from '$lib/utils/shorts-upload';

  let file: File | null = null;
  type Out = { blob: Blob; name: string; width: number; height: number; duration: number; poster: Blob | null; ext: string };
  let out: Out | null = null;
  let outUrl = '';
  let publishing = false;
  $: outFile = out ? new File([out.blob], out.name, { type: out.blob.type }) : null;

  function onRendered(e: CustomEvent<Out>) {
    if (outUrl) URL.revokeObjectURL(outUrl);
    out = e.detail;
    outUrl = URL.createObjectURL(out.blob);
    publishing = false;
    // Saved straight away: the reason most people come here.
    downloadBlob(out.blob, out.name);
  }
  function again() {
    if (outUrl) URL.revokeObjectURL(outUrl);
    out = null; outUrl = ''; publishing = false;
  }
  onDestroy(() => { if (outUrl) URL.revokeObjectURL(outUrl); });

  const mb = (n: number) => `${(n / 1024 / 1024).toFixed(1)} MB`;
</script>

<svelte:head><title>Video resizer — Admin</title></svelte:head>

<div class="page">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Shorts', href: '/admin/shorts' }, { label: 'Video resizer' }]} />
  <header class="head">
    <p class="eyebrow ui-rise">9:16 · 4:5 · 1:1 · 16:9 · any size</p>
    <h1 class="ui-rise" style="--i:1">Video resizer <span class="title-mark" aria-hidden="true"><Icon name="crop" size={22} /></span></h1>
    <p class="lede ui-rise" style="--i:2">Turn a landscape recording into a vertical short (or any other shape): fill and crop it, or fit the whole picture on a blurred background, then trim it. It renders in this browser, so nothing is uploaded until you publish.</p>
  </header>

  {#if out}
    <section class="result ui-rise">
      <div class="res-video" style="--ar:{out.width}/{out.height}">
        <!-- svelte-ignore a11y-media-has-caption -->
        <video src={outUrl} controls playsinline loop></video>
      </div>
      <div class="res-side">
        <span class="ui-pill mint"><Icon name="checkCircle" size={15} /> Rendered and downloaded</span>
        <h2>{out.name}</h2>
        <p class="facts">{out.width} × {out.height} · {clock(out.duration)} · {mb(out.blob.size)} · {out.ext.toUpperCase()}</p>
        {#if publishing && outFile}
          <div class="pub">
            <ShortPublishForm file={outFile}
              meta={{ width: out.width, height: out.height, duration: out.duration }} poster={out.poster} madeWith="resizer"
              on:published={() => goto('/admin/shorts')}>
              <button slot="extra" class="btn-ghost" on:click={() => (publishing = false)}>Cancel</button>
            </ShortPublishForm>
          </div>
        {:else}
          <div class="res-actions">
            <button class="btn-ghost" on:click={() => out && downloadBlob(out.blob, out.name)}><Icon name="download" size={17} /> Download again</button>
            {#if out.duration <= MAX_SHORT_SECONDS + 1.5}
              <button class="btn-primary" on:click={() => (publishing = true)}><Icon name="shorts" size={17} /> Publish as a short</button>
            {:else}
              <p class="hint">Over 3:00, so it can't be a short. Trim it to publish it as one.</p>
            {/if}
          </div>
          <button class="link" on:click={again}><Icon name="refresh" size={15} /> Change the settings and render again</button>
        {/if}
      </div>
    </section>
  {/if}

  <div class:hidden={!!out}>
    <VideoResizer bind:file actionLabel="Render and download" on:rendered={onRendered} />
  </div>
</div>

<style>
  .page { max-width: 1280px; margin: 0 auto; }
  .head { margin-bottom: 1.25rem; }
  .eyebrow { color: var(--muted); font-size: 0.92rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.04; display: flex; align-items: center; gap: 0.6rem; }
  .title-mark { display: inline-grid; place-items: center; width: 46px; height: 46px; border-radius: 50%; background: var(--tile-lilac); color: var(--tile-ink); rotate: -8deg; }
  .lede { color: var(--text-secondary); max-width: 70ch; margin-top: 0.6rem; font-size: 0.95rem; line-height: 1.55; }
  .hidden { display: none; }
  .result { display: grid; grid-template-columns: minmax(0, 1fr) 420px; gap: 1.5rem; align-items: start; background: var(--surface); border-radius: 30px; padding: 1.4rem; box-shadow: var(--shadow-sm); }
  .res-video { display: flex; align-items: center; justify-content: center; height: min(66vh, 640px); background: #0b0b0d; border-radius: 22px; padding: 1rem; }
  .res-video video { max-width: 100%; max-height: 100%; width: auto; height: auto; border-radius: 12px; background: #000; }
  .res-side { display: flex; flex-direction: column; gap: 0.75rem; align-items: flex-start; min-width: 0; }
  .res-side h2 { font-size: 1.15rem; overflow-wrap: anywhere; }
  .facts { color: var(--muted); font-size: 0.86rem; font-variant-numeric: tabular-nums; }
  .res-actions { display: flex; flex-wrap: wrap; gap: 0.6rem; }
  .pub { width: 100%; }
  .hint { font-size: 0.82rem; color: var(--muted); }
  .link { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.86rem; font-weight: 700; text-decoration: underline; text-underline-offset: 3px; }
  @media (max-width: 1020px) { .result { grid-template-columns: 1fr; } .res-video { height: min(56vh, 520px); } }
</style>
