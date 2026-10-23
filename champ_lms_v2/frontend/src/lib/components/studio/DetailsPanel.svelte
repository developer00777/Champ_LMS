<script lang="ts">
  // The episode's title and description, with an AI suggestion from the
  // transcript. Saved straight away, separately from the video edits, like
  // the thumbnail.
  import { api } from '$lib/api/client';
  import { useStudio } from './studio';

  const st = useStudio();
  const { ep } = st;

  let title = $ep.title;
  let description = $ep.description ?? '';
  let busy = '';
  $: changed = title.trim() !== $ep.title || (description.trim() || null) !== ($ep.description ?? null);

  async function save() {
    busy = 'save';
    try {
      const t = title.trim() || 'Untitled episode';
      const desc = description.trim() || null;
      await api.updateEpisode($ep.id, { title: t, description: desc });
      ep.update(e => ({ ...e, title: t, description: desc }));
      title = t;
      st.say('Title and description saved.');
    } catch (e: any) { st.say(e.message, 'bad'); }
    finally { busy = ''; }
  }

  async function suggest() {
    busy = 'ai';
    try {
      const r = await api.studioAi($ep.id, { task: 'details' });
      title = r.details.title;
      description = r.details.description;
      st.say('Suggested from the transcript. Edit it, then save.');
    } catch (e: any) { st.say(e.message, 'bad'); }
    finally { busy = ''; }
  }
</script>

<div class="p-sec">
  <h3 class="p-h">Title and description</h3>
  <p class="p-note">What learners see on the {$ep.layout === 'canvas' ? 'course' : 'module'} page and above the player. Saved on its own, straight away.</p>
  <label class="field">Title
    <input type="text" bind:value={title} maxlength="200" />
  </label>
  <label class="field">Description
    <textarea rows="5" bind:value={description} maxlength="1000" placeholder="What this video teaches"></textarea>
  </label>
  <div class="row">
    <button class="btn sm hot" on:click={save} disabled={!!busy || !changed}>{busy === 'save' ? 'Saving…' : 'Save details'}</button>
    <button class="btn sm ai" on:click={suggest} disabled={!!busy || $ep.transcript_segments.length < 3}>{busy === 'ai' ? 'Writing…' : '✦ Suggest with AI'}</button>
    {#if changed}<button class="btn sm ghost" on:click={() => { title = $ep.title; description = $ep.description ?? ''; }}>Revert</button>{/if}
  </div>
  {#if $ep.part}<p class="p-note">This is part {$ep.part[0]} of {$ep.part[1]}; each part has its own title.</p>{/if}
</div>

<style>
  textarea { font: inherit; font-size: 0.82rem; color: var(--st-text); background: var(--st-deep); border: 1px solid var(--st-line); border-radius: 7px; padding: 0.45rem 0.55rem; resize: vertical; line-height: 1.45; }
  textarea:focus { outline: none; border-color: #6ea8ff; }
</style>
