<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type Employee, type EmployeeRoster } from '$lib/api/client';

  const ROLES = [
    { value: 'learner', label: 'Learner' },
    { value: 'ld_lead', label: 'L&D Lead (admin access)' },
    { value: 'admin', label: 'Admin' },
  ];

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
  let eName = '', eDept = '', eTeam = '', eRole = '';
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
        department: cDept.trim() || undefined,
        team: cTeam.trim() || undefined,
        role: cRole,
      });
      issued = { name: emp.full_name ?? emp.email, email: emp.email, password: emp.initial_password };
      cEmail = cName = cDept = cTeam = ''; cRole = 'learner';
      showCreate = false;
      await load();
    } catch (e: any) { createError = e.message; }
    finally { creating = false; }
  }

  function startEdit(emp: Employee) {
    editing = emp.id;
    eName = emp.full_name ?? ''; eDept = emp.department ?? '';
    eTeam = emp.team ?? ''; eRole = emp.role;
  }

  async function saveEdit(id: string) {
    rowBusy = id; error = '';
    try {
      await api.updateEmployee(id, {
        full_name: eName.trim(), department: eDept.trim(),
        team: eTeam.trim(), role: eRole,
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
</script>

<svelte:head><title>Champ LMS — Employees</title></svelte:head>

<div class="wrap">
  <header class="head">
    <div>
      <h1>Employees</h1>
      <p class="sub">
        Accounts are created here — there is no public sign-up. Each new account
        starts with a generated password the employee is asked to change on first
        sign-in.
      </p>
    </div>
    <button class="btn primary" on:click={() => { showCreate = !showCreate; createError = ''; }}>
      {showCreate ? 'Cancel' : '+ Add employee'}
    </button>
  </header>

  {#if issued}
    <div class="issued">
      <div>
        <b>Password for {issued.name}</b>
        <p>Share this with them. It stays visible in the table below.</p>
        <code>{issued.password}</code>
      </div>
      <div class="issued-actions">
        <button class="btn ghost" on:click={() => copy(issued?.password ?? '')}>Copy</button>
        <button class="btn ghost" on:click={() => (issued = null)}>Dismiss</button>
      </div>
    </div>
  {/if}

  {#if showCreate}
    <div class="card">
      <h2>New employee</h2>
      <div class="grid">
        <label>Full name<input bind:value={cName} placeholder="Jane Doe" /></label>
        <label>Email<input type="email" bind:value={cEmail} placeholder="jane@championsmail.com" /></label>
        <label>Department<input bind:value={cDept} placeholder="Sales" /></label>
        <label>Team<input bind:value={cTeam} placeholder="Enterprise West" /></label>
        <label>
          Privileges
          <select bind:value={cRole}>
            {#each ROLES as r}<option value={r.value}>{r.label}</option>{/each}
          </select>
        </label>
      </div>
      {#if createError}<p class="error">{createError}</p>{/if}
      <button class="btn primary" disabled={creating} on:click={create}>
        {creating ? 'Creating…' : 'Create account'}
      </button>
    </div>
  {/if}

  <div class="filters">
    <input placeholder="Search name or email…" bind:value={q} on:input={load} />
    <select bind:value={filterDept} on:change={load}>
      <option value="">All departments</option>
      {#each roster?.departments ?? [] as d}<option value={d}>{d}</option>{/each}
    </select>
    <select bind:value={filterTeam} on:change={load}>
      <option value="">All teams</option>
      {#each roster?.teams ?? [] as t}<option value={t}>{t}</option>{/each}
    </select>
    <select bind:value={filterRole} on:change={load}>
      <option value="">All roles</option>
      {#each ROLES as r}<option value={r.value}>{r.label}</option>{/each}
    </select>
  </div>

  {#if error}<p class="error">{error}</p>{/if}

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if !roster || roster.employees.length === 0}
    <p class="muted">No employees match. Add one to get started.</p>
  {:else}
    <p class="count">{roster.total} account{roster.total === 1 ? '' : 's'}</p>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Name</th><th>Department</th><th>Team</th><th>Privileges</th>
            <th>Password</th><th>Status</th><th></th>
          </tr>
        </thead>
        <tbody>
          {#each roster.employees as emp (emp.id)}
            <tr class:inactive={!emp.is_active}>
              {#if editing === emp.id}
                <td><input bind:value={eName} /><div class="email">{emp.email}</div></td>
                <td><input bind:value={eDept} /></td>
                <td><input bind:value={eTeam} /></td>
                <td>
                  <select bind:value={eRole}>
                    {#each ROLES as r}<option value={r.value}>{r.label}</option>{/each}
                  </select>
                </td>
                <td colspan="2" class="muted">Save to apply changes.</td>
                <td class="actions">
                  <button class="btn small primary" disabled={rowBusy === emp.id} on:click={() => saveEdit(emp.id)}>Save</button>
                  <button class="btn small ghost" on:click={() => (editing = null)}>Cancel</button>
                </td>
              {:else}
                <td>
                  <div class="name">{emp.full_name ?? '—'}</div>
                  <div class="email">{emp.email}</div>
                </td>
                <td>{emp.department ?? '—'}</td>
                <td>{emp.team ?? '—'}</td>
                <td>{roleLabel(emp.role)}</td>
                <td class="pw">
                  {#if emp.password_available === false}
                    <span class="muted">Unreadable — reset it</span>
                  {:else if revealed.has(emp.id)}
                    <code>{emp.current_password}</code>
                    <button class="link" on:click={() => copy(emp.current_password ?? '')}>Copy</button>
                    <button class="link" on:click={() => toggleReveal(emp.id)}>Hide</button>
                  {:else}
                    <code>••••••••</code>
                    <button class="link" on:click={() => toggleReveal(emp.id)}>Show</button>
                  {/if}
                </td>
                <td>
                  {#if !emp.is_active}
                    <span class="tag off">Deactivated</span>
                  {:else if emp.must_change_password}
                    <span class="tag warn">Password not changed yet</span>
                  {:else}
                    <span class="tag ok">Active</span>
                  {/if}
                </td>
                <td class="actions">
                  <button class="btn small ghost" on:click={() => startEdit(emp)}>Edit</button>
                  <button class="btn small ghost" disabled={rowBusy === emp.id} on:click={() => resetPassword(emp)}>Reset password</button>
                  <button class="btn small ghost" disabled={rowBusy === emp.id} on:click={() => toggleActive(emp)}>
                    {emp.is_active ? 'Deactivate' : 'Reactivate'}
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
  .wrap { max-width: 1200px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
  .head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
  h1 { font-size: 1.6rem; margin: 0 0 0.35rem; }
  h2 { font-size: 1.05rem; margin: 0 0 1rem; }
  .sub { color: var(--muted); font-size: 0.88rem; max-width: 60ch; margin: 0; }
  .card, .issued {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem;
  }
  .issued { display: flex; justify-content: space-between; gap: 1rem; align-items: center; flex-wrap: wrap; border-color: var(--accent); }
  .issued p { color: var(--muted); font-size: 0.82rem; margin: 0.25rem 0 0.5rem; }
  .issued code { font-size: 1.05rem; letter-spacing: 0.05em; }
  .issued-actions { display: flex; gap: 0.5rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1rem; }
  label { display: flex; flex-direction: column; gap: 0.35rem; font-size: 0.82rem; color: var(--muted); }
  input, select {
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 0.55rem 0.7rem; font-size: 0.9rem; outline: none; width: 100%;
  }
  input:focus, select:focus { border-color: var(--accent); }
  .filters { display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; }
  .filters input { flex: 1 1 220px; }
  .filters select { flex: 0 1 170px; }
  .count { color: var(--muted); font-size: 0.82rem; margin: 0 0 0.5rem; }
  /* Wide table scrolls inside its own container so the page never scrolls sideways. */
  .table-scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.87rem; min-width: 900px; }
  th, td { text-align: left; padding: 0.7rem 0.8rem; border-bottom: 1px solid var(--border); vertical-align: middle; }
  th { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; }
  tbody tr:last-child td { border-bottom: none; }
  tr.inactive { opacity: 0.55; }
  .name { font-weight: 600; }
  .email { color: var(--muted); font-size: 0.78rem; }
  code { background: var(--surface2); padding: 0.2rem 0.45rem; border-radius: 4px; font-family: ui-monospace, monospace; font-size: 0.85rem; }
  .pw { white-space: nowrap; }
  .tag { font-size: 0.72rem; padding: 0.2rem 0.5rem; border-radius: 999px; white-space: nowrap; }
  .tag.ok { background: color-mix(in srgb, green 22%, transparent); }
  .tag.warn { background: color-mix(in srgb, orange 25%, transparent); }
  .tag.off { background: var(--surface2); color: var(--muted); }
  .actions { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .btn { border: 1px solid var(--border); background: var(--surface2); color: var(--text); border-radius: 6px; padding: 0.5rem 0.85rem; font-size: 0.85rem; cursor: pointer; }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
  .btn.ghost { background: transparent; }
  .btn.small { padding: 0.32rem 0.55rem; font-size: 0.78rem; }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .link { background: none; border: none; color: var(--accent); cursor: pointer; font-size: 0.78rem; padding: 0 0.15rem; }
  .error { color: var(--accent); font-size: 0.85rem; }
  .muted { color: var(--muted); font-size: 0.85rem; }
</style>
