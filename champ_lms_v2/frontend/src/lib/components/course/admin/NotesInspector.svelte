<script lang="ts">
  import { api, type AdminNotesItem } from '$lib/api/client';
  import { icons } from '../icons';

  export let item: AdminNotesItem;
  export let onReload: () => void;

  let title = item.title;
  let body = item.body;
  let area: HTMLTextAreaElement;
  let busy = '';
  let error = '';
  let saved = '';
  let shownId = item.id;

  $: if (item.id !== shownId) { shownId = item.id; title = item.title; body = item.body; error = saved = ''; }

  let timer: ReturnType<typeof setTimeout>;
  function save() {
    clearTimeout(timer);
    saved = '';
    timer = setTimeout(async () => {
      try {
        const r = await api.updateNote(item.ref_id, { title: title.trim() || 'Notes', body });
        item.source = r.source; item.title = r.title; item.body = r.body; item = item;
        saved = 'Saved'; onReload();
      } catch (e: any) { error = e.message; }
    }, 700);
  }

  // Put a markup prefix at the start of the current line.
  function prefix(mark: string) {
    const start = body.lastIndexOf('\n', area.selectionStart - 1) + 1;
    body = body.slice(0, start) + mark + body.slice(start);
    save();
    requestAnimationFrame(() => { area.focus(); area.selectionStart = area.selectionEnd = start + mark.length; });
  }

  async function draft() {
    busy = 'draft'; error = '';
    try { const r = await api.draftNote(item.ref_id); body = r.body; item.source = r.source; item = item; onReload(); }
    catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  async function attach(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    (e.target as HTMLInputElement).value = '';
    if (!f) return;
    busy = 'attach'; error = '';
    try { const r = await api.uploadNoteAttachment(item.ref_id, f); item.attachment_name = r.attachment_name; item.attachment_size = r.attachment_size; item = item; onReload(); }
    catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  async function unattach() {
    busy = 'attach'; error = '';
    try { await api.deleteNoteAttachment(item.ref_id); item.attachment_name = null; item.attachment_size = null; item = item; onReload(); }
    catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  const kb = (n: number | null) => (n ? (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`) : '');
</script>

<div class="insp-body">
  <label class="field">
    <span>Page title</span>
    <input type="text" bind:value={title} on:input={save} maxlength="200" />
  </label>
  <div class="src-row">
    {#if item.source === 'ai'}<span class="pill course">{@html icons.sparkle} AI draft</span>{:else}<span class="pill ok">Written by you</span>{/if}
    <button class="btn sm ghost" on:click={draft} disabled={!!busy}>{@html icons.sparkle} {busy === 'draft' ? 'Drafting…' : 'Draft from this section’s videos'}</button>
  </div>
  <div>
    <div class="toolbar">
      <button on:click={() => prefix('## ')} title="Heading">H</button>
      <button on:click={() => prefix('- ')} title="Bullet">•</button>
      <span class="saved">{saved}</span>
    </div>
    <textarea bind:this={area} rows="14" bind:value={body} on:input={save} class="with-toolbar"
      placeholder={'## Heading\n- A bullet\n\nA paragraph.'}></textarea>
  </div>
  <div class="field">
    <span>Attachment</span>
    {#if item.attachment_name}
      <div class="filechip">
        <span class="ti">{@html icons.file}</span><b class="mono grow">{item.attachment_name}</b>
        <span class="hint">{kb(item.attachment_size)}</span>
        <button class="icon-btn" on:click={unattach} disabled={!!busy} aria-label="Remove attachment">{@html icons.x}</button>
      </div>
    {:else}
      <label class="btn sm ghost">{@html icons.upload} {busy === 'attach' ? 'Uploading…' : 'Attach a PDF (up to 10 MB)'}
        <input type="file" accept="application/pdf,.pdf" hidden on:change={attach} disabled={!!busy} /></label>
    {/if}
  </div>
  {#if error}<p class="error">{error}</p>{/if}
</div>
