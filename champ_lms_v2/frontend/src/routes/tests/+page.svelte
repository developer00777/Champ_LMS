<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type LearnerTest, type MyAttempt } from '$lib/api/client';
  import Icon from '$lib/components/Icon.svelte';
  import { countUp } from '$lib/actions/motion';

  let tests: LearnerTest[] = [];
  let attempts: MyAttempt[] = [];
  let loading = true;
  let error = '';

  onMount(async () => {
    try {
      [tests, attempts] = await Promise.all([api.testSeries(), api.myTestAttempts()]);
    } catch (e: any) { error = e.message; }
    finally { loading = false; }
  });

  // ---------- state of one test for this learner ----------
  type State = 'passed' | 'required' | 'retry' | 'new' | 'locked';
  function state(t: LearnerTest): State {
    if (t.passed) return 'passed';
    if (t.attempts_left === 0 && !(t.requires_approval && t.course_id)) return 'locked';
    if (t.required) return 'required';
    return t.my_attempts > 0 ? 'retry' : 'new';
  }
  // Colour per state lives in CSS (.s-<state> sets --tone).
  const STATE: Record<State, { label: string; icon: string }> = {
    passed: { label: 'Passed', icon: 'checkCircle' },
    required: { label: 'Required', icon: 'flag' },
    retry: { label: 'Try again', icon: 'refresh' },
    new: { label: 'New', icon: 'sparkles' },
    locked: { label: 'No attempts left', icon: 'lock' },
  };
  // Required and unfinished work first, passed tests last.
  const ORDER: Record<State, number> = { required: 0, new: 1, retry: 2, locked: 3, passed: 4 };

  // ---------- filters ----------
  type Filter = 'all' | 'todo' | 'required' | 'passed';
  let filter: Filter = 'all';
  let query = '';
  $: q = query.trim().toLowerCase();
  $: sorted = [...tests].sort((a, b) => ORDER[state(a)] - ORDER[state(b)] || a.title.localeCompare(b.title));
  $: shown = sorted.filter((t) => {
    if (q && !t.title.toLowerCase().includes(q) && !(t.category ?? '').toLowerCase().includes(q)) return false;
    if (filter === 'todo') return !t.passed;
    if (filter === 'required') return t.required;
    if (filter === 'passed') return t.passed;
    return true;
  });
  $: counts = {
    all: tests.length,
    todo: tests.filter((t) => !t.passed).length,
    required: tests.filter((t) => t.required).length,
    passed: tests.filter((t) => t.passed).length,
  } as Record<Filter, number>;
  const TABS: { key: Filter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'todo', label: 'To do' },
    { key: 'required', label: 'Required' },
    { key: 'passed', label: 'Passed' },
  ];

  // ---------- summary ----------
  $: tried = tests.filter((t) => t.my_best_score !== null && t.my_best_score !== undefined);
  $: avgBest = tried.length ? Math.round(tried.reduce((a, t) => a + (t.my_best_score ?? 0), 0) / tried.length) : 0;
  $: requiredOpen = tests.filter((t) => t.required && !t.passed).length;

  // ---------- history ----------
  let histLimit = 8;
  const pct = (n: number | null | undefined) => Math.max(0, Math.min(100, Math.round(n ?? 0)));
  function ago(iso: string) {
    const d = (Date.now() - new Date(iso).getTime()) / 1000;
    if (d < 3600) return `${Math.max(1, Math.floor(d / 60))} min ago`;
    if (d < 86400) return `${Math.floor(d / 3600)} h ago`;
    const days = Math.floor(d / 86400);
    if (days === 1) return 'yesterday';
    if (days < 7) return `${days} days ago`;
    return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }
  // The score is marks_earned / marks_total. Show marks beside the correct
  // count only when they differ from it (weighted questions, or partial
  // credit on written answers); otherwise they'd just repeat it.
  const showMarks = (a: MyAttempt) =>
    !!a.marks_total && (a.marks_total !== a.total_questions || a.marks_earned !== a.correct_count);
  // Attempt dots: used / allowed, capped so a large allowance stays one line.
  const dots = (t: LearnerTest) => {
    const total = t.attempts_allowed ?? 0;
    return total > 0 && total <= 10 ? Array.from({ length: total }, (_, i) => i < t.my_attempts) : null;
  };
</script>

<svelte:head><title>Test Series — Champ LMS</title></svelte:head>

<header class="head">
  <div>
    <p class="eyebrow ui-rise">Prove what you've learned</p>
    <h1 class="ui-rise" style="--i:1">
      Test Series
      <span class="title-mark" aria-hidden="true"><Icon name="clipboard" size={24} /></span>
    </h1>
    <p class="sub ui-rise" style="--i:2">Scored instantly, with feedback on exactly where to improve.</p>
  </div>
  {#if !loading && tests.length}
    <label class="search ui-rise" style="--i:3">
      <Icon name="search" size={18} />
      <span class="sr">Search tests</span>
      <input type="search" placeholder="Search tests" bind:value={query} />
      {#if query}<button class="clear" on:click={() => (query = '')} aria-label="Clear search"><Icon name="close" size={13} /></button>{/if}
    </label>
  {/if}
</header>

{#if error}<p class="error ui-rise"><Icon name="alert" size={16} /> {error}</p>{/if}

{#if loading}
  <div class="stats">{#each Array(4) as _}<div class="ui-skeleton" style="height:112px;border-radius:24px"></div>{/each}</div>
  <div class="grid">{#each Array(3) as _}<div class="ui-skeleton" style="height:330px;border-radius:22px"></div>{/each}</div>
{:else if tests.length === 0 && !error}
  <div class="empty ui-rise">
    <span class="empty-ico"><Icon name="clipboard" size={28} /></span>
    <h2>No tests available</h2>
    <p>When your L&amp;D team publishes a test series, it shows up here.</p>
  </div>
{:else if tests.length}
  <!-- ---------- summary ---------- -->
  <section class="stats" aria-label="Your test summary">
    <div class="stat mint ui-rise" style="--i:3"><span class="s-ico"><Icon name="checkCircle" size={18} /></span><b use:countUp={counts.passed}></b><span>Passed</span></div>
    <div class="stat butter ui-rise" style="--i:4"><span class="s-ico"><Icon name="flag" size={18} /></span><b use:countUp={requiredOpen}></b><span>Required to do</span></div>
    <div class="stat lilac ui-rise" style="--i:5"><span class="s-ico"><Icon name="trend" size={18} /></span><b><span use:countUp={avgBest}></span><i>%</i></b><span>Average best score</span></div>
    <div class="stat sky ui-rise" style="--i:6"><span class="s-ico"><Icon name="history" size={18} /></span><b use:countUp={attempts.length}></b><span>Attempts</span></div>
  </section>

  <!-- ---------- filters ---------- -->
  <div class="tabs ui-rise" style="--i:6" role="tablist" aria-label="Filter tests">
    {#each TABS as t}
      <button role="tab" aria-selected={filter === t.key} class:on={filter === t.key} on:click={() => (filter = t.key)}>
        {t.label} <span class="n">{counts[t.key]}</span>
      </button>
    {/each}
  </div>

  {#if shown.length === 0}
    <div class="empty small">
      <span class="empty-ico"><Icon name="target" size={24} /></span>
      <h2>{q ? `No tests match “${query}”` : filter === 'passed' ? 'Nothing passed yet' : filter === 'required' ? 'No required tests' : 'All done here'}</h2>
      <p>{q ? 'Try a shorter word or a category.' : 'Switch filters to see your other tests.'}</p>
    </div>
  {:else}
    {#key filter + q}
      <div class="grid">
        {#each shown as t, n (t.id)}
          {@const s = state(t)}
          {@const st = STATE[s]}
          {@const best = pct(t.my_best_score)}
          {@const d = dots(t)}
          <article class="card ui-rise s-{s}" style="--i:{Math.min(n, 8)}">
            <div class="body">
              <div class="top">
                <span class="state"><Icon name={st.icon} size={13} /> {st.label}</span>
                {#if t.required && s !== 'required'}<span class="tag"><Icon name="flag" size={12} /> Required</span>{/if}
                {#if t.course_id}<span class="tag"><Icon name="layers" size={12} /> Course test</span>{/if}
                {#if t.category}<span class="cat">{t.category}</span>{/if}
              </div>

              <h2>{t.title}</h2>
              <p class="desc">{t.description || (t.course_title ? `Part of ${t.course_title}.` : 'Answer every question, then see your score and feedback.')}</p>

              <div class="facts">
                <span><Icon name="list" size={13} /> <b>{t.total_questions}</b> question{t.total_questions === 1 ? '' : 's'}</span>
                <span><Icon name="target" size={13} /> <b>{t.pass_threshold}%</b> to pass</span>
                <span><Icon name="clock" size={13} /> {#if t.duration_minutes}<b>{t.duration_minutes} min</b>{:else}No limit{/if}</span>
              </div>

              <div class="score" class:none={t.my_attempts === 0}>
                <div class="score-row">
                  <span>{t.my_attempts > 0 ? 'Best score' : 'Not attempted yet'}</span>
                  {#if t.my_attempts > 0}<b class:pass={t.passed}>{best}<small>%</small></b>{:else}<b>—</b>{/if}
                </div>
                <span class="meter" class:pass={t.passed}>
                  {#if t.my_attempts > 0}<span style="--p:{best}%"></span>{/if}
                  <i style="left:{pct(t.pass_threshold)}%" title="Pass mark {t.pass_threshold}%"></i>
                </span>
                <div class="tries">
                  {#if d}
                    <span class="dots" aria-hidden="true">{#each d as used}<i class:used></i>{/each}</span>
                    <span>{t.my_attempts} of {t.attempts_allowed} attempt{t.attempts_allowed === 1 ? '' : 's'} used</span>
                  {:else if t.attempts_allowed === null}
                    <span><Icon name="refresh" size={12} /> Unlimited attempts · {t.my_attempts} used</span>
                  {:else}
                    <span>{t.my_attempts} attempt{t.my_attempts === 1 ? '' : 's'} used{#if t.attempts_left !== null} · {t.attempts_left} left{/if}</span>
                  {/if}
                  {#if t.extra_attempts_granted > 0}<span class="granted">+{t.extra_attempts_granted} granted</span>{/if}
                </div>
              </div>

              {#if t.requires_approval && t.course_id}
                <!-- Course tests are asked for, and approved, inside their course. -->
                {#if t.attempts_left}
                  <a href="/tests/{t.id}?course={t.course_id}" class="btn-primary act"><Icon name="play" size={13} stroke={0} /> Start test</a>
                {:else}
                  <a href="/course/{t.course_id}?ref={t.id}" class="btn-ghost act"><Icon name="message" size={15} /> Ask in {t.course_title ?? 'the course'}</a>
                {/if}
              {:else if t.attempts_left === 0}
                <button class="btn-ghost act" disabled><Icon name="lock" size={15} /> No attempts left</button>
              {:else}
                <a href="/tests/{t.id}" class="btn-primary act">
                  {#if t.my_attempts > 0}<Icon name="refresh" size={15} /> Retake test{:else}<Icon name="play" size={13} stroke={0} /> Start test{/if}
                </a>
              {/if}
            </div>
          </article>
        {/each}
      </div>
    {/key}
  {/if}
{/if}

<!-- ---------- history ---------- -->
{#if !loading && attempts.length > 0}
  <div class="sec-head ui-rise">
    <h2><Icon name="history" size={22} /> Your history</h2>
    <span class="n big">{attempts.length}</span>
  </div>
  <div class="history">
    {#each attempts.slice(0, histLimit) as a, n (a.attempt_id)}
      {@const sc = pct(a.score)}
      {@const mark = a.pass_threshold != null ? pct(a.pass_threshold) : null}
      {@const hasMarks = showMarks(a)}
      <a class="hist ui-rise" style="--i:{Math.min(n, 8)}" href="/tests/result/{a.attempt_id}" class:pass={a.passed}
         aria-label="{a.test_title}: {sc}%, {a.passed ? 'passed' : 'not passed'}">
        <span class="ring" aria-hidden="true">
          <svg viewBox="0 0 48 48">
            <circle class="r-track" cx="24" cy="24" r="20" />
            <circle class="r-arc" cx="24" cy="24" r="20" pathLength="100" style="stroke-dasharray:{sc} 100" />
          </svg>
          <span class="r-val"><span><b>{sc}</b><i>%</i></span></span>
        </span>

        <span class="h-info">
          <b class="h-title">{a.test_title}</b>
          <span class="h-sub"><Icon name="calendar" size={12} /> {ago(a.submitted_at)}</span>
          <span class="h-bar" aria-hidden="true">
            <span class="h-fill" style="--p:{sc}%"></span>
            {#if mark !== null}<i class="h-mark" style="left:{mark}%"></i>{/if}
          </span>
          {#if mark !== null}<span class="h-pm">Pass mark {mark}%</span>{/if}
        </span>

        <span class="h-stats">
          <span class="kv">
            <b>{a.correct_count}<small>/{a.total_questions}</small></b>
            <span>Correct</span>
          </span>
          {#if hasMarks}
            <span class="kv">
              <b>{a.marks_earned}<small>/{a.marks_total}</small></b>
              <span>Marks</span>
            </span>
          {/if}
        </span>

        <span class="ui-pill st" class:mint={a.passed} class:fail={!a.passed}>
          <Icon name={a.passed ? 'check' : 'xCircle'} size={13} /> {a.passed ? 'Passed' : 'Not passed'}
        </span>
        <span class="ui-round go" aria-hidden="true"><Icon name="arrowRight" size={16} /></span>
      </a>
    {/each}
  </div>
  {#if attempts.length > histLimit}
    <button class="btn-ghost more" on:click={() => (histLimit += 8)}>Show more <span class="n">{attempts.length - histLimit}</span></button>
  {/if}
{/if}

<style>
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

  /* ---------- header ---------- */
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: 1.5rem; flex-wrap: wrap; margin: 0.25rem 0 1.5rem; }
  .eyebrow { color: var(--muted); font-size: 0.95rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 { font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02; display: flex; align-items: center; gap: 0.6rem; }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-sky); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .sub { color: var(--muted); font-size: 0.95rem; margin-top: 0.55rem; }
  .search {
    display: flex; align-items: center; gap: 0.55rem; width: min(340px, 100%); height: 50px; padding: 0 1rem;
    border-radius: 999px; background: var(--surface2); color: var(--muted);
    transition: background-color var(--dur-2), box-shadow var(--dur-2);
  }
  .search:focus-within { background: var(--surface); box-shadow: 0 0 0 2px var(--accent), var(--shadow); }
  .search input { flex: 1; min-width: 0; height: 100%; border: none; background: none; color: var(--text); font-size: 0.92rem; }
  .search input:focus { outline: none; box-shadow: none; }
  .search input::-webkit-search-cancel-button { display: none; }
  .clear { width: 26px; height: 26px; border-radius: 50%; display: grid; place-items: center; background: var(--surface3); color: var(--text); animation: pop 300ms var(--ease-out); }
  .error { display: flex; align-items: center; gap: 0.4rem; color: var(--danger); font-size: 0.88rem; margin-bottom: 1rem; }

  /* ---------- summary tiles: one even row ---------- */
  .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); grid-auto-rows: 1fr; gap: 0.9rem; margin-bottom: 1.5rem; }
  .stat {
    position: relative; display: flex; flex-direction: column; justify-content: flex-end; gap: 0.1rem;
    min-height: 112px; padding: 0.9rem 1rem; border-radius: 24px; color: var(--tile-ink);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .stat:hover { translate: 0 -3px; box-shadow: var(--shadow); }
  .stat b { font-size: clamp(1.6rem, 1.2rem + 1vw, 2.1rem); font-weight: 700; letter-spacing: -0.03em; line-height: 1.1; font-variant-numeric: tabular-nums; }
  .stat b i { font-style: normal; font-size: 0.55em; opacity: 0.65; margin-left: 1px; }
  .stat > span:last-child { font-size: 0.78rem; opacity: 0.72; font-weight: 500; }
  .stat:hover b { animation: pop 420ms var(--ease-out); }
  .s-ico {
    position: absolute; top: 0.8rem; right: 0.8rem; width: 34px; height: 34px; border-radius: 50%;
    display: grid; place-items: center; background: var(--tile-inner);
    transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .stat:hover .s-ico { rotate: -14deg; scale: 1.1; }
  .mint { background: var(--tile-mint); } .butter { background: var(--tile-butter); }
  .sky { background: var(--tile-sky); } .lilac { background: var(--tile-lilac); }

  /* ---------- tabs ---------- */
  .tabs { display: inline-flex; flex-wrap: wrap; gap: 0.25rem; padding: 0.3rem; border-radius: 999px; background: var(--surface2); margin-bottom: 1.2rem; }
  .tabs button {
    height: 38px; padding: 0 1rem; border-radius: 999px; font-size: 0.86rem; font-weight: 600; color: var(--muted);
    display: inline-flex; align-items: center; gap: 0.4rem; background: transparent;
    transition: background-color var(--dur-2), color var(--dur-2);
  }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); }
  .n {
    min-width: 22px; height: 20px; padding: 0 6px; border-radius: 99px; font-size: 0.72rem; font-weight: 700;
    display: inline-grid; place-items: center; background: var(--surface3); color: var(--text-secondary);
  }
  .tabs button.on .n { background: var(--accent); color: var(--on-accent); animation: pop 320ms var(--ease-out); }
  .n.big { min-width: 28px; height: 24px; font-size: 0.8rem; }

  /* ---------- cards: an even grid ---------- */
  /* Compact cards: a status-coloured top edge and pill instead of the old
     92px pastel band, facts as one chip row, and score + attempts in one box. */
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); grid-auto-rows: 1fr; gap: 1rem; }
  .card {
    --tone: var(--info);
    position: relative; display: flex; flex-direction: column; height: 100%; overflow: hidden;
    border-radius: 22px; background: var(--surface);
    box-shadow: var(--shadow-sm), 0 0 0 1px var(--border);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .card::before { content: ''; position: absolute; left: 0; right: 0; top: 0; height: 4px; background: var(--tone); }
  .s-passed { --tone: var(--success); }
  .s-required { --tone: var(--gold); }
  .s-retry { --tone: var(--caution); }
  .s-new { --tone: var(--info); }
  .s-locked { --tone: var(--muted); }
  .card:hover { translate: 0 -4px; box-shadow: var(--shadow-md), 0 0 0 1px var(--border-hover); }

  .body { flex: 1; display: flex; flex-direction: column; gap: 0.6rem; padding: 1.05rem 1.05rem 1rem; }

  .top { display: flex; align-items: center; flex-wrap: wrap; gap: 0.35rem; }
  .state, .tag {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 24px; padding: 0 0.6rem; border-radius: 99px;
    font-size: 0.72rem; font-weight: 700;
  }
  .state { background: color-mix(in srgb, var(--tone) 15%, transparent); color: var(--tone); }
  .tag { background: var(--surface2); color: var(--text-secondary); }
  .cat {
    margin-left: auto; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
  }
  .card h2 {
    font-size: 1.06rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.3; color: var(--text);
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .desc {
    font-size: 0.82rem; color: var(--text-secondary); line-height: 1.45; margin-top: -0.25rem;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }

  .facts { display: flex; flex-wrap: wrap; gap: 0.35rem; }
  .facts > span {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 28px; padding: 0 0.6rem; border-radius: 10px;
    background: var(--surface2); color: var(--text-secondary); font-size: 0.75rem; font-weight: 500;
  }
  .facts b { color: var(--text); font-weight: 700; font-variant-numeric: tabular-nums; }

  .score {
    display: flex; flex-direction: column; gap: 0.45rem; margin-top: auto;
    padding: 0.7rem 0.8rem; border-radius: 16px;
    background: var(--surface2); box-shadow: inset 0 0 0 1px var(--border);
  }
  .score-row { display: flex; justify-content: space-between; align-items: baseline; font-size: 0.78rem; color: var(--text-secondary); font-weight: 600; }
  .score-row b { font-size: 1.2rem; font-weight: 800; letter-spacing: -0.02em; color: var(--caution); font-variant-numeric: tabular-nums; line-height: 1; }
  .score-row b small { font-size: 0.65em; font-weight: 700; margin-left: 1px; }
  .score-row b.pass { color: var(--success); }
  .score.none .score-row b { color: var(--muted); }
  .meter { position: relative; display: block; height: 8px; border-radius: 99px; background: var(--surface3); }
  .meter > span {
    display: block; height: 100%; width: var(--p); border-radius: inherit; background: var(--caution);
    transform-origin: left; animation: grow 1s var(--ease-out) 300ms backwards;
  }
  .meter.pass > span { background: var(--success); }
  .meter i { position: absolute; top: -4px; width: 3px; height: 16px; margin-left: -1.5px; border-radius: 2px; background: var(--text); opacity: 0.7; }
  @keyframes grow { from { transform: scaleX(0); } }

  .tries { display: flex; align-items: center; flex-wrap: wrap; gap: 0.45rem; font-size: 0.74rem; color: var(--text-secondary); }
  .tries > span { display: inline-flex; align-items: center; gap: 0.3rem; }
  .dots { display: inline-flex; gap: 4px; }
  .dots i { width: 8px; height: 8px; border-radius: 50%; background: var(--surface3); box-shadow: inset 0 0 0 1px var(--border-hover); transition: scale var(--dur-2) var(--ease-out); }
  .dots i.used { background: var(--accent); box-shadow: none; }
  .card:hover .dots i { scale: 1.15; }
  .granted { font-size: 0.7rem; font-weight: 700; padding: 0.1rem 0.5rem; border-radius: 999px; background: var(--tile-butter); color: var(--tile-ink); }

  .act { justify-content: center; }
  .act :global(svg[stroke-width="0"]) { fill: currentColor; }
  .act :global(.icon) { transition: translate var(--dur-2) var(--ease-out), rotate var(--dur-3) var(--ease-out); }
  .act:hover :global(.icon) { translate: 2px 0; }
  .act:disabled { opacity: 0.55; cursor: not-allowed; }

  /* ---------- history ---------- */
  .sec-head { display: flex; align-items: center; gap: 0.6rem; margin: 2.4rem 0 0.9rem; }
  .sec-head h2 { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 1.45rem; letter-spacing: -0.025em; }
  .history { display: flex; flex-direction: column; gap: 0.6rem; }
  /* Row: score ring | title, date, score bar with the pass-mark tick |
     correct + marks | status | open. */
  .hist {
    --tone: var(--danger);
    display: grid; grid-template-columns: 66px minmax(0, 1fr) auto auto 38px; align-items: center; gap: 1.1rem;
    padding: 0.7rem 0.9rem 0.7rem 0.7rem;
    border-radius: 22px; background: var(--surface); box-shadow: var(--shadow-sm); color: var(--text);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .hist.pass { --tone: var(--success); }
  .hist:hover { translate: 4px 0; box-shadow: var(--shadow); }

  .ring {
    position: relative; width: 66px; height: 66px; border-radius: 50%;
    background: color-mix(in srgb, var(--tone) 9%, transparent);
  }
  .ring svg { position: absolute; inset: 0; width: 100%; height: 100%; rotate: -90deg; }
  .ring circle { fill: none; stroke-width: 4.5; }
  .r-track { stroke: color-mix(in srgb, var(--tone) 16%, var(--surface3)); }
  .r-arc { stroke: var(--tone); stroke-linecap: round; animation: draw 1.1s var(--ease-out) 200ms backwards; }
  @keyframes draw { from { stroke-dasharray: 0 100; } }
  /* Number and % share one text baseline inside a span, and that span is
     centred in the ring. */
  .r-val {
    position: absolute; inset: 0; display: grid; place-items: center;
    line-height: 1; color: var(--text); font-variant-numeric: tabular-nums;
  }
  .r-val > span { white-space: nowrap; }
  .r-val b { font-size: 1.12rem; font-weight: 800; letter-spacing: -0.03em; }
  .r-val i { font-style: normal; font-size: 0.66rem; font-weight: 700; color: var(--muted); margin-left: 1px; }

  .h-info { min-width: 0; display: flex; flex-direction: column; gap: 0.28rem; }
  .h-title { font-size: 0.98rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .h-sub { display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.76rem; color: var(--muted); }
  .h-bar {
    position: relative; display: block; height: 6px; max-width: 320px; margin-top: 0.15rem;
    border-radius: 99px; background: var(--surface3);
  }
  .h-fill {
    position: absolute; left: 0; top: 0; bottom: 0; width: var(--p); border-radius: inherit; background: var(--tone);
    transform-origin: left; animation: grow-x 1s var(--ease-out) 250ms backwards;
  }
  @keyframes grow-x { from { transform: scaleX(0); } }
  .h-mark {
    position: absolute; top: -3px; bottom: -3px; width: 2px; margin-left: -1px; border-radius: 2px;
    background: var(--text); opacity: 0.55;
  }
  .h-pm { font-size: 0.7rem; color: var(--muted); font-weight: 600; }

  .h-stats { display: flex; gap: 0.45rem; }
  .kv {
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.15rem;
    min-width: 74px; padding: 0.45rem 0.7rem; border-radius: 14px; background: var(--surface2);
  }
  .kv b { font-size: 1rem; font-weight: 700; line-height: 1; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }
  .kv small { font-size: 0.74rem; font-weight: 600; color: var(--muted); }
  .kv > span { font-size: 0.66rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }

  .st.fail { background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger); }
  .hist:hover .st { animation: pop 380ms var(--ease-out); }
  .go { width: 38px; height: 38px; transition: transform var(--dur-3) var(--ease-out); }
  .hist:hover .go { transform: translateX(3px) rotate(-30deg); }
  .more { display: flex; margin: 1rem auto 0; }

  /* ---------- states ---------- */
  .empty { display: flex; flex-direction: column; align-items: center; gap: 0.6rem; text-align: center; padding: 3rem 1rem; background: var(--surface); border-radius: 32px; }
  .empty.small { padding: 2.4rem 1rem; }
  .empty-ico { width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-sky); color: var(--tile-ink); animation: pop 520ms var(--ease-out); }
  .empty h2 { font-size: 1.3rem; }
  .empty p { color: var(--muted); font-size: 0.9rem; }

  @media (max-width: 900px) {
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 900px) {
    /* Status pill drops out; the ring's colour already says pass/fail. */
    .hist { grid-template-columns: 66px minmax(0, 1fr) auto 38px; }
    .hist .st { display: none; }
  }
  @media (max-width: 760px) {
    .grid { grid-template-columns: 1fr; }
    .search { width: 100%; }
    .hist { grid-template-columns: 58px minmax(0, 1fr) 34px; gap: 0.8rem; }
    .ring { width: 58px; height: 58px; }
    .r-val b { font-size: 1rem; }
    .h-stats { grid-column: 2 / -1; grid-row: 2; }
    .kv { flex-direction: row; gap: 0.35rem; min-width: 0; padding: 0.3rem 0.6rem; border-radius: 99px; }
    .kv b { font-size: 0.86rem; }
    .go { width: 34px; height: 34px; }
  }
</style>
