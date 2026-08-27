<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api,
    type AccessLevel,
    type AudienceCatalogue,
    type ContentKind,
    type ModuleAccessPeople,
    type ModuleAudienceOut,
  } from '$lib/api/client';

  let catalogue: AudienceCatalogue | null = null;
  let loading = true;
  let error = '';

  // Modules and tests are targeted identically, so one screen serves both and
  // a tab picks which catalogue is on show.
  let tab: ContentKind = 'module';

  // Which item is expanded, and its per-person detail. The kind is tracked
  // alongside the id because the id alone doesn't say which endpoint to call.
  let openId: string | null = null;
  let openKind: ContentKind = 'module';
  let detail: ModuleAccessPeople | null = null;
  let detailLoading = false;

  // Draft audience for the expanded item, applied on Save.
  let draftTeams: string[] = [];
  let draftDepts: string[] = [];
  let draftRoles: string[] = [];
  let draftRequired: string[] = [];
  let saving = false;

  let personFilter = '';
  let rowBusy: string | null = null;

  async function load() {
    loading = true; error = '';
    try {
      catalogue = await api.contentAudiences();
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  }

  onMount(load);

  // The rows for the active tab. `tests` is defaulted because an older API
  // build returns only `modules`.
  $: items = tab === 'test' ? (catalogue?.tests ?? []) : (catalogue?.modules ?? []);

  function switchTab(next: ContentKind) {
    if (tab === next) return;
    tab = next;
    // Collapse — the open row belongs to the tab being left.
    openId = null;
    detail = null;
  }

  async function openItem(m: ModuleAudienceOut) {
    if (openId === m.id) { openId = null; detail = null; return; }
    openId = m.id;
    openKind = m.kind ?? tab;
    detail = null;
    detailLoading = true;
    personFilter = '';
    draftTeams = [...m.audience_teams];
    draftDepts = [...m.audience_departments];
    draftRoles = [...m.target_roles];
    draftRequired = [...m.required_for_teams];
    try {
      detail = await api.contentAccessPeople(openKind, m.id);
    } catch (e: any) { error = e.message; }
    finally { detailLoading = false; }
  }

  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }

  async function saveAudience() {
    if (!openId) return;
    saving = true; error = '';
    try {
      await api.setContentAudience(openKind, openId, {
        audience_teams: draftTeams,
        audience_departments: draftDepts,
        target_roles: draftRoles,
        required_for_teams: draftRequired,
      });
      await load();
      detail = await api.contentAccessPeople(openKind, openId);
    } catch (e: any) { error = e.message; }
    finally { saving = false; }
  }

  async function openToEveryone() {
    draftTeams = []; draftDepts = []; draftRoles = []; draftRequired = [];
    await saveAudience();
  }

  async function setPerson(userId: string, access: AccessLevel) {
    if (!openId) return;
    rowBusy = userId; error = '';
    try {
      await api.setPersonAccess(openKind, openId, userId, access);
      detail = await api.contentAccessPeople(openKind, openId);
    } catch (e: any) { error = e.message; }
    finally { rowBusy = null; }
  }

  // Retakes. Additive: clicking again after the learner burns the grant hands
  // them another. Only meaningful on a capped test.
  async function grantRetake(userId: string) {
    if (!openId || openKind !== 'test') return;
    rowBusy = userId; error = '';
    try {
      await api.grantTestAttempts(openId, userId, 1);
      detail = await api.contentAccessPeople(openKind, openId);
    } catch (e: any) { error = e.message; }
    finally { rowBusy = null; }
  }

  async function clearPerson(userId: string) {
    if (!openId) return;
    rowBusy = userId; error = '';
    try {
      await api.clearPersonAccess(openKind, openId, userId);
      detail = await api.contentAccessPeople(openKind, openId);
    } catch (e: any) { error = e.message; }
    finally { rowBusy = null; }
  }

  $: people = (detail?.people ?? []).filter((p) => {
    const needle = personFilter.trim().toLowerCase();
    if (!needle) return true;
    return (
      (p.full_name ?? '').toLowerCase().includes(needle) ||
      p.email.toLowerCase().includes(needle) ||
      (p.team ?? '').toLowerCase().includes(needle)
    );
  });

  function audienceSummary(m: ModuleAudienceOut): string {
    if (!m.is_restricted) return 'Everyone';
    const parts: string[] = [];
    if (m.audience_teams.length) parts.push(`Teams: ${m.audience_teams.join(', ')}`);
    // A test's legacy single department restricts it just like the list does,
    // so it has to appear here or the row would read "Limited" with no reason.
    const depts = [...m.audience_departments];
    if (m.department && !depts.some((d) => d.toLowerCase() === m.department!.toLowerCase())) {
      depts.push(m.department);
    }
    if (depts.length) parts.push(`Depts: ${depts.join(', ')}`);
    if (m.target_roles.length) parts.push(`Roles: ${m.target_roles.join(', ')}`);
    if (m.required_for_teams.length) parts.push(`Required: ${m.required_for_teams.join(', ')}`);
    return parts.join(' · ');
  }
</script>

<svelte:head><title>Champ LMS — Content Access</title></svelte:head>

<div class="wrap">
  <h1>Content access</h1>
  <p class="sub">
    Project content team-wise, and override it for individuals. Anything with no
    audience is visible to everyone — assigning a team, department or role limits
    it to people who match at least one of them. Per-person rules win over the
    audience, and a revoke always beats a grant. The same rules cover learning
    modules and test series.
  </p>

  {#if error}<p class="error">{error}</p>{/if}

  <div class="tabs" role="tablist">
    <button
      class="tab" class:on={tab === 'module'} role="tab"
      aria-selected={tab === 'module'}
      on:click={() => switchTab('module')}>
      Modules{#if catalogue} <span class="count">{catalogue.modules.length}</span>{/if}
    </button>
    <button
      class="tab" class:on={tab === 'test'} role="tab"
      aria-selected={tab === 'test'}
      on:click={() => switchTab('test')}>
      Test series{#if catalogue} <span class="count">{catalogue.tests?.length ?? 0}</span>{/if}
    </button>
  </div>

  {#if loading}
    <p class="muted">Loading…</p>
  {:else if items.length === 0}
    <p class="muted">
      {#if tab === 'test'}
        No test series yet. Upload a question paper under Test series first.
      {:else}
        No modules yet. Upload content first.
      {/if}
    </p>
  {:else}
    <div class="mod-list">
      {#each items as m (m.id)}
        <div class="mod" class:open={openId === m.id}>
          <button class="mod-head" on:click={() => openItem(m)}>
            <div class="mod-title">
              <b>{m.title}</b>
              {#if !m.is_published}<span class="tag draft">Draft</span>{/if}
              {#if tab === 'test' && m.total_questions !== undefined}
                <span class="tag draft">{m.total_questions} Qs</span>
              {/if}
              {#if m.is_restricted}
                <span class="tag limited">Limited</span>
              {:else}
                <span class="tag open">Everyone</span>
              {/if}
            </div>
            <div class="mod-aud">{audienceSummary(m)}</div>
            <span class="chev">{openId === m.id ? '▲' : '▼'}</span>
          </button>

          {#if openId === m.id}
            <div class="mod-body">
              {#if detailLoading}
                <p class="muted">Loading access…</p>
              {:else}
                <section>
                  <h3>Who is this for?</h3>
                  {#if tab === 'test'}
                    <p class="hint tight">
                      Only people in this audience see the test in their list, and
                      only they can open or submit it.
                    </p>
                  {/if}
                  {#if catalogue.teams.length === 0}
                    <p class="muted">
                      No teams exist yet — set a team on employees first.
                    </p>
                  {:else}
                    <div class="field">
                      <span class="lbl">Teams</span>
                      <div class="chips">
                        {#each catalogue.teams as t}
                          <button class="chip" class:on={draftTeams.includes(t)}
                            on:click={() => (draftTeams = toggle(draftTeams, t))}>{t}</button>
                        {/each}
                      </div>
                    </div>
                  {/if}

                  <div class="field">
                    <span class="lbl">Departments</span>
                    <div class="chips">
                      {#each catalogue.departments as d}
                        <button class="chip" class:on={draftDepts.includes(d)}
                          on:click={() => (draftDepts = toggle(draftDepts, d))}>{d}</button>
                      {/each}
                    </div>
                  </div>

                  <div class="field">
                    <span class="lbl">Roles</span>
                    <div class="chips">
                      {#each catalogue.roles as r}
                        <button class="chip" class:on={draftRoles.includes(r)}
                          on:click={() => (draftRoles = toggle(draftRoles, r))}>{r}</button>
                      {/each}
                    </div>
                  </div>

                  <div class="field">
                    <span class="lbl">Required for</span>
                    <div class="chips">
                      {#each catalogue.teams as t}
                        <button class="chip req" class:on={draftRequired.includes(t)}
                          on:click={() => (draftRequired = toggle(draftRequired, t))}>{t}</button>
                      {/each}
                    </div>
                    <p class="hint">
                      Mandatory for these teams. Being required also grants access.
                    </p>
                  </div>

                  <div class="row-actions">
                    <button class="btn primary" disabled={saving} on:click={saveAudience}>
                      {saving ? 'Saving…' : 'Save audience'}
                    </button>
                    <button class="btn ghost" disabled={saving} on:click={openToEveryone}>
                      Open to everyone
                    </button>
                  </div>
                </section>

                <section>
                  <h3>
                    People
                    {#if detail}
                      <span class="muted"> — {detail.can_access_count} of {detail.people.length} can {tab === 'test' ? 'sit' : 'open'} this</span>
                    {/if}
                  </h3>
                  <input class="search" placeholder="Filter by name, email or team…" bind:value={personFilter} />
                  <div class="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Person</th><th>Team</th><th>Access</th>
                          {#if tab === 'test' && detail?.max_attempts != null}<th>Attempts</th>{/if}
                          <th>Why</th><th>Override</th>
                        </tr>
                      </thead>
                      <tbody>
                        {#each people as p (p.user_id)}
                          <tr class:denied={!p.can_access}>
                            <td>
                              <div class="name">{p.full_name ?? '—'}</div>
                              <div class="email">{p.email}</div>
                            </td>
                            <td>{p.team ?? '—'}</td>
                            <td>
                              {#if p.can_access}
                                <span class="tag open">Can open</span>
                              {:else}
                                <span class="tag no">Blocked</span>
                              {/if}
                              {#if p.required}<span class="tag req-tag">Required</span>{/if}
                            </td>
                            {#if tab === 'test' && detail?.max_attempts != null}
                              <td class="att">
                                {#if p.attempts}
                                  <span class:spent={p.attempts.exhausted}>
                                    {p.attempts.used}/{p.attempts.allowed}
                                  </span>
                                  {#if p.attempts.granted_extra}
                                    <span class="tag req-tag">+{p.attempts.granted_extra}</span>
                                  {/if}
                                {:else}—{/if}
                              </td>
                            {/if}
                            <td class="why">{p.why}</td>
                            <td class="actions">
                              <button class="btn small ghost" class:active={p.rule === 'grant'}
                                disabled={rowBusy === p.user_id}
                                on:click={() => setPerson(p.user_id, 'grant')}>Grant</button>
                              <button class="btn small ghost" class:active={p.rule === 'required'}
                                disabled={rowBusy === p.user_id}
                                on:click={() => setPerson(p.user_id, 'required')}>Require</button>
                              <button class="btn small ghost" class:active={p.rule === 'revoke'}
                                disabled={rowBusy === p.user_id}
                                on:click={() => setPerson(p.user_id, 'revoke')}>Revoke</button>
                              {#if p.rule}
                                <button class="btn small ghost" disabled={rowBusy === p.user_id}
                                  on:click={() => clearPerson(p.user_id)}>Clear</button>
                              {/if}
                              {#if tab === 'test' && detail?.max_attempts != null}
                                <button class="btn small retake" disabled={rowBusy === p.user_id}
                                  title="Give this person one more attempt"
                                  on:click={() => grantRetake(p.user_id)}>+1 retake</button>
                              {/if}
                            </td>
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  </div>
                </section>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .wrap { max-width: 1150px; margin: 0 auto; padding: 2rem 1.25rem 4rem; }
  h1 { font-size: 1.6rem; margin: 0 0 0.35rem; }
  h3 { font-size: 0.95rem; margin: 0 0 0.75rem; }
  .sub { color: var(--muted); font-size: 0.88rem; max-width: 72ch; margin: 0 0 1.5rem; line-height: 1.55; }
  .tabs { display: flex; gap: 0.4rem; margin-bottom: 1.1rem; border-bottom: 1px solid var(--border); }
  .tab {
    background: none; border: none; border-bottom: 2px solid transparent;
    color: var(--muted); font-size: 0.9rem; font-weight: 600;
    padding: 0.55rem 0.85rem; cursor: pointer; margin-bottom: -1px;
  }
  .tab.on { color: var(--text); border-bottom-color: var(--accent); }
  .count {
    background: var(--surface2); border-radius: 999px;
    padding: 0.05rem 0.4rem; font-size: 0.72rem; font-weight: 600;
  }
  .hint.tight { margin: -0.35rem 0 0.9rem; }
  .mod-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .mod { border: 1px solid var(--border); border-radius: 10px; background: var(--surface); overflow: hidden; }
  .mod.open { border-color: var(--accent); }
  .mod-head {
    width: 100%; display: grid; grid-template-columns: 1fr auto auto;
    gap: 1rem; align-items: center; text-align: left;
    padding: 0.9rem 1.1rem; background: none; border: none; color: var(--text); cursor: pointer;
  }
  .mod-title { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
  .mod-aud { color: var(--muted); font-size: 0.78rem; text-align: right; max-width: 45ch; }
  .chev { color: var(--muted); font-size: 0.7rem; }
  .mod-body { padding: 0 1.1rem 1.25rem; display: flex; flex-direction: column; gap: 1.75rem; }
  .field { margin-bottom: 1rem; }
  .lbl { display: block; font-size: 0.78rem; color: var(--muted); margin-bottom: 0.4rem; }
  .chips { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .chip {
    border: 1px solid var(--border); background: var(--surface2); color: var(--text);
    border-radius: 999px; padding: 0.3rem 0.7rem; font-size: 0.8rem; cursor: pointer;
  }
  .chip.on { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
  .chip.req.on { background: color-mix(in srgb, orange 70%, black 10%); border-color: transparent; }
  .hint { color: var(--muted); font-size: 0.75rem; margin: 0.4rem 0 0; }
  .row-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
  .search {
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    border-radius: 6px; padding: 0.5rem 0.7rem; font-size: 0.85rem; width: 100%;
    max-width: 340px; margin-bottom: 0.75rem; outline: none;
  }
  .search:focus { border-color: var(--accent); }
  /* Wide table scrolls in its own box so the page never scrolls sideways. */
  .table-scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; min-width: 760px; }
  th, td { text-align: left; padding: 0.6rem 0.75rem; border-bottom: 1px solid var(--border); vertical-align: middle; }
  th { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; }
  tbody tr:last-child td { border-bottom: none; }
  tr.denied { opacity: 0.6; }
  .name { font-weight: 600; }
  .email { color: var(--muted); font-size: 0.75rem; }
  .why { color: var(--muted); font-size: 0.78rem; }
  .tag { font-size: 0.7rem; padding: 0.15rem 0.45rem; border-radius: 999px; white-space: nowrap; }
  .tag.open { background: color-mix(in srgb, green 22%, transparent); }
  .tag.no { background: color-mix(in srgb, red 22%, transparent); }
  .tag.limited { background: color-mix(in srgb, orange 25%, transparent); }
  .tag.req-tag { background: color-mix(in srgb, orange 30%, transparent); margin-left: 0.3rem; }
  .tag.draft { background: var(--surface2); color: var(--muted); }
  .actions { display: flex; gap: 0.3rem; flex-wrap: wrap; }
  .att { white-space: nowrap; font-variant-numeric: tabular-nums; }
  .att .spent { color: var(--accent); font-weight: 600; }
  .btn.retake { border-color: color-mix(in srgb, orange 55%, transparent); }
  .btn {
    border: 1px solid var(--border); background: var(--surface2); color: var(--text);
    border-radius: 6px; padding: 0.5rem 0.85rem; font-size: 0.85rem; cursor: pointer;
  }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
  .btn.ghost { background: transparent; }
  .btn.small { padding: 0.28rem 0.5rem; font-size: 0.75rem; }
  .btn.active { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .error { color: var(--accent); font-size: 0.85rem; }
  .muted { color: var(--muted); font-size: 0.85rem; font-weight: 400; }
</style>
