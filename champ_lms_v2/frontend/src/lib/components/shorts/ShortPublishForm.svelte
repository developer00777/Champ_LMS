<script lang="ts">
  // Title, course link and how it sits in the feed, then the upload. Used for
  // a file as it is and for one the resizer just rendered.
  import { createEventDispatcher, onMount } from 'svelte';
  import { api, type AdminShort, type ShortFit } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Select from '$lib/components/Select.svelte';
  import { publishShort, MAX_SHORT_SECONDS } from '$lib/utils/shorts-upload';
  import { clock, ratioLabel, type VideoMeta } from '$lib/utils/resize-video';

  export let file: File;
  export let meta: VideoMeta;
  export let poster: Blob | null = null;
  export let madeWith: 'resizer' | undefined = undefined;

  const dispatch = createEventDispatcher<{ published: AdminShort }>();

  let title = file.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ').replace(/\s+\d+x\d+$/, '').trim().slice(0, 120);
  let description = '';
  let moduleId = '';
  let fit: ShortFit = 'contain';
  let publishNow = true;
  let busy = false;
  let progress = 0;
  let status = '';
  let error = '';

  $: vertical = meta.height > meta.width * 1.5;
  $: tooLong = meta.duration > MAX_SHORT_SECONDS + 1.5;

  let courseOptions = [{ value: '', label: 'No course' }];
  onMount(async () => {
    try {
      const c = await api.adminContent();
      courseOptions = [{ value: '', label: 'No course' }, ...c.modules.map(m => ({ value: m.id, label: m.title }))];
    } catch { /* the link is optional */ }
  });

  async function publish() {
    if (!title.trim()) { error = 'Give the short a title'; return; }
    busy = true; error = ''; progress = 0;
    try {
      const short = await publishShort(file, {
        title: title.trim(),
        description: description.trim() || undefined,
        module_id: moduleId || null,
        duration_seconds: meta.duration,
        width: meta.width,
        height: meta.height,
        fit: vertical ? 'cover' : fit,
        is_published: publishNow,
        made_with: madeWith,
      }, (p, s) => { if (p) progress = p; status = s; }, poster);
      dispatch('published', short);
    } catch (e: any) {
      error = e?.message ?? 'Upload failed';
    } finally {
      busy = false;
    }
  }
</script>

<div class="form">
  <p class="facts">
    <span class="ui-pill sky"><Icon name="shorts" size={14} /> {ratioLabel(meta.width, meta.height)} · {meta.width}×{meta.height}</span>
    <span class="ui-pill" class:bad={tooLong}><Icon name="clock" size={14} /> {clock(meta.duration)}</span>
  </p>
  {#if tooLong}
    <p class="msg bad"><Icon name="alert" size={15} /> Shorts can be up to {clock(MAX_SHORT_SECONDS)}. Trim it in the resizer first.</p>
  {/if}
  <label class="field">Title *
    <input bind:value={title} maxlength="120" placeholder="e.g. 3 objection handlers in 60 seconds" />
  </label>
  <label class="field">Description
    <textarea bind:value={description} rows="2" maxlength="2000" placeholder="One or two lines under the title"></textarea>
  </label>
  <!-- svelte-ignore a11y-label-has-associated-control -->
  <label class="field">Link a course <span class="opt">optional · shown as “Watch the course” on the short</span>
    <Select bind:value={moduleId} options={courseOptions} searchable placeholder="No course" />
  </label>
  {#if !vertical}
    <div class="field">In the feed
      <div class="seg" role="radiogroup" aria-label="How it fills the screen">
        <button role="radio" aria-checked={fit === 'contain'} class:on={fit === 'contain'} on:click={() => (fit = 'contain')}>Whole picture, blurred sides</button>
        <button role="radio" aria-checked={fit === 'cover'} class:on={fit === 'cover'} on:click={() => (fit = 'cover')}>Fill the screen, crop</button>
      </div>
    </div>
  {/if}
  <label class="check"><input type="checkbox" bind:checked={publishNow} /> Show it to learners as soon as it's ready</label>

  {#if busy}
    <div class="bar"><span style="width:{Math.round(progress * 100)}%"></span></div>
    <p class="msg"><span class="spin"></span> {status} {progress ? `${Math.round(progress * 100)}%` : ''}</p>
  {/if}
  {#if error}<p class="msg bad"><Icon name="alert" size={15} /> {error}</p>{/if}
  <div class="actions">
    <slot name="extra" />
    <button class="btn-primary" on:click={publish} disabled={busy || tooLong || !title.trim()}>
      {#if busy}<span class="spin"></span> Uploading…{:else}<Icon name="upload" size={17} /> Publish short{/if}
    </button>
  </div>
</div>

<style>
  .form { display: flex; flex-direction: column; gap: 0.9rem; }
  .facts { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .ui-pill.bad { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }
  .field { display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.84rem; font-weight: 600; color: var(--text-secondary); }
  .opt { font-weight: 400; color: var(--muted); font-size: 0.76rem; }
  input:not([type='checkbox']), textarea {
    background: var(--surface2); border: 1px solid transparent; color: var(--text); border-radius: 14px;
    padding: 0.7rem 0.9rem; font-size: 0.93rem; font-weight: 400; font-family: inherit; outline: none; resize: vertical;
  }
  input:focus, textarea:focus { background: var(--surface); border-color: var(--accent); }
  .seg { display: grid; grid-template-columns: 1fr 1fr; gap: 0.25rem; padding: 0.25rem; border-radius: 18px; background: var(--surface2); }
  .seg button { min-height: 38px; border-radius: 14px; font-size: 0.8rem; font-weight: 600; color: var(--muted); padding: 0.3rem 0.5rem; }
  .seg button.on { background: var(--accent); color: var(--on-accent); }
  .check { display: flex; gap: 0.55rem; align-items: center; font-size: 0.86rem; }
  .check input { width: 18px; height: 18px; accent-color: var(--accent); }
  .msg { display: flex; gap: 0.45rem; align-items: center; font-size: 0.84rem; color: var(--text-secondary); }
  .msg.bad { color: var(--danger); }
  .bar { height: 10px; border-radius: 99px; background: var(--surface2); overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); transition: width 200ms linear; }
  .actions { display: flex; flex-wrap: wrap; gap: 0.6rem; justify-content: flex-end; }
  .spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid currentColor; border-right-color: transparent; display: inline-block; animation: sp 0.8s linear infinite; }
  @keyframes sp { to { rotate: 360deg; } }
</style>
