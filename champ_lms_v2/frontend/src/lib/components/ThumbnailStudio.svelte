<script lang="ts">
  // Make a course or episode thumbnail three ways: design one from text, ask
  // the AI for a picture, or upload an image. Every tab draws into the same
  // 1280x720 canvas, and saving uploads that canvas, so the preview is always
  // exactly what learners will see.
  //
  // With an ownerId the result is saved straight away. Without one (an
  // episode that doesn't exist yet), it is handed back through onPicked and
  // the page saves it once the episode is created.
  import { onDestroy, onMount, tick } from 'svelte';
  import {
    api, type ThumbnailAiStyle, type ThumbnailDesign, type ThumbnailOwner, type ThumbnailState,
  } from '$lib/api/client';
  import {
    FONTS, H, PALETTES, TEMPLATES, W, canvasBlob, coverInto, defaultDesign, drawThumbnail,
    ensureFonts, loadImage, shuffleDesign, type FontId, type PickedThumbnail,
  } from '$lib/thumbnails/designer';

  export let kind: ThumbnailOwner;
  export let ownerId: string | null = null;
  export let title = '';
  export let kicker = '';
  // Extra words for the AI when there is no saved row to read them from.
  export let context = '';
  export let current: ThumbnailState | null = null;
  export let onClose: () => void;
  export let onSaved: (s: ThumbnailState) => void = () => {};
  export let onPicked: (p: PickedThumbnail) => void = () => {};

  type Tab = 'design' | 'ai' | 'upload';
  const AI_STYLES: { id: ThumbnailAiStyle; name: string; hint: string }[] = [
    { id: 'illustration', name: 'Illustration', hint: 'Flat editorial shapes' },
    { id: '3d', name: '3D', hint: 'Soft clay render' },
    { id: 'photo', name: 'Photo', hint: 'Cinematic, realistic' },
    { id: 'abstract', name: 'Abstract', hint: 'Gradients and forms' },
    { id: 'isometric', name: 'Isometric', hint: 'A small scene' },
    { id: 'minimal', name: 'Minimal', hint: 'Line art, one accent' },
  ];
  const MAX_UPLOAD = 12 * 1024 * 1024;

  // Only same-origin images can be drawn into a canvas that is then exported;
  // older Bunny thumbnails live on another host, so they are shown, not reused.
  const reusable = (url: string | null | undefined) => !!url && url.startsWith('/');

  const src = current?.thumbnail_source ?? null;
  let tab: Tab = src === 'ai' ? 'ai' : src === 'upload' ? 'upload' : 'design';
  let design: ThumbnailDesign = current?.thumbnail_design
    ? { ...current.thumbnail_design }
    : defaultDesign(title.trim() || 'Untitled course', kicker);
  let bgImg: HTMLImageElement | null = null;

  let aiStyle: ThumbnailAiStyle = 'illustration';
  let direction = '';
  let leaveSpace = false;
  let generating = false;
  let aiResults: string[] = src === 'ai' && reusable(current?.thumbnail_url) ? [current!.thumbnail_url!] : [];
  let aiPick: string | null = aiResults[0] ?? null;

  let upUrl: string | null = src === 'upload' && reusable(current?.thumbnail_url) ? current!.thumbnail_url : null;
  let upName = upUrl ? 'Current thumbnail' : '';
  let dragHot = false;

  let canvas: HTMLCanvasElement;
  let mini: HTMLCanvasElement;
  let saving = false;
  let removing = false;
  let error = '';
  let fontsLoaded = false;
  const images = new Map<string, HTMLImageElement>();
  const objectUrls: string[] = [];

  async function image(url: string | null): Promise<HTMLImageElement | null> {
    if (!url) return null;
    if (!images.has(url)) images.set(url, await loadImage(url));
    return images.get(url)!;
  }

  // ---- rendering ------------------------------------------------------------
  let frame = 0;
  let shownImage: HTMLImageElement | null = null;
  async function render() {
    if (!canvas) return;
    const n = ++frame;
    let img: HTMLImageElement | null = null;
    try {
      img = tab === 'ai' ? await image(aiPick) : tab === 'upload' ? await image(upUrl) : null;
    } catch (e: any) { error = e.message; }
    if (n !== frame) return; // a newer render started while this one loaded
    shownImage = img;
    const ctx = canvas.getContext('2d')!;
    if (tab === 'design') drawThumbnail(ctx, design, bgImg);
    else coverInto(ctx, img);
    const m = mini?.getContext('2d');
    if (m) { m.imageSmoothingQuality = 'high'; m.drawImage(canvas, 0, 0, mini.width, mini.height); }
  }
  $: if (canvas) { tab; design; bgImg; aiPick; upUrl; fontsLoaded; render(); }

  // Small live previews of each template with the current title and palette.
  let tplCanvases: Record<string, HTMLCanvasElement> = {};
  let tplTimer: ReturnType<typeof setTimeout>;
  let scratch: HTMLCanvasElement | null = null;
  function renderTemplates() {
    clearTimeout(tplTimer);
    tplTimer = setTimeout(() => {
      scratch ??= Object.assign(document.createElement('canvas'), { width: W, height: H });
      const sctx = scratch.getContext('2d')!;
      for (const t of TEMPLATES) {
        const c = tplCanvases[t.id];
        if (!c) continue;
        drawThumbnail(sctx, { ...design, template: t.id }, bgImg);
        const ctx = c.getContext('2d')!;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(scratch, 0, 0, c.width, c.height);
      }
    }, 120);
  }
  $: if (tab === 'design') { design.title; design.kicker; design.palette; design.font; bgImg; fontsLoaded; tick().then(renderTemplates); }

  // ---- design -----------------------------------------------------------------
  function set<K extends keyof ThumbnailDesign>(k: K, v: ThumbnailDesign[K]) { design = { ...design, [k]: v }; }
  function shuffle() { design = shuffleDesign(design, !!bgImg); }

  function titleOnTop() {
    if (!shownImage) return;
    bgImg = shownImage;
    design = { ...design, template: 'overlay', title: design.title || title, kicker: design.kicker || kicker };
    tab = 'design';
  }

  // ---- AI -------------------------------------------------------------------
  async function generate() {
    generating = true; error = '';
    try {
      const { image: dataUrl } = await api.generateThumbnail({
        ...(ownerId ? { owner_kind: kind, owner_id: ownerId } : { title: title.trim(), context }),
        style: aiStyle, direction: direction.trim() || undefined, leave_space: leaveSpace,
      });
      aiResults = [dataUrl, ...aiResults].slice(0, 8);
      aiPick = dataUrl;
    } catch (e: any) { error = e.message; }
    finally { generating = false; }
  }

  // ---- upload -------------------------------------------------------------
  function takeFile(f: File | undefined | null) {
    error = '';
    if (!f) return;
    if (!f.type.startsWith('image/')) { error = 'That isn’t an image. Use a PNG, JPEG or WebP.'; return; }
    if (f.size > MAX_UPLOAD) { error = 'Images can be up to 12 MB.'; return; }
    const url = URL.createObjectURL(f);
    objectUrls.push(url);
    upUrl = url; upName = f.name;
  }
  function onDrop(e: DragEvent) { dragHot = false; takeFile(e.dataTransfer?.files?.[0]); }

  // ---- save -------------------------------------------------------------------
  $: canSave = tab === 'design' ? !!design.title.trim() : tab === 'ai' ? !!aiPick : !!upUrl;

  async function save() {
    if (!canSave || saving) return;
    saving = true; error = '';
    try {
      await render();
      const blob = await canvasBlob(canvas);
      const source = tab === 'design' ? 'text' : tab;
      const d = tab === 'design' ? { ...design, had_image: design.template === 'overlay' && !!bgImg } : null;
      if (!ownerId) {
        onPicked({ blob, url: URL.createObjectURL(blob), source, design: d });
        onClose();
        return;
      }
      onSaved(await api.saveThumbnail(kind, ownerId, blob, source, d));
      onClose();
    } catch (e: any) { error = e.message; }
    finally { saving = false; }
  }

  async function remove() {
    if (!ownerId) return;
    removing = true; error = '';
    try { onSaved(await api.deleteThumbnail(kind, ownerId)); onClose(); }
    catch (e: any) { error = e.message; }
    finally { removing = false; }
  }

  function onKey(e: KeyboardEvent) { if (e.key === 'Escape' && !saving) onClose(); }

  // The studio opens from inside sticky side panels, which trap z-index; on
  // the body it always sits above the page.
  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return { destroy() { node.remove(); } };
  }

  let dialog: HTMLElement;
  onMount(async () => {
    document.body.style.overflow = 'hidden';
    dialog?.focus();
    await ensureFonts();
    fontsLoaded = true;
  });
  onDestroy(() => {
    if (typeof document !== 'undefined') document.body.style.overflow = '';
    clearTimeout(tplTimer);
    objectUrls.forEach(u => URL.revokeObjectURL(u));
  });

  const hasStudioImage = !!current?.thumbnail_source;
  const heading = kind === 'module' ? 'Course thumbnail' : 'Episode thumbnail';
</script>

<svelte:window on:keydown={onKey} />

<div class="ts-backdrop" role="presentation" use:portal>
  <div class="ts" role="dialog" aria-modal="true" aria-labelledby="ts-title" tabindex="-1" bind:this={dialog}>
    <header class="ts-head">
      <div>
        <h2 id="ts-title">{heading}</h2>
        <p>{title || 'Untitled'}</p>
      </div>
      <button class="ts-x" on:click={onClose} aria-label="Close" disabled={saving}>✕</button>
    </header>

    <div class="ts-tabs" role="tablist">
      <button role="tab" aria-selected={tab === 'design'} class:on={tab === 'design'} on:click={() => (tab = 'design')}>
        <span class="ti">Aa</span> Design with text
      </button>
      <button role="tab" aria-selected={tab === 'ai'} class:on={tab === 'ai'} on:click={() => (tab = 'ai')}>
        <span class="ti">✦</span> AI image
      </button>
      <button role="tab" aria-selected={tab === 'upload'} class:on={tab === 'upload'} on:click={() => (tab = 'upload')}>
        <span class="ti">↑</span> Upload
      </button>
    </div>

    <div class="ts-body">
      <div class="ts-stage">
        <div class="ts-canvas" class:empty={tab !== 'design' && !(tab === 'ai' ? aiPick : upUrl)}>
          <canvas bind:this={canvas} width={W} height={H} aria-label="Thumbnail preview"></canvas>
          {#if tab === 'ai' && !aiPick}
            <div class="ts-placeholder">{generating ? '' : 'Pick a style and press Generate. Your picture appears here.'}</div>
          {:else if tab === 'upload' && !upUrl}
            <div class="ts-placeholder">Drop an image or choose a file. It's cropped to 16:9 from the centre.</div>
          {/if}
          {#if generating}
            <div class="ts-painting"><span class="ts-spin"></span> Painting your thumbnail… about 10–20 seconds</div>
          {/if}
        </div>
        <div class="ts-under">
          <figure class="ts-card">
            <canvas bind:this={mini} width="320" height="180" aria-hidden="true"></canvas>
            <figcaption>As a course card</figcaption>
          </figure>
          {#if tab !== 'design' && shownImage}
            <div class="ts-overlay-cta">
              <b>Want the title on it?</b>
              <span>{tab === 'ai'
                ? 'AI images never contain text, so the title is drawn on top: crisp and spelled right.'
                : 'Draw the title over this picture, with a shade behind it so it stays readable.'}</span>
              <button class="ts-btn" on:click={titleOnTop}>Add title on top</button>
            </div>
          {/if}
        </div>
      </div>

      <aside class="ts-panel">
        {#if tab === 'design'}
          <label class="ts-field"><span>Title</span>
            <textarea rows="2" maxlength="120" value={design.title}
              on:input={e => set('title', e.currentTarget.value)} placeholder="What the course is called"></textarea>
          </label>
          <label class="ts-field"><span>Label above the title <em>optional</em></span>
            <input type="text" maxlength="48" value={design.kicker}
              on:input={e => set('kicker', e.currentTarget.value)} placeholder="e.g. Sales · Module 2" />
          </label>

          <div class="ts-field">
            <span class="ts-row"><span>Layout</span><button class="ts-link" on:click={shuffle}>⟳ Surprise me</button></span>
            <div class="ts-tpls">
              {#each TEMPLATES as t (t.id)}
                <button class="ts-tpl" class:on={design.template === t.id} on:click={() => set('template', t.id)}
                  aria-pressed={design.template === t.id} title={t.id === 'overlay' && !bgImg ? 'Best with a background image: make one in AI image or Upload' : t.name}>
                  <canvas bind:this={tplCanvases[t.id]} width="192" height="108" aria-hidden="true"></canvas>
                  <span>{t.name}</span>
                </button>
              {/each}
            </div>
          </div>

          <div class="ts-field"><span>Colours</span>
            <div class="ts-swatches">
              {#each PALETTES as p (p.id)}
                <button class="ts-sw" class:on={design.palette === p.id} on:click={() => set('palette', p.id)}
                  aria-label={p.name} aria-pressed={design.palette === p.id} title={p.name}
                  style="--a:{p.bg[0]};--b:{p.bg[1]};--c:{p.accent}"></button>
              {/each}
            </div>
          </div>

          <div class="ts-field"><span>Typeface</span>
            <div class="ts-fonts">
              {#each Object.entries(FONTS) as [id, f] (id)}
                <button class="ts-font" class:on={design.font === id} on:click={() => set('font', id)}
                  aria-pressed={design.font === id} style="font-family:{f.family};font-weight:{f.weight}">
                  {f.upper ? 'AA' : 'Aa'}<small>{f.name}</small>
                </button>
              {/each}
            </div>
          </div>

          {#if bgImg}
            <div class="ts-note">
              <span>Drawn over your picture.</span>
              <button class="ts-link" on:click={() => (bgImg = null)}>Remove picture</button>
            </div>
          {:else if design.had_image && design.template === 'overlay'}
            <p class="ts-hint">This design had a picture behind it, which isn't kept for editing. Make or upload one again and choose “Add title on top”.</p>
          {/if}
        {:else if tab === 'ai'}
          <div class="ts-field"><span>Style</span>
            <div class="ts-styles">
              {#each AI_STYLES as s (s.id)}
                <button class="ts-style" class:on={aiStyle === s.id} on:click={() => (aiStyle = s.id)} aria-pressed={aiStyle === s.id}>
                  <b>{s.name}</b><small>{s.hint}</small>
                </button>
              {/each}
            </div>
          </div>
          <label class="ts-field"><span>What should be in it? <em>optional</em></span>
            <textarea rows="3" maxlength="500" bind:value={direction}
              placeholder="e.g. a compass on a desk in warm morning light"></textarea>
          </label>
          <label class="ts-check"><input type="checkbox" bind:checked={leaveSpace} /> Keep the left side clear for a title</label>
          <p class="ts-hint">
            {ownerId ? 'The AI reads the title, description and lessons to decide what to draw.' : 'The AI works from the title and anything you add above.'}
            Nothing is saved until you press Save.
          </p>
          <button class="ts-btn primary wide" on:click={generate} disabled={generating || (!ownerId && !title.trim())}>
            {#if generating}<span class="ts-spin"></span> Generating…{:else}✦ {aiResults.length ? 'Generate another' : 'Generate'}{/if}
          </button>
          {#if aiResults.length}
            <div class="ts-field"><span>Results</span>
              <div class="ts-results">
                {#each aiResults as r, i (r)}
                  <button class="ts-result" class:on={aiPick === r} on:click={() => (aiPick = r)} aria-label="Use result {i + 1}" aria-pressed={aiPick === r}>
                    <img src={r} alt="" />
                  </button>
                {/each}
              </div>
            </div>
          {/if}
        {:else}
          <label class="ts-drop" class:hot={dragHot}
            on:dragover|preventDefault={() => (dragHot = true)} on:dragleave={() => (dragHot = false)} on:drop|preventDefault={onDrop}>
            <input type="file" accept="image/*" hidden on:change={e => { takeFile(e.currentTarget.files?.[0]); e.currentTarget.value = ''; }} />
            <b>{upUrl ? 'Choose a different image' : 'Drop an image here'}</b>
            <span>or click to choose · PNG, JPEG or WebP, up to 12 MB</span>
          </label>
          {#if upName}<p class="ts-hint">Using: {upName}</p>{/if}
          <p class="ts-hint">Best at 1280 × 720 or larger. Other shapes are cropped to 16:9 from the centre, as the preview shows.</p>
        {/if}
      </aside>
    </div>

    <footer class="ts-foot">
      {#if error}<p class="ts-error" role="alert">{error}</p>{/if}
      <div class="ts-actions">
        {#if ownerId && hasStudioImage}
          <button class="ts-btn ghost danger" on:click={remove} disabled={removing || saving}>{removing ? 'Removing…' : 'Remove thumbnail'}</button>
        {/if}
        <span class="ts-grow"></span>
        <button class="ts-btn ghost" on:click={onClose} disabled={saving}>Cancel</button>
        <button class="ts-btn primary" on:click={save} disabled={!canSave || saving || generating}>
          {saving ? 'Saving…' : ownerId ? 'Save thumbnail' : 'Use this thumbnail'}
        </button>
      </div>
    </footer>
  </div>
</div>

<style>
  .ts-backdrop {
    position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 16px;
    background: rgba(4, 4, 8, 0.72); backdrop-filter: blur(6px);
  }
  .ts {
    width: min(1120px, 100%); max-height: calc(100vh - 32px); overflow: auto; outline: none;
    background: var(--surface); border: 1px solid var(--border-hover); border-radius: 16px;
    box-shadow: var(--shadow-lg); display: flex; flex-direction: column;
  }
  .ts > * { flex-shrink: 0; }
  .ts-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; padding: 1.1rem 1.25rem 0.6rem; }
  .ts-head h2 { font-size: 1.15rem; font-weight: 800; }
  .ts-head p { font-size: 0.82rem; color: var(--muted); margin-top: 0.1rem; }
  .ts-x { width: 32px; height: 32px; border-radius: 8px; color: var(--muted); font-size: 0.95rem; }
  .ts-x:hover { background: var(--surface2); color: var(--text); }

  .ts-tabs { display: flex; gap: 0.35rem; padding: 0 1.25rem; border-bottom: 1px solid var(--border); overflow-x: auto; }
  .ts-tabs button {
    display: inline-flex; gap: 0.45rem; align-items: center; padding: 0.55rem 0.75rem 0.7rem; white-space: nowrap;
    font-weight: 600; font-size: 0.86rem; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px;
  }
  .ts-tabs button:hover { color: var(--text); }
  .ts-tabs button.on { color: var(--text); border-color: var(--accent); }
  .ti { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: 6px; background: var(--surface3); font-size: 0.72rem; font-weight: 800; }
  .on .ti { background: var(--accent); color: #fff; }

  .ts-body { display: grid; gap: 1.1rem; padding: 1.1rem 1.25rem; grid-template-columns: minmax(0, 1fr); }
  @media (min-width: 900px) { .ts-body { grid-template-columns: minmax(0, 1fr) 340px; } }

  .ts-stage { display: grid; gap: 0.9rem; align-content: start; min-width: 0; }
  .ts-canvas { position: relative; border-radius: 12px; overflow: hidden; background: #0a0a0f; box-shadow: 0 0 0 1px var(--border-hover); }
  .ts-canvas canvas { display: block; width: 100%; height: auto; aspect-ratio: 16 / 9; }
  .ts-canvas.empty canvas { opacity: 0.35; }
  .ts-placeholder { position: absolute; inset: 0; display: grid; place-items: center; padding: 1.5rem; text-align: center; color: var(--text-secondary); font-size: 0.9rem; }
  .ts-painting {
    position: absolute; inset: 0; display: flex; gap: 0.6rem; align-items: center; justify-content: center;
    background: rgba(10, 10, 15, 0.6); color: #fff; font-weight: 600; font-size: 0.9rem;
  }
  .ts-under { display: flex; gap: 1rem; align-items: flex-start; flex-wrap: wrap; }
  .ts-card { margin: 0; display: grid; gap: 0.35rem; }
  .ts-card canvas { width: 200px; height: auto; aspect-ratio: 16 / 9; border-radius: 8px; box-shadow: 0 0 0 1px var(--border); }
  .ts-card figcaption { font-size: 0.72rem; color: var(--muted); }
  .ts-overlay-cta { flex: 1; min-width: 220px; display: grid; gap: 0.3rem; justify-items: start; padding: 0.75rem 0.9rem; border-radius: 10px; background: var(--surface2); }
  .ts-overlay-cta b { font-size: 0.86rem; }
  .ts-overlay-cta span { font-size: 0.78rem; color: var(--text-secondary); line-height: 1.45; }
  .ts-overlay-cta .ts-btn { margin-top: 0.25rem; }

  .ts-panel { display: grid; gap: 1rem; align-content: start; min-width: 0; }
  .ts-field { display: grid; gap: 0.45rem; font-size: 0.78rem; font-weight: 600; color: var(--text-secondary); min-width: 0; }
  .ts-field em { font-style: normal; font-weight: 400; color: var(--muted); }
  .ts-field input, .ts-field textarea {
    font: inherit; font-weight: 400; font-size: 0.88rem; color: var(--text); background: var(--bg);
    border: 1px solid var(--border-hover); border-radius: 8px; padding: 0.5rem 0.65rem; width: 100%; resize: vertical;
  }
  .ts-field input:focus, .ts-field textarea:focus { outline: none; border-color: var(--accent); }
  .ts-row { display: flex; justify-content: space-between; align-items: center; }
  .ts-link { font-size: 0.78rem; font-weight: 600; color: var(--text); padding: 0.1rem 0.3rem; border-radius: 6px; }
  .ts-link:hover { background: var(--surface2); }

  .ts-tpls { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.45rem; }
  .ts-tpl { display: grid; gap: 0.25rem; padding: 3px; border-radius: 9px; border: 1px solid var(--border); text-align: center; font-size: 0.7rem; font-weight: 600; color: var(--muted); }
  .ts-tpl canvas { width: 100%; height: auto; aspect-ratio: 16 / 9; border-radius: 6px; display: block; }
  .ts-tpl span { padding-bottom: 2px; }
  .ts-tpl:hover { border-color: var(--border-hover); color: var(--text); }
  .ts-tpl.on { border-color: var(--accent); color: var(--text); box-shadow: 0 0 0 2px rgba(229, 9, 20, 0.25); }

  .ts-swatches { display: flex; flex-wrap: wrap; gap: 0.5rem; }
  .ts-sw {
    width: 34px; height: 34px; border-radius: 50%; position: relative;
    background: linear-gradient(135deg, var(--a) 0 50%, var(--b) 50% 100%);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.15);
  }
  .ts-sw::after { content: ''; position: absolute; right: 2px; bottom: 2px; width: 11px; height: 11px; border-radius: 50%; background: var(--c); box-shadow: 0 0 0 2px var(--surface); }
  .ts-sw.on { box-shadow: 0 0 0 2px var(--surface), 0 0 0 4px var(--text); }

  .ts-fonts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.4rem; }
  .ts-font { display: grid; justify-items: center; gap: 0.15rem; padding: 0.45rem 0.2rem; border-radius: 9px; border: 1px solid var(--border); font-size: 1.35rem; line-height: 1; color: var(--text); }
  .ts-font small { font: 600 0.64rem/1 -apple-system, 'Segoe UI', sans-serif; color: var(--muted); }
  .ts-font:hover { border-color: var(--border-hover); }
  .ts-font.on { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(229, 9, 20, 0.25); }

  .ts-styles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.4rem; }
  .ts-style { display: grid; gap: 0.1rem; padding: 0.5rem 0.6rem; border-radius: 9px; border: 1px solid var(--border); text-align: left; }
  .ts-style b { font-size: 0.82rem; color: var(--text); }
  .ts-style small { font-size: 0.7rem; color: var(--muted); font-weight: 400; }
  .ts-style:hover { border-color: var(--border-hover); }
  .ts-style.on { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(229, 9, 20, 0.25); }
  .ts-check { display: flex; gap: 0.5rem; align-items: center; font-size: 0.82rem; color: var(--text); }
  .ts-check input { accent-color: var(--accent); width: 15px; height: 15px; }
  .ts-results { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.4rem; }
  .ts-result { padding: 2px; border-radius: 7px; border: 1px solid var(--border); }
  .ts-result img { width: 100%; aspect-ratio: 16 / 9; object-fit: cover; border-radius: 5px; }
  .ts-result.on { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(229, 9, 20, 0.25); }

  .ts-drop {
    display: grid; gap: 0.3rem; justify-items: center; text-align: center; padding: 1.6rem 1rem; cursor: pointer;
    border: 1.5px dashed var(--border-hover); border-radius: 12px; background: var(--bg);
  }
  .ts-drop b { font-size: 0.9rem; }
  .ts-drop span { font-size: 0.76rem; color: var(--muted); }
  .ts-drop:hover, .ts-drop.hot { border-color: var(--accent); background: rgba(229, 9, 20, 0.06); }

  .ts-note { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; padding: 0.55rem 0.7rem; border-radius: 9px; background: var(--surface2); font-size: 0.8rem; }
  .ts-hint { font-size: 0.76rem; color: var(--muted); line-height: 1.5; }

  .ts-foot { border-top: 1px solid var(--border); padding: 0.85rem 1.25rem; display: grid; gap: 0.6rem; position: sticky; bottom: 0; background: var(--surface); }
  .ts-error { color: #ff8a8f; font-size: 0.84rem; }
  .ts-actions { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
  .ts-grow { flex: 1; }
  .ts-btn {
    display: inline-flex; align-items: center; justify-content: center; gap: 0.45rem; height: 36px; padding: 0 1rem;
    border-radius: 8px; border: 1px solid var(--border-hover); background: var(--surface2); color: var(--text);
    font-weight: 600; font-size: 0.84rem; white-space: nowrap;
  }
  .ts-btn:hover:not(:disabled) { background: var(--surface3); }
  .ts-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .ts-btn.primary:hover:not(:disabled) { background: var(--accent-hover); }
  .ts-btn.ghost { background: transparent; }
  .ts-btn.danger { color: #ff8a8f; border-color: rgba(255, 107, 112, 0.35); }
  .ts-btn.wide { width: 100%; height: 40px; }
  .ts-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .ts-spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid currentColor; border-right-color: transparent; animation: ts-spin 0.8s linear infinite; display: inline-block; }
  @keyframes ts-spin { to { transform: rotate(360deg); } }
</style>
