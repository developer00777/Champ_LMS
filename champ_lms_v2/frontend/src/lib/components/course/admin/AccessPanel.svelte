<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type AccessPerson, type AdminCourse, type AdminTestItem, type ContentKind, type ModuleAccessPeople } from '$lib/api/client';
  import { icons } from '../icons';
  import SortHeader from '$lib/components/SortHeader.svelte';
  import Select from '$lib/components/Select.svelte';
  import { ariaSort, sortRows, NO_SORT, type SortAccessors } from '$lib/utils/table-sort';

  export let course: AdminCourse;
  export let focusTestId: string | null = null;
  export let onChanged: () => void;

  type Kind = 'team' | 'dept' | 'person';
  const KIND_LABEL: Record<Kind, string> = { team: 'Team', dept: 'Department', person: 'Person' };
  const KINDS: Kind[] = ['team', 'dept', 'person'];

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

  // The selected test's row for each person, looked up once rather than per cell.
  $: testPerson = new Map((currentTest?.people ?? []).map(x => [x.user_id, x]));
  let sort = NO_SORT;
  const sortBy = (tp: Map<string, AccessPerson>): SortAccessors<AccessPerson> => ({
    name: p => p.full_name || p.email,
    team: p => p.team,
    watch: p => p.can_access,
    ask: p => !!tp.get(p.user_id)?.can_access,
    left: p => tp.get(p.user_id)?.attempts?.left ?? 0,
  });
  // The test columns come and go with the test; don't keep sorting by a hidden one.
  $: if (!currentTest && (sort.key === 'ask' || sort.key === 'left')) sort = NO_SORT;
  $: rows = sortRows(people, sort, sortBy(testPerson));
</script>

<div class="access">
  {#if error}<p class="error">{error}</p>{/if}
  {#if loading && !watch}
    <div class="acc-grid" aria-busy="true" aria-label="Loading who can see this course">
      <div class="ui-skeleton" style="height:260px;border-radius:26px"></div>
      <div class="ui-skeleton" style="height:260px;border-radius:26px"></div>
    </div>
    <div class="ui-skeleton" style="height:220px;border-radius:26px"></div>
  {:else}
    <div class="acc-grid">
      {#each [{ kind: 'module', target: watch, title: 'Watch access', copy: 'People here can watch every episode and read the notes and transcripts, as often as they like. There is no view limit and no end date.' }, { kind: 'test', target: currentTest, title: 'Test access', copy: 'People here can see the tests and ask to take them. Each attempt still needs your approval.' }] as panel, pi}
        <section class="acc-panel ui-rise" style="--i:{pi}">
          <div class="acc-h">
            <h3><span class="h-ico {panel.kind === 'test' ? 'butter' : 'sky'}">{@html panel.kind === 'test' ? icons.test : icons.eye}</span>{panel.title}</h3>
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
              <Select bind:value={testId} ariaLabel="Which test" size="sm" shape="pill"
                options={testItems.map(t => ({ value: t.ref_id, label: t.title }))} />
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
              <Select bind:value={addKind[panel.kind]} on:change={() => (addValue[panel.kind] = '')} ariaLabel="Add by" size="sm" shape="pill"
                options={KINDS.map(k => ({ value: k, label: KIND_LABEL[k] }))} />
              <Select bind:value={addValue[panel.kind]} ariaLabel="Who" size="sm" shape="pill" placeholder="Nobody to add"
                options={options(addKind[panel.kind], teams, departments, people)
                  .map(o => ({ value: o, label: addKind[panel.kind] === 'person' ? personName(o) : o }))} />
              <button class="btn" on:click={() => add(panel.kind === 'test' ? 'test' : 'module', panel.target)}>Add</button>
            </div>
            {#if panel.kind === 'test'}
              <button class="btn sm ghost start" on:click={copyWatchToTest}>Same people as watch access</button>
            {/if}
          {/if}
        </section>
      {/each}
    </div>

    <h3 class="tbl-h ui-rise" style="--i:2">What each person gets</h3>
    <div class="table-wrap ui-rise" style="--i:3">
      <table>
        <thead>
          <tr>
            <th aria-sort={ariaSort(sort, 'name')}><SortHeader field="name" bind:sort>Person</SortHeader></th>
            <th aria-sort={ariaSort(sort, 'team')}><SortHeader field="team" bind:sort>Team</SortHeader></th>
            <th aria-sort={ariaSort(sort, 'watch')}><SortHeader field="watch" bind:sort>Can watch</SortHeader></th>
            {#if currentTest}
              <th aria-sort={ariaSort(sort, 'ask')}><SortHeader field="ask" bind:sort>Can ask for “{currentTest.title}”</SortHeader></th>
              <th aria-sort={ariaSort(sort, 'left')}><SortHeader field="left" bind:sort>Attempts left</SortHeader></th>
            {/if}
          </tr>
        </thead>
        <tbody>
          {#each rows as p (p.user_id)}
            {@const t = testPerson.get(p.user_id)}
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
            <tr><td colspan={currentTest ? 5 : 3} class="hint">No learner accounts yet.</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .access { display: grid; gap: 1rem; }
  .error { color: var(--danger); font-size: 0.86rem; padding: 0.7rem 0.9rem; border-radius: 18px; background: color-mix(in srgb, var(--danger) 12%, var(--surface)); animation: rise 320ms var(--ease-out); }
  .acc-grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr)); }
  .acc-panel {
    background: var(--surface); border-radius: 26px; box-shadow: var(--shadow-sm); padding: 1.2rem; display: grid; gap: 0.85rem; align-content: start;
    transition: box-shadow var(--dur-3) var(--ease-out), translate var(--dur-3) var(--ease-out);
  }
  .acc-panel:hover { box-shadow: var(--shadow); translate: 0 -2px; }
  .acc-h { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
  h3 { font-size: 1.12rem; font-weight: 700; letter-spacing: -0.015em; display: flex; align-items: center; gap: 0.55rem; }
  .h-ico {
    width: 34px; height: 34px; border-radius: 50%; display: inline-grid; place-items: center; font-size: 1rem; color: var(--tile-ink); flex: none;
    transition: rotate var(--dur-3) var(--ease-out);
  }
  .acc-panel:hover .h-ico { rotate: -10deg; }
  .h-ico.sky { background: var(--tile-sky); }
  .h-ico.butter { background: var(--tile-butter); }
  .copy { font-size: 0.86rem; color: var(--text-secondary); line-height: 1.55; }
  .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.4rem; height: 32px; padding: 0 0.25rem 0 0.75rem; border-radius: 99px; background: var(--surface2); font-size: 0.83rem;
    animation: pop 340ms var(--ease-out) backwards;
    transition: background-color var(--dur-2) var(--ease-out);
  }
  .chip:hover { background: var(--surface3); }
  .chip .k { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); }
  .chip button { display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; color: var(--muted); transition: background-color var(--dur-2), color var(--dur-2), rotate var(--dur-3) var(--ease-out); }
  .chip button:hover { background: var(--surface); color: var(--danger); rotate: 90deg; }
  .none { display: flex; gap: 0.45rem; align-items: center; height: 32px; padding: 0 0.8rem; border-radius: 99px; color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); font-weight: 600; font-size: 0.82rem; }
  .acc-add { display: grid; grid-template-columns: 130px minmax(0, 1fr) auto; gap: 0.45rem; }
  @media (max-width: 460px) { .acc-add { grid-template-columns: 1fr; } }
  .start { justify-self: start; }
  .tbl-h { margin-top: 0.5rem; }
  .table-wrap { overflow-x: auto; border-radius: 26px; background: var(--surface); box-shadow: var(--shadow-sm); }
  table { width: 100%; min-width: 620px; border-collapse: collapse; }
  th { text-align: left; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); padding: 0.9rem 1.1rem 0.7rem; border-bottom: 1px solid var(--border); }
  td { padding: 0.75rem 1.1rem; border-bottom: 1px solid var(--border); font-size: 0.87rem; transition: background-color var(--dur-2) var(--ease-out); }
  tbody tr { animation: fade 360ms var(--ease-out) backwards; }
  tbody tr:hover td { background: var(--surface2); }
  tr:last-child td { border-bottom: 0; }
  .yes { color: var(--tile-ink); background: var(--tile-mint); font-weight: 600; display: inline-flex; gap: 0.3rem; align-items: center; height: 26px; padding: 0 0.65rem; border-radius: 99px; font-size: 0.78rem; }
  .no { color: var(--muted); display: inline-flex; height: 26px; align-items: center; padding: 0 0.65rem; border-radius: 99px; background: var(--surface2); font-size: 0.78rem; }
</style>
