<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { api, isScorable, type AdminTest, type TestQuestionDraft, type ParsedPdfForTest } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import Select from '$lib/components/Select.svelte';
  import { countUp } from '$lib/actions/motion';

  const CATEGORIES = ['sales', 'leadership', 'onboarding', 'product', 'engineering', 'ops'];
  const CATEGORY_OPTIONS = [
    { value: null, label: 'No category' },
    ...CATEGORIES.map(c => ({ value: c, label: c[0].toUpperCase() + c.slice(1) })),
  ];
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

  // Same rule as the backend: written questions are AI-graded, so always count.
  const scorable = (q: TestQuestionDraft) => isScorable(q);
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

<svelte:head><title>{test?.title ?? 'Test'} — Champ LMS</title></svelte:head>

<div class="page">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Test Series', href: '/admin/tests' }, { label: test?.title || 'Test' }]} />

  {#if loading}
    <div class="ui-skeleton" style="height:110px;border-radius:24px;margin-bottom:1.25rem"></div>
    <div class="ui-skeleton" style="height:360px;border-radius:28px;margin-bottom:1.25rem"></div>
    {#each Array(2) as _}<div class="ui-skeleton" style="height:220px;border-radius:24px;margin-bottom:1rem"></div>{/each}
  {:else if !test}
    <div class="state ui-rise">
      <span class="state-ico danger"><Icon name="alert" size={26} /></span>
      <h2>Test not available</h2>
      <p>{error || 'Test not found'}</p>
      <a class="btn-ghost" href="/admin/tests">Back to Test Series</a>
    </div>
  {:else}
    <header class="head">
      <div class="head-copy">
        <p class="eyebrow ui-rise" style="--i:1">Test editor</p>
        <h1 class="ui-rise" style="--i:2">
          <span class="title-text">{test.title}</span>
          <span class="title-mark" aria-hidden="true"><Icon name="clipboard" size={22} /></span>
        </h1>
        <div class="meta ui-rise" style="--i:3">
          <span class="ui-pill sky"><Icon name="hash" size={14} /> <b use:countUp={test.total_questions}></b> questions</span>
          <span class="ui-pill butter"><Icon name="star" size={14} /> <b use:countUp={test.total_marks}></b> marks</span>
          {#if test.source_filename}
            <span class="ui-pill src" title="{test.source_filename} ({test.source_parser})"><Icon name="file" size={14} /> {test.source_filename}</span>
          {/if}
        </div>
      </div>
      <div class="head-actions ui-rise" style="--i:3">
        <span class="status" class:live={test.is_published}><span class="s-dot"></span>{test.is_published ? 'Published' : 'Draft'}</span>
        <a href="/admin/tests/{id}/results" class="btn-ghost"><Icon name="chart" size={16} /> Results</a>
        <button class="btn-primary add-toggle" class:open={showExtend} on:click={() => (showExtend ? cancelExtend() : (showExtend = true))}>
          <span class="plus"><Icon name="plus" size={16} /></span>
          {showExtend ? 'Cancel' : 'Add questions from a document'}
        </button>
      </div>
    </header>

    {#if error}<p class="note bad" role="alert"><Icon name="alert" size={16} /> {error}</p>{/if}
    {#if saved}<p class="note good" role="status"><Icon name="checkCircle" size={16} /> {saved}</p>{/if}

    <section class="card ui-rise" style="--i:4">
      <div class="card-head">
        <span class="c-ico lilac"><Icon name="sliders" size={18} /></span>
        <h2>Settings</h2>
      </div>
      <label>Title<input bind:value={test.title} /></label>
      <label>Description<input bind:value={test.description} placeholder="Optional" /></label>
      <div class="row">
        <!-- svelte-ignore a11y-label-has-associated-control -->
        <label>Category
          <Select bind:value={test.category} size="lg" placeholder="No category" options={CATEGORY_OPTIONS} />
        </label>
        <label>Department<input bind:value={test.department} placeholder="blank = everyone" /></label>
      </div>

      <div class="audience">
        <span class="aud-ico"><Icon name="users" size={17} /></span>
        <span class="aud-txt">
          <span class="aud-lbl">Audience</span>
          <span class="aud-val">
            {#if test.is_restricted}
              {[
                test.audience_teams?.length ? `Teams: ${test.audience_teams.join(', ')}` : '',
                test.audience_departments?.length ? `Depts: ${test.audience_departments.join(', ')}` : '',
                test.target_roles?.length ? `Roles: ${test.target_roles.join(', ')}` : '',
                test.required_for_teams?.length ? `Required for: ${test.required_for_teams.join(', ')}` : '',
              ].filter(Boolean).join(' · ') || `Department: ${test.department}`}
            {:else}
              Everyone
            {/if}
          </span>
        </span>
        <a class="aud-link" href="/admin/content-access">Change in Content access <Icon name="arrowRight" size={14} /></a>
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
          <span class="check-title"><Icon name="shield" size={15} /> AI proctoring</span>
          <small>
            Blocks copying, pasting and the right-click menu, records tab
            switches, and gives every attempt an AI integrity verdict you can
            review with the results.
          </small>
        </span>
      </label>
    </section>

    {#if showExtend}
      <section class="card extend">
        <div class="card-head">
          <span class="c-ico mint"><Icon name="upload" size={18} /></span>
          <h2>Add more questions</h2>
        </div>
        {#if !parsed}
          <p class="info">
            <Icon name="info" size={16} />
            <span>
              Upload another question paper. The questions already in this test stay
              exactly as they are — this only appends.
              {#if test.is_published}
                <br />This test is <b>live</b>: anyone who already took it keeps the
                score they were graded on, and new attempts will include what you add.
              {/if}
            </span>
          </p>
          <label>
            Question paper (PDF or Word .docx, max 10MB)
            <input type="file" accept="application/pdf,.pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" on:change={pickExtendFile} />
          </label>
          {#if extendFile}<p class="file-info"><Icon name="file" size={14} /> {extendFile.name} — {(extendFile.size / 1024).toFixed(0)} KB</p>{/if}
          <label class="check">
            <input type="checkbox" bind:checked={extendUseAi} />
            <span><span class="check-title"><Icon name="sparkles" size={15} /> Use AI extraction</span><small>Slower — try it if the layout is unusual.</small></span>
          </label>
          {#if extendError}<p class="note bad"><Icon name="alert" size={16} /> {extendError}</p>{/if}
          <div class="btn-row">
            <button class="btn-primary" disabled={parsing || !extendFile} on:click={parseMore}>
              {#if parsing}<span class="spin"></span> Reading document…{:else}<Icon name="sparkles" size={16} /> Extract questions{/if}
            </button>
          </div>
        {:else}
          <div class="parse-summary">
            <div class="ps sky"><b use:countUp={parsed.detected_questions}></b><span>detected</span></div>
            <div class="ps mint"><b use:countUp={selectedCount}></b><span>selected to add</span></div>
            <div class="ps lilac"><b use:countUp={parsed.existing_questions}></b><span>already in this test</span></div>
            <div class="ps" class:butter={parsed.duplicate_count > 0} class:plain={parsed.duplicate_count === 0}><b use:countUp={parsed.duplicate_count}></b><span>look like duplicates</span></div>
          </div>
          {#each parsed.warnings as w}<p class="warn"><Icon name="alert" size={16} /> {w}</p>{/each}
          {#if selectedUnscorable > 0}
            <p class="warn">
              <Icon name="alert" size={16} />
              <span>{selectedUnscorable} selected question(s) have no correct answer marked. You can
              still add them, but the test drops back to draft until they're set.</span>
            </p>
          {/if}

          <div class="incoming">
            {#each incoming as q, qi (qi)}
              <div class="in-card ui-rise" style="--i:{Math.min(qi, 10)}" class:skipped={!include[qi]} class:dupe={q.duplicate_of_existing}>
                <label class="in-head">
                  <input type="checkbox" bind:checked={include[qi]} />
                  <span class="in-num">New Q{qi + 1}</span>
                  {#if q.duplicate_of_existing}
                    <span class="dupe-tag"><Icon name="copy" size={12} /> already in this test</span>
                  {/if}
                </label>
                <textarea class="q-text" rows="2" bind:value={q.question} disabled={!include[qi]}></textarea>
                {#if q.question_type === 'written'}
                  <p class="hint">Written answer{#if q.max_words} · up to {q.max_words} words{/if} — graded by AI</p>
                {/if}
                {#each q.question_type === 'written' ? [] : q.options as _, oi}
                  <div class="opt" class:chosen={q.correct_index === oi}>
                    <button class="radio" class:on={q.correct_index === oi}
                            disabled={!include[qi]} on:click={() => setIncomingAnswer(qi, oi)}
                            aria-label="Mark option {String.fromCharCode(65 + oi)} correct">
                      {#if q.correct_index === oi}<Icon name="check" size={14} stroke={2.4} />{:else}{String.fromCharCode(65 + oi)}{/if}
                    </button>
                    <input bind:value={q.options[oi]} disabled={!include[qi]} />
                  </div>
                {/each}
                <div class="row">
                  <label>Topic<input bind:value={q.topic} disabled={!include[qi]} placeholder="e.g. Pricing" /></label>
                  <label class="narrow">Marks<input type="number" min="1" bind:value={q.marks} disabled={!include[qi]} /></label>
                </div>
              </div>
            {/each}
          </div>

          {#if extendError}<p class="note bad"><Icon name="alert" size={16} /> {extendError}</p>{/if}
          <div class="btn-row">
            <button class="btn-primary" disabled={busy || selectedCount === 0} on:click={appendSelected}>
              <Icon name="plus" size={16} /> {busy ? 'Adding…' : `Add ${selectedCount} question${selectedCount === 1 ? '' : 's'}`}
            </button>
            <button class="btn-ghost" disabled={busy} on:click={cancelExtend}>Cancel</button>
          </div>
        {/if}
      </section>
    {/if}

    <div class="q-head-row ui-rise" style="--i:5">
      <h2>Questions <span class="count">{questions.length}</span></h2>
      {#if unscorable > 0}
        <span class="ui-pill butter"><Icon name="alert" size={14} /> {unscorable} need an answer</span>
      {:else if questions.length}
        <span class="ui-pill mint"><Icon name="check" size={14} /> All scorable</span>
      {/if}
    </div>

    {#if unscorable > 0}
      <p class="warn"><Icon name="alert" size={16} /> {unscorable} question(s) have no correct answer marked — set them to publish.</p>
    {/if}

    <div class="q-list">
      {#each questions as q, qi (qi)}
        <div class="q-card ui-rise" style="--i:{Math.min(qi + 6, 14)}" class:incomplete={!scorable(q)}>
          <div class="q-head">
            <span class="q-num" class:done={scorable(q)}>
              {#if scorable(q)}<Icon name="check" size={13} stroke={2.4} />{:else}<Icon name="alert" size={13} />{/if}
              Q{qi + 1}
            </span>
            <button class="link danger" on:click={() => removeQuestion(qi)}><Icon name="trash" size={14} /> Remove</button>
          </div>
          <textarea class="q-text" rows="2" bind:value={q.question}></textarea>
          {#if q.question_type === 'written'}
            <!-- Written: the learner types prose and the AI grades it, so there
                 are no options to mark. The reference answer guides the grading. -->
            <p class="hint">Written answer{#if q.max_words} · up to {q.max_words} words{/if} — graded by AI</p>
            <label>Reference answer<textarea rows="2" bind:value={q.expected_answer} placeholder="Optional: what a good answer covers"></textarea></label>
          {:else}
            <p class="hint">Click the circle to mark the correct answer</p>
            {#each q.options as _, oi}
              <div class="opt" class:chosen={q.correct_index === oi}>
                <button class="radio" class:on={q.correct_index === oi} on:click={() => setAnswer(qi, oi)}
                        aria-label="Mark option {String.fromCharCode(65 + oi)} correct">
                  {#if q.correct_index === oi}<Icon name="check" size={14} stroke={2.4} />{:else}{String.fromCharCode(65 + oi)}{/if}
                </button>
                <input bind:value={q.options[oi]} />
                <button class="x" on:click={() => removeOption(qi, oi)} aria-label="Remove option"><Icon name="close" size={14} /></button>
              </div>
            {/each}
            <button class="link add-opt" on:click={() => addOption(qi)}><Icon name="plus" size={14} /> add option</button>
          {/if}
          <div class="row">
            <label>Topic<input bind:value={q.topic} placeholder="e.g. Objection Handling" /></label>
            <label class="narrow">Marks<input type="number" min="1" bind:value={q.marks} /></label>
          </div>
          <label>Explanation<input bind:value={q.explanation} placeholder="Optional" /></label>
        </div>
      {/each}
    </div>

    <button class="add-q" on:click={addQuestion}><span class="aq-ico"><Icon name="plus" size={18} /></span> Add a question</button>

    <div class="save-bar">
      <button class="btn-primary" disabled={busy} on:click={save}><Icon name="save" size={16} /> {busy ? 'Saving…' : 'Save changes'}</button>
      <button class="btn-ghost" disabled={busy || (!test.is_published && unscorable > 0)} on:click={togglePublish}>
        <Icon name={test.is_published ? 'eyeOff' : 'send'} size={16} />
        {test.is_published ? 'Unpublish' : 'Publish'}
      </button>
    </div>
  {/if}
</div>

<style>
  .page { max-width: 860px; margin: 0 auto; }

  /* ---------- header ---------- */
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1.25rem; flex-wrap: wrap; margin-bottom: 1.25rem; }
  .head-copy { min-width: 0; }
  .eyebrow { color: var(--muted); font-size: 0.92rem; font-weight: 500; margin-bottom: 0.3rem; }
  h1 { font-size: clamp(1.6rem, 1.1rem + 1.6vw, 2.3rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.08; display: flex; align-items: center; gap: 0.6rem; }
  .title-text { min-width: 0; overflow-wrap: anywhere; }
  .title-mark {
    flex: none; display: inline-grid; place-items: center; width: 44px; height: 44px; border-radius: 50%;
    background: var(--tile-butter); color: var(--tile-ink); rotate: 8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: -8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .meta { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.75rem; }
  .meta b { font-weight: 700; font-variant-numeric: tabular-nums; }
  .src { background: var(--surface2); color: var(--text-secondary); max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .head-actions { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
  .status {
    display: inline-flex; align-items: center; gap: 0.45rem; height: 34px; padding: 0 0.85rem;
    border-radius: 999px; font-size: 0.78rem; font-weight: 700; background: var(--surface2); color: var(--muted);
  }
  .status.live { background: color-mix(in srgb, var(--success) 15%, transparent); color: var(--success); }
  .s-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .status.live .s-dot { animation: pulse-ring 1.6s var(--ease-out) infinite; }
  .plus { display: inline-grid; transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-2) var(--ease-out); }
  .add-toggle.open .plus { rotate: 45deg; }
  .add-toggle:hover .plus { scale: 1.15; }

  /* ---------- notes ---------- */
  .note, .warn {
    display: flex; align-items: flex-start; gap: 0.5rem; font-size: 0.86rem; font-weight: 500; line-height: 1.5;
    padding: 0.7rem 0.95rem; border-radius: 16px; margin-bottom: 1rem; animation: rise 360ms var(--ease-out);
  }
  .note :global(.icon), .warn :global(.icon) { flex: none; margin-top: 2px; }
  .note.bad { background: color-mix(in srgb, var(--danger) 12%, transparent); color: var(--danger); }
  .note.good { background: color-mix(in srgb, var(--success) 13%, transparent); color: var(--success); }
  .warn { background: color-mix(in srgb, var(--warn) 14%, transparent); color: var(--text); }
  .warn :global(.icon) { color: var(--warn); }

  /* ---------- cards / forms ---------- */
  .card {
    background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-sm);
    padding: 1.4rem 1.5rem 1.5rem; display: flex; flex-direction: column; gap: 1rem; margin-bottom: 1.5rem;
  }
  .card.extend { box-shadow: 0 0 0 2px var(--accent), var(--shadow); animation: rise 420ms var(--ease-out); }
  .card-head { display: flex; align-items: center; gap: 0.7rem; }
  .c-ico { width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; color: var(--tile-ink); transition: rotate var(--dur-3) var(--ease-out); }
  .card:hover .c-ico { rotate: -12deg; }
  .c-ico.lilac { background: var(--tile-lilac); }
  .c-ico.mint { background: var(--tile-mint); }
  h2 { font-size: 1.2rem; font-weight: 700; letter-spacing: -0.02em; }
  label { display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.82rem; font-weight: 500; color: var(--muted); flex: 1; min-width: 160px; }
  label.narrow { flex: 0 0 120px; min-width: 100px; }
  input, textarea {
    background: var(--surface2); border: 1px solid transparent; color: var(--text);
    border-radius: 14px; padding: 0.7rem 0.9rem; font-size: 0.9rem; font-family: inherit; width: 100%;
    transition: background-color var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out);
  }
  input:hover:not(:disabled), textarea:hover:not(:disabled) { background: var(--surface3); }
  input:focus, textarea:focus { background: var(--surface); box-shadow: 0 0 0 2px var(--accent); outline: none; }
  input[type='file'] { padding: 0.55rem; cursor: pointer; }
  .row { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .check { flex-direction: row; align-items: flex-start; gap: 0.65rem; color: var(--text); font-size: 0.88rem; cursor: pointer; padding: 0.15rem 0; }
  .check input { width: 18px; height: 18px; flex: none; margin-top: 0.1rem; accent-color: var(--accent); }
  /* The proctoring toggle carries an explanation, so its label stacks. */
  .check > span { display: flex; flex-direction: column; gap: 0.15rem; }
  .check-title { display: inline-flex; align-items: center; gap: 0.35rem; font-weight: 600; }
  .check small { font-weight: 400; font-size: 0.76rem; color: var(--muted); line-height: 1.5; max-width: 52ch; }
  .btn-row { display: flex; gap: 0.6rem; flex-wrap: wrap; }

  .audience {
    display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;
    padding: 0.7rem 0.9rem; border-radius: 18px; background: var(--tile-sky); color: var(--tile-ink);
  }
  .aud-ico { flex: none; width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); }
  .aud-txt { flex: 1; min-width: 14ch; display: flex; flex-direction: column; }
  .aud-lbl { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.7; }
  .aud-val { font-size: 0.88rem; font-weight: 600; }
  .aud-link {
    display: inline-flex; align-items: center; gap: 0.3rem; white-space: nowrap;
    font-size: 0.8rem; font-weight: 600; padding: 0.35rem 0.75rem; border-radius: 99px; background: var(--tile-inner);
    transition: background-color var(--dur-2);
  }
  .aud-link:hover { background: var(--surface); }
  .aud-link:hover :global(.icon) { translate: 3px 0; transition: translate var(--dur-2) var(--ease-out); }

  .info {
    display: flex; gap: 0.55rem; align-items: flex-start;
    font-size: 0.84rem; color: var(--tile-ink); background: var(--tile-sky);
    padding: 0.75rem 0.95rem; border-radius: 16px; line-height: 1.6;
  }
  .info :global(.icon) { flex: none; margin-top: 3px; }
  .file-info { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.8rem; color: var(--text-secondary); animation: fade 300ms var(--ease-out); }
  .spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid color-mix(in srgb, var(--on-accent) 35%, transparent); border-top-color: var(--on-accent); animation: spin 800ms linear infinite; }
  @keyframes spin { to { rotate: 360deg; } }

  .parse-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.6rem; }
  .ps { display: flex; flex-direction: column; padding: 0.8rem 0.95rem; border-radius: 18px; color: var(--tile-ink); animation: pop 420ms var(--ease-out) backwards; }
  .ps:nth-child(2) { animation-delay: 60ms; } .ps:nth-child(3) { animation-delay: 120ms; } .ps:nth-child(4) { animation-delay: 180ms; }
  .ps b { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.03em; font-variant-numeric: tabular-nums; line-height: 1.1; }
  .ps span { font-size: 0.76rem; opacity: 0.75; }
  .ps.sky { background: var(--tile-sky); } .ps.mint { background: var(--tile-mint); }
  .ps.lilac { background: var(--tile-lilac); } .ps.butter { background: var(--tile-butter); }
  .ps.plain { background: var(--surface2); color: var(--text); }

  .incoming { display: flex; flex-direction: column; gap: 0.75rem; }
  .in-card {
    background: var(--surface2); border-radius: 20px; padding: 0.95rem;
    display: flex; flex-direction: column; gap: 0.55rem;
    transition: opacity var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .in-card input, .in-card textarea { background: var(--surface); }
  .in-card.dupe { box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--warn) 55%, transparent); }
  .in-card.skipped { opacity: 0.45; scale: 0.985; }
  .in-head { flex-direction: row; align-items: center; gap: 0.55rem; color: var(--text); cursor: pointer; }
  .in-head input { width: 18px; height: 18px; flex: none; accent-color: var(--accent); }
  .in-num { font-size: 0.8rem; font-weight: 700; }
  .dupe-tag {
    display: inline-flex; align-items: center; gap: 0.25rem; font-size: 0.7rem; font-weight: 600;
    color: var(--tile-ink); background: var(--tile-butter); border-radius: 999px; padding: 0.15rem 0.55rem;
  }

  /* ---------- questions ---------- */
  .q-head-row { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin: 0.4rem 0 0.9rem; }
  .q-head-row h2 { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 1.4rem; }
  .count { min-width: 26px; height: 24px; padding: 0 7px; border-radius: 99px; font-size: 0.78rem; display: inline-grid; place-items: center; background: var(--surface2); color: var(--text-secondary); }

  .q-list { display: flex; flex-direction: column; gap: 0.9rem; }
  .q-card {
    background: var(--surface); border-radius: 24px; box-shadow: var(--shadow-sm);
    padding: 1.15rem 1.25rem; display: flex; flex-direction: column; gap: 0.7rem;
    transition: box-shadow var(--dur-3) var(--ease-out), translate var(--dur-3) var(--ease-out);
  }
  .q-card:hover { box-shadow: var(--shadow); }
  .q-card:focus-within { box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 25%, transparent), var(--shadow); }
  .q-card.incomplete { box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--warn) 55%, transparent), var(--shadow-sm); }
  .q-head { display: flex; justify-content: space-between; align-items: center; }
  .q-num {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 28px; padding: 0 0.7rem; border-radius: 99px;
    font-size: 0.8rem; font-weight: 700; background: var(--tile-butter); color: var(--tile-ink);
    transition: background-color var(--dur-3) var(--ease-out);
  }
  .q-num.done { background: var(--tile-mint); }
  .q-num :global(.icon) { animation: pop 360ms var(--ease-out); }
  .q-text { font-size: 0.94rem; resize: vertical; line-height: 1.5; }
  .hint { font-size: 0.74rem; color: var(--muted); }
  .opt { display: flex; align-items: center; gap: 0.5rem; }
  .opt input { padding: 0.6rem 0.85rem; }
  .opt.chosen input { box-shadow: inset 0 0 0 1.5px var(--success); background: color-mix(in srgb, var(--success) 8%, var(--surface2)); }
  .radio {
    flex-shrink: 0; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center;
    background: var(--surface2); color: var(--muted); font-size: 0.78rem; font-weight: 700;
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2), scale var(--dur-2) var(--ease-out);
  }
  .radio:hover:not(:disabled) { background: var(--surface3); color: var(--text); scale: 1.08; }
  .radio.on { background: var(--success); color: var(--on-accent); animation: pop 380ms var(--ease-out); }
  .radio:disabled { opacity: 0.5; cursor: not-allowed; }
  .x {
    flex: none; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center;
    background: none; color: var(--muted); transition: color var(--dur-2), background-color var(--dur-2), rotate var(--dur-3) var(--ease-out);
  }
  .x:hover { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); rotate: 90deg; }

  .link {
    display: inline-flex; align-items: center; gap: 0.3rem; align-self: flex-start;
    background: none; color: var(--text-secondary); font-size: 0.8rem; font-weight: 600;
    padding: 0.3rem 0.65rem; border-radius: 99px; transition: color var(--dur-2), background-color var(--dur-2);
  }
  .link:hover { color: var(--text); background: var(--surface2); }
  .link.danger { color: var(--muted); }
  .link.danger:hover { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); }
  .link.danger:hover :global(.icon) { animation: wiggle 420ms var(--ease-out); }
  .add-opt:hover :global(.icon) { rotate: 90deg; transition: rotate var(--dur-3) var(--ease-out); }

  .add-q {
    display: flex; align-items: center; justify-content: center; gap: 0.6rem; width: 100%;
    margin: 1rem 0; padding: 1rem; border-radius: 24px;
    background: transparent; border: 2px dashed var(--border); color: var(--muted); font-weight: 600; font-size: 0.92rem;
    transition: border-color var(--dur-2), color var(--dur-2), background-color var(--dur-2);
  }
  .add-q:hover { border-color: var(--accent); color: var(--text); background: var(--surface); }
  .aq-ico { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: var(--surface2); transition: rotate var(--dur-3) var(--ease-out), background-color var(--dur-2); }
  .add-q:hover .aq-ico { rotate: 90deg; background: var(--accent); color: var(--on-accent); }

  .save-bar {
    display: flex; gap: 0.6rem; position: sticky; bottom: 1rem; z-index: 5;
    width: fit-content; margin: 0.5rem auto 0; padding: 0.5rem; border-radius: 999px;
    background: var(--surface); box-shadow: var(--shadow-lg);
    animation: rise 500ms var(--ease-out) 300ms backwards;
  }

  /* ---------- states ---------- */
  .state { display: flex; flex-direction: column; align-items: center; gap: 0.7rem; text-align: center; padding: 3rem 1.5rem; border-radius: 28px; background: var(--surface); }
  .state h2 { font-size: 1.25rem; }
  .state p { color: var(--muted); }
  .state-ico { width: 60px; height: 60px; border-radius: 50%; display: grid; place-items: center; animation: pop 520ms var(--ease-out); }
  .state-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }

  @media (max-width: 760px) {
    .card { padding: 1.1rem; border-radius: 24px; }
    .parse-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .head-actions { width: 100%; }
    label.narrow { flex: 1 1 100px; }
    .save-bar { width: auto; bottom: 0.6rem; }
    .save-bar > * { flex: 1; justify-content: center; }
  }
</style>
