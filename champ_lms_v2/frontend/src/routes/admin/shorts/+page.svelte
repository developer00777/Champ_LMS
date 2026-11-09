<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { api, type AdminShort } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Select from '$lib/components/Select.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import VideoResizer from '$lib/components/shorts/VideoResizer.svelte';
  import ShortPublishForm from '$lib/components/shorts/ShortPublishForm.svelte';
  import { clock, nearestPreset, posterFromFile, ratioLabel, readVideoMeta, SIZE_PRESETS, type VideoMeta } from '$lib/utils/resize-video';
  import { MAX_SHORT_SECONDS } from '$lib/utils/shorts-upload';

  let shorts: AdminShort[] = [];
  let loading = true;
  let error = '';

  async function load() {
    try { shorts = await api.adminShorts(); error = ''; }
    catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  // Anything still encoding on Bunny is checked every few seconds.
  let poll: ReturnType<typeof setInterval> | null = null;
  $: pending = shorts.filter(s => s.status === 'processing');
  $: if (pending.length && !poll) poll = setInterval(checkPending, 6000);
  $: if (!pending.length && poll) { clearInterval(poll); poll = null; }
  async function checkPending() {
    for (const s of pending) {
      try {
        const st = await api.shortStatus(s.id);
        if (st.status !== s.status || st.poster_url !== s.poster_url) {
          shorts = shorts.map(x => x.id === s.id ? { ...x, status: st.status as AdminShort['status'], duration_seconds: st.duration_seconds ?? x.duration_seconds, poster_url: st.poster_url } : x);
        }
      } catch { /* try again next round */ }
    }
  }
  onMount(load);
  onDestroy(() => { if (poll) clearInterval(poll); revoke(); });

  // ---- adding a short ----------------------------------------------------
  type Step = 'closed' | 'pick' | 'details' | 'resize';
  let step: Step = 'closed';
  let file: File | null = null;
  let meta: VideoMeta | null = null;
  let poster: Blob | null = null;
  let previewUrl = '';
  let posterUrl = '';
  let madeWith: 'resizer' | undefined;
  let resizeTo = '9:16';
  let pickError = '';
  let hot = false;

  function revoke() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (posterUrl) URL.revokeObjectURL(posterUrl);
    previewUrl = posterUrl = '';
  }
  function openAdd() { reset(); step = 'pick'; }
  function reset() { revoke(); file = null; meta = null; poster = null; madeWith = undefined; pickError = ''; }
  function closeAdd() { reset(); step = 'closed'; }

  async function useFile(f: File, m?: VideoMeta, p?: Blob | null, via?: 'resizer') {
    pickError = '';
    try { meta = m ?? (await readVideoMeta(f)); }
    catch (e: any) { pickError = e.message; return; }
    revoke();
    file = f; madeWith = via;
    poster = p ?? (await posterFromFile(f, Math.min(1, meta.duration / 3)));
    previewUrl = URL.createObjectURL(f);
    posterUrl = poster ? URL.createObjectURL(poster) : '';
    step = 'details';
  }
  function pick(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    if (f) useFile(f);
  }
  $: isVertical = !!meta && meta.height > meta.width * 1.5;
  $: tooLong = !!meta && meta.duration > MAX_SHORT_SECONDS + 1.5;
  $: shapeNow = meta ? nearestPreset(meta.width, meta.height).key : '';

  function resize(to: string) { resizeTo = to; step = 'resize'; }
  async function onRendered(e: CustomEvent<{ blob: Blob; name: string; width: number; height: number; duration: number; poster: Blob | null }>) {
    const r = e.detail;
    await useFile(new File([r.blob], r.name, { type: r.blob.type }), { width: r.width, height: r.height, duration: r.duration }, r.poster, 'resizer');
  }
  function onPublished(e: CustomEvent<AdminShort>) {
    shorts = [e.detail, ...shorts.filter(s => s.id !== e.detail.id)];
    closeAdd();
    flash('Uploaded. Bunny is encoding it; it goes live in the feed when it\'s ready.');
  }

  // ---- editing -----------------------------------------------------------
  let editing: AdminShort | null = null;
  let draft = { title: '', description: '', module_id: '', fit: 'contain' as AdminShort['fit'], is_published: true };
  let saving = false;
  let editError = '';
  let courseOptions = [{ value: '', label: 'No course' }];
  async function openEdit(s: AdminShort) {
    editing = s; editError = '';
    draft = { title: s.title, description: s.description ?? '', module_id: s.module_id ?? '', fit: s.fit, is_published: s.is_published };
    if (courseOptions.length === 1) {
      try {
        const c = await api.adminContent();
        courseOptions = [{ value: '', label: 'No course' }, ...c.modules.map(m => ({ value: m.id, label: m.title }))];
      } catch { /* optional */ }
    }
  }
  async function saveEdit() {
    if (!editing) return;
    saving = true; editError = '';
    try {
      const out = await api.updateShort(editing.id, { ...draft, description: draft.description || null, module_id: draft.module_id || null });
      shorts = shorts.map(s => s.id === out.id ? out : s);
      editing = null;
    } catch (e: any) { editError = e.message; }
    finally { saving = false; }
  }
  async function togglePublish(s: AdminShort) {
    try {
      const out = await api.updateShort(s.id, { is_published: !s.is_published });
      shorts = shorts.map(x => x.id === out.id ? out : x);
    } catch (e: any) { flash(e.message, true); }
  }

  // ---- deleting ----------------------------------------------------------
  let deleting: AdminShort | null = null;
  let deleteBusy = false;
  async function confirmDelete() {
    if (!deleting) return;
    deleteBusy = true;
    try {
      await api.deleteShort(deleting.id);
      shorts = shorts.filter(s => s.id !== deleting!.id);
      flash(`Deleted “${deleting.title}” and its video on Bunny.`);
      deleting = null;
    } catch (e: any) { flash(e.message, true); }
    finally { deleteBusy = false; }
  }

  let toast = '';
  let toastBad = false;
  let toastTimer: ReturnType<typeof setTimeout>;
  function flash(msg: string, bad = false) {
    toast = msg; toastBad = bad;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (toast = ''), 4500);
  }

  // ---- list --------------------------------------------------------------
  const FILTERS = ['all', '9:16', '4:5', '1:1', '16:9'] as const;
  let filter: (typeof FILTERS)[number] = 'all';
  $: shown = filter === 'all' ? shorts : shorts.filter(s => s.aspect === filter);
  $: totals = {
    live: shorts.filter(s => s.is_published && s.status === 'ready').length,
    views: shorts.reduce((a, s) => a + s.view_count, 0),
    likes: shorts.reduce((a, s) => a + s.like_count, 0),
  };
  const STATUS: Record<AdminShort['status'], [string, string]> = {
    pending: ['No video yet', 'butter'], processing: ['Encoding', 'sky'], ready: ['Ready', 'mint'], failed: ['Failed', 'bad'],
  };
</script>

<svelte:head><title>Shorts — Admin</title></svelte:head>
<svelte:window on:keydown={e => { if (e.key === 'Escape') { editing = null; deleting = null; } }} />

<div class="page">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Shorts' }]} />
  <header class="head">
    <div>
      <p class="eyebrow ui-rise">Short videos, any shape, in a swipeable feed</p>
      <h1 class="ui-rise" style="--i:1">Shorts <span class="title-mark" aria-hidden="true"><Icon name="shorts" size={22} /></span></h1>
    </div>
    <div class="head-actions ui-rise" style="--i:2">
      <a href="/admin/resizer" class="btn-ghost"><Icon name="crop" size={17} /> Video resizer</a>
      <a href="/shorts" class="btn-ghost"><Icon name="eye" size={17} /> Learner view</a>
      {#if step === 'closed'}<button class="btn-primary" on:click={openAdd}><Icon name="plus" size={17} /> Add a short</button>{/if}
    </div>
  </header>

  {#if step !== 'closed'}
    <section class="card add ui-rise">
      <div class="card-h">
        <span class="k-ico"><Icon name="shorts" size={20} /></span>
        <div>
          <h2>{step === 'resize' ? 'Resize before publishing' : 'Add a short'}</h2>
          <p>{step === 'resize' ? 'Pick the new shape, frame it and trim it. It renders here, then you publish it.' : 'Up to 3 minutes. Vertical 9:16 fills the screen; 4:5, 1:1 and 16:9 work too.'}</p>
        </div>
        <button class="ui-round close" on:click={closeAdd} aria-label="Close"><Icon name="close" size={18} /></button>
      </div>

      {#if step === 'pick'}
        <label class="drop" class:hot on:dragenter={() => (hot = true)} on:dragleave={() => (hot = false)} on:drop={() => (hot = false)}>
          <input type="file" accept="video/*" on:change={pick} aria-label="Short video file" />
          <span class="d-ico"><Icon name="upload" size={26} /></span>
          <b>Drop a video here, or click to choose</b>
          <span>Any shape. You can keep it as it is, or resize it to 9:16, 4:5, 1:1 or 16:9 next.</span>
        </label>
        {#if pickError}<p class="msg bad"><Icon name="alert" size={15} /> {pickError}</p>{/if}
      {:else if step === 'resize' && file}
        <VideoResizer {file} preset={resizeTo} maxSeconds={MAX_SHORT_SECONDS} actionLabel="Render and continue" on:rendered={onRendered}>
          <button slot="extra-actions" class="btn-ghost" on:click={() => (step = 'details')}>Back</button>
        </VideoResizer>
      {:else if step === 'details' && file && meta}
        <div class="details">
          <!-- How learners will see it: the feed's 9:16 frame. -->
          <div class="phone" aria-label="Preview in the feed">
            {#if posterUrl && !isVertical}<img class="bg" src={posterUrl} alt="" />{/if}
            <!-- svelte-ignore a11y-media-has-caption -->
            <video src={previewUrl} poster={posterUrl} controls playsinline loop class="pv" style="object-fit:{isVertical ? 'cover' : 'contain'}"></video>
            <span class="phone-tag">Feed preview</span>
          </div>
          <div class="side">
            <div class="shape-box">
              <h3>Shape</h3>
              <p class="note">
                {#if madeWith === 'resizer'}Rendered by the resizer at {meta.width}×{meta.height}.
                {:else if isVertical}Vertical already: it fills the screen.
                {:else}This is {ratioLabel(meta.width, meta.height)}. Keep it, or resize it for a phone screen.{/if}
              </p>
              <div class="shape-row">
                {#each SIZE_PRESETS as p}
                  <button class="chip" class:on={p.key === shapeNow} on:click={() => resize(p.key)}
                    title={p.key === shapeNow ? 'The shape it is now: open the resizer to trim or reframe it' : `Resize to ${p.ratio}`}>
                    {#if p.key !== shapeNow}<Icon name="crop" size={13} />{/if} {p.ratio}{#if p.key === shapeNow} · now{/if}
                  </button>
                {/each}
              </div>
              <p class="note small">Pick a shape to open the resizer: frame, trim and render it here, then publish.</p>
              {#if tooLong}<p class="msg bad"><Icon name="alert" size={15} /> It's {clock(meta.duration)} long. Open the resizer to trim it to 3:00 or less.</p>{/if}
            </div>
            <ShortPublishForm {file} {meta} {poster} {madeWith} on:published={onPublished}>
              <button slot="extra" class="btn-ghost" on:click={() => { reset(); step = 'pick'; }}>Choose another file</button>
            </ShortPublishForm>
          </div>
        </div>
      {/if}
    </section>
  {/if}

  <div class="stats ui-rise" style="--i:3">
    <div class="stat mint"><b>{totals.live}</b><span>Live shorts</span></div>
    <div class="stat sky"><b>{totals.views}</b><span>Viewers</span></div>
    <div class="stat peach"><b>{totals.likes}</b><span>Likes</span></div>
  </div>

  <div class="list-head">
    <h2>All shorts <span class="count">{shorts.length}</span></h2>
    <div class="filters" role="tablist" aria-label="Filter by shape">
      {#each FILTERS as f}
        <button role="tab" aria-selected={filter === f} class:on={filter === f} on:click={() => (filter = f)}>{f === 'all' ? 'All' : f}</button>
      {/each}
    </div>
  </div>

  {#if loading}
    <div class="grid">{#each Array(5) as _}<div class="ui-skeleton" style="aspect-ratio:9/16;border-radius:22px"></div>{/each}</div>
  {:else if error}
    <p class="msg bad"><Icon name="alert" size={15} /> {error}</p>
  {:else if !shown.length}
    <div class="empty">
      <span class="e-ico"><Icon name="shorts" size={28} /></span>
      <h3>{shorts.length ? 'No shorts in this shape' : 'No shorts yet'}</h3>
      <p>Short, vertical videos learners swipe through, like YouTube Shorts. A tip, a demo, a 60-second recap of a course.</p>
      {#if !shorts.length && step === 'closed'}<button class="btn-primary" on:click={openAdd}><Icon name="plus" size={17} /> Add the first short</button>{/if}
    </div>
  {:else}
    <div class="grid">
      {#each shown as s (s.id)}
        <article class="sc">
          <a class="art" href="/shorts?s={s.id}" aria-label="Watch {s.title}">
            {#if s.poster_url}
              {#if s.aspect !== '9:16'}<img class="bg" src={s.poster_url} alt="" loading="lazy" />{/if}
              <img class="poster" class:cover={s.aspect === '9:16'} src={s.poster_url} alt="" loading="lazy" />
            {:else}<span class="ph"><Icon name="shorts" size={34} stroke={1.4} /></span>{/if}
            <span class="tags">
              <span class="tag {STATUS[s.status][1]}">{STATUS[s.status][0]}</span>
              {#if !s.is_published}<span class="tag dim">Hidden</span>{/if}
            </span>
            <span class="tag aspect">{ratioLabel(s.width, s.height) || s.aspect}</span>
            {#if s.duration_seconds}<span class="tag dur">{clock(s.duration_seconds)}</span>{/if}
          </a>
          <div class="sc-body">
            <h3 title={s.title}>{s.title}</h3>
            <p class="meta">
              <span title="Viewers"><Icon name="eye" size={13} /> {s.view_count}</span>
              <span title="Likes"><Icon name="thumbUp" size={13} /> {s.like_count}</span>
              {#if s.made_with === 'resizer'}<span title="Made with the video resizer"><Icon name="crop" size={13} /></span>{/if}
            </p>
            {#if s.module_title}<p class="course" title="Linked course"><Icon name="layers" size={13} /> {s.module_title}</p>{/if}
            <div class="sc-actions">
              <button class="mini" on:click={() => togglePublish(s)} title={s.is_published ? 'Hide from learners' : 'Show to learners'}>
                <Icon name={s.is_published ? 'eye' : 'eyeOff'} size={15} /> {s.is_published ? 'Shown' : 'Hidden'}
              </button>
              <button class="mini icon" on:click={() => openEdit(s)} aria-label="Edit {s.title}"><Icon name="edit" size={15} /></button>
              <button class="mini icon danger" on:click={() => (deleting = s)} aria-label="Delete {s.title}"><Icon name="trash" size={15} /></button>
            </div>
          </div>
        </article>
      {/each}
    </div>
  {/if}
</div>

{#if editing}
  <div class="scrim" on:click={() => (editing = null)} aria-hidden="true"></div>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="edit-h">
    <h2 id="edit-h">Edit short</h2>
    <label class="field">Title<input bind:value={draft.title} maxlength="120" /></label>
    <label class="field">Description<textarea rows="3" bind:value={draft.description} maxlength="2000"></textarea></label>
    <!-- svelte-ignore a11y-label-has-associated-control -->
    <label class="field">Linked course<Select bind:value={draft.module_id} options={courseOptions} searchable /></label>
    {#if editing.aspect !== '9:16'}
      <div class="field">In the feed
        <div class="seg">
          <button class:on={draft.fit === 'contain'} on:click={() => (draft.fit = 'contain')}>Whole picture</button>
          <button class:on={draft.fit === 'cover'} on:click={() => (draft.fit = 'cover')}>Fill, crop</button>
        </div>
      </div>
    {/if}
    <label class="check"><input type="checkbox" bind:checked={draft.is_published} /> Shown to learners</label>
    {#if editError}<p class="msg bad"><Icon name="alert" size={15} /> {editError}</p>{/if}
    <div class="m-actions">
      <button class="btn-ghost" on:click={() => (editing = null)}>Cancel</button>
      <button class="btn-primary" on:click={saveEdit} disabled={saving || !draft.title.trim()}>{saving ? 'Saving…' : 'Save'}</button>
    </div>
  </div>
{/if}

{#if deleting}
  <div class="scrim" on:click={() => (deleting = null)} aria-hidden="true"></div>
  <div class="modal" role="alertdialog" aria-modal="true" aria-labelledby="del-h">
    <h2 id="del-h">Delete this short?</h2>
    <p>“{deleting.title}”, its video on Bunny Stream, its likes and views are removed for good.</p>
    <div class="m-actions">
      <button class="btn-ghost" on:click={() => (deleting = null)}>Keep it</button>
      <button class="btn-primary danger-btn" on:click={confirmDelete} disabled={deleteBusy}>{deleteBusy ? 'Deleting…' : 'Delete for good'}</button>
    </div>
  </div>
{/if}

{#if toast}<div class="toast" class:bad={toastBad} role="status">{toast}</div>{/if}

<style>
  .page { max-width: 1280px; margin: 0 auto; }
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
  .eyebrow { color: var(--muted); font-size: 0.92rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.04; display: flex; align-items: center; gap: 0.6rem; }
  .title-mark { display: inline-grid; place-items: center; width: 46px; height: 46px; border-radius: 50%; background: var(--tile-peach); color: var(--tile-ink); rotate: -8deg; }
  .head-actions { display: flex; gap: 0.6rem; flex-wrap: wrap; }

  .card { background: var(--surface); border-radius: 30px; padding: 1.4rem; box-shadow: var(--shadow-sm); display: flex; flex-direction: column; gap: 1.1rem; margin-bottom: 1.5rem; }
  .card-h { display: flex; gap: 0.9rem; align-items: center; }
  .card-h > div { flex: 1; }
  .card-h p { color: var(--muted); font-size: 0.88rem; }
  .card-h h2 { font-size: 1.2rem; }
  .k-ico { width: 46px; height: 46px; border-radius: 16px; display: grid; place-items: center; background: var(--tile-peach); color: var(--tile-ink); flex: none; }
  .drop {
    position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.4rem;
    min-height: 200px; padding: 1.5rem; border-radius: 24px; text-align: center; cursor: pointer; font-size: 0.85rem; color: var(--muted);
    background: var(--surface2); border: 2px dashed var(--border-hover);
  }
  .drop:hover { background: var(--surface3); }
  .drop.hot { background: var(--tile-sky); }
  .drop b { color: var(--text); font-size: 0.98rem; }
  .drop input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  .drop b, .drop span { pointer-events: none; }
  .d-ico { width: 56px; height: 56px; border-radius: 50%; display: grid; place-items: center; background: var(--surface); color: var(--text); }

  .details { display: grid; grid-template-columns: 300px 1fr; gap: 1.5rem; align-items: start; }
  .phone { position: relative; aspect-ratio: 9 / 16; border-radius: 26px; overflow: hidden; background: #000; box-shadow: 0 0 0 6px #18181b, var(--shadow-md); }
  .phone .bg { position: absolute; inset: -10%; width: 120%; height: 120%; object-fit: cover; filter: blur(26px) brightness(0.62); }
  .pv { position: relative; width: 100%; height: 100%; display: block; }
  .phone-tag { position: absolute; top: 10px; left: 10px; padding: 0.2rem 0.55rem; border-radius: 99px; background: rgba(0,0,0,.55); color: #fff; font-size: 0.7rem; font-weight: 700; pointer-events: none; }
  .side { display: flex; flex-direction: column; gap: 1.1rem; min-width: 0; }
  .shape-box { display: flex; flex-direction: column; gap: 0.5rem; padding: 1rem; border-radius: 20px; background: var(--surface2); }
  .shape-box h3 { font-size: 0.95rem; }
  .note { font-size: 0.84rem; color: var(--text-secondary); }
  .note.small { font-size: 0.76rem; color: var(--muted); }
  .shape-row { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .chip { display: inline-flex; align-items: center; gap: 0.3rem; height: 34px; padding: 0 0.85rem; border-radius: 99px; background: var(--surface); border: 1px solid var(--border); font-size: 0.8rem; font-weight: 600; }
  .chip:hover { border-color: var(--border-hover); }
  .chip.on { background: var(--accent); color: var(--on-accent); border-color: var(--accent); }

  .stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.8rem; margin-bottom: 1.5rem; }
  .stat { border-radius: 24px; padding: 1rem 1.2rem; color: var(--tile-ink); display: flex; flex-direction: column; }
  .stat b { font-size: 1.9rem; font-weight: 700; letter-spacing: -0.03em; font-variant-numeric: tabular-nums; }
  .stat span { font-size: 0.82rem; opacity: 0.75; }
  .mint { background: var(--tile-mint); } .sky { background: var(--tile-sky); } .peach { background: var(--tile-peach); }

  .list-head { display: flex; justify-content: space-between; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .list-head h2 { font-size: 1.3rem; display: flex; align-items: center; gap: 0.5rem; }
  .count { font-size: 0.8rem; font-weight: 700; padding: 0.15rem 0.55rem; border-radius: 99px; background: var(--surface2); color: var(--muted); }
  .filters { display: flex; gap: 0.25rem; padding: 0.25rem; background: var(--surface2); border-radius: 99px; }
  .filters button { height: 34px; padding: 0 0.85rem; border-radius: 99px; font-size: 0.8rem; font-weight: 600; color: var(--muted); }
  .filters button.on { background: var(--accent); color: var(--on-accent); }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 1rem; }
  .sc { display: flex; flex-direction: column; background: var(--surface); border-radius: 22px; overflow: hidden; box-shadow: var(--shadow-sm); transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out); }
  .sc:hover { translate: 0 -3px; box-shadow: var(--shadow-md); }
  .art { position: relative; display: block; aspect-ratio: 9 / 16; background: #0b0b0d; overflow: hidden; }
  .art .bg { position: absolute; inset: -10%; width: 120%; height: 120%; object-fit: cover; filter: blur(18px) brightness(0.6); }
  .poster { position: relative; width: 100%; height: 100%; object-fit: contain; }
  .poster.cover { object-fit: cover; }
  .ph { position: absolute; inset: 0; display: grid; place-items: center; color: rgba(255,255,255,.4); }
  .tags { position: absolute; top: 8px; left: 8px; display: flex; gap: 0.3rem; flex-wrap: wrap; }
  .tag { padding: 0.18rem 0.5rem; border-radius: 99px; font-size: 0.68rem; font-weight: 700; background: rgba(0,0,0,.6); color: #fff; }
  .tag.mint { background: var(--tile-mint); color: var(--tile-ink); }
  .tag.sky { background: var(--tile-sky); color: var(--tile-ink); }
  .tag.butter { background: var(--tile-butter); color: var(--tile-ink); }
  .tag.bad { background: var(--danger); color: #fff; }
  .tag.aspect { position: absolute; right: 8px; top: 8px; }
  .tag.dur { position: absolute; right: 8px; bottom: 8px; font-variant-numeric: tabular-nums; }
  .sc-body { padding: 0.75rem 0.85rem 0.85rem; display: flex; flex-direction: column; gap: 0.35rem; }
  .sc-body h3 { font-size: 0.9rem; font-weight: 700; line-height: 1.3; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .meta, .course { display: flex; gap: 0.7rem; font-size: 0.76rem; color: var(--muted); align-items: center; }
  .meta span, .course { display: inline-flex; align-items: center; gap: 0.25rem; }
  .course { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .sc-actions { display: flex; gap: 0.35rem; margin-top: 0.25rem; }
  .mini { display: inline-flex; align-items: center; gap: 0.3rem; height: 32px; padding: 0 0.65rem; border-radius: 99px; background: var(--surface2); font-size: 0.76rem; font-weight: 600; }
  .mini:hover { background: var(--surface3); }
  .mini.icon { width: 32px; padding: 0; justify-content: center; }
  .mini.danger { color: var(--danger); }
  .mini:first-child { flex: 1; justify-content: center; }

  .empty { display: flex; flex-direction: column; align-items: center; gap: 0.6rem; text-align: center; padding: 3rem 1.5rem; border-radius: 30px; background: var(--surface); box-shadow: var(--shadow-sm); }
  .empty p { color: var(--muted); max-width: 46ch; font-size: 0.9rem; }
  .e-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-peach); color: var(--tile-ink); }

  .msg { display: flex; gap: 0.45rem; align-items: center; font-size: 0.85rem; }
  .msg.bad { color: var(--danger); }

  .scrim { position: fixed; inset: 0; z-index: 200; background: var(--scrim); animation: fade var(--dur-2) var(--ease-out); }
  .modal {
    position: fixed; z-index: 210; left: 50%; top: 50%; translate: -50% -50%; width: min(480px, calc(100vw - 32px));
    max-height: calc(100vh - 32px); overflow: auto;
    background: var(--surface); border-radius: 28px; padding: 1.4rem; box-shadow: var(--shadow-lg);
    display: flex; flex-direction: column; gap: 0.9rem;
  }
  .modal h2 { font-size: 1.2rem; }
  .modal p { color: var(--text-secondary); font-size: 0.9rem; }
  .field { display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.84rem; font-weight: 600; color: var(--text-secondary); }
  .field input, .field textarea { background: var(--surface2); border: 1px solid transparent; color: var(--text); border-radius: 14px; padding: 0.65rem 0.85rem; font-size: 0.92rem; font-weight: 400; font-family: inherit; outline: none; }
  .field input:focus, .field textarea:focus { border-color: var(--accent); }
  .seg { display: grid; grid-template-columns: 1fr 1fr; gap: 0.25rem; padding: 0.25rem; border-radius: 99px; background: var(--surface2); }
  .seg button { min-height: 36px; border-radius: 99px; font-size: 0.8rem; font-weight: 600; color: var(--muted); }
  .seg button.on { background: var(--accent); color: var(--on-accent); }
  .check { display: flex; gap: 0.55rem; align-items: center; font-size: 0.86rem; }
  .check input { width: 18px; height: 18px; accent-color: var(--accent); }
  .m-actions { display: flex; justify-content: flex-end; gap: 0.6rem; }
  .danger-btn { background: var(--danger); color: #fff; }
  .danger-btn:hover { background: var(--danger); filter: brightness(1.08); }
  .toast {
    position: fixed; z-index: 220; left: 50%; bottom: 1.5rem; translate: -50% 0; max-width: calc(100vw - 32px);
    padding: 0.75rem 1.1rem; border-radius: 16px; background: var(--accent); color: var(--on-accent);
    font-size: 0.88rem; font-weight: 600; box-shadow: var(--shadow-lg); animation: rise 360ms var(--ease-out);
  }
  .toast.bad { background: var(--danger); color: #fff; }

  @media (max-width: 860px) {
    .details { grid-template-columns: 1fr; }
    .phone { max-width: 280px; margin: 0 auto; width: 100%; }
  }
  @media (max-width: 560px) {
    .stats { grid-template-columns: repeat(3, 1fr); gap: 0.5rem; }
    .stat b { font-size: 1.4rem; }
    .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.6rem; }
  }
</style>
