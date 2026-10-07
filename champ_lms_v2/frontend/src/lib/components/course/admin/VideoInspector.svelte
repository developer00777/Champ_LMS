<script lang="ts">
  import { onDestroy } from 'svelte';
  import { api, type AdminVideoItem } from '$lib/api/client';
  import { uploads, startVideoUpload, transcribeFiles, retryTranscript } from '$lib/stores/course-uploads';
  import { clock, parseCaptions, segmentsToText, textToSegments } from '$lib/utils/transcribe';
  import { icons } from '../icons';
  import VideoEditor from './VideoEditor.svelte';
  import ThumbnailStudio from '$lib/components/ThumbnailStudio.svelte';

  export let item: AdminVideoItem;
  export let courseId: string;
  export let onReload: () => void;

  let editing = false;
  let thumbOpen = false;
  $: thumbLabel = item.thumbnail_source === 'ai' ? 'AI image' : item.thumbnail_source === 'text' ? 'Text design'
    : item.thumbnail_source === 'upload' ? 'Uploaded' : item.thumbnail_url ? 'Frame picked by Bunny' : 'None yet';
  $: srcLen = item.source_duration_seconds;
  $: clipped = item.clip_start != null || item.clip_end != null;
  $: rangeText = clipped && srcLen
    ? `Plays ${clock(item.clip_start ?? 0)} – ${clock(item.clip_end ?? srcLen)} of the ${clock(srcLen)} video.`
    : srcLen ? `Plays the whole video (${clock(srcLen)}).` : 'Plays the whole video.';

  async function joinNext() {
    busy = 'join'; error = ''; message = '';
    try { await api.joinNextPart(courseId, item.id); onReload(); }
    catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  let tab: 'transcript' | 'notes' = 'transcript';
  let title = item.title;
  let description = item.description ?? '';
  let transcriptText = segmentsToText(item.transcript_segments);
  let notesText = item.notes ?? '';
  let transcriptDirty = false;
  let notesDirty = false;
  let busy = '';
  let message = '';
  let error = '';
  let shownId = item.id;

  // A different item selected, or fresh data from the server for this one.
  $: if (item.id !== shownId) {
    shownId = item.id;
    title = item.title; description = item.description ?? '';
    transcriptText = segmentsToText(item.transcript_segments); notesText = item.notes ?? '';
    transcriptDirty = notesDirty = false; message = error = '';
  }
  $: if (!transcriptDirty) transcriptText = segmentsToText(item.transcript_segments);
  $: if (!notesDirty) notesText = item.notes ?? '';

  $: up = $uploads[item.id];

  let saveTimer: ReturnType<typeof setTimeout>;
  function saveDetails() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      try {
        await api.updateEpisode(item.ref_id, { title: title.trim() || 'Untitled episode', description: description.trim() || null });
        item.title = title; onReload();
      } catch (e: any) { error = e.message; }
    }, 600);
  }

  async function run(label: string, fn: () => Promise<unknown>, done?: string) {
    busy = label; error = ''; message = '';
    try { await fn(); if (done) message = done; onReload(); }
    catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  function saveTranscript() {
    const segs = textToSegments(transcriptText);
    run('transcript', async () => {
      await api.saveTranscript(item.ref_id, segs, 'manual');
      transcriptDirty = false;
    }, `Saved ${segs.length} lines.`);
  }

  function onCaptionFile(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    (e.target as HTMLInputElement).value = '';
    if (!f) return;
    run('captions', async () => {
      const segs = parseCaptions(await f.text());
      if (!segs.length) throw new Error('No captions found in that file. Use a .vtt or .srt file.');
      // A caption file covers the whole video, so it is timed from the video's
      // start and reaches every part split from it.
      await api.saveTranscript(item.ref_id, segs, 'manual', 'source');
      transcriptDirty = false;
    }, 'Caption file saved as the transcript.');
  }

  function onRerunFile(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    (e.target as HTMLInputElement).value = '';
    if (!f) return;
    // Through the shared queue, so a passing failure is retried on its own.
    transcribeFiles([{ itemId: item.id, episodeId: item.ref_id, file: f }], onReload);
    message = `Transcribing ${f.name}. Notes follow once the transcript is saved.`;
  }

  // Retry a failed upload, or give an empty episode its file.
  function onRetryFile(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    (e.target as HTMLInputElement).value = '';
    if (f) { startVideoUpload(item.id, item.ref_id, f, onReload); message = `Uploading ${f.name}.`; }
  }

  function saveNotes() {
    run('notes', async () => { await api.saveEpisodeNotes(item.ref_id, notesText); notesDirty = false; }, 'Notes saved.');
  }
  function redraftNotes() {
    run('redraft', async () => { await api.generateEpisodeNotes(item.ref_id); notesDirty = false; }, 'Notes redrafted from the transcript.');
  }

  $: tStatus = up?.transcript === 'working' ? 'working' : up?.transcript === 'waiting' && up.retryAt ? 'retrying' : item.transcript_status;
  // Ticks once a second so the retry countdown stays current.
  let now = Date.now();
  const clockTimer = setInterval(() => (now = Date.now()), 1000);
  onDestroy(() => clearInterval(clockTimer));
</script>

<div class="insp-body">
  <div class="poster" style={item.thumbnail_url ? `background-image:url(${item.thumbnail_url})` : ''}>
    <span class="poster-ico">{@html icons.play}</span>
    {#if item.duration_seconds}<span class="dur">{clock(item.duration_seconds)}</span>{/if}
  </div>
  <div class="setting thumb">
    <div><b>Thumbnail</b><span>{thumbLabel}</span></div>
    <button class="btn sm" on:click={() => (thumbOpen = true)}>{@html icons.sparkle} {item.thumbnail_source ? 'Change' : 'Create'}</button>
  </div>
  {#if thumbOpen}
    <ThumbnailStudio kind="episode" ownerId={item.ref_id} title={item.title}
      kicker={item.episode_number ? `Episode ${item.episode_number}` : ''} current={item}
      onClose={() => (thumbOpen = false)} onSaved={() => { message = 'Thumbnail saved.'; onReload(); }} />
  {/if}

  <div class="kv">
    <span>Video</span>
    <b>
      {#if up?.stage === 'uploading' || up?.stage === 'queued'}
        <span class="pill warn">Uploading {Math.round((up.progress ?? 0) * 100)}%</span>
      {:else if up?.stage === 'failed'}
        <span class="pill bad" title={up.error}>Upload failed</span>
      {:else if item.status === 'ready'}
        <span class="pill ok">Ready</span>
      {:else if item.status === 'failed'}
        <span class="pill bad">Encoding failed</span>
      {:else if item.has_remote_video}
        <span class="pill warn">Encoding on Bunny</span>
      {:else}
        <span class="pill">No file yet</span>
      {/if}
    </b>
    {#if up}<span>File</span><b class="mono">{up.fileName}</b>{/if}
  </div>
  {#if up?.stage === 'failed'}<p class="error">{up.error}</p>{/if}
  {#if (up?.stage === 'failed' || (!up && !item.has_remote_video))}
    <label class="btn sm">{@html icons.upload} {up?.stage === 'failed' ? 'Try the upload again' : 'Upload the video file'}
      <input type="file" accept="video/*" hidden on:change={onRetryFile} /></label>
  {/if}

  <div class="setting clip">
    <div>
      <b>Trim and split{#if item.part} · part {item.part[0]} of {item.part[1]}{/if}</b>
      <span>{rangeText}</span>
      {#if item.status !== 'ready'}<span>Opens once the video has finished processing.</span>{/if}
    </div>
    <div class="row end">
      <button class="btn sm" on:click={() => (editing = true)} disabled={item.status !== 'ready'}>Trim or split</button>
      {#if item.part && item.part[0] < item.part[1]}
        <button class="btn sm ghost" on:click={joinNext} disabled={!!busy} title="Undo the split between this part and the next">
          {busy === 'join' ? 'Joining…' : 'Join with next part'}
        </button>
      {/if}
    </div>
  </div>
  {#if editing}
    <VideoEditor {courseId} {item} onClose={() => (editing = false)}
      onSaved={() => { editing = false; message = 'Saved. The canvas shows the new parts; add a quiz or test between them with +.'; onReload(); }} />
  {/if}

  <label class="field">
    <span>Episode title</span>
    <input type="text" bind:value={title} on:input={saveDetails} maxlength="200" />
  </label>
  <label class="field">
    <span>Short description</span>
    <textarea rows="2" bind:value={description} on:input={saveDetails}></textarea>
  </label>

  <div class="subtabs" role="tablist">
    <button class:on={tab === 'transcript'} on:click={() => (tab = 'transcript')}>Transcript</button>
    <button class:on={tab === 'notes'} on:click={() => (tab = 'notes')}>Notes</button>
  </div>

  {#if tab === 'transcript'}
    <div class="src-row">
      {#if tStatus === 'working' || tStatus === 'processing'}
        <span class="pill course"><span class="spin"></span>
          Writing transcript{#if up?.transcript === 'working'} · {Math.round(up.transcriptProgress * 100)}%{/if}
        </span>
      {:else if tStatus === 'retrying' && up?.retryAt}
        <span class="pill warn" title={up.transcriptError ?? ''}>Trying again in {Math.max(0, Math.ceil((up.retryAt - now) / 1000))} s</span>
      {:else if tStatus === 'failed'}
        <span class="pill bad" title={up?.transcriptError ?? ''}>Automatic transcript failed</span>
      {:else if item.transcript_source === 'auto'}
        <span class="pill course">{@html icons.sparkle} Auto-generated</span>
      {:else if item.transcript_source === 'manual'}
        <span class="pill ok">Edited by you</span>
      {:else}
        <span class="pill">No transcript yet</span>
      {/if}
      <div class="row">
        <label class="btn sm ghost">Upload .vtt / .srt<input type="file" accept=".vtt,.srt,text/vtt" hidden on:change={onCaptionFile} /></label>
        {#if item.transcript_source !== 'manual'}
          <label class="btn sm ghost" title="Pick the original video file again to redo the automatic transcript">
            Transcribe from file<input type="file" accept="video/*,audio/*" hidden on:change={onRerunFile} />
          </label>
        {/if}
      </div>
    </div>
    {#if up?.transcriptError && (up.transcript === 'failed' || up.transcript === 'waiting')}
      <p class="error">{up.transcriptError}</p>
      {#if up.transcript === 'failed'}<button class="btn sm" on:click={() => retryTranscript(item.id, onReload)}>Try again now</button>{/if}
    {/if}
    <textarea class="mono" rows="12" bind:value={transcriptText} on:input={() => (transcriptDirty = true)}
      placeholder="[0:00] First line of what is said…"></textarea>
    <p class="hint">One line per caption, starting with its time as [m:ss]. The learner's transcript follows the video using these times.</p>
    <div class="row end">
      <button class="btn sm primary" on:click={saveTranscript} disabled={!transcriptDirty || !!busy}>Save transcript</button>
    </div>
  {:else}
    <div class="src-row">
      {#if item.notes_source === 'ai'}<span class="pill course">{@html icons.sparkle} AI draft</span>
      {:else if item.notes_source === 'manual'}<span class="pill ok">Written by you</span>
      {:else}<span class="pill">No notes yet</span>{/if}
      <button class="btn sm ghost" on:click={redraftNotes} disabled={!item.transcript_segments.length || !!busy}>
        {@html icons.sparkle} {busy === 'redraft' ? 'Drafting…' : 'Redraft from transcript'}
      </button>
    </div>
    <textarea rows="11" bind:value={notesText} on:input={() => (notesDirty = true)}
      placeholder={'## Key points\n- …'}></textarea>
    <p class="hint">Learners see these under the video. Lines starting with “## ” become headings, “- ” become bullets.</p>
    <div class="row end">
      <button class="btn sm primary" on:click={saveNotes} disabled={!notesDirty || !!busy}>Save notes</button>
    </div>
  {/if}

  {#if message}<p class="okmsg">{message}</p>{/if}
  {#if error}<p class="error">{error}</p>{/if}
</div>
