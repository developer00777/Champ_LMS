<script lang="ts">
  import { api, type AdminCourse, type AdminTestItem, type ParsedPdfForTest } from '$lib/api/client';
  import { icons } from '../icons';

  export let course: AdminCourse;
  export let item: AdminTestItem;
  export let onReload: () => void;
  export let onOpenAccess: () => void;

  let title = item.title;
  let busy = '';
  let error = '';
  let message = '';
  let parsed: ParsedPdfForTest | null = null;
  let aiCount = 15;
  let shownId = item.id;

  $: if (item.id !== shownId) { shownId = item.id; title = item.title; parsed = null; error = message = ''; }

  let timer: ReturnType<typeof setTimeout>;
  function save(change: Parameters<typeof api.updateCourseTest>[2], wait = 500) {
    Object.assign(item, change); item = item;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try { await api.updateCourseTest(course.id, item.ref_id, change); onReload(); }
      catch (e: any) { error = e.message; }
    }, wait);
  }

  async function onPaper(e: Event) {
    const f = (e.target as HTMLInputElement).files?.[0];
    (e.target as HTMLInputElement).value = '';
    if (!f) return;
    busy = 'parse'; error = ''; message = ''; parsed = null;
    try { parsed = await api.parseTestPdfForTest(item.ref_id, f); }
    catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  $: toAdd = parsed ? parsed.questions.filter(q => !q.duplicate_of_existing) : [];

  async function addParsed() {
    if (!parsed) return;
    busy = 'append'; error = '';
    try {
      const r = await api.appendTestQuestions(item.ref_id, toAdd, { filename: parsed.source_filename, parser: parsed.source_parser });
      message = `Added ${r.added} question${r.added === 1 ? '' : 's'}.`;
      parsed = null; onReload();
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }

  async function writeWithAi() {
    busy = 'ai'; error = ''; message = '';
    try {
      const r = await api.generateCourseTest(course.id, item.ref_id, aiCount);
      message = `The paper now has ${r.question_count} AI-written questions. Review them in the question editor.`;
      onReload();
    } catch (e: any) { error = e.message; }
    finally { busy = ''; }
  }
</script>

<div class="insp-body">
  <label class="field">
    <span>Test title</span>
    <input type="text" bind:value={title} on:input={() => save({ title: title.trim() || 'Course test' })} maxlength="200" />
  </label>

  <div class="kv">
    <span>Questions</span>
    <b>
      {item.question_count || 'None yet'}
      {#if item.unscorable_count}<span class="pill warn">{item.unscorable_count} need an answer</span>{/if}
    </b>
    <span>Status</span>
    <b>
      {#if item.is_published}<span class="pill ok">Live</span>
      {:else if item.is_ready}<span class="pill">Goes live when you publish the course</span>
      {:else}<span class="pill warn">Not ready</span>{/if}
    </b>
    {#if item.source_filename}<span>From</span><b class="mono">{item.source_filename}</b>{/if}
  </div>

  <div class="field">
    <span>Add questions</span>
    <div class="row">
      <label class="btn sm">{@html icons.upload} {busy === 'parse' ? 'Reading…' : 'Upload PDF or Word'}
        <input type="file" accept=".pdf,.docx" hidden on:change={onPaper} disabled={!!busy} /></label>
      <a class="btn sm ghost" href="/admin/tests/{item.ref_id}">Open question editor</a>
    </div>
  </div>

  {#if parsed}
    <div class="parsed">
      <b>{parsed.detected_questions} questions found in {parsed.source_filename}</b>
      {#if parsed.unscorable_count}<p class="hint">{parsed.unscorable_count} have no answer key. Set those in the question editor after adding.</p>{/if}
      {#each parsed.warnings as w}<p class="hint">{w}</p>{/each}
      <div class="row">
        <button class="btn sm primary" on:click={addParsed} disabled={!toAdd.length || !!busy}>Add {toAdd.length} question{toAdd.length === 1 ? '' : 's'}</button>
        <button class="btn sm ghost" on:click={() => (parsed = null)}>Discard</button>
      </div>
    </div>
  {/if}

  <div class="row">
    {#if busy === 'ai'}
      <div class="gen-load grow"><span class="spin"></span>Writing {aiCount} questions from every episode…</div>
    {:else}
      <button class="btn sm" on:click={writeWithAi} disabled={!!busy}>{@html icons.sparkle} Write the paper with AI</button>
      <label class="inline">
        <input type="number" min="3" max="50" bind:value={aiCount} aria-label="Number of questions" /> questions
      </label>
    {/if}
  </div>
  {#if item.question_count && busy !== 'ai'}<p class="hint">Writing with AI replaces the questions already on this test.</p>{/if}

  <div class="row">
    <label class="field" style="width:90px"><span>Pass %</span>
      <input type="number" min="1" max="100" value={item.pass_threshold}
        on:input={e => { const v = +e.currentTarget.value; if (v >= 1 && v <= 100) save({ pass_threshold: v }); }} /></label>
    <label class="field" style="width:100px"><span>Minutes</span>
      <input type="number" min="1" max="600" value={item.duration_minutes ?? ''}
        on:input={e => { const v = +e.currentTarget.value; if (v >= 1) save({ duration_minutes: v }); }} /></label>
  </div>
  <div class="row">
    <label class="field grow"><span>Opens</span>
      <select value={item.unlock_rule} on:change={e => save({ unlock_rule: e.currentTarget.value === 'any' ? 'any' : 'all_videos' }, 0)}>
        <option value="all_videos">After every episode is watched</option>
        <option value="any">Any time</option>
      </select></label>
  </div>

  <div class="lock-row">
    {@html icons.lock}
    <div><b>You approve every attempt.</b> When someone asks to take this test, the request pops up on your screen and you choose how many attempts to allow.
      {#if item.pending_requests}<a href="/admin/test-requests">{item.pending_requests} waiting now.</a>{/if}</div>
  </div>

  <div class="setting">
    <div><b>Attempts to suggest when approving</b><span>Pre-filled in the approval pop-up. You can change it for each person.</span></div>
    <div class="stepper">
      <button on:click={() => save({ attempts_per_approval: Math.max(1, item.attempts_per_approval - 1) }, 0)} aria-label="Fewer">−</button>
      <b>{item.attempts_per_approval}</b>
      <button on:click={() => save({ attempts_per_approval: Math.min(10, item.attempts_per_approval + 1) }, 0)} aria-label="More">+</button>
    </div>
  </div>
  <div class="setting">
    <div><b>Proctoring</b><span>Locked-down exam window and an AI integrity check.</span></div>
    <button class="tgl" class:on={item.proctoring_enabled} role="switch" aria-checked={item.proctoring_enabled} aria-label="Proctoring"
      on:click={() => save({ proctoring_enabled: !item.proctoring_enabled }, 0)}></button>
  </div>
  <div class="setting">
    <div><b>Shuffle questions</b><span>Each attempt gets a different order.</span></div>
    <button class="tgl" class:on={item.shuffle_questions} role="switch" aria-checked={item.shuffle_questions} aria-label="Shuffle questions"
      on:click={() => save({ shuffle_questions: !item.shuffle_questions }, 0)}></button>
  </div>
  <div class="setting">
    <div><b>Who can ask to take it</b><span>Separate from who can watch the course. Starts with nobody.</span></div>
    <button class="btn sm" on:click={onOpenAccess}>{@html icons.key} Test access</button>
  </div>

  {#if message}<p class="okmsg">{message}</p>{/if}
  {#if error}<p class="error">{error}</p>{/if}
</div>
