<script lang="ts">
  import { goto } from '$app/navigation';
  import { api, type TestQuestionDraft, type ParsedPdf } from '$lib/api/client';

  const CATEGORIES = ['sales', 'leadership', 'onboarding', 'product', 'engineering', 'ops'];

  let step: 'upload' | 'review' = 'upload';
  let file: File | null = null;
  let useAi = false;
  let busy = false;
  let error = '';
  let parsed: ParsedPdf | null = null;

  // test metadata
  let title = '';
  let description = '';
  let category = '';
  let department = '';
  let passThreshold = 70;
  let durationMinutes: number | null = null;
  let maxAttempts: number | null = null;
  let questions: TestQuestionDraft[] = [];

  function pick(e: Event) {
    file = (e.target as HTMLInputElement).files?.[0] ?? null;
    error = '';
    if (file && !title) title = file.name.replace(/\.pdf$/i, '').replace(/[_-]+/g, ' ');
  }

  async function parsePdf() {
    if (!file) { error = 'Choose a PDF first'; return; }
    busy = true; error = '';
    try {
      parsed = await api.parseTestPdf(file, useAi);
      questions = parsed.questions.map((q) => ({ ...q }));
      step = 'review';
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  function scorable(q: TestQuestionDraft): boolean {
    return q.correct_index !== null && q.correct_index >= 0
      && q.correct_index < q.options.length && q.options.length >= 2;
  }
  $: unscorable = questions.filter((q) => !scorable(q)).length;
  $: totalMarks = questions.filter(scorable).reduce((s, q) => s + (q.marks || 1), 0);

  function setAnswer(qi: number, oi: number) {
    questions[qi].correct_index = oi;
    questions = questions;
  }
  function removeQuestion(qi: number) {
    questions = questions.filter((_, i) => i !== qi);
  }
  function addOption(qi: number) {
    questions[qi].options = [...questions[qi].options, ''];
    questions = questions;
  }
  function removeOption(qi: number, oi: number) {
    const q = questions[qi];
    q.options = q.options.filter((_, i) => i !== oi);
    if (q.correct_index === oi) q.correct_index = null;
    else if (q.correct_index !== null && q.correct_index > oi) q.correct_index -= 1;
    questions = questions;
  }
  function addQuestion() {
    questions = [...questions, {
      question: '', options: ['', ''], correct_index: null,
      explanation: null, topic: null, marks: 1,
    }];
  }

  async function save(publish: boolean) {
    if (!title.trim()) { error = 'Give the test a title'; return; }
    if (questions.length === 0) { error = 'Add at least one question'; return; }
    if (publish && unscorable > 0) {
      error = `${unscorable} question(s) still have no correct answer marked.`;
      return;
    }
    busy = true; error = '';
    try {
      const created = await api.createTestSeries({
        title: title.trim(),
        description: description.trim() || null,
        category: category || null,
        department: department.trim() || null,
        pass_threshold: passThreshold,
        duration_minutes: durationMinutes || null,
        max_attempts: maxAttempts || null,
        questions,
      }, { filename: parsed?.source_filename ?? undefined, parser: parsed?.source_parser });

      if (publish) await api.publishTestSeries(created.id, true);
      goto(`/admin/tests/${created.id}`);
    } catch (e: any) { error = e.message; busy = false; }
  }
</script>

<div class="page">
  <p class="breadcrumb"><a href="/admin/tests">← Test Series</a></p>
  <h1>New test series from PDF</h1>
  <p class="sub">Upload a PDF of questions and answers. We extract them, you confirm, learners take it.</p>

  <div class="steps">
    <span class="step" class:active={step === 'upload'} class:done={step === 'review'}>1. Upload PDF</span>
    <span class="divider">›</span>
    <span class="step" class:active={step === 'review'}>2. Review &amp; publish</span>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if step === 'upload'}
    <div class="form-card">
      <h2>Choose your question paper</h2>
      <p class="info">
        Works best with numbered questions and lettered options, e.g.
        <code>1. What is …</code> then <code>A) …  B) …</code>, with either
        <code>Answer: B</code> under each question or an <code>Answer Key</code>
        section at the end. Topic, Marks and Explanation lines are picked up too.
      </p>

      <label>
        Question paper (PDF, max 10MB)
        <input type="file" accept="application/pdf,.pdf" on:change={pick} />
      </label>
      {#if file}<p class="file-info">{file.name} — {(file.size / 1024).toFixed(0)} KB</p>{/if}

      <label class="check">
        <input type="checkbox" bind:checked={useAi} />
        <span>Use AI extraction (slower, costs tokens — try this if the layout is unusual)</span>
      </label>

      <button class="btn primary" disabled={busy || !file} on:click={parsePdf}>
        {busy ? 'Reading PDF…' : 'Extract questions'}
      </button>
    </div>
  {:else if parsed}
    <div class="form-card">
      <h2>Test details</h2>
      <label>Title<input bind:value={title} placeholder="Sales Certification Level 1" /></label>
      <label>Description<input bind:value={description} placeholder="Optional" /></label>
      <div class="row">
        <label>Category
          <select bind:value={category}>
            <option value="">—</option>
            {#each CATEGORIES as c}<option value={c}>{c}</option>{/each}
          </select>
        </label>
        <label>Department (blank = everyone)<input bind:value={department} placeholder="sales" /></label>
      </div>
      <div class="row">
        <label>Pass mark %<input type="number" min="1" max="100" bind:value={passThreshold} /></label>
        <label>Time limit (min)<input type="number" min="1" bind:value={durationMinutes} placeholder="none" /></label>
        <label>Max attempts<input type="number" min="1" bind:value={maxAttempts} placeholder="unlimited" /></label>
      </div>
    </div>

    <div class="parse-summary">
      <div><b>{parsed.detected_questions}</b> detected</div>
      <div><b>{questions.length}</b> kept</div>
      <div><b>{totalMarks}</b> total marks</div>
      <div class:bad={unscorable > 0}><b>{unscorable}</b> missing answer</div>
      <div class="parser-tag">parsed by {parsed.source_parser}</div>
    </div>

    {#each parsed.warnings as w}<p class="warn">{w}</p>{/each}
    {#if unscorable > 0}
      <p class="warn">
        Pick the correct option for every highlighted question below. You can save as
        a draft now and finish later, but publishing needs all answers set.
      </p>
    {/if}

    <div class="q-list">
      {#each questions as q, qi (qi)}
        <div class="q-card" class:incomplete={!scorable(q)}>
          <div class="q-head">
            <span class="q-num">Q{qi + 1}</span>
            <button class="link danger" on:click={() => removeQuestion(qi)}>Remove</button>
          </div>
          <textarea class="q-text" rows="2" bind:value={q.question} placeholder="Question text"></textarea>

          <p class="hint">Click the circle to mark the correct answer</p>
          {#each q.options as opt, oi}
            <div class="opt" class:chosen={q.correct_index === oi}>
              <button class="radio" class:on={q.correct_index === oi}
                      title="Mark as correct" on:click={() => setAnswer(qi, oi)}>
                {q.correct_index === oi ? '✓' : String.fromCharCode(65 + oi)}
              </button>
              <input bind:value={q.options[oi]} placeholder={`Option ${String.fromCharCode(65 + oi)}`} />
              <button class="link danger" on:click={() => removeOption(qi, oi)}>×</button>
            </div>
          {/each}
          <button class="link" on:click={() => addOption(qi)}>+ add option</button>

          <div class="row">
            <label>Topic (groups weak areas)<input bind:value={q.topic} placeholder="e.g. Objection Handling" /></label>
            <label>Marks<input type="number" min="1" bind:value={q.marks} /></label>
          </div>
          <label>Explanation (shown after submission)
            <input bind:value={q.explanation} placeholder="Optional" />
          </label>
        </div>
      {/each}
    </div>

    <button class="link add-q" on:click={addQuestion}>+ add a question manually</button>

    <div class="save-bar">
      <button class="btn" disabled={busy} on:click={() => save(false)}>Save as draft</button>
      <button class="btn primary" disabled={busy || unscorable > 0} on:click={() => save(true)}>
        {busy ? 'Saving…' : 'Save & publish'}
      </button>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 780px; margin: 0 auto; padding-bottom: 4rem; }
  .breadcrumb { font-size: 0.83rem; margin-bottom: 1rem; }
  .breadcrumb a { color: var(--accent); text-decoration: none; }
  h1 { font-size: 1.6rem; font-weight: 800; margin-bottom: 0.35rem; }
  .sub { color: var(--muted); font-size: 0.9rem; margin-bottom: 1.75rem; }
  .steps { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1.5rem; }
  .step { padding: 0.3rem 0.8rem; border-radius: 4px; font-size: 0.83rem; font-weight: 600;
          color: var(--muted); border: 1px solid var(--border); }
  .step.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .step.done { color: var(--success); border-color: var(--success); }
  .divider { color: var(--muted); }

  .form-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
               padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.25rem; }
  h2 { font-size: 1.1rem; font-weight: 700; }
  label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.82rem; color: var(--muted); flex: 1; }
  input, select, textarea {
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 0.55rem 0.75rem; font-size: 0.88rem; outline: none;
    font-family: inherit; width: 100%;
  }
  input:focus, select:focus, textarea:focus { border-color: var(--accent); }
  .row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .check { flex-direction: row; align-items: center; gap: 0.55rem; font-size: 0.83rem; }
  .check input { width: auto; }
  .info { font-size: 0.82rem; color: var(--muted); background: var(--surface2);
          padding: 0.7rem 0.85rem; border-radius: 6px; line-height: 1.55; }
  .info code { background: var(--surface); padding: 0.05rem 0.3rem; border-radius: 3px; font-size: 0.78rem; }
  .file-info { font-size: 0.8rem; color: var(--muted); }
  .error { color: var(--accent); font-size: 0.85rem; margin-bottom: 1rem; }
  .warn { font-size: 0.82rem; color: #ffc107; background: rgba(255,193,7,0.1);
          border: 1px solid rgba(255,193,7,0.35); border-radius: 6px;
          padding: 0.6rem 0.8rem; margin-bottom: 0.75rem; }

  .parse-summary { display: flex; flex-wrap: wrap; gap: 1.5rem; align-items: center;
                   background: var(--surface); border: 1px solid var(--border);
                   border-radius: 10px; padding: 0.9rem 1.25rem; margin-bottom: 1rem; font-size: 0.8rem; color: var(--muted); }
  .parse-summary b { font-size: 1.15rem; color: var(--text); display: block; font-weight: 800; }
  .parse-summary .bad b { color: #ffc107; }
  .parser-tag { margin-left: auto; font-size: 0.72rem; background: var(--surface2);
                border-radius: 999px; padding: 0.2rem 0.6rem; }

  .q-list { display: flex; flex-direction: column; gap: 1rem; }
  .q-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
            padding: 1.15rem; display: flex; flex-direction: column; gap: 0.7rem; }
  .q-card.incomplete { border-color: rgba(255,193,7,0.55); }
  .q-head { display: flex; justify-content: space-between; align-items: center; }
  .q-num { font-size: 0.78rem; font-weight: 700; color: var(--muted); letter-spacing: 0.05em; }
  .q-text { font-size: 0.92rem; resize: vertical; }
  .hint { font-size: 0.72rem; color: var(--muted); }

  .opt { display: flex; align-items: center; gap: 0.5rem; }
  .opt.chosen input { border-color: var(--success); }
  .radio { flex-shrink: 0; width: 27px; height: 27px; border-radius: 50%;
           border: 1px solid var(--border); background: var(--surface2); color: var(--muted);
           font-size: 0.75rem; font-weight: 700; cursor: pointer; }
  .radio.on { background: var(--success); border-color: var(--success); color: #fff; }

  .link { background: none; border: none; color: var(--accent); font-size: 0.78rem;
          cursor: pointer; padding: 0; text-align: left; font-weight: 600; }
  .link.danger { color: var(--muted); }
  .link.danger:hover { color: #e05260; }
  .add-q { margin: 1rem 0; display: block; }

  .save-bar { display: flex; gap: 0.6rem; position: sticky; bottom: 0;
              background: var(--bg); padding: 1rem 0; border-top: 1px solid var(--border); }
  .btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text);
         border-radius: 6px; padding: 0.6rem 1.1rem; font-size: 0.88rem; font-weight: 600; cursor: pointer; }
  .btn:hover:not(:disabled) { border-color: var(--accent); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn.primary { background: var(--accent); color: #fff; border-color: var(--accent); }
</style>
