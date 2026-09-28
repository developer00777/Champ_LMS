<script lang="ts">
  import { api, type AdminCourse, type AdminQuizItem, type AdminVideoItem, type QuizQuestion } from '$lib/api/client';
  import { icons } from '../icons';

  export let course: AdminCourse;
  export let item: AdminQuizItem;
  export let onReload: () => void;

  let title = item.title;
  let questions: QuizQuestion[] = clone(item.questions);
  let dirty = false;
  let busy = '';
  let error = '';
  let message = '';
  let shownId = item.id;

  function clone(qs: QuizQuestion[]) { return qs.map(q => ({ ...q, options: [...q.options] })); }

  $: if (item.id !== shownId) {
    shownId = item.id; title = item.title; questions = clone(item.questions); dirty = false; error = message = '';
  }
  $: if (!dirty) questions = clone(item.questions);

  $: videos = course.items.filter((i): i is AdminVideoItem => i.kind === 'video');
  $: epTitle = (id?: string | null) => {
    const v = videos.find(x => x.ref_id === id);
    return v ? `Ep ${v.episode_number} · ${v.title}` : null;
  };

  let settingsTimer: ReturnType<typeof setTimeout>;
  function saveSettings(change: Parameters<typeof api.updateQuiz>[1], wait = 500) {
    Object.assign(item, change);
    item = item;
    clearTimeout(settingsTimer);
    settingsTimer = setTimeout(async () => {
      try { await api.updateQuiz(item.ref_id, change); onReload(); }
      catch (e: any) { error = e.message; }
    }, wait);
  }

  const asDifficulty = (v: string) => (v === 'easy' || v === 'hard' ? v : 'medium') as AdminQuizItem['difficulty'];

  function toggleSource(id: string, on: boolean) {
    const next = on ? [...item.source_episode_ids, id] : item.source_episode_ids.filter(x => x !== id);
    saveSettings({ source_episode_ids: next }, 0);
  }

  async function writeWithAi() {
    busy = 'ai'; error = ''; message = '';
    try {
      const r = await api.generateQuiz(item.ref_id);
      dirty = false;
      message = `${r.questions.length} questions written. Check them before learners see the quiz.`
        + (r.skipped_episodes.length ? ` Left out (no transcript yet): ${r.skipped_episodes.join(', ')}.` : '');
      onReload();
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  async function saveQuestions() {
    busy = 'save'; error = ''; message = '';
    try {
      await api.updateQuiz(item.ref_id, { questions });
      dirty = false; message = 'Questions saved.'; onReload();
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  function edit(fn: () => void) { fn(); questions = questions; dirty = true; }
  const addQuestion = () => edit(() => questions.push({ question: '', options: ['', '', '', ''], correct_index: 0 }));
</script>

<div class="insp-body">
  <label class="field">
    <span>Quiz title</span>
    <input type="text" bind:value={title} on:input={() => saveSettings({ title: title.trim() || 'Checkpoint quiz' })} maxlength="200" />
  </label>

  <div class="field">
    <span>Write questions from these episodes</span>
    {#each videos as v (v.id)}
      <label class="chk">
        <input type="checkbox" checked={item.source_episode_ids.includes(v.ref_id)}
          on:change={e => toggleSource(v.ref_id, e.currentTarget.checked)} />
        Ep {v.episode_number} · {v.title}
        {#if !v.transcript_segments.length}<span class="muted">(no transcript yet)</span>{/if}
      </label>
    {:else}
      <p class="hint">Add videos to the course first.</p>
    {/each}
  </div>

  <div class="row">
    <label class="field grow">
      <span>Questions <b class="mono">{item.question_count}</b></span>
      <input type="range" min="1" max="20" value={item.question_count}
        on:input={e => saveSettings({ question_count: +e.currentTarget.value })} />
    </label>
    <label class="field" style="width:120px">
      <span>Difficulty</span>
      <select value={item.difficulty} on:change={e => saveSettings({ difficulty: asDifficulty(e.currentTarget.value) }, 0)}>
        <option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option>
      </select>
    </label>
    <label class="field" style="width:90px">
      <span>Pass %</span>
      <input type="number" min="1" max="100" value={item.pass_threshold}
        on:input={e => { const v = +e.currentTarget.value; if (v >= 1 && v <= 100) saveSettings({ pass_threshold: v }); }} />
    </label>
  </div>

  <div class="setting">
    <div><b>Must pass to continue</b><span>Locks the next item until this quiz is passed. Retakes are unlimited and need no approval.</span></div>
    <button class="tgl" class:on={item.must_pass} role="switch" aria-checked={item.must_pass} aria-label="Must pass to continue"
      on:click={() => saveSettings({ must_pass: !item.must_pass }, 0)}></button>
  </div>

  {#if busy === 'ai'}
    <div class="gen-load"><span class="spin"></span>Reading {item.source_episode_ids.length} transcript{item.source_episode_ids.length === 1 ? '' : 's'} and writing {item.question_count} questions…</div>
  {:else}
    <button class="btn" on:click={writeWithAi} disabled={!item.source_episode_ids.length || !!busy}>
      {@html icons.sparkle} {item.questions.length ? 'Rewrite questions with AI' : 'Write questions with AI'}
    </button>
  {/if}

  {#if !questions.length}
    <p class="hint">Learners don't see this quiz until it has questions.</p>
  {/if}
  <ol class="qlist">
    {#each questions as q, qi}
      <li>
        <div class="q-top">
          <input type="text" value={q.question} placeholder="Question" aria-label="Question {qi + 1}"
            on:input={e => edit(() => (q.question = e.currentTarget.value))} />
          <button class="icon-btn" aria-label="Remove question" on:click={() => edit(() => questions.splice(qi, 1))}>{@html icons.x}</button>
        </div>
        <ul>
          {#each q.options as o, oi}
            <li>
              <button class="opt" class:ok={oi === q.correct_index} aria-label="Mark as the correct answer"
                on:click={() => edit(() => (q.correct_index = oi))}>{@html oi === q.correct_index ? icons.check : ''}</button>
              <input type="text" value={o} placeholder="Option {oi + 1}" on:input={e => edit(() => (q.options[oi] = e.currentTarget.value))} />
            </li>
          {/each}
        </ul>
        {#if epTitle(q.source_episode_id)}<div class="q-src">From {epTitle(q.source_episode_id)}</div>{/if}
      </li>
    {/each}
  </ol>
  <div class="row between">
    <button class="btn sm ghost" on:click={addQuestion}>{@html icons.plus} Write a question yourself</button>
    <button class="btn sm primary" on:click={saveQuestions} disabled={!dirty || !!busy}>{busy === 'save' ? 'Saving…' : 'Save questions'}</button>
  </div>

  {#if message}<p class="okmsg">{message}</p>{/if}
  {#if error}<p class="error">{error}</p>{/if}
</div>
