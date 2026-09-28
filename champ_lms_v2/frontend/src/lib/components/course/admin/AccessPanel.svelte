<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type AdminCourse, type AdminTestItem, type ContentKind, type ModuleAccessPeople } from '$lib/api/client';
  import { icons } from '../icons';

  export let course: AdminCourse;
  export let focusTestId: string | null = null;
  export let onChanged: () => void;

  type Kind = 'team' | 'dept' | 'person';
  const KIND_LABEL: Record<Kind, string> = { team: 'Team', dept: 'Department', person: 'Person' };

  let teams: string[] = [];
  let departments: string[] = [];
  let watch: ModuleAccessPeople | null = null;
  let tests: Record<string, ModuleAccessPeople> = {};
  let testId: string | null = null;
  let loading = true;
  let error = '';
  let addKind: Record<string, Kind> = { module: 'team', test: 'team' };
  let addValue: Record<string, string> = { module: '', test: '' };

  $: testItems = course.items.filter((i): i is AdminTestItem => i.kind === 'test');
  $: if (!testId && testItems.length) testId = focusTestId ?? testItems[0].ref_id;
  $: if (focusTestId) testId = focusTestId;
  $: currentTest = testId ? tests[testId] : null;
  $: people = (watch?.people ?? []).filter(p => p.role === 'learner' && p.is_active);

  async function load() {
    loading = true; error = '';
    try {
      const [cat, w, ...ts] = await Promise.all([
        api.contentAudiences(),
        api.contentAccessPeople('module', course.id),
        ...testItems.map(t => api.contentAccessPeople('test', t.ref_id)),
      ]);
      teams = cat.teams; departments = cat.departments; watch = w;
      tests = Object.fromEntries(ts.map(t => [t.id, t]));
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }
  onMount(load);

  // Keep each picker on a real option, so Add never sends an empty value.
  $: for (const key of ['module', 'test']) {
    const opts = options(addKind[key], teams, departments, people);
    if (!opts.includes(addValue[key])) addValue[key] = opts[0] ?? '';
  }
  const options = (k: Kind, ..._deps: unknown[]) => (k === 'team' ? teams : k === 'dept' ? departments : people.map(p => p.user_id));
  const personName = (id: string) => {
    const p = watch?.people.find(x => x.user_id === id);
    return p ? (p.full_name ?? p.email) : id;
  };

  function chips(c: ModuleAccessPeople | null) {
    if (!c) return [];
    return [
      ...c.audience_teams.map(v => ({ kind: 'team' as Kind, value: v, label: v })),
      ...c.audience_departments.map(v => ({ kind: 'dept' as Kind, value: v, label: v })),
      ...c.people.filter(p => p.rule === 'grant' || p.rule === 'required')
        .map(p => ({ kind: 'person' as Kind, value: p.user_id, label: p.full_name ?? p.email })),
    ];
  }

  async function add(kind: ContentKind, target: ModuleAccessPeople | null) {
    if (!target) return;
    const k = addKind[kind];
    const v = addValue[kind] || options(k)[0];
    if (!v) return;
    error = '';
    try {
      if (k === 'person') await api.setPersonAccess(kind, target.id, v, 'grant', 'Added from the course canvas');
      else if (k === 'team') await api.setContentAudience(kind, target.id, { audience_teams: [...new Set([...target.audience_teams, v])] });
      else await api.setContentAudience(kind, target.id, { audience_departments: [...new Set([...target.audience_departments, v])] });
      await load(); onChanged();
    } catch (e: any) { error = e.message; }
  }

  async function remove(kind: ContentKind, target: ModuleAccessPeople, chip: { kind: Kind; value: string }) {
    error = '';
    try {
      if (chip.kind === 'person') await api.clearPersonAccess(kind, target.id, chip.value);
      else if (chip.kind === 'team') await api.setContentAudience(kind, target.id, { audience_teams: target.audience_teams.filter(t => t !== chip.value) });
      else await api.setContentAudience(kind, target.id, { audience_departments: target.audience_departments.filter(t => t !== chip.value) });
      await load(); onChanged();
    } catch (e: any) { error = e.message; }
  }

  async function copyWatchToTest() {
    if (!watch || !currentTest) return;
    error = '';
    try {
      await api.setContentAudience('test', currentTest.id, {
        audience_teams: watch.audience_teams, audience_departments: watch.audience_departments,
      });
      for (const p of watch.people.filter(p => p.rule === 'grant' || p.rule === 'required')) {
        await api.setPersonAccess('test', currentTest.id, p.user_id, 'grant', 'Same as watch access');
      }
      await load(); onChanged();
    } catch (e: any) { error = e.message; }
  }

  const count = (c: ModuleAccessPeople | null) => (c?.people ?? []).filter(p => p.can_access && p.role === 'learner' && p.is_active).length;
</script>

<div class="access">
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading && !watch}
    <p class="hint">Loading who can see this course…</p>
  {:else}
    <div class="acc-grid">
      {#each [{ kind: 'module', target: watch, title: 'Watch access', copy: 'People here can watch every episode and read the notes and transcripts, as often as they like. There is no view limit and no end date.' }, { kind: 'test', target: currentTest, title: 'Test access', copy: 'People here can see the tests and ask to take them. Each attempt still needs your approval.' }] as panel}
        <section class="acc-panel">
          <div class="acc-h">
            <h3>{panel.title}</h3>
            {#if panel.kind === 'test' && !testItems.length}
              <span class="pill">No tests</span>
            {:else if count(panel.target)}
              <span class="pill ok">{count(panel.target)} people</span>
            {:else}
              <span class="pill bad">Nobody yet</span>
            {/if}
          </div>
          {#if panel.kind === 'test' && !testItems.length}
            <p class="hint">This course has no tests. Add one on the canvas and choose here who may ask to take it.</p>
          {:else}
            {#if panel.kind === 'test' && testItems.length > 1}
              <select bind:value={testId} aria-label="Which test">
                {#each testItems as t}<option value={t.ref_id}>{t.title}</option>{/each}
              </select>
            {/if}
            <p class="copy">{panel.copy}</p>
            <div class="chips">
              {#each chips(panel.target) as chip (chip.kind + chip.value)}
                <span class="chip"><span class="k">{KIND_LABEL[chip.kind]}</span>{chip.label}
                  <button on:click={() => panel.target && remove(panel.kind === 'test' ? 'test' : 'module', panel.target, chip)} aria-label="Remove {chip.label}">{@html icons.x}</button></span>
              {:else}
                <span class="none">{@html icons.lock} Nobody has been added</span>
              {/each}
            </div>
            <div class="acc-add">
              <select bind:value={addKind[panel.kind]} on:change={() => (addValue[panel.kind] = '')} aria-label="Add by">
                <option value="team">Team</option><option value="dept">Department</option><option value="person">Person</option>
              </select>
              <select bind:value={addValue[panel.kind]} aria-label="Who">
                {#each options(addKind[panel.kind]) as o}
                  <option value={o}>{addKind[panel.kind] === 'person' ? personName(o) : o}</option>
                {/each}
              </select>
              <button class="btn" on:click={() => add(panel.kind === 'test' ? 'test' : 'module', panel.target)}>Add</button>
            </div>
            {#if panel.kind === 'test'}
              <button class="btn sm ghost start" on:click={copyWatchToTest}>Same people as watch access</button>
            {/if}
          {/if}
        </section>
      {/each}
    </div>

    <h3 class="tbl-h">What each person gets</h3>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Person</th><th>Team</th><th>Can watch</th>{#if currentTest}<th>Can ask for “{currentTest.title}”</th><th>Attempts left</th>{/if}</tr></thead>
        <tbody>
          {#each people as p (p.user_id)}
            {@const t = currentTest?.people.find(x => x.user_id === p.user_id)}
            <tr>
              <td><b>{p.full_name ?? p.email}</b></td>
              <td>{p.team ?? '—'}</td>
              <td>{#if p.can_access}<span class="yes">{@html icons.check} Yes</span>{:else}<span class="no">No</span>{/if}</td>
              {#if currentTest}
                <td>{#if t?.can_access}<span class="yes">{@html icons.check} Yes</span>{:else}<span class="no">No</span>{/if}</td>
                <td class="mono">{t?.attempts?.left ?? 0}</td>
              {/if}
            </tr>
          {:else}
            <tr><td colspan="5" class="hint">No learner accounts yet.</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .access { display: grid; gap: 1rem; }
  .acc-grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr)); }
  .acc-panel { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1rem; display: grid; gap: 0.75rem; align-content: start; }
  .acc-h { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
  h3 { font-size: 1.05rem; font-weight: 700; }
  .copy { font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .chip { display: inline-flex; align-items: center; gap: 0.4rem; height: 30px; padding: 0 0.25rem 0 0.65rem; border-radius: 99px; background: var(--surface2); font-size: 0.82rem; }
  .chip .k { font-size: 0.64rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
  .chip button { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; color: var(--muted); }
  .chip button:hover { background: var(--surface3); color: var(--text); }
  .none { display: flex; gap: 0.4rem; align-items: center; color: #ff6b70; font-weight: 600; font-size: 0.82rem; }
  .acc-add { display: grid; grid-template-columns: 120px minmax(0, 1fr) auto; gap: 0.4rem; }
  @media (max-width: 460px) { .acc-add { grid-template-columns: 1fr; } }
  select { font: inherit; font-size: 0.85rem; color: var(--text); background: var(--bg); border: 1px solid var(--border-hover); border-radius: 8px; height: 34px; padding: 0 0.5rem; min-width: 0; }
  .start { justify-self: start; }
  .tbl-h { margin-top: 0.5rem; }
  .table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
  table { width: 100%; min-width: 620px; border-collapse: collapse; }
  th { text-align: left; font-size: 0.68rem; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); padding: 0.7rem 1rem; border-bottom: 1px solid var(--border); }
  td { padding: 0.65rem 1rem; border-bottom: 1px solid var(--border); font-size: 0.86rem; }
  tr:last-child td { border-bottom: 0; }
  .yes { color: #2ecc71; font-weight: 600; display: inline-flex; gap: 0.3rem; align-items: center; }
  .no { color: var(--muted); }
</style>
