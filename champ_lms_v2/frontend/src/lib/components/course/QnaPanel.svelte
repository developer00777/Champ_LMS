<script lang="ts">
  import { tick } from 'svelte';
  import { api, type EpisodeQuestion } from '$lib/api/client';
  import { clock } from '$lib/utils/transcribe';
  import { icons } from './icons';

  export let courseId: string;
  export let episodeId: string;
  export let questions: EpisodeQuestion[] = [];
  export let time = 0; // playhead, clip time
  export let isAdmin = false;
  export let onSeek: (seconds: number) => void;
  export let onChange: (questions: EpisodeQuestion[]) => void;

  let body = '';
  let pin = true;
  let pinnedAt: number | null = null; // set when the player's Q&A button opened this
  let busy = '';
  let error = '';
  let filter: 'all' | 'mine' | 'open' = 'all';
  let box: HTMLTextAreaElement;
  let drafts: Record<string, string> = {};
  let editing: string | null = null;

  $: at = pinnedAt ?? time;
  $: shown = questions.filter(q => filter === 'all' || (filter === 'mine' ? q.mine : !q.answer));
  $: openCount = questions.filter(q => !q.answer).length;

  /** Called by the page when the player's Q&A button is pressed. */
  export async function focusAsk(atSeconds: number) {
    pinnedAt = atSeconds; pin = true;
    await tick();
    box?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    box?.focus({ preventScroll: true });
  }

  async function ask() {
    const text = body.trim();
    if (!text) return;
    busy = 'ask'; error = '';
    try {
      const q = await api.askQuestion(courseId, episodeId, text, pin ? Math.floor(at) : null);
      onChange([q, ...questions]);
      body = ''; pinnedAt = null;
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  async function remove(q: EpisodeQuestion) {
    if (!confirm(q.mine ? 'Delete your question?' : 'Delete this question for everyone?')) return;
    busy = q.id; error = '';
    try {
      await api.deleteMyQuestion(courseId, q.id);
      onChange(questions.filter(x => x.id !== q.id));
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  async function answer(q: EpisodeQuestion) {
    const text = (drafts[q.id] ?? '').trim();
    if (!text) return;
    busy = q.id; error = '';
    try {
      const saved = await api.answerQuestion(q.id, text);
      onChange(questions.map(x => (x.id === q.id ? { ...saved, mine: x.mine } : x)));
      editing = null; delete drafts[q.id]; drafts = drafts;
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  function startEdit(q: EpisodeQuestion) { editing = q.id; drafts[q.id] = q.answer ?? ''; }

  function ago(iso: string | null) {
    if (!iso) return '';
    const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (m < 1) return 'just now';
    if (m < 60) return `${m} min ago`;
    if (m < 1440) return `${Math.round(m / 60)} h ago`;
    return `${Math.round(m / 1440)} d ago`;
  }
  const initials = (n: string) => n.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
</script>

<div class="qna">
  <form class="ask" on:submit|preventDefault={ask}>
    <textarea bind:this={box} bind:value={body} rows="3" maxlength="2000"
      placeholder="Ask about this video. Your admin answers, and everyone on the course can read it."
      on:keydown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) ask(); }}></textarea>
    <div class="ask-f">
      <label class="pin"><input type="checkbox" bind:checked={pin} /> At <span class="mono">{clock(at)}</span></label>
      {#if pinnedAt !== null}<button type="button" class="link" on:click={() => (pinnedAt = null)}>follow the video</button>{/if}
      <span class="grow"></span>
      <button class="btn primary sm" type="submit" disabled={!body.trim() || busy === 'ask'}>{busy === 'ask' ? 'Posting…' : 'Ask'}</button>
    </div>
  </form>

  {#if error}<p class="error">{error}</p>{/if}

  <div class="bar">
    <span class="eyebrow">{questions.length} question{questions.length === 1 ? '' : 's'}{openCount ? ` · ${openCount} waiting for an answer` : ''}</span>
    <div class="seg">
      <button class:on={filter === 'all'} on:click={() => (filter = 'all')}>All</button>
      <button class:on={filter === 'mine'} on:click={() => (filter = 'mine')}>Mine</button>
      <button class:on={filter === 'open'} on:click={() => (filter = 'open')}>Unanswered</button>
    </div>
  </div>

  {#if !shown.length}
    <p class="empty">{questions.length ? 'Nothing here.' : 'No questions yet. Be the first to ask.'}</p>
  {:else}
    <ol class="list">
      {#each shown as q (q.id)}
        <li class="q">
          <span class="av">{initials(q.full_name)}</span>
          <div class="qb">
            <div class="meta">
              <b>{q.mine ? 'You' : q.full_name}</b>
              {#if q.at_seconds !== null}<button class="chip mono" on:click={() => q.at_seconds !== null && onSeek(q.at_seconds)} title="Play from here">{@html icons.play} {clock(q.at_seconds)}</button>{/if}
              <span class="muted">{ago(q.created_at)}</span>
              {#if !q.answer}<span class="pill wait">Waiting for an answer</span>{/if}
              <span class="grow"></span>
              {#if q.mine || isAdmin}
                <button class="icon-btn" on:click={() => remove(q)} disabled={busy === q.id} aria-label="Delete question">{@html icons.x}</button>
              {/if}
            </div>
            <p class="text">{q.body}</p>

            {#if q.answer && editing !== q.id}
              <div class="ans">
                <div class="meta"><span class="pill ok">{@html icons.check} Answer</span><b>{q.answered_by_name}</b><span class="muted">{ago(q.answered_at)}</span>
                  {#if isAdmin}<span class="grow"></span><button class="link" on:click={() => startEdit(q)}>Edit</button>{/if}
                </div>
                <p class="text">{q.answer}</p>
              </div>
            {:else if isAdmin}
              <div class="reply">
                <textarea rows="2" bind:value={drafts[q.id]} placeholder="Write an answer everyone on the course will see"></textarea>
                <div class="ask-f">
                  <span class="grow"></span>
                  {#if editing === q.id}<button class="btn sm ghost" on:click={() => (editing = null)}>Cancel</button>{/if}
                  <button class="btn sm primary" on:click={() => answer(q)} disabled={!(drafts[q.id] ?? '').trim() || busy === q.id}>
                    {busy === q.id ? 'Saving…' : editing === q.id ? 'Save answer' : 'Answer'}
                  </button>
                </div>
              </div>
            {/if}
          </div>
        </li>
      {/each}
    </ol>
  {/if}
</div>

<style>
  .qna { display: grid; gap: 0.9rem; }
  .ask { display: grid; gap: 0.45rem; padding: 0.8rem; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
  textarea {
    width: 100%; resize: vertical; font: inherit; font-size: 0.88rem; color: var(--text); line-height: 1.45;
    background: var(--bg); border: 1px solid var(--border-hover); border-radius: 8px; padding: 0.55rem 0.7rem;
  }
  textarea:focus { outline: none; border-color: var(--accent); }
  .ask-f { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
  .grow { flex: 1; }
  .pin { display: inline-flex; gap: 0.35rem; align-items: center; font-size: 0.8rem; color: var(--text-secondary); }
  .mono { font-family: ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; }
  .link { font-size: 0.78rem; color: var(--accent); font-weight: 600; }
  .error { font-size: 0.82rem; color: #ff6b70; }
  .bar { display: flex; gap: 0.6rem; align-items: center; justify-content: space-between; flex-wrap: wrap; }
  .eyebrow { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  .seg { display: inline-flex; padding: 3px; gap: 2px; border-radius: 9px; background: var(--surface2); }
  .seg button { height: 26px; padding: 0 0.7rem; border-radius: 6px; font-weight: 600; font-size: 0.76rem; color: var(--muted); }
  .seg button.on { background: var(--surface); color: var(--text); }
  .empty { padding: 1.6rem 1rem; text-align: center; color: var(--muted); font-size: 0.88rem; border: 1px dashed var(--border-hover); border-radius: 12px; }
  .list { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.6rem; }
  .q { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 0.7rem; padding: 0.8rem; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
  .av { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 50%; background: var(--surface3); font-weight: 700; font-size: 0.72rem; }
  .qb { display: grid; gap: 0.35rem; min-width: 0; }
  .meta { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; font-size: 0.8rem; }
  .muted { color: var(--muted); }
  .text { font-size: 0.9rem; line-height: 1.5; white-space: pre-wrap; overflow-wrap: anywhere; }
  .chip { display: inline-flex; gap: 0.25rem; align-items: center; height: 22px; padding: 0 0.5rem; border-radius: 6px; background: var(--surface2); font-size: 0.74rem; color: var(--text); }
  .chip:hover { background: var(--surface3); }
  .pill { display: inline-flex; gap: 0.25rem; align-items: center; height: 20px; padding: 0 8px; border-radius: 99px; font-size: 0.7rem; font-weight: 600; }
  .pill.ok { background: rgba(46, 204, 113, 0.14); color: #2ecc71; }
  .pill.wait { background: rgba(240, 165, 64, 0.13); color: #f0a540; }
  .ans { margin-top: 0.2rem; padding: 0.6rem 0.75rem; border-left: 3px solid #2ecc71; border-radius: 0 8px 8px 0; background: var(--surface2); display: grid; gap: 0.3rem; }
  .reply { display: grid; gap: 0.4rem; margin-top: 0.2rem; }
  .btn { display: inline-flex; align-items: center; gap: 0.35rem; height: 32px; padding: 0 0.9rem; border-radius: 8px; border: 1px solid var(--border-hover); background: var(--surface2); color: var(--text); font-weight: 600; font-size: 0.82rem; }
  .btn.sm { height: 28px; padding: 0 0.7rem; font-size: 0.78rem; }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
  .btn.ghost { background: transparent; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .icon-btn { display: inline-grid; place-items: center; width: 26px; height: 26px; border-radius: 7px; color: var(--muted); }
  .icon-btn:hover { background: var(--surface2); color: var(--text); }
</style>
