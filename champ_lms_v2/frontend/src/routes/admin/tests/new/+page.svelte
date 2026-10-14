<script lang="ts">
  import { goto } from '$app/navigation';
  import { api, isScorable, type TestQuestionDraft, type ParsedPdf } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Select from '$lib/components/Select.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import { countUp } from '$lib/actions/motion';

  const CATEGORIES = ['sales', 'leadership', 'onboarding', 'product', 'engineering', 'ops'];
  const CATEGORY_OPTIONS = [
    { value: '', label: 'No category' },
    ...CATEGORIES.map(c => ({ value: c, label: c[0].toUpperCase() + c.slice(1) })),
  ];

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
  // On by default — a company exam should be proctored unless the admin says
  // otherwise, which matches the server-side default.
  let proctoringEnabled = true;
  let questions: TestQuestionDraft[] = [];

  function pick(e: Event) {
    file = (e.target as HTMLInputElement).files?.[0] ?? null;
    error = '';
    if (file && !title) title = file.name.replace(/\.(pdf|docx)$/i, '').replace(/[_-]+/g, ' ');
  }

  async function parsePdf() {
    if (!file) { error = 'Choose a PDF or Word file first'; return; }
    busy = true; error = '';
    try {
      parsed = await api.parseTestPdf(file, useAi);
      questions = parsed.questions.map((q) => ({ ...q }));
      step = 'review';
    } catch (e: any) { error = e.message; }
    finally { busy = false; }
  }

  // Same rule as the backend: written questions are AI-graded, so always count.
  const scorable = (q: TestQuestionDraft) => isScorable(q);
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
        proctoring_enabled: proctoringEnabled,
        questions,
      }, { filename: parsed?.source_filename ?? undefined, parser: parsed?.source_parser });

      if (publish) await api.publishTestSeries(created.id, true);
      goto(`/admin/tests/${created.id}`);
    } catch (e: any) { error = e.message; busy = false; }
  }
</script>

<svelte:head><title>New test series — Champ LMS</title></svelte:head>

<div class="page">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Test Series', href: '/admin/tests' }, { label: 'New test' }]} />
  <h1 class="ui-rise" style="--i:1">
    New test series from a document
    <span class="title-mark" aria-hidden="true"><Icon name="file" size={23} /></span>
  </h1>
  <p class="sub ui-rise" style="--i:2">Upload a PDF or Word document of questions and answers. We extract them, you confirm, learners take it.</p>

  <div class="steps ui-rise" style="--i:3">
    <span class="step" class:active={step === 'upload'} class:done={step === 'review'}>
      <span class="s-num">{#if step === 'review'}<Icon name="check" size={13} stroke={2.4} />{:else}1{/if}</span> Upload
    </span>
    <span class="divider" class:filled={step === 'review'} aria-hidden="true"><span></span></span>
    <span class="step" class:active={step === 'review'}><span class="s-num">2</span> Review &amp; publish</span>
  </div>

  {#if error}{#key error}<p class="error"><Icon name="alert" size={16} /> {error}</p>{/key}{/if}

  {#if step === 'upload'}
    <div class="form-card ui-rise" style="--i:4">
      <h2>Choose your question paper</h2>
      <p class="info">
        <Icon name="info" size={16} />
        <span>
          Works best with numbered questions and lettered options, e.g.
          <code>1. What is …</code> then <code>A) …  B) …</code>, with either
          <code>Answer: B</code> under each question or an <code>Answer Key</code>
          section at the end. Topic, Marks and Explanation lines are picked up too.
          In Word files, questions laid out in a table work as well as plain
          paragraphs. Scanned or image-only files have no text to read — export a
          text-based file, or tick AI extraction for unusual layouts.
        </span>
      </p>

      <label class="drop" class:has={!!file}>
        <span class="d-ico"><Icon name={file ? 'file' : 'upload'} size={24} /></span>
        <span class="d-txt">
          <b>{file ? file.name : 'Question paper (PDF or Word .docx, max 10MB)'}</b>
          <small>{file ? `${(file.size / 1024).toFixed(0)} KB · click to choose another` : 'Click to browse your files'}</small>
        </span>
        <input type="file" accept="application/pdf,.pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" on:change={pick} />
      </label>

      <label class="check">
        <input type="checkbox" bind:checked={useAi} />
        <span>Use AI extraction (slower, costs tokens — try this if the layout is unusual)</span>
      </label>

      <button class="btn-primary go" disabled={busy || !file} on:click={parsePdf}>
        {#if busy}<span class="spin" aria-hidden="true"></span> Reading document…{:else}<Icon name="sparkles" size={16} /> Extract questions{/if}
      </button>
    </div>
  {:else if parsed}
    <div class="form-card ui-rise">
      <h2>Test details</h2>
      <label><span class="lbl">Title</span><input bind:value={title} placeholder="Sales Certification Level 1" /></label>
      <label><span class="lbl">Description</span><input bind:value={description} placeholder="Optional" /></label>
      <div class="row">
        <!-- svelte-ignore a11y-label-has-associated-control -->
        <label><span class="lbl">Category</span>
          <Select bind:value={category} size="lg" placeholder="No category" options={CATEGORY_OPTIONS} />
        </label>
        <label><span class="lbl">Department (blank = everyone)</span><input bind:value={department} placeholder="sales" /></label>
      </div>
      <div class="row">
        <label><span class="lbl">Pass mark %</span><input type="number" min="1" max="100" bind:value={passThreshold} /></label>
        <label><span class="lbl">Time limit (min)</span><input type="number" min="1" bind:value={durationMinutes} placeholder="none" /></label>
        <label><span class="lbl">Max attempts</span><input type="number" min="1" bind:value={maxAttempts} placeholder="unlimited" /></label>
      </div>
      <label class="check proctor" class:on={proctoringEnabled}>
        <input type="checkbox" bind:checked={proctoringEnabled} />
        <span>
          <b><Icon name="shield" size={15} /> AI proctoring</b>
          <small>
            Blocks copying, pasting and the right-click menu, records tab
            switches, and gives every attempt an AI integrity verdict in the
            results.
          </small>
        </span>
      </label>
    </div>

    <div class="parse-summary ui-rise" style="--i:1">
      <div class="sum sky"><b use:countUp={parsed.detected_questions}></b> detected</div>
      <div class="sum lilac"><b use:countUp={questions.length}></b> kept</div>
      <div class="sum mint"><b use:countUp={totalMarks}></b> total marks</div>
      <div class="sum" class:bad={unscorable > 0} class:butter={unscorable > 0}><b use:countUp={unscorable}></b> missing answer</div>
      <div class="parser-tag"><Icon name="sparkles" size={13} /> parsed by {parsed.source_parser}</div>
    </div>

    {#each parsed.warnings as w}<p class="warn"><Icon name="alert" size={15} /> {w}</p>{/each}
    {#if unscorable > 0}
      <p class="warn">
        <Icon name="alert" size={15} />
        Pick the correct option for every highlighted question below. You can save as
        a draft now and finish later, but publishing needs all answers set.
      </p>
    {/if}

    <div class="q-list">
      {#each questions as q, qi (qi)}
        <div class="q-card ui-rise" style="--i:{Math.min(qi, 8)}" class:incomplete={!scorable(q)}>
          <div class="q-head">
            <span class="q-num">Q{qi + 1}</span>
            {#if !scorable(q)}<span class="need"><Icon name="alert" size={13} /> Needs an answer</span>{/if}
            <button class="link danger rm" on:click={() => removeQuestion(qi)}><Icon name="trash" size={14} /> Remove</button>
          </div>
          <textarea class="q-text" rows="2" bind:value={q.question} placeholder="Question text"></textarea>

          {#if q.question_type === 'written'}
            <!-- Written: typed answer graded by AI; no options to mark. -->
            <p class="hint">Written answer{#if q.max_words} · up to {q.max_words} words{/if} — graded by AI</p>
            <label><span class="lbl">Reference answer (guides the AI grading)</span>
              <textarea rows="2" bind:value={q.expected_answer} placeholder="Optional"></textarea>
            </label>
          {:else}
            <p class="hint">Click the circle to mark the correct answer</p>
            {#each q.options as opt, oi}
              <div class="opt" class:chosen={q.correct_index === oi}>
                <button class="radio" class:on={q.correct_index === oi}
                        title="Mark as correct" on:click={() => setAnswer(qi, oi)}>
                  {#if q.correct_index === oi}<Icon name="check" size={14} stroke={2.6} />{:else}{String.fromCharCode(65 + oi)}{/if}
                </button>
                <input bind:value={q.options[oi]} placeholder={`Option ${String.fromCharCode(65 + oi)}`} />
                <button class="x" aria-label="Remove option" on:click={() => removeOption(qi, oi)}><Icon name="close" size={14} /></button>
              </div>
            {/each}
            <button class="link add-opt" on:click={() => addOption(qi)}><Icon name="plus" size={14} /> add option</button>
          {/if}

          <div class="row">
            <label><span class="lbl">Topic (groups weak areas)</span><input bind:value={q.topic} placeholder="e.g. Objection Handling" /></label>
            <label class="marks"><span class="lbl">Marks</span><input type="number" min="1" bind:value={q.marks} /></label>
          </div>
          <label><span class="lbl">Explanation (shown after submission)</span>
            <input bind:value={q.explanation} placeholder="Optional" />
          </label>
        </div>
      {/each}
    </div>

    <button class="add-q" on:click={addQuestion}><span class="plus"><Icon name="plus" size={18} stroke={2.2} /></span> add a question manually</button>

    <div class="save-bar">
      <button class="btn-ghost" disabled={busy} on:click={() => save(false)}><Icon name="save" size={16} /> Save as draft</button>
      <button class="btn-primary" disabled={busy || unscorable > 0} on:click={() => save(true)}>
        {#if busy}<span class="spin" aria-hidden="true"></span> Saving…{:else}<Icon name="send" size={16} /> Save &amp; publish{/if}
      </button>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 820px; margin: 0 auto; }
  h1 {
    font-size: clamp(1.7rem, 1.1rem + 1.8vw, 2.5rem); font-weight: 700; letter-spacing: -0.035em; line-height: 1.08;
    display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; margin-bottom: 0.55rem;
  }
  .title-mark {
    display: inline-grid; place-items: center; width: 44px; height: 44px; border-radius: 50%;
    background: var(--tile-peach); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  .sub { color: var(--muted); font-size: 0.95rem; margin-bottom: 1.5rem; }

  .steps { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 1.5rem; }
  .step {
    display: inline-flex; align-items: center; gap: 0.5rem; height: 40px; padding: 0 1rem 0 0.4rem;
    border-radius: 999px; font-size: 0.86rem; font-weight: 600; color: var(--muted); background: var(--surface2);
    transition: background-color var(--dur-3) var(--ease-out), color var(--dur-3);
  }
  .s-num {
    width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center;
    background: var(--surface); font-size: 0.8rem; font-weight: 700;
  }
  .step.active { background: var(--accent); color: var(--on-accent); }
  .step.active .s-num { background: var(--on-accent); color: var(--accent); animation: pop 420ms var(--ease-out); }
  .step.done { background: var(--tile-mint); color: var(--tile-ink); }
  .step.done .s-num { background: var(--tile-inner); }
  .divider { width: 48px; height: 3px; border-radius: 99px; background: var(--surface3); overflow: hidden; }
  .divider span { display: block; height: 100%; width: 0; background: var(--success); transition: width 600ms var(--ease-out); }
  .divider.filled span { width: 100%; }

  .form-card {
    background: var(--surface); border-radius: 30px; box-shadow: var(--shadow-sm);
    padding: 1.6rem; display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.25rem;
  }
  h2 { font-size: 1.2rem; font-weight: 700; letter-spacing: -0.02em; }
  label { display: flex; flex-direction: column; gap: 0.4rem; flex: 1; }
  .lbl { font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }
  input, textarea {
    background: var(--surface2); border: 1px solid transparent; color: var(--text);
    border-radius: 14px; padding: 0.65rem 0.9rem; font-size: 0.9rem;
    font-family: inherit; width: 100%;
  }
  input { height: 46px; }
  input:hover, textarea:hover { background: var(--surface3); }
  .row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .row label { min-width: 160px; }
  .row .marks { flex: 0 0 110px; min-width: 110px; }
  .check { flex-direction: row; align-items: flex-start; gap: 0.6rem; font-size: 0.86rem; color: var(--text-secondary); cursor: pointer; }
  .check input { width: 18px; height: 18px; padding: 0; margin-top: 0.1rem; flex: none; }
  /* The proctoring toggle carries an explanation, so its label stacks. */
  .check span { display: flex; flex-direction: column; gap: 0.2rem; }
  .check b { display: inline-flex; align-items: center; gap: 0.35rem; color: var(--text); }
  .check small { font-weight: 400; font-size: 0.76rem; color: var(--muted); line-height: 1.5; max-width: 52ch; }
  .proctor { padding: 0.9rem 1rem; border-radius: 18px; background: var(--surface2); transition: background-color var(--dur-3) var(--ease-out); }
  .proctor.on { background: var(--tile-lilac); }
  .proctor.on b, .proctor.on small { color: var(--tile-ink); }
  .info {
    display: flex; gap: 0.6rem; align-items: flex-start;
    font-size: 0.84rem; color: var(--text-secondary); background: var(--bg-alt);
    padding: 0.85rem 1rem; border-radius: 18px; line-height: 1.6;
  }
  .info > :global(.icon) { flex: none; margin-top: 0.2rem; }
  .info code { background: var(--surface); padding: 0.05rem 0.35rem; border-radius: 6px; font-size: 0.78rem; }

  .drop {
    position: relative; flex-direction: row; align-items: center; gap: 1rem; cursor: pointer;
    padding: 1.2rem 1.2rem; border-radius: 22px; border: 2px dashed var(--border-hover); background: var(--surface2);
    transition: background-color var(--dur-2) var(--ease-out), border-color var(--dur-2), translate var(--dur-3) var(--ease-out);
  }
  .drop:hover { background: var(--surface3); translate: 0 -2px; }
  .drop:focus-within { border-color: var(--accent); }
  .drop.has { border-style: solid; border-color: transparent; background: var(--tile-sky); }
  .drop.has .d-txt b, .drop.has .d-txt small { color: var(--tile-ink); }
  .drop input { position: absolute; inset: 0; opacity: 0; cursor: pointer; height: auto; }
  .d-ico {
    width: 52px; height: 52px; border-radius: 50%; display: grid; place-items: center; flex: none;
    background: var(--surface); color: var(--text); transition: translate var(--dur-3) var(--ease-out);
  }
  .drop:hover .d-ico { translate: 0 -3px; }
  .drop.has .d-ico { animation: pop 420ms var(--ease-out); }
  .d-txt { display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; }
  .d-txt b { font-size: 0.92rem; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .d-txt small { font-size: 0.78rem; color: var(--muted); }
  .go { align-self: flex-start; }

  .error {
    display: flex; align-items: center; gap: 0.5rem; padding: 0.75rem 1rem; border-radius: 18px; margin-bottom: 1rem;
    background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); font-weight: 600; font-size: 0.88rem;
    animation: shake 420ms var(--ease-out);
  }
  @keyframes shake { 20%, 60% { translate: -5px 0; } 40%, 80% { translate: 5px 0; } }
  .warn {
    display: flex; align-items: flex-start; gap: 0.5rem;
    font-size: 0.84rem; color: var(--tile-ink); background: var(--tile-butter);
    border-radius: 16px; padding: 0.7rem 0.9rem; margin-bottom: 0.75rem; line-height: 1.5;
  }
  .warn :global(.icon) { flex: none; margin-top: 0.15rem; }

  .parse-summary {
    display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center;
    background: var(--surface); border-radius: 24px; box-shadow: var(--shadow-sm);
    padding: 0.6rem; margin-bottom: 1rem; font-size: 0.8rem;
  }
  .sum { padding: 0.55rem 0.9rem; border-radius: 18px; background: var(--surface2); color: var(--text-secondary); }
  .sum b { font-size: 1.3rem; display: block; font-weight: 700; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; color: inherit; }
  .sum.sky, .sum.lilac, .sum.mint, .sum.butter { color: var(--tile-ink); }
  .sky { background: var(--tile-sky); }
  .lilac { background: var(--tile-lilac); }
  .mint { background: var(--tile-mint); }
  .butter { background: var(--tile-butter); }
  .sum:hover b { animation: pop 420ms var(--ease-out); }
  .parser-tag {
    display: inline-flex; align-items: center; gap: 0.3rem;
    margin-left: auto; margin-right: 0.4rem; font-size: 0.74rem; color: var(--muted); background: var(--surface2);
    border-radius: 999px; padding: 0.3rem 0.7rem;
  }

  .q-list { display: flex; flex-direction: column; gap: 1rem; }
  .q-card {
    background: var(--surface); border-radius: 26px; box-shadow: var(--shadow-sm);
    padding: 1.25rem; display: flex; flex-direction: column; gap: 0.7rem;
    transition: box-shadow var(--dur-3) var(--ease-out), background-color var(--dur-3);
  }
  .q-card:hover, .q-card:focus-within { box-shadow: var(--shadow); }
  .q-card.incomplete { background: color-mix(in srgb, var(--tile-butter) 45%, var(--surface)); }
  .q-head { display: flex; align-items: center; gap: 0.5rem; }
  .q-num {
    height: 28px; padding: 0 0.7rem; border-radius: 99px; display: inline-grid; place-items: center;
    background: var(--accent); color: var(--on-accent); font-size: 0.76rem; font-weight: 700; letter-spacing: 0.03em;
  }
  .need {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 26px; padding: 0 0.6rem; border-radius: 99px;
    background: var(--tile-butter); color: var(--tile-ink); font-size: 0.74rem; font-weight: 600;
  }
  .rm { margin-left: auto; }
  .q-text { font-size: 0.95rem; resize: vertical; }
  .hint { font-size: 0.74rem; color: var(--muted); }

  .opt { display: flex; align-items: center; gap: 0.5rem; }
  .opt.chosen input { background: color-mix(in srgb, var(--success) 12%, var(--surface2)); }
  .radio {
    flex-shrink: 0; width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
    background: var(--surface2); color: var(--muted);
    font-size: 0.8rem; font-weight: 700; cursor: pointer;
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2), scale var(--dur-2) var(--ease-out);
  }
  .radio:hover { background: var(--surface3); color: var(--text); scale: 1.08; }
  .radio.on { background: var(--success); color: var(--on-accent); animation: pop 380ms var(--ease-out); }
  .x {
    flex: none; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; color: var(--muted);
    transition: background-color var(--dur-2), color var(--dur-2), rotate var(--dur-3) var(--ease-out);
  }
  .x:hover { background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger); rotate: 90deg; }

  .link {
    display: inline-flex; align-items: center; gap: 0.3rem;
    background: none; border: none; color: var(--text); font-size: 0.8rem;
    cursor: pointer; padding: 0.3rem 0.5rem; border-radius: 99px; text-align: left; font-weight: 600;
  }
  .link:hover { background: var(--surface2); }
  .link.danger { color: var(--muted); }
  .link.danger:hover { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); }
  .add-opt { align-self: flex-start; }
  .add-q {
    display: flex; align-items: center; justify-content: center; gap: 0.5rem; width: 100%;
    margin: 1rem 0; padding: 1rem; border-radius: 22px; border: 2px dashed var(--border-hover);
    color: var(--text-secondary); font-weight: 600; font-size: 0.9rem;
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2), border-color var(--dur-2);
  }
  .add-q:hover { background: var(--surface); color: var(--text); border-color: var(--accent); }
  .plus { display: grid; transition: rotate var(--dur-3) var(--ease-out); }
  .add-q:hover .plus { rotate: 90deg; }

  .save-bar {
    display: flex; gap: 0.6rem; justify-content: flex-end; position: sticky; bottom: 1rem; z-index: 5;
    background: var(--surface); padding: 0.6rem; border-radius: 999px; box-shadow: var(--shadow-lg);
    animation: rise 420ms var(--ease-out);
  }
  .spin {
    width: 16px; height: 16px; border-radius: 50%; flex: none;
    border: 2px solid color-mix(in srgb, currentColor 25%, transparent); border-top-color: currentColor;
    animation: spin 800ms linear infinite;
  }
  @keyframes spin { to { rotate: 360deg; } }

  @media (max-width: 640px) {
    .form-card { padding: 1.15rem; border-radius: 24px; }
    .parser-tag { margin-left: 0; }
    .save-bar { border-radius: 24px; flex-wrap: wrap; }
    .save-bar > * { flex: 1; }
  }
</style>
