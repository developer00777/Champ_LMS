<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, type AdminTest, type TestQuestionDraft, type ParsedPdfForTest } from '$lib/api/client';

  const CATEGORIES = ['sales', 'leadership', 'onboarding', 'product', 'engineering', 'ops'];
  const id = $page.params.id;

  let test: AdminTest | null = null;
  let questions: TestQuestionDraft[] = [];
  let loading = true;
  let busy = false;
  let error = '';
  let saved = '';

  // --- extend this test with more questions -------------------------------
  type Draft = TestQuestionDraft & { duplicate_of_existing?: boolean };
  let showExtend = false;
  let extendFile: File | null = null;
  let extendUseAi = false;
  let parsing = false;
  let extendError = '';
  let parsed: ParsedPdfForTest | null = null;
  let incoming: Draft[] = [];
  // which of the parsed questions to actually append — duplicates start off
  let include: boolean[] = [];

  function pickExtendFile(e: Event) {
    extendFile = (e.target as HTMLInputElement).files?.[0] ?? null;
    extendError = '';
  }

  async function parseMore() {
    if (!extendFile) { extendError = 'Choose a PDF or Word file first'; return; }
    parsing = true; extendError = '';
    try {
      parsed = await api.parseTestPdfForTest(id, extendFile, extendUseAi);
      incoming = parsed.questions.map((q) => ({ ...q }));
      include = incoming.map((q) => !q.duplicate_of_existing);
    } catch (e: any) { extendError = e.message; }
    finally { parsing = false; }
  }

  function cancelExtend() {
    showExtend = false; parsed = null; incoming = []; include = [];
    extendFile = null; extendError = '';
  }

  $: selectedCount = include.filter(Boolean).length;
  $: selectedUnscorable = incoming.filter((q, i) => include[i] && !scorable(q)).length;

  function setIncomingAnswer(qi: number, oi: number) {
    incoming[qi].correct_index = oi;
    incoming = incoming;
  }

  // Appends only the ticked questions. The existing set is never resent, so a
  // long test can be extended without round-tripping every question it holds.
  async function appendSelected() {
    const chosen = incoming.filter((_, i) => include[i]);
    if (chosen.length === 0) { extendError = 'Tick at least one question to add'; return; }
    busy = true; extendError = '';
    try {
      const result = await api.appendTestQuestions(id, chosen, {
        filename: parsed?.source_filename,
        parser: parsed?.source_parser,
      });
      test = result;
      questions = result.questions.map((q) => ({ ...q }));
      cancelExtend();
      saved = result.unpublished_by_this_change
        ? `${result.added} question(s) added. The test was moved back to draft because `
          + `some of them still need a correct answer.`
        : `${result.added} question(s) added.`
          + (result.existing_attempts
            ? ` ${result.existing_attempts} earlier attempt(s) keep the scores they were graded on.`
            : '');
      setTimeout(() => (saved = ''), 6000);
    } catch (e: any) { extendError = e.message; }
    finally { busy = false; }
  }

  onMount(load);

  async function load() {
    loading = true;
    try {
      test = await api.adminTest(id);
      questions = test.questions.map((q) => ({ ...q }));
      error = '';
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  function scorable(q: TestQuestionDraft): boolean {
    return q.correct_index !== null && q.correct_index >= 0
      && q.correct_index < q.options.length && q.options.length >= 2;
  }
  $: unscorable = questions.filter((q) => !scorable(q)).length;

  function setAnswer(qi: number, oi: number) { questions[qi].correct_index = oi; questions = questions; }
  function removeQuestion(qi: number) { questions = questions.filter((_, i) => i !== qi); }
  function addOption(qi: number) { questions[qi].options = [...questions[qi].options, '']; questions = questions; }
  function removeOption(qi: number, oi: number) {
    const q = questions[qi];
    q.options = q.options.filter((_, i) => i !== oi);
    if (q.correct_index === oi) q.correct_index = null;
    else if (q.correct_index !== null && q.correct_index > oi) q.correct_index -= 1;
    questions = questions;
  }
  function addQuestion() {
    questions = [...questions, { question: '', options: ['', ''], correct_index: null,
      explanation: null, topic: null, marks: 1 }];
  }

  async function save() {
    if (!test) return;
    busy = true; error = ''; saved = '';
    try {
      test = await api.updateTestSeries(id, {
        title: test.title,
        description: test.description,
        category: test.category,
        department: test.department,
        pass_threshold: test.pass_threshold,
        duration_minutes: test.duration_minutes,
        max_attempts: test.max_attempts,
        shuffle_questions: test.shuffle_questions,
        proctoring_enabled: test.proctoring_enabled,
        questions,
      });
      questions = test.questions.map((q) => ({ ...q }));
      saved = 'Saved.';
      setTimeout(() => (saved = ''), 2500);
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  async function togglePublish() {
    if (!test) return;
    busy = true; error = '';
    try {
      const r = await api.publishTestSeries(id, !test.is_published);
      test.is_published = r.is_published;
      test = test;
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }
</script>

<div class="page">
  <p class="breadcrumb"><a href="/admin/tests">← Test Series</a></p>

  {#if loading}
    <div class="skeleton big"></div>
  {:else if !test}
    <p class="error">{error || 'Test not found'}</p>
  {:else}
    <div class="head">
      <div>
        <h1>{test.title}</h1>
        <p class="sub">
          {test.total_questions} questions · {test.total_marks} marks
          {#if test.source_filename}· from {test.source_filename} ({test.source_parser}){/if}
        </p>
      </div>
      <div class="head-actions">
        <span class="status" class:live={test.is_published}>{test.is_published ? 'Published' : 'Draft'}</span>
        <button class="btn primary" on:click={() => (showExtend ? cancelExtend() : (showExtend = true))}>
          {showExtend ? 'Cancel' : '+ Add questions from a document'}
        </button>
        <a href="/admin/tests/{id}/results" class="btn">Results</a>
      </div>
    </div>

    {#if error}<p class="error">{error}</p>{/if}
    {#if saved}<p class="ok">{saved}</p>{/if}

    <div class="form-card">
      <h2>Settings</h2>
      <label>Title<input bind:value={test.title} /></label>
      <label>Description<input bind:value={test.description} placeholder="Optional" /></label>
      <div class="row">
        <label>Category
          <select bind:value={test.category}>
            <option value={null}>—</option>
            {#each CATEGORIES as c}<option value={c}>{c}</option>{/each}
          </select>
        </label>
        <label>Department<input bind:value={test.department} placeholder="blank = everyone" /></label>
      </div>
      <div class="row">
        <label>Pass mark %<input type="number" min="1" max="100" bind:value={test.pass_threshold} /></label>
        <label>Time limit (min)<input type="number" min="1" bind:value={test.duration_minutes} placeholder="none" /></label>
        <label>Max attempts<input type="number" min="1" bind:value={test.max_attempts} placeholder="unlimited" /></label>
      </div>
      <label class="check">
        <input type="checkbox" bind:checked={test.shuffle_questions} />
        <span>Shuffle question order for each learner</span>
      </label>
      <label class="check">
        <input type="checkbox" bind:checked={test.proctoring_enabled} />
        <span>
          AI proctoring
          <small>
            Blocks copying, pasting and the right-click menu, records tab
            switches, and gives every attempt an AI integrity verdict you can
            review with the results.
          </small>
        </span>
      </label>
    </div>

    {#if showExtend}
      <div class="form-card extend">
        <h2>Add more questions</h2>
        {#if !parsed}
          <p class="info">
            Upload another question paper. The questions already in this test stay
            exactly as they are — this only appends.
            {#if test.is_published}
              <br />This test is <b>live</b>: anyone who already took it keeps the
              score they were graded on, and new attempts will include what you add.
            {/if}
          </p>
          <label>
            Question paper (PDF or Word .docx, max 10MB)
            <input type="file" accept="application/pdf,.pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" on:change={pickExtendFile} />
          </label>
          {#if extendFile}<p class="file-info">{extendFile.name} — {(extendFile.size / 1024).toFixed(0)} KB</p>{/if}
          <label class="check">
            <input type="checkbox" bind:checked={extendUseAi} />
            <span>Use AI extraction (slower — try it if the layout is unusual)</span>
          </label>
          {#if extendError}<p class="error">{extendError}</p>{/if}
          <button class="btn primary" disabled={parsing || !extendFile} on:click={parseMore}>
            {parsing ? 'Reading document…' : 'Extract questions'}
          </button>
        {:else}
          <div class="parse-summary">
            <div><b>{parsed.detected_questions}</b> detected</div>
            <div><b>{selectedCount}</b> selected to add</div>
            <div><b>{parsed.existing_questions}</b> already in this test</div>
            <div class:bad={parsed.duplicate_count > 0}><b>{parsed.duplicate_count}</b> look like duplicates</div>
          </div>
          {#each parsed.warnings as w}<p class="warn">{w}</p>{/each}
          {#if selectedUnscorable > 0}
            <p class="warn">
              {selectedUnscorable} selected question(s) have no correct answer marked. You can
              still add them, but the test drops back to draft until they're set.
            </p>
          {/if}

          <div class="incoming">
            {#each incoming as q, qi (qi)}
              <div class="in-card" class:skipped={!include[qi]} class:dupe={q.duplicate_of_existing}>
                <label class="in-head">
                  <input type="checkbox" bind:checked={include[qi]} />
                  <span class="in-num">New Q{qi + 1}</span>
                  {#if q.duplicate_of_existing}
                    <span class="dupe-tag">already in this test</span>
                  {/if}
                </label>
                <textarea class="q-text" rows="2" bind:value={q.question} disabled={!include[qi]}></textarea>
                {#each q.options as _, oi}
                  <div class="opt" class:chosen={q.correct_index === oi}>
                    <button class="radio" class:on={q.correct_index === oi}
                            disabled={!include[qi]} on:click={() => setIncomingAnswer(qi, oi)}>
                      {q.correct_index === oi ? '✓' : String.fromCharCode(65 + oi)}
                    </button>
                    <input bind:value={q.options[oi]} disabled={!include[qi]} />
                  </div>
                {/each}
                <div class="row">
                  <label>Topic<input bind:value={q.topic} disabled={!include[qi]} placeholder="e.g. Pricing" /></label>
                  <label>Marks<input type="number" min="1" bind:value={q.marks} disabled={!include[qi]} /></label>
                </div>
              </div>
            {/each}
          </div>

          {#if extendError}<p class="error">{extendError}</p>{/if}
          <div class="btn-row">
            <button class="btn primary" disabled={busy || selectedCount === 0} on:click={appendSelected}>
              {busy ? 'Adding…' : `Add ${selectedCount} question${selectedCount === 1 ? '' : 's'}`}
            </button>
            <button class="btn" disabled={busy} on:click={cancelExtend}>Cancel</button>
          </div>
        {/if}
      </div>
    {/if}

    {#if unscorable > 0}
      <p class="warn">{unscorable} question(s) have no correct answer marked — set them to publish.</p>
    {/if}

    <div class="q-list">
      {#each questions as q, qi (qi)}
        <div class="q-card" class:incomplete={!scorable(q)}>
          <div class="q-head">
            <span class="q-num">Q{qi + 1}</span>
            <button class="link danger" on:click={() => removeQuestion(qi)}>Remove</button>
          </div>
          <textarea class="q-text" rows="2" bind:value={q.question}></textarea>
          <p class="hint">Click the circle to mark the correct answer</p>
          {#each q.options as _, oi}
            <div class="opt" class:chosen={q.correct_index === oi}>
              <button class="radio" class:on={q.correct_index === oi} on:click={() => setAnswer(qi, oi)}>
                {q.correct_index === oi ? '✓' : String.fromCharCode(65 + oi)}
              </button>
              <input bind:value={q.options[oi]} />
              <button class="link danger" on:click={() => removeOption(qi, oi)}>×</button>
            </div>
          {/each}
          <button class="link" on:click={() => addOption(qi)}>+ add option</button>
          <div class="row">
            <label>Topic<input bind:value={q.topic} placeholder="e.g. Objection Handling" /></label>
            <label>Marks<input type="number" min="1" bind:value={q.marks} /></label>
          </div>
          <label>Explanation<input bind:value={q.explanation} placeholder="Optional" /></label>
        </div>
      {/each}
    </div>

    <button class="link add-q" on:click={addQuestion}>+ add a question</button>

    <div class="save-bar">
      <button class="btn primary" disabled={busy} on:click={save}>{busy ? 'Saving…' : 'Save changes'}</button>
      <button class="btn" disabled={busy || (!test.is_published && unscorable > 0)} on:click={togglePublish}>
        {test.is_published ? 'Unpublish' : 'Publish'}
      </button>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 780px; margin: 0 auto; padding-bottom: 4rem; }
  .breadcrumb { font-size: 0.83rem; margin-bottom: 1rem; }
  .breadcrumb a { color: var(--accent); text-decoration: none; }
  .head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
  .head-actions { display: flex; align-items: center; gap: 0.6rem; }
  h1 { font-size: 1.5rem; font-weight: 800; margin-bottom: 0.3rem; }
  .sub { color: var(--muted); font-size: 0.85rem; }
  .status { font-size: 0.72rem; font-weight: 700; text-transform: uppercase; color: var(--muted);
            border: 1px solid var(--border); border-radius: 999px; padding: 0.2rem 0.6rem; }
  .status.live { color: var(--success); border-color: var(--success); }

  .form-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
               padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.25rem; }
  h2 { font-size: 1.1rem; font-weight: 700; }
  label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.82rem; color: var(--muted); flex: 1; }
  input, select, textarea { background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 0.55rem 0.75rem; font-size: 0.88rem; outline: none; font-family: inherit; width: 100%; }
  input:focus, select:focus, textarea:focus { border-color: var(--accent); }
  .row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .check { flex-direction: row; align-items: flex-start; gap: 0.55rem; }
  .check input { width: auto; margin-top: 0.15rem; }
  /* The proctoring toggle carries an explanation, so its label stacks. */
  .check span { display: flex; flex-direction: column; gap: 0.15rem; }
  .check small { font-weight: 400; font-size: 0.72rem; color: var(--muted); line-height: 1.5; max-width: 46ch; }

  .error { color: var(--accent); font-size: 0.85rem; margin-bottom: 1rem; }
  .ok { color: var(--success); font-size: 0.85rem; margin-bottom: 1rem; }
  .warn { font-size: 0.82rem; color: #ffc107; background: rgba(255,193,7,0.1);
          border: 1px solid rgba(255,193,7,0.35); border-radius: 6px; padding: 0.6rem 0.8rem; margin-bottom: 1rem; }

  .q-list { display: flex; flex-direction: column; gap: 1rem; }
  .q-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
            padding: 1.15rem; display: flex; flex-direction: column; gap: 0.7rem; }
  .q-card.incomplete { border-color: rgba(255,193,7,0.55); }
  .q-head { display: flex; justify-content: space-between; align-items: center; }
  .q-num { font-size: 0.78rem; font-weight: 700; color: var(--muted); }
  .q-text { font-size: 0.92rem; resize: vertical; }
  .hint { font-size: 0.72rem; color: var(--muted); }
  .opt { display: flex; align-items: center; gap: 0.5rem; }
  .opt.chosen input { border-color: var(--success); }
  .radio { flex-shrink: 0; width: 27px; height: 27px; border-radius: 50%; border: 1px solid var(--border);
           background: var(--surface2); color: var(--muted); font-size: 0.75rem; font-weight: 700; cursor: pointer; }
  .radio.on { background: var(--success); border-color: var(--success); color: #fff; }

  .link { background: none; border: none; color: var(--accent); font-size: 0.78rem; cursor: pointer;
          padding: 0; text-align: left; font-weight: 600; }
  .link.danger { color: var(--muted); }
  .link.danger:hover { color: #e05260; }
  .add-q { margin: 1rem 0; display: block; }

  .save-bar { display: flex; gap: 0.6rem; position: sticky; bottom: 0; background: var(--bg);
              padding: 1rem 0; border-top: 1px solid var(--border); }
  .btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text); border-radius: 6px;
         padding: 0.6rem 1.1rem; font-size: 0.88rem; font-weight: 600; cursor: pointer; text-decoration: none; }
  .btn:hover:not(:disabled) { border-color: var(--accent); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }

  /* extend-with-more-questions panel */
  .form-card.extend { border-color: var(--accent); }
  .info { font-size: 0.82rem; color: var(--muted); background: var(--surface2);
          padding: 0.65rem 0.8rem; border-radius: 6px; line-height: 1.6; }
  .file-info { font-size: 0.78rem; color: var(--muted); }
  .btn-row { display: flex; gap: 0.6rem; }
  .parse-summary { display: flex; flex-wrap: wrap; gap: 1.5rem; align-items: center;
                   background: var(--surface2); border-radius: 8px;
                   padding: 0.8rem 1.1rem; font-size: 0.78rem; color: var(--muted); }
  .parse-summary b { font-size: 1.1rem; color: var(--text); display: block; font-weight: 800; }
  .parse-summary .bad b { color: #ffc107; }
  .incoming { display: flex; flex-direction: column; gap: 0.85rem; }
  .in-card { background: var(--surface2); border: 1px solid var(--border); border-radius: 9px;
             padding: 0.95rem; display: flex; flex-direction: column; gap: 0.55rem; }
  .in-card.dupe { border-color: rgba(255,193,7,0.5); }
  .in-card.skipped { opacity: 0.45; }
  .in-head { flex-direction: row; align-items: center; gap: 0.5rem; }
  .in-head input { width: auto; }
  .in-num { font-size: 0.76rem; font-weight: 700; color: var(--muted); }
  .dupe-tag { font-size: 0.68rem; color: #ffc107; border: 1px solid rgba(255,193,7,0.45);
              border-radius: 999px; padding: 0.1rem 0.45rem; }
  .radio:disabled { opacity: 0.5; cursor: not-allowed; }

  .skeleton { border-radius: 10px; background: linear-gradient(90deg, var(--surface) 25%, var(--surface2) 50%, var(--surface) 75%);
              background-size: 200% 100%; animation: shimmer 1.4s infinite; }
  .skeleton.big { height: 320px; }
  @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
</style>
