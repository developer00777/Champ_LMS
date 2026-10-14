<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api, ApiError,
    type Employee, type EmployeeRoster, type BulkUploadResult, type BulkUploadError, type BulkUploadRow,
  } from '$lib/api/client';
  import Avatar from '$lib/components/Avatar.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import { countUp } from '$lib/actions/motion';
  import SortHeader from '$lib/components/SortHeader.svelte';
  import Select from '$lib/components/Select.svelte';
  import { ariaSort, sortRows, NO_SORT, type SortAccessors } from '$lib/utils/table-sort';

  const ROLES = [
    { value: 'learner', label: 'Learner' },
    { value: 'ld_lead', label: 'L&D Lead (admin access)' },
    { value: 'admin', label: 'Admin' },
  ];
  const ROLE_FILTERS = [{ value: '', label: 'All roles' }, ...ROLES];
  const allOf = (label: string, values: string[] = []) => [{ value: '', label }, ...values.map(v => ({ value: v, label: v }))];

  let roster: EmployeeRoster | null = null;
  let loading = true;
  let error = '';

  // filters
  let q = '';
  let filterDept = '';
  let filterTeam = '';
  let filterRole = '';

  // create form
  let showCreate = false;
  let cEmail = '';
  let cName = '';
  let cCode = '';
  let cDept = '';
  let cTeam = '';
  let cRole = 'learner';
  let creating = false;
  let createError = '';
  // Shown after a create/reset so the admin can copy the password out. It also
  // stays visible on the roster, so this is a convenience, not the only chance.
  let issued: { name: string; email: string; password: string } | null = null;

  // per-row state
  let revealed = new Set<string>();
  let editing: string | null = null;
  let eName = '', eDept = '', eTeam = '', eRole = '', eCode = '';
  let rowBusy: string | null = null;

  async function load() {
    loading = true; error = '';
    try {
      roster = await api.employees({
        q: q || undefined,
        department: filterDept || undefined,
        team: filterTeam || undefined,
        role: filterRole || undefined,
      });
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  onMount(load);

  async function create() {
    if (!cEmail.trim() || !cName.trim()) { createError = 'Name and email are required'; return; }
    creating = true; createError = '';
    try {
      const emp = await api.createEmployee({
        email: cEmail.trim(), full_name: cName.trim(),
        employee_code: cCode.trim() || undefined,
        department: cDept.trim() || undefined,
        team: cTeam.trim() || undefined,
        role: cRole,
      });
      issued = { name: emp.full_name ?? emp.email, email: emp.email, password: emp.initial_password };
      cEmail = cName = cCode = cDept = cTeam = ''; cRole = 'learner';
      showCreate = false;
      await load();
    } catch (e: any) { createError = e.message; }
    finally { creating = false; }
  }

  // --- bulk upload from the master tracker ---------------------------------
  let showBulk = false;
  let bulkFile: File | null = null;
  let bulkInput: HTMLInputElement;
  let bulkBusy = false;
  let bulkError = '';
  // Row-level failures from the server. The upload is all-or-nothing, so these
  // are what the admin must fix in the spreadsheet before anything is created.
  let bulkRowErrors: BulkUploadError['errors'] = [];
  // A validated dry run: what *would* be created, held until the admin confirms.
  let bulkPreview: BulkUploadResult | null = null;
  // Created accounts with their starting passwords, kept on screen so the
  // admin can copy them out or export them in one go.
  let bulkCreated: BulkUploadResult['created'] = [];

  function pickBulkFile(e: Event) {
    bulkFile = (e.target as HTMLInputElement).files?.[0] ?? null;
    bulkError = ''; bulkRowErrors = []; bulkPreview = null;
  }

  function resetBulk() {
    bulkFile = null; bulkError = ''; bulkRowErrors = [];
    bulkPreview = null; bulkCreated = [];
    if (bulkInput) bulkInput.value = '';
  }

  async function runBulk(dryRun: boolean) {
    if (!bulkFile) { bulkError = 'Choose a CSV or Excel file first'; return; }
    bulkBusy = true; bulkError = ''; bulkRowErrors = [];
    try {
      const r = await api.bulkUploadEmployees(bulkFile, dryRun);
      if (dryRun) {
        bulkPreview = r;
      } else {
        bulkCreated = r.created ?? [];
        bulkPreview = null;
        bulkFile = null;
        if (bulkInput) bulkInput.value = '';
        await load();
      }
    } catch (e: any) {
      bulkError = e.message;
      // The server sends a structured detail listing every bad row.
      const detail = e instanceof ApiError ? (e.detail as BulkUploadError | undefined) : undefined;
      if (detail && Array.isArray(detail.errors)) bulkRowErrors = detail.errors;
      bulkPreview = null;
    } finally { bulkBusy = false; }
  }

  /** All new passwords as one block, so they can be pasted into a tracker. */
  function copyCreated() {
    const lines = (bulkCreated ?? []).map(
      (r) => [r.employee_code ?? '', r.full_name ?? '', r.email, r.initial_password].join('\t'),
    );
    copy(['Employee ID\tName\tEmail\tPassword', ...lines].join('\n'));
  }

  /** A starter CSV with exactly the headings the importer expects. */
  function downloadTemplate() {
    const csv =
      'Employee ID,Employee Name,Official Email ID,Department,Team,Role\n' +
      'CHMP-0001,Jane Doe,jane@championsmail.com,Sales,Enterprise West,learner\n';
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url; a.download = 'champ-employee-tracker-template.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  function startEdit(emp: Employee) {
    editing = emp.id;
    eName = emp.full_name ?? ''; eDept = emp.department ?? '';
    eTeam = emp.team ?? ''; eRole = emp.role; eCode = emp.employee_code ?? '';
  }

  async function saveEdit(id: string) {
    rowBusy = id; error = '';
    try {
      await api.updateEmployee(id, {
        full_name: eName.trim(), department: eDept.trim(),
        team: eTeam.trim(), role: eRole,
        // Only an admin can set this — employees cannot relabel themselves.
        employee_code: eCode.trim(),
      });
      editing = null;
      await load();
    } catch (e: any) { error = e.message; }
    finally { rowBusy = null; }
  }

  async function resetPassword(emp: Employee) {
    rowBusy = emp.id; error = '';
    try {
      const r = await api.resetEmployeePassword(emp.id);
      issued = { name: emp.full_name ?? emp.email, email: emp.email, password: r.initial_password };
      await load();
    } catch (e: any) { error = e.message; }
    finally { rowBusy = null; }
  }

  async function toggleActive(emp: Employee) {
    rowBusy = emp.id; error = '';
    try {
      if (emp.is_active) await api.deactivateEmployee(emp.id);
      else await api.updateEmployee(emp.id, { is_active: true });
      await load();
    } catch (e: any) { error = e.message; }
    finally { rowBusy = null; }
  }

  function toggleReveal(id: string) {
    // Reassigned rather than mutated so Svelte picks the change up.
    const next = new Set(revealed);
    next.has(id) ? next.delete(id) : next.add(id);
    revealed = next;
  }

  async function copy(text: string) {
    try { await navigator.clipboard.writeText(text); } catch { /* clipboard blocked — the value is on screen anyway */ }
  }

  function roleLabel(role: string): string {
    return ROLES.find((r) => r.value === role)?.label ?? role;
  }

  // Summary tiles: counted from the rows currently on screen (after filters).
  $: rows = roster?.employees ?? [];
  $: activeCount = rows.filter((e) => e.is_active && !e.must_change_password).length;
  $: pendingCount = rows.filter((e) => e.is_active && e.must_change_password).length;
  $: offCount = rows.filter((e) => !e.is_active).length;

  // Column sorting. Each table keeps its own state.
  const ROLE_RANK: Record<string, number> = { learner: 0, ld_lead: 1, admin: 2 };
  const statusRank = (e: Employee) => (!e.is_active ? 2 : e.must_change_password ? 1 : 0);
  const EMP_SORT: SortAccessors<Employee> = {
    name: (e) => e.full_name || e.email,
    code: (e) => e.employee_code,
    dept: (e) => e.department,
    team: (e) => e.team,
    role: (e) => ROLE_RANK[e.role] ?? 3,
    status: statusRank,
  };
  type RowError = BulkUploadError['errors'][number];
  const ERR_SORT: SortAccessors<RowError> = { row: (r) => r.row, email: (r) => r.email, error: (r) => r.error };
  const CREATED_SORT: SortAccessors<BulkUploadRow> = {
    code: (r) => r.employee_code, name: (r) => r.full_name, email: (r) => r.email,
  };
  let empSort = NO_SORT;
  let errSort = NO_SORT;
  let createdSort = NO_SORT;
  $: sortedEmployees = sortRows(rows, empSort, EMP_SORT);
  $: sortedErrors = sortRows(bulkRowErrors, errSort, ERR_SORT);
  $: sortedCreated = sortRows(bulkCreated ?? [], createdSort, CREATED_SORT);
</script>

<svelte:head><title>Champ LMS — Employees</title></svelte:head>

<div class="wrap">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Employees' }]} />
  <header class="head">
    <div>
      <h1 class="ui-rise" style="--i:1">
        Employees
        <span class="title-mark" aria-hidden="true"><Icon name="users" size={24} /></span>
      </h1>
      <p class="sub ui-rise" style="--i:2">
        Accounts are created here — there is no public sign-up. Each new account
        starts with a generated password the employee is asked to change on first
        login.
      </p>
    </div>
    <div class="head-actions ui-rise" style="--i:3">
      <button class="btn" class:on={showBulk} on:click={() => { showBulk = !showBulk; if (!showBulk) resetBulk(); }}>
        <Icon name={showBulk ? 'close' : 'upload'} size={16} />
        {showBulk ? 'Close bulk upload' : 'Bulk upload'}
      </button>
      <button class="btn primary" on:click={() => { showCreate = !showCreate; createError = ''; }}>
        <span class="swap" class:turned={showCreate}><Icon name="plus" size={16} /></span>
        {showCreate ? 'Cancel' : 'Add employee'}
      </button>
    </div>
  </header>

  <section class="tiles" aria-label="Roster summary">
    <div class="tile sky ui-rise" style="--i:3">
      <span class="t-ico"><Icon name="users" size={18} /></span>
      <b use:countUp={roster?.total ?? 0}></b><span>Accounts</span>
    </div>
    <div class="tile mint ui-rise" style="--i:4">
      <span class="t-ico"><Icon name="checkCircle" size={18} /></span>
      <b use:countUp={activeCount}></b><span>Active</span>
    </div>
    <div class="tile butter ui-rise" style="--i:5">
      <span class="t-ico"><Icon name="key" size={18} /></span>
      <b use:countUp={pendingCount}></b><span>Password not changed</span>
    </div>
    <div class="tile peach ui-rise" style="--i:6">
      <span class="t-ico"><Icon name="lock" size={18} /></span>
      <b use:countUp={offCount}></b><span>Deactivated</span>
    </div>
  </section>

  {#if showBulk}
    <div class="card pop-in">
      <div class="card-head">
        <span class="c-ico lilac"><Icon name="upload" size={20} /></span>
        <div>
          <h2>Bulk upload from the master tracker</h2>
          <p class="sub">
            Upload the tracker as CSV or Excel (.xlsx). It needs columns for
            <b>employee ID</b>, <b>employee name</b> and <b>official email ID</b>;
            department, team and role are optional. Headings are matched loosely, so
            the usual tracker column names work as they are.
          </p>
        </div>
      </div>

      <div class="bulk-controls">
        <label class="drop" class:has={bulkFile}>
          <span class="d-ico"><Icon name={bulkFile ? 'file' : 'upload'} size={22} /></span>
          <span class="d-txt">
            {#if bulkFile}<b>{bulkFile.name}</b><small>Click to choose a different file</small>
            {:else}<b>Choose a CSV or Excel file</b><small>.csv, .xlsx or .xlsm</small>{/if}
          </span>
          <input
            type="file"
            accept=".csv,.xlsx,.xlsm,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            bind:this={bulkInput}
            on:change={pickBulkFile}
          />
        </label>
        <button class="btn" on:click={downloadTemplate}><Icon name="download" size={16} /> Download template</button>
      </div>

      <div class="bulk-actions">
        <button class="btn" disabled={bulkBusy || !bulkFile} on:click={() => runBulk(true)}>
          <Icon name="shield" size={16} /> {bulkBusy ? 'Working…' : 'Validate file'}
        </button>
        <button class="btn primary" disabled={bulkBusy || !bulkFile} on:click={() => runBulk(false)}>
          <Icon name="users" size={16} /> {bulkBusy ? 'Working…' : 'Create accounts'}
        </button>
        {#if bulkFile || bulkCreated?.length || bulkRowErrors.length}
          <button class="btn ghost" disabled={bulkBusy} on:click={resetBulk}>Clear</button>
        {/if}
      </div>

      {#if bulkError}<p class="error pop-in"><Icon name="alert" size={16} /> {bulkError}</p>{/if}

      {#if bulkRowErrors.length}
        <!-- Nothing was created: the import is all-or-nothing, so a half-imported
             tracker can never leave the roster in a state nobody can reason about. -->
        <div class="row-errors pop-in">
          <p class="error"><b>Nothing was created.</b> Fix these rows and upload again.</p>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th aria-sort={ariaSort(errSort, 'row')}><SortHeader field="row" bind:sort={errSort}>Row</SortHeader></th>
                  <th aria-sort={ariaSort(errSort, 'email')}><SortHeader field="email" bind:sort={errSort}>Email</SortHeader></th>
                  <th aria-sort={ariaSort(errSort, 'error')}><SortHeader field="error" bind:sort={errSort}>Problem</SortHeader></th>
                </tr>
              </thead>
              <tbody>
                {#each sortedErrors as re}
                  <tr><td>{re.row}</td><td>{re.email ?? '—'}</td><td>{re.error}</td></tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      {/if}

      {#if bulkPreview}
        <p class="ok pop-in">
          <Icon name="checkCircle" size={17} />
          <span>File is valid — <b>{bulkPreview.would_create}</b> account{bulkPreview.would_create === 1 ? '' : 's'}
          ready to create. Nothing has been created yet; choose “Create accounts” to go ahead.</span>
        </p>
      {/if}

      {#if bulkCreated?.length}
        <div class="created pop-in">
          <div class="created-head">
            <span class="ui-pill mint"><Icon name="check" size={14} /> {bulkCreated.length} account{bulkCreated.length === 1 ? '' : 's'} created</span>
            <button class="btn small" on:click={copyCreated}><Icon name="copy" size={14} /> Copy all with passwords</button>
          </div>
          <p class="sub">Share each password with its owner. They stay readable in the table below.</p>
          <div class="table-scroll">
            <table>
              <thead>
                <tr>
                  <th aria-sort={ariaSort(createdSort, 'code')}><SortHeader field="code" bind:sort={createdSort}>Employee ID</SortHeader></th>
                  <th aria-sort={ariaSort(createdSort, 'name')}><SortHeader field="name" bind:sort={createdSort}>Name</SortHeader></th>
                  <th aria-sort={ariaSort(createdSort, 'email')}><SortHeader field="email" bind:sort={createdSort}>Email</SortHeader></th>
                  <th>Password</th>
                </tr>
              </thead>
              <tbody>
                {#each sortedCreated as r}
                  <tr>
                    <td>{r.employee_code ?? '—'}</td>
                    <td>{r.full_name ?? '—'}</td>
                    <td>{r.email}</td>
                    <td><code>{r.initial_password}</code></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      {/if}
    </div>
  {/if}

  {#if issued}
    <div class="issued pop-in">
      <span class="c-ico butter"><Icon name="key" size={20} /></span>
      <div class="issued-body">
        <b>Password for {issued.name}</b>
        <p>Share this with them. It stays visible in the table below.</p>
        <code>{issued.password}</code>
      </div>
      <div class="issued-actions">
        <button class="btn" on:click={() => copy(issued?.password ?? '')}><Icon name="copy" size={15} /> Copy</button>
        <button class="btn ghost" on:click={() => (issued = null)}>Dismiss</button>
      </div>
    </div>
  {/if}

  {#if showCreate}
    <div class="card pop-in">
      <div class="card-head">
        <span class="c-ico mint"><Icon name="user" size={20} /></span>
        <div><h2>New employee</h2><p class="sub">A starting password is generated when you create the account.</p></div>
      </div>
      <div class="grid">
        <label>Employee code<input bind:value={cCode} placeholder="CHMP-0001" /></label>
        <label>Full name<input bind:value={cName} placeholder="Jane Doe" /></label>
        <label>Email<input type="email" bind:value={cEmail} placeholder="jane@championsmail.com" /></label>
        <label>Department<input bind:value={cDept} placeholder="Sales" /></label>
        <label>Team<input bind:value={cTeam} placeholder="Enterprise West" /></label>
        <!-- svelte-ignore a11y-label-has-associated-control -->
        <label>
          Privileges
          <Select bind:value={cRole} options={ROLES} />
        </label>
      </div>
      {#if createError}<p class="error pop-in"><Icon name="alert" size={16} /> {createError}</p>{/if}
      <button class="btn primary" disabled={creating} on:click={create}>
        <Icon name="check" size={16} /> {creating ? 'Creating…' : 'Create account'}
      </button>
    </div>
  {/if}

  <div class="filters ui-rise" style="--i:7">
    <label class="search">
      <Icon name="search" size={18} />
      <input placeholder="Search name or email…" bind:value={q} on:input={load} aria-label="Search name or email" />
    </label>
    <Select class="filter" shape="pill" bind:value={filterDept} on:change={load} ariaLabel="Department"
      options={allOf('All departments', roster?.departments)} />
    <Select class="filter" shape="pill" bind:value={filterTeam} on:change={load} ariaLabel="Team"
      options={allOf('All teams', roster?.teams)} />
    <Select class="filter" shape="pill" bind:value={filterRole} on:change={load} ariaLabel="Role"
      options={ROLE_FILTERS} />
  </div>

  {#if error}<p class="error pop-in"><Icon name="alert" size={16} /> {error}</p>{/if}

  {#if loading && !roster}
    <div class="sk">
      {#each Array(6) as _, i}<div class="ui-skeleton" style="height:58px;border-radius:16px;opacity:{1 - i * 0.12}"></div>{/each}
    </div>
  {:else if !roster || roster.employees.length === 0}
    <div class="empty ui-rise">
      <span class="e-ico"><Icon name="users" size={26} /></span>
      <h3>No employees match</h3>
      <p>Change the filters, or add one to get started.</p>
    </div>
  {:else}
    <p class="count">
      <span class="ui-pill sky">{roster.total} account{roster.total === 1 ? '' : 's'}</span>
      {#if loading}<span class="spin" aria-label="Refreshing"></span>{/if}
    </p>
    <div class="table-scroll main-table ui-rise" style="--i:8">
      <table>
        <thead>
          <tr>
            <th aria-sort={ariaSort(empSort, 'name')}><SortHeader field="name" bind:sort={empSort}>Employee</SortHeader></th>
            <th aria-sort={ariaSort(empSort, 'code')}><SortHeader field="code" bind:sort={empSort}>Employee code</SortHeader></th>
            <th aria-sort={ariaSort(empSort, 'dept')}><SortHeader field="dept" bind:sort={empSort}>Department</SortHeader></th>
            <th aria-sort={ariaSort(empSort, 'team')}><SortHeader field="team" bind:sort={empSort}>Team</SortHeader></th>
            <th aria-sort={ariaSort(empSort, 'role')}><SortHeader field="role" bind:sort={empSort}>Privileges</SortHeader></th>
            <th>Password</th>
            <th aria-sort={ariaSort(empSort, 'status')}><SortHeader field="status" bind:sort={empSort}>Status</SortHeader></th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each sortedEmployees as emp (emp.id)}
            <tr class:inactive={!emp.is_active} class:editing={editing === emp.id}>
              {#if editing === emp.id}
                <td><input bind:value={eName} /><div class="email">{emp.email}</div></td>
                <td><input bind:value={eCode} placeholder="CHMP-0001" /></td>
                <td><input bind:value={eDept} /></td>
                <td><input bind:value={eTeam} /></td>
                <td>
                  <Select bind:value={eRole} size="sm" ariaLabel="Role" options={ROLES} />
                </td>
                <td colspan="2" class="muted">Save to apply changes.</td>
                <td class="actions">
                  <button class="btn small primary" disabled={rowBusy === emp.id} on:click={() => saveEdit(emp.id)}><Icon name="save" size={14} /> Save</button>
                  <button class="btn small ghost" on:click={() => (editing = null)}>Cancel</button>
                </td>
              {:else}
                <td>
                  <div class="person">
                    <span class="av"><Avatar src={emp.avatar_url} name={emp.full_name} size={36} /></span>
                    <div>
                      <div class="name">{emp.full_name ?? '—'}</div>
                      <div class="email">{emp.email}</div>
                    </div>
                  </div>
                </td>
                <td>
                  {#if emp.employee_code}
                    <code class="code">{emp.employee_code}</code>
                  {:else}
                    <span class="muted">Not set</span>
                  {/if}
                </td>
                <td>{emp.department ?? '—'}</td>
                <td>{emp.team ?? '—'}</td>
                <td><span class="role" class:admin={emp.role !== 'learner'}>{roleLabel(emp.role)}</span></td>
                <td class="pw">
                  {#if emp.password_available === false}
                    <span class="muted">Unreadable — reset it</span>
                  {:else if revealed.has(emp.id)}
                    <code class="reveal">{emp.current_password}</code>
                    <button class="icon-btn" title="Copy" aria-label="Copy password" on:click={() => copy(emp.current_password ?? '')}><Icon name="copy" size={15} /></button>
                    <button class="icon-btn" title="Hide" aria-label="Hide password" on:click={() => toggleReveal(emp.id)}><Icon name="eyeOff" size={15} /></button>
                  {:else}
                    <code class="dots">••••••••</code>
                    <button class="icon-btn" title="Show" aria-label="Show password" on:click={() => toggleReveal(emp.id)}><Icon name="eye" size={15} /></button>
                  {/if}
                </td>
                <td>
                  {#if !emp.is_active}
                    <span class="tag off">Deactivated</span>
                  {:else if emp.must_change_password}
                    <span class="tag warn"><span class="dot"></span>Password not changed yet</span>
                  {:else}
                    <span class="tag ok"><span class="dot"></span>Active</span>
                  {/if}
                </td>
                <td class="actions">
                  <button class="btn small ghost" on:click={() => startEdit(emp)}><Icon name="edit" size={14} /> Edit</button>
                  <button class="btn small ghost" disabled={rowBusy === emp.id} on:click={() => resetPassword(emp)}><Icon name="refresh" size={14} /> Reset password</button>
                  <button class="btn small ghost" class:danger={emp.is_active} disabled={rowBusy === emp.id} on:click={() => toggleActive(emp)}>
                    <Icon name={emp.is_active ? 'lock' : 'unlock'} size={14} /> {emp.is_active ? 'Deactivate' : 'Reactivate'}
                  </button>
                </td>
              {/if}
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  /* ---------- header ---------- */
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 1.25rem; margin: 0 0 1.25rem; flex-wrap: wrap; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; display: flex; align-items: center; gap: 0.6rem; margin: 0 0 0.6rem; }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-sky); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  h2 { font-size: 1.15rem; letter-spacing: -0.015em; margin: 0 0 0.3rem; }
  .sub { color: var(--muted); font-size: 0.9rem; line-height: 1.5; max-width: 62ch; margin: 0; }
  .head-actions { display: flex; gap: 0.6rem; flex-wrap: wrap; }

  /* ---------- tiles ---------- */
  .tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.9rem; margin-bottom: 1.75rem; }
  .tile {
    display: flex; flex-direction: column; gap: 0.1rem; padding: 1rem 1.1rem; border-radius: 24px; color: var(--tile-ink);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .tile:hover { translate: 0 -3px; box-shadow: var(--shadow); }
  .tile b { font-size: clamp(1.5rem, 1.1rem + 1vw, 2rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.1; margin-top: 0.55rem; font-variant-numeric: tabular-nums; }
  .tile:hover b { animation: pop 420ms var(--ease-out); }
  .tile > span:last-child { font-size: 0.8rem; opacity: 0.72; font-weight: 500; }
  .t-ico { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-inner); transition: transform var(--dur-3) var(--ease-out); }
  .tile:hover .t-ico { transform: rotate(-14deg) scale(1.1); }
  .sky { background: var(--tile-sky); } .mint { background: var(--tile-mint); }
  .butter { background: var(--tile-butter); } .peach { background: var(--tile-peach); } .lilac { background: var(--tile-lilac); }

  /* ---------- cards ---------- */
  .card, .issued {
    background: var(--surface); border-radius: 28px; padding: 1.4rem; margin-bottom: 1.5rem; box-shadow: var(--shadow-sm);
  }
  .card-head { display: flex; gap: 0.9rem; align-items: flex-start; margin-bottom: 1.1rem; }
  .c-ico { flex: none; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; color: var(--tile-ink); animation: pop 500ms var(--ease-out) 120ms backwards; }
  .pop-in { animation: modal-in 380ms var(--ease-out) backwards; }
  .issued { display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; background: var(--tile-butter); color: var(--tile-ink); }
  .issued-body { flex: 1; min-width: 220px; }
  .issued p { opacity: 0.72; font-size: 0.84rem; margin: 0.2rem 0 0.55rem; }
  .issued code { font-size: 1.08rem; letter-spacing: 0.06em; background: var(--tile-inner); padding: 0.35rem 0.7rem; }
  .issued .c-ico { background: var(--tile-inner); }
  .issued-actions { display: flex; gap: 0.5rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 1rem; margin-bottom: 1.1rem; }
  label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.82rem; font-weight: 500; color: var(--muted); }
  input {
    background: var(--surface2); border: 1px solid transparent; color: var(--text);
    border-radius: 14px; padding: 0.62rem 0.85rem; font-size: 0.9rem; outline: none; width: 100%;
    transition: background-color var(--dur-2) var(--ease-out), border-color var(--dur-2), box-shadow var(--dur-2);
  }
  input:focus { background: var(--surface); border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent); }

  /* ---------- bulk ---------- */
  .bulk-controls { display: flex; gap: 0.75rem; align-items: stretch; flex-wrap: wrap; margin: 0 0 0.9rem; }
  .drop {
    position: relative; flex: 1 1 300px; flex-direction: row; align-items: center; gap: 0.85rem;
    padding: 0.85rem 1rem; border-radius: 20px; border: 2px dashed var(--border); background: var(--surface2); cursor: pointer;
    color: var(--text); transition: border-color var(--dur-2), background-color var(--dur-2), translate var(--dur-3) var(--ease-out);
  }
  .drop:hover { border-color: var(--accent); translate: 0 -2px; }
  .drop.has { border-style: solid; border-color: color-mix(in srgb, var(--success) 50%, transparent); }
  .drop input { position: absolute; inset: 0; opacity: 0; cursor: pointer; padding: 0; }
  .d-ico { width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-lilac); color: var(--tile-ink); transition: transform var(--dur-3) var(--ease-out); }
  .drop:hover .d-ico { transform: translateY(-3px); }
  .d-txt { display: flex; flex-direction: column; min-width: 0; }
  .d-txt b { font-size: 0.92rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .d-txt small { color: var(--muted); font-size: 0.76rem; }
  .bulk-actions { display: flex; gap: 0.6rem; flex-wrap: wrap; margin-bottom: 0.5rem; }
  .row-errors { margin-top: 1rem; }
  .row-errors table { min-width: 480px; }
  .created { margin-top: 1.25rem; }
  .created-head { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.4rem; }
  .created table { min-width: 620px; }
  .ok { display: flex; gap: 0.55rem; align-items: flex-start; color: var(--text); background: var(--tile-mint); padding: 0.8rem 1rem; border-radius: 16px; font-size: 0.86rem; margin-top: 0.85rem; }
  .ok :global(.icon) { color: var(--success); flex: none; margin-top: 1px; }

  /* ---------- filters ---------- */
  .filters { display: flex; gap: 0.6rem; margin-bottom: 1rem; flex-wrap: wrap; }
  .search {
    flex: 1 1 260px; flex-direction: row; align-items: center; gap: 0.55rem; padding: 0 1rem; height: 48px;
    background: var(--surface2); border-radius: 999px; color: var(--muted); transition: background-color var(--dur-2), box-shadow var(--dur-2);
  }
  .search:focus-within { background: var(--surface); box-shadow: 0 0 0 2px var(--accent), var(--shadow-sm); }
  .search input { background: none; border: none; padding: 0; height: 100%; box-shadow: none; }
  .search input:focus { box-shadow: none; background: none; }
  .filters :global(.filter) { flex: 0 1 190px; width: auto; }
  .filters :global(.filter .trigger) { height: 48px; }
  .count { display: flex; align-items: center; gap: 0.6rem; margin: 0 0 0.6rem; }
  .spin { width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--surface3); border-top-color: var(--accent); animation: spin 700ms linear infinite; }
  @keyframes spin { to { rotate: 360deg; } }
  .sk { display: flex; flex-direction: column; gap: 0.5rem; }

  /* ---------- table ---------- */
  /* Wide table scrolls inside its own container so the page never scrolls sideways. */
  .table-scroll { overflow-x: auto; background: var(--surface); border-radius: 24px; box-shadow: var(--shadow-sm); }
  .card .table-scroll { background: var(--surface2); box-shadow: none; border-radius: 18px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.87rem; min-width: 1080px; }
  th, td { text-align: left; padding: 0.75rem 0.9rem; border-bottom: 1px solid var(--border); vertical-align: middle; }
  th { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; background: color-mix(in srgb, var(--surface2) 60%, transparent); }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr { transition: background-color var(--dur-2) var(--ease-out); }
  tbody tr:hover { background: var(--surface2); }
  tr.inactive { opacity: 0.55; }
  tr.editing { background: color-mix(in srgb, var(--tile-lilac) 45%, transparent); }
  tr.editing input { background: var(--surface); }
  tr.editing :global(.trigger) { background: var(--surface); }
  .name { font-weight: 600; }
  .person { display: flex; align-items: center; gap: 0.7rem; }
  .av { display: inline-flex; border-radius: 50%; transition: transform var(--dur-3) var(--ease-out); }
  tbody tr:hover .av { transform: scale(1.08) rotate(-4deg); }
  .email { color: var(--muted); font-size: 0.78rem; }
  code { background: var(--surface2); padding: 0.22rem 0.5rem; border-radius: 8px; font-family: ui-monospace, monospace; font-size: 0.84rem; }
  tbody tr:hover code { background: var(--surface3); }
  .code { font-weight: 600; letter-spacing: 0.03em; }
  .reveal { animation: pop 300ms var(--ease-out); }
  .dots { letter-spacing: 0.1em; color: var(--muted); }
  .pw { white-space: nowrap; }
  .icon-btn {
    display: inline-grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; margin-left: 0.2rem; vertical-align: middle;
    color: var(--muted); background: transparent; transition: background-color var(--dur-2), color var(--dur-2), transform var(--dur-3) var(--ease-out);
  }
  .icon-btn:hover { background: var(--surface3); color: var(--text); transform: scale(1.1); }
  .role { font-size: 0.78rem; font-weight: 600; padding: 0.22rem 0.6rem; border-radius: 999px; background: var(--surface2); white-space: nowrap; }
  .role.admin { background: var(--tile-lilac); color: var(--tile-ink); }
  .tag { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.74rem; font-weight: 600; padding: 0.24rem 0.65rem; border-radius: 999px; white-space: nowrap; }
  .tag .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .tag.ok { background: var(--tile-mint); color: var(--tile-ink); }
  .tag.ok .dot { background: var(--success); animation: pulse-ring 2s var(--ease-out) infinite; }
  .tag.warn { background: var(--tile-butter); color: var(--tile-ink); }
  .tag.warn .dot { background: var(--warn); }
  .tag.off { background: var(--surface2); color: var(--muted); }
  .actions { display: flex; gap: 0.35rem; flex-wrap: wrap; }

  /* ---------- buttons ---------- */
  .btn {
    display: inline-flex; align-items: center; gap: 0.45rem;
    border: none; background: var(--surface2); color: var(--text); border-radius: 999px;
    padding: 0.6rem 1.05rem; font-size: 0.86rem; font-weight: 600; cursor: pointer;
    transition: background-color var(--dur-2), translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .btn:hover:not(:disabled) { background: var(--surface3); translate: 0 -1px; }
  .btn.on { background: var(--tile-lilac); color: var(--tile-ink); }
  .btn.primary { background: var(--accent); color: var(--on-accent); }
  .btn.primary:hover:not(:disabled) { background: var(--accent-hover); box-shadow: var(--shadow); }
  .btn.ghost { background: transparent; }
  .btn.ghost:hover:not(:disabled) { background: var(--surface2); }
  .btn.small { padding: 0.36rem 0.7rem; font-size: 0.77rem; gap: 0.3rem; }
  .btn.danger:hover:not(:disabled) { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn :global(.icon) { transition: transform var(--dur-3) var(--ease-out); }
  .btn:hover:not(:disabled) :global(.icon) { transform: rotate(-10deg) scale(1.1); }
  .swap { display: inline-flex; transition: rotate var(--dur-3) var(--ease-out); }
  .swap.turned { rotate: 45deg; }

  .error { display: flex; align-items: center; gap: 0.45rem; color: var(--danger); font-size: 0.86rem; }
  .muted { color: var(--muted); font-size: 0.85rem; }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 0.4rem; text-align: center; padding: 2.75rem 1rem; border-radius: 28px; background: var(--surface); }
  .empty h3 { font-size: 1.2rem; }
  .empty p { color: var(--muted); font-size: 0.9rem; }
  .e-ico { width: 60px; height: 60px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); margin-bottom: 0.4rem; animation: pop 520ms var(--ease-out); }

  @media (max-width: 900px) {
    .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 760px) {
    .filters :global(.filter) { flex: 1 1 140px; }
    .card, .issued { padding: 1.1rem; border-radius: 24px; }
    .head-actions { width: 100%; }
    .head-actions .btn { flex: 1; justify-content: center; }
  }
</style>
