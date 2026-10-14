<script lang="ts">
  import { onMount } from 'svelte';
  import {
    api,
    type AccessLevel,
    type AccessPerson,
    type AudienceCatalogue,
    type ContentKind,
    type ModuleAccessPeople,
    type ModuleAudienceOut,
  } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import { countUp } from '$lib/actions/motion';
  import SortHeader from '$lib/components/SortHeader.svelte';
  import { ariaSort, sortRows, NO_SORT, type SortAccessors } from '$lib/utils/table-sort';

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

  // Clearing the whole audience takes a second click: it changes who can see
  // the item for every learner at once.
  let confirmOpenAll = false;
  async function openToEveryone() {
    if (!confirmOpenAll) { confirmOpenAll = true; return; }
    confirmOpenAll = false;
    draftTeams = []; draftDepts = []; draftRoles = []; draftRequired = [];
    await saveAudience();
  }

  // A row action can change the column the table is sorted by, which would move
  // the row under the admin's pointer and land their next click on someone
  // else. So after an action the current order is kept until they re-sort,
  // filter or open another item.
  let frozenOrder: string[] | null = null;
  const freezeOrder = () => (frozenOrder = people.map((p) => p.user_id));
  $: { peopleSort; personFilter; openId; frozenOrder = null; confirmOpenAll = false; }
  function keepOrder(rows: AccessPerson[], order: string[] | null): AccessPerson[] {
    if (!order) return rows;
    const pos = new Map(order.map((id, i) => [id, i]));
    return [...rows].sort((a, b) => (pos.get(a.user_id) ?? order.length) - (pos.get(b.user_id) ?? order.length));
  }

  async function setPerson(userId: string, access: AccessLevel) {
    if (!openId) return;
    freezeOrder();
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
    freezeOrder();
    rowBusy = userId; error = '';
    try {
      await api.grantTestAttempts(openId, userId, 1);
      detail = await api.contentAccessPeople(openKind, openId);
    } catch (e: any) { error = e.message; }
    finally { rowBusy = null; }
  }

  async function clearPerson(userId: string) {
    if (!openId) return;
    freezeOrder();
    rowBusy = userId; error = '';
    try {
      await api.clearPersonAccess(openKind, openId, userId);
      detail = await api.contentAccessPeople(openKind, openId);
    } catch (e: any) { error = e.message; }
    finally { rowBusy = null; }
  }

  $: people = keepOrder(sortRows((detail?.people ?? []).filter((p) => {
    const needle = personFilter.trim().toLowerCase();
    if (!needle) return true;
    return (
      (p.full_name ?? '').toLowerCase().includes(needle) ||
      p.email.toLowerCase().includes(needle) ||
      (p.team ?? '').toLowerCase().includes(needle)
    );
  }), peopleSort, PEOPLE_SORT), frozenOrder);

  const RULE_RANK: Record<string, number> = { grant: 0, required: 1, revoke: 2 };
  const PEOPLE_SORT: SortAccessors<AccessPerson> = {
    name: (p) => p.full_name || p.email,
    team: (p) => p.team,
    access: (p) => (p.can_access ? (p.required ? 2 : 1) : 0),
    attempts: (p) => p.attempts?.used,
    why: (p) => p.why,
    rule: (p) => (p.rule ? RULE_RANK[p.rule] : null),
  };
  let peopleSort = NO_SORT;
  // The Attempts column only exists on capped tests; don't keep sorting by a hidden column.
  $: if (peopleSort.key === 'attempts' && !(tab === 'test' && capped)) peopleSort = NO_SORT;

  // Closed content (canvas courses and their tests) with no audience is visible
  // to nobody, not everyone — the API's matches_audience treats it that way.
  const isClosedEmpty = (m: ModuleAudienceOut) => !m.is_restricted && m.access_mode === 'closed';
  const isLimited = (m: ModuleAudienceOut) => m.is_restricted || m.access_mode === 'closed';

  function audienceSummary(m: ModuleAudienceOut): string {
    if (isClosedEmpty(m)) return 'Nobody yet — closed until you add an audience or people';
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

  // Summary tiles for the active tab (presentation only).
  $: limitedCount = items.filter(isLimited).length;
  $: everyoneCount = items.length - limitedCount;
  $: draftCount = items.filter((m) => !m.is_published).length;

  // Retakes apply when the test has an attempt ceiling: max_attempts, or a
  // test that needs approval (its allowance starts at 0, so max_attempts is
  // null but grants still count). The per-person `attempts.allowed` says so.
  $: capped = openKind === 'test' && !!detail &&
    (detail.max_attempts != null || detail.people.some((p) => p.attempts?.allowed != null));
</script>

<svelte:head><title>Champ LMS — Content Access</title></svelte:head>

<div class="wrap">
  <Breadcrumbs items={[{ label: 'Admin', href: '/admin' }, { label: 'Content Access' }]} />
  <header class="head">
    <h1 class="ui-rise" style="--i:1">
      Content access
      <span class="title-mark" aria-hidden="true"><Icon name="shield" size={24} /></span>
    </h1>
    <p class="sub ui-rise" style="--i:2">
      Project content team-wise, and override it for individuals. Anything with no
      audience is visible to everyone, except canvas courses and their tests, which
      stay closed until you add people. Assigning a team, department or role limits
      it to people who match at least one of them. Per-person rules win over the
      audience, and a revoke always beats a grant. The same rules cover learning
      modules and test series.
    </p>
  </header>

  {#if error}<p class="error pop-in"><Icon name="alert" size={16} /> {error}</p>{/if}

  <div class="bar ui-rise" style="--i:3">
    <div class="tabs" role="tablist">
      <button
        class="tab" class:on={tab === 'module'} role="tab"
        aria-selected={tab === 'module'}
        on:click={() => switchTab('module')}>
        <Icon name="layers" size={16} />
        Modules{#if catalogue} <span class="count">{catalogue.modules.length}</span>{/if}
      </button>
      <button
        class="tab" class:on={tab === 'test'} role="tab"
        aria-selected={tab === 'test'}
        on:click={() => switchTab('test')}>
        <Icon name="clipboard" size={16} />
        Test series{#if catalogue} <span class="count">{catalogue.tests?.length ?? 0}</span>{/if}
      </button>
    </div>
    {#if !loading && items.length}
      <div class="mini-stats">
        <span class="ms mint"><Icon name="users" size={14} /><b use:countUp={everyoneCount}></b> everyone</span>
        <span class="ms butter"><Icon name="lock" size={14} /><b use:countUp={limitedCount}></b> limited</span>
        {#if draftCount}<span class="ms"><Icon name="edit" size={14} /><b use:countUp={draftCount}></b> draft</span>{/if}
      </div>
    {/if}
  </div>

  {#if loading}
    <div class="mod-list">
      {#each Array(5) as _, i}<div class="ui-skeleton" style="height:72px;border-radius:22px;opacity:{1 - i * 0.14}"></div>{/each}
    </div>
  {:else if items.length === 0}
    <div class="empty ui-rise">
      <span class="e-ico"><Icon name={tab === 'test' ? 'clipboard' : 'layers'} size={26} /></span>
      <p>
        {#if tab === 'test'}
          No test series yet. Upload a question paper under Test series first.
        {:else}
          No modules yet. Upload content first.
        {/if}
      </p>
    </div>
  {:else}
    {#key tab}
      <div class="mod-list">
        {#each items as m, n (m.id)}
          <div class="mod ui-rise" class:open={openId === m.id} style="--i:{Math.min(n, 10)}">
            <button class="mod-head" on:click={() => openItem(m)} aria-expanded={openId === m.id}>
              <span class="m-ico" class:limited={isLimited(m)}>
                <Icon name={isLimited(m) ? 'lock' : 'unlock'} size={18} />
              </span>
              <div class="mod-main">
                <div class="mod-title">
                  <b>{m.title}</b>
                  {#if !m.is_published}<span class="tag draft">Draft</span>{/if}
                  {#if tab === 'test' && m.total_questions !== undefined}
                    <span class="tag draft">{m.total_questions} Qs</span>
                  {/if}
                  {#if m.is_restricted}
                    <span class="tag limited">Limited</span>
                  {:else if isClosedEmpty(m)}
                    <span class="tag limited">Closed</span>
                  {:else}
                    <span class="tag open">Everyone</span>
                  {/if}
                </div>
                <div class="mod-aud">{audienceSummary(m)}</div>
              </div>
              <span class="chev ui-round" aria-hidden="true"><Icon name="chevronDown" size={16} /></span>
            </button>

            {#if openId === m.id}
              <div class="mod-body">
                {#if detailLoading}
                  <div class="sk">
                    <div class="ui-skeleton" style="height:22px;width:40%;border-radius:8px"></div>
                    <div class="ui-skeleton" style="height:38px;border-radius:999px"></div>
                    <div class="ui-skeleton" style="height:38px;width:80%;border-radius:999px"></div>
                    <div class="ui-skeleton" style="height:180px;border-radius:18px"></div>
                  </div>
                {:else}
                  <section class="panel">
                    <h3><Icon name="target" size={18} /> Who is this for?</h3>
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
                              on:click={() => (draftTeams = toggle(draftTeams, t))}>
                              {#if draftTeams.includes(t)}<span class="tick"><Icon name="check" size={13} /></span>{/if}{t}
                            </button>
                          {/each}
                        </div>
                      </div>
                    {/if}

                    <div class="field">
                      <span class="lbl">Departments</span>
                      <div class="chips">
                        {#each catalogue.departments as d}
                          <button class="chip" class:on={draftDepts.includes(d)}
                            on:click={() => (draftDepts = toggle(draftDepts, d))}>
                            {#if draftDepts.includes(d)}<span class="tick"><Icon name="check" size={13} /></span>{/if}{d}
                          </button>
                        {/each}
                      </div>
                    </div>

                    <div class="field">
                      <span class="lbl">Roles</span>
                      <div class="chips">
                        {#each catalogue.roles as r}
                          <button class="chip" class:on={draftRoles.includes(r)}
                            on:click={() => (draftRoles = toggle(draftRoles, r))}>
                            {#if draftRoles.includes(r)}<span class="tick"><Icon name="check" size={13} /></span>{/if}{r}
                          </button>
                        {/each}
                      </div>
                    </div>

                    <div class="field">
                      <span class="lbl">Required for</span>
                      <div class="chips">
                        {#each catalogue.teams as t}
                          <button class="chip req" class:on={draftRequired.includes(t)}
                            on:click={() => (draftRequired = toggle(draftRequired, t))}>
                            {#if draftRequired.includes(t)}<span class="tick"><Icon name="flag" size={13} /></span>{/if}{t}
                          </button>
                        {/each}
                      </div>
                      <p class="hint">
                        Mandatory for these teams. Being required also grants access.
                      </p>
                    </div>

                    <div class="row-actions">
                      <button class="btn primary" disabled={saving} on:click={saveAudience}>
                        <Icon name="save" size={15} /> {saving ? 'Saving…' : 'Save audience'}
                      </button>
                      <!-- Closed content (canvas courses and their tests) with no
                           audience is visible to nobody, so clearing it would lock
                           everyone out rather than open it up. -->
                      {#if m.access_mode !== 'closed'}
                        <button class="btn ghost" class:armed={confirmOpenAll} disabled={saving} on:click={openToEveryone}>
                          <Icon name="users" size={15} /> {confirmOpenAll ? 'Click again to open to everyone' : 'Open to everyone'}
                        </button>
                      {/if}
                    </div>
                  </section>

                  <section>
                    <div class="people-head">
                      <h3>
                        <Icon name="users" size={18} /> People
                        {#if detail}
                          <span class="muted"> — {detail.can_access_count} of {detail.people.length} can {tab === 'test' ? 'sit' : 'open'} this</span>
                        {/if}
                      </h3>
                      <label class="search">
                        <Icon name="search" size={16} />
                        <input placeholder="Filter by name, email or team…" bind:value={personFilter} aria-label="Filter people" />
                      </label>
                    </div>
                    {#if detail && detail.people.length}
                      <div class="meter" aria-hidden="true">
                        <span style="--p:{(detail.can_access_count / detail.people.length) * 100}%"></span>
                      </div>
                    {/if}
                    <div class="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th aria-sort={ariaSort(peopleSort, 'name')}><SortHeader field="name" bind:sort={peopleSort}>Person</SortHeader></th>
                            <th aria-sort={ariaSort(peopleSort, 'team')}><SortHeader field="team" bind:sort={peopleSort}>Team</SortHeader></th>
                            <th aria-sort={ariaSort(peopleSort, 'access')}><SortHeader field="access" bind:sort={peopleSort}>Access</SortHeader></th>
                            {#if tab === 'test' && capped}
                              <th aria-sort={ariaSort(peopleSort, 'attempts')}><SortHeader field="attempts" bind:sort={peopleSort}>Attempts</SortHeader></th>
                            {/if}
                            <th aria-sort={ariaSort(peopleSort, 'why')}><SortHeader field="why" bind:sort={peopleSort}>Why</SortHeader></th>
                            <th aria-sort={ariaSort(peopleSort, 'rule')}><SortHeader field="rule" bind:sort={peopleSort}>Override</SortHeader></th>
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
                                  <span class="tag open"><span class="dot"></span>Can open</span>
                                {:else}
                                  <span class="tag no"><span class="dot"></span>Blocked</span>
                                {/if}
                                {#if p.required}<span class="tag req-tag">Required</span>{/if}
                              </td>
                              {#if tab === 'test' && capped}
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
                                <div class="seg">
                                  <button class="sbtn" class:active={p.rule === 'grant'}
                                    disabled={rowBusy === p.user_id}
                                    on:click={() => setPerson(p.user_id, 'grant')}>Grant</button>
                                  <button class="sbtn" class:active={p.rule === 'required'}
                                    disabled={rowBusy === p.user_id}
                                    on:click={() => setPerson(p.user_id, 'required')}>Require</button>
                                  <button class="sbtn revoke" class:active={p.rule === 'revoke'}
                                    disabled={rowBusy === p.user_id}
                                    on:click={() => setPerson(p.user_id, 'revoke')}>Revoke</button>
                                </div>
                                {#if p.rule}
                                  <button class="btn small ghost" disabled={rowBusy === p.user_id}
                                    on:click={() => clearPerson(p.user_id)}><Icon name="close" size={13} /> Clear</button>
                                {/if}
                                {#if tab === 'test' && capped}
                                  <button class="btn small retake" disabled={rowBusy === p.user_id}
                                    title="Give this person one more attempt"
                                    on:click={() => grantRetake(p.user_id)}><Icon name="refresh" size={13} /> +1 retake</button>
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
    {/key}
  {/if}
</div>

<style>
  /* ---------- header ---------- */
  .head { margin: 0 0 1.25rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; display: flex; align-items: center; gap: 0.6rem; margin: 0 0 0.6rem; }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-mint); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .sub { color: var(--muted); font-size: 0.9rem; max-width: 74ch; margin: 0; line-height: 1.55; }
  h3 { display: flex; align-items: center; gap: 0.45rem; flex-wrap: wrap; font-size: 1rem; margin: 0 0 0.8rem; }

  /* ---------- tab bar ---------- */
  .bar { display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.1rem; }
  .tabs { display: inline-flex; gap: 0.25rem; padding: 0.3rem; border-radius: 999px; background: var(--surface2); }
  .tab {
    display: inline-flex; align-items: center; gap: 0.45rem; height: 40px; padding: 0 1rem; border-radius: 999px;
    background: transparent; border: none; color: var(--muted); font-size: 0.88rem; font-weight: 600; cursor: pointer;
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2);
  }
  .tab:hover { color: var(--text); }
  .tab.on { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); }
  .count {
    min-width: 22px; height: 20px; padding: 0 6px; border-radius: 99px; font-size: 0.72rem; font-weight: 700;
    display: inline-grid; place-items: center; background: var(--surface3); color: var(--text-secondary);
  }
  .tab.on .count { background: var(--accent); color: var(--on-accent); animation: pop 320ms var(--ease-out); }
  .mini-stats { display: flex; gap: 0.45rem; flex-wrap: wrap; }
  .ms {
    display: inline-flex; align-items: center; gap: 0.35rem; height: 32px; padding: 0 0.8rem; border-radius: 999px;
    font-size: 0.8rem; font-weight: 500; background: var(--surface2); color: var(--text-secondary);
  }
  .ms b { font-variant-numeric: tabular-nums; }
  .ms.mint { background: var(--tile-mint); color: var(--tile-ink); }
  .ms.butter { background: var(--tile-butter); color: var(--tile-ink); }

  /* ---------- list ---------- */
  .mod-list { display: flex; flex-direction: column; gap: 0.6rem; }
  .mod {
    border-radius: 24px; background: var(--surface); box-shadow: var(--shadow-sm); overflow: hidden;
    transition: box-shadow var(--dur-3) var(--ease-out), translate var(--dur-3) var(--ease-out);
  }
  .mod:not(.open):hover { box-shadow: var(--shadow); translate: 0 -2px; }
  .mod.open { box-shadow: var(--shadow-md), 0 0 0 2px var(--accent); }
  .mod-head {
    width: 100%; display: grid; grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 0.95rem; align-items: center; text-align: left;
    padding: 0.9rem 1rem 0.9rem 0.95rem; background: none; border: none; color: var(--text); cursor: pointer;
  }
  .m-ico {
    width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center;
    background: var(--tile-mint); color: var(--tile-ink); transition: transform var(--dur-3) var(--ease-out);
  }
  .m-ico.limited { background: var(--tile-butter); }
  .mod-head:hover .m-ico { transform: rotate(-12deg) scale(1.08); }
  .mod-main { min-width: 0; display: flex; flex-direction: column; gap: 0.25rem; }
  .mod-title { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
  .mod-title b { font-size: 1rem; }
  .mod-aud { color: var(--muted); font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .chev { width: 34px; height: 34px; transition: rotate var(--dur-3) var(--ease-out), background-color var(--dur-2); }
  .mod.open .chev { rotate: 180deg; background: var(--accent); color: var(--on-accent); }
  .mod-body {
    padding: 0.2rem 1rem 1.25rem; display: flex; flex-direction: column; gap: 1.5rem;
    animation: open-down 420ms var(--ease-out) backwards;
  }
  @keyframes open-down { from { opacity: 0; translate: 0 -8px; } }
  .panel { background: var(--surface2); border-radius: 22px; padding: 1.1rem 1.1rem 1rem; }
  .sk { display: flex; flex-direction: column; gap: 0.7rem; }
  .field { margin-bottom: 1rem; }
  .lbl { display: block; font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); margin-bottom: 0.45rem; }
  .chips { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .chip {
    display: inline-flex; align-items: center; gap: 0.3rem;
    border: none; background: var(--surface); color: var(--text);
    border-radius: 999px; padding: 0.4rem 0.85rem; font-size: 0.82rem; font-weight: 500; cursor: pointer;
    box-shadow: inset 0 0 0 1px var(--border);
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2), translate var(--dur-3) var(--ease-out), box-shadow var(--dur-2);
  }
  .chip:hover { translate: 0 -2px; box-shadow: inset 0 0 0 1px var(--text-secondary); }
  .chip.on { background: var(--accent); color: var(--on-accent); font-weight: 600; box-shadow: none; }
  .chip.req.on { background: var(--tile-butter); color: var(--tile-ink); box-shadow: inset 0 0 0 1.5px var(--warn); }
  .tick { display: inline-flex; animation: pop 300ms var(--ease-out); }
  .hint { color: var(--muted); font-size: 0.78rem; margin: 0.45rem 0 0; }
  .hint.tight { margin: -0.35rem 0 0.9rem; }
  .row-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }

  .people-head { display: flex; align-items: center; justify-content: space-between; gap: 0.8rem; flex-wrap: wrap; margin-bottom: 0.6rem; }
  .people-head h3 { margin: 0; }
  .search {
    display: flex; align-items: center; gap: 0.5rem; height: 42px; padding: 0 0.95rem; width: min(340px, 100%);
    background: var(--surface2); border-radius: 999px; color: var(--muted); transition: background-color var(--dur-2), box-shadow var(--dur-2);
  }
  .search:focus-within { background: var(--surface); box-shadow: 0 0 0 2px var(--accent); }
  .search input { flex: 1; min-width: 0; background: none; border: none; outline: none; color: var(--text); font-size: 0.86rem; }
  .search input:focus { box-shadow: none; }
  .meter { height: 6px; border-radius: 99px; background: var(--surface3); overflow: hidden; margin-bottom: 0.8rem; }
  .meter span { display: block; height: 100%; width: var(--p); background: var(--success); border-radius: inherit; transform-origin: left; animation: grow 900ms var(--ease-out) 200ms backwards; }
  @keyframes grow { from { transform: scaleX(0); } }

  /* Wide table scrolls in its own box so the page never scrolls sideways. */
  .table-scroll { overflow-x: auto; border-radius: 18px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--border); }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; min-width: 820px; }
  th, td { text-align: left; padding: 0.65rem 0.8rem; border-bottom: 1px solid var(--border); vertical-align: middle; }
  th { color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; background: var(--surface2); }
  tbody tr:last-child td { border-bottom: none; }
  tbody tr { transition: background-color var(--dur-2); }
  tbody tr:hover { background: var(--surface2); }
  tr.denied { opacity: 0.6; }
  .name { font-weight: 600; }
  .email { color: var(--muted); font-size: 0.75rem; }
  .why { color: var(--muted); font-size: 0.78rem; }
  .tag { display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.72rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 999px; white-space: nowrap; }
  .tag .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .tag.open { background: var(--tile-mint); color: var(--tile-ink); }
  .tag.open .dot { background: var(--success); }
  .tag.no { background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); }
  .tag.limited { background: var(--tile-butter); color: var(--tile-ink); }
  .tag.req-tag { background: var(--tile-peach); color: var(--tile-ink); margin-left: 0.3rem; }
  .tag.draft { background: var(--surface2); color: var(--muted); }
  .actions { display: flex; gap: 0.35rem; flex-wrap: wrap; align-items: center; }
  .att { white-space: nowrap; font-variant-numeric: tabular-nums; }
  .att .spent { color: var(--danger); font-weight: 600; }

  /* Override buttons as one segmented pill. */
  .seg { display: inline-flex; padding: 3px; border-radius: 999px; background: var(--surface2); }
  .sbtn {
    border: none; background: transparent; color: var(--text-secondary); font-size: 0.75rem; font-weight: 600;
    padding: 0.3rem 0.65rem; border-radius: 999px; cursor: pointer;
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2);
  }
  .sbtn:hover:not(:disabled) { color: var(--text); background: var(--surface3); }
  .sbtn.active { background: var(--accent); color: var(--on-accent); animation: pop 300ms var(--ease-out); }
  .sbtn.revoke.active { background: color-mix(in srgb, var(--danger) 18%, transparent); color: var(--danger); }
  .sbtn:disabled { opacity: 0.5; cursor: not-allowed; }

  .btn {
    display: inline-flex; align-items: center; gap: 0.4rem;
    border: none; background: var(--surface2); color: var(--text);
    border-radius: 999px; padding: 0.6rem 1.05rem; font-size: 0.86rem; font-weight: 600; cursor: pointer;
    transition: background-color var(--dur-2), translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .btn:hover:not(:disabled) { background: var(--surface3); translate: 0 -1px; }
  .btn.primary { background: var(--accent); color: var(--on-accent); }
  .btn.primary:hover:not(:disabled) { background: var(--accent-hover); box-shadow: var(--shadow); }
  .btn.ghost { background: transparent; }
  .panel .btn.ghost:hover:not(:disabled) { background: var(--surface); }
  .btn.ghost.armed, .panel .btn.ghost.armed:hover:not(:disabled) { background: var(--tile-butter); color: var(--tile-ink); animation: pop 300ms var(--ease-out); }
  .btn.small { padding: 0.32rem 0.65rem; font-size: 0.75rem; gap: 0.3rem; }
  .btn.retake { background: var(--tile-butter); color: var(--tile-ink); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn :global(.icon) { transition: transform var(--dur-3) var(--ease-out); }
  .btn:hover:not(:disabled) :global(.icon) { transform: rotate(-10deg) scale(1.1); }

  .pop-in { animation: modal-in 380ms var(--ease-out) backwards; }
  .error { display: flex; align-items: center; gap: 0.45rem; color: var(--danger); font-size: 0.86rem; }
  .muted { color: var(--muted); font-size: 0.85rem; font-weight: 400; }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 0.6rem; text-align: center; padding: 2.75rem 1rem; border-radius: 28px; background: var(--surface); color: var(--muted); }
  .e-ico { width: 60px; height: 60px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-mint); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }

  @media (max-width: 760px) {
    .tabs { width: 100%; }
    .tab { flex: 1; justify-content: center; padding: 0 0.5rem; }
    .mod-aud { white-space: normal; }
    .panel { padding: 0.9rem; }
  }
</style>
