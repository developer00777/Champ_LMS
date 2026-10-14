<script lang="ts">
  import { onMount } from 'svelte';
  import { api, type AnalyticsData } from '$lib/api/client';
  import { countUp } from '$lib/actions/motion';
  import Icon from '$lib/components/Icon.svelte';

  let analytics: AnalyticsData | null = null;
  let loading = true;
  let openQuestions = 0;

  onMount(async () => {
    api.openQuestionCount().then(r => (openQuestions = r.open)).catch(() => {});
    try { analytics = await api.analytics(); }
    finally { loading = false; }
  });

  const LINKS = [
    { href: '/admin/employees', icon: 'users', tone: 'sky', title: 'Employees', text: 'Create logins, set teams and privileges, and view or reset passwords' },
    { href: '/admin/content-access', icon: 'shield', tone: 'lilac', title: 'Content Access', text: 'Project modules team-wise and grant or revoke access per person' },
    { href: '/admin/courses', icon: 'layers', tone: 'mint', title: 'Courses', text: 'Build a course on one canvas: videos, AI quizzes, tests and notes, with access you control' },
    { href: '/admin/test-requests', icon: 'bell', tone: 'butter', title: 'Test requests', text: 'Approve who sits a course test, and how many attempts they get' },
    { href: '/admin/questions', icon: 'message', tone: 'sky', title: 'Questions', text: 'Answer what learners ask from the Q&A button on course videos', countsOpen: true },
    { href: '/admin/upload', icon: 'upload', tone: 'peach', title: 'Upload Video', text: 'Upload to Bunny Stream — auto-transcodes to HLS' },
    { href: '/admin/zoom', icon: 'video', tone: 'sky', title: 'Zoom → Module Builder', text: 'Convert Zoom recordings into AI-structured modules' },
    { href: '/admin/tests', icon: 'clipboard', tone: 'lilac', title: 'Test Series', text: 'Turn a Q&A PDF or Word doc into a scored test with AI improvement insights' },
    { href: '/admin/daily', icon: 'flame', tone: 'peach', title: 'Daily Challenges', text: "Write a challenge pool — three rotate into everyone's day automatically" },
    { href: '/admin/content', icon: 'folder', tone: 'mint', title: 'Content Library', text: 'Browse every module and video — and permanently delete from Bunny/CDN' },
    { href: '/leaderboard', icon: 'trophy', tone: 'butter', title: 'Leaderboard', text: 'View rankings and gamification data' },
  ];
</script>

<svelte:head><title>Admin Dashboard — Champ LMS</title></svelte:head>

<div class="page">
  <header class="head">
    <p class="eyebrow ui-rise">Run the academy</p>
    <h1 class="ui-rise" style="--i:1">
      Admin Dashboard
      <span class="title-mark" aria-hidden="true"><Icon name="chart" size={24} /></span>
    </h1>
  </header>

  {#if loading}
    <div class="stats-grid">
      {#each Array(4) as _}<div class="ui-skeleton" style="height:132px;border-radius:26px"></div>{/each}
    </div>
  {:else if analytics}
    <div class="stats-grid">
      <div class="stat-card sky ui-rise" style="--i:2">
        <span class="s-ico"><Icon name="users" size={18} /></span>
        <div class="num" use:countUp={analytics.total_users}></div>
        <div class="lbl">Total Users</div>
      </div>
      <div class="stat-card mint ui-rise" style="--i:3">
        <span class="s-ico"><Icon name="layers" size={18} /></span>
        <div class="num" use:countUp={analytics.published_modules}></div>
        <div class="lbl">Published Modules</div>
      </div>
      <div class="stat-card lilac ui-rise" style="--i:4">
        <span class="s-ico"><Icon name="checkCircle" size={18} /></span>
        <div class="num" use:countUp={analytics.episode_completions}></div>
        <div class="lbl">Episode Completions</div>
      </div>
      <div class="stat-card butter ui-rise" style="--i:5">
        <span class="s-ico"><Icon name="trend" size={18} /></span>
        <div class="num" use:countUp={analytics.total_enrollments}></div>
        <div class="lbl">Total Enrollments</div>
      </div>
    </div>
  {/if}

  <h2 class="sec ui-rise" style="--i:5">Tools</h2>
  <div class="quick-links">
    {#each LINKS as l, n}
      <a href={l.href} class="link-card ui-rise" style="--i:{6 + n}">
        <span class="icon {l.tone}"><Icon name={l.icon} size={22} /></span>
        <h3>{l.title}{#if l.countsOpen && openQuestions}<span class="badge" title="{openQuestions} waiting for an answer">{openQuestions}</span>{/if}</h3>
        <p>{l.text}</p>
        <span class="go ui-round" aria-hidden="true"><Icon name="arrowRight" size={16} /></span>
      </a>
    {/each}
  </div>
</div>

<style>
  .head { margin: 0 0 1.25rem; }
  .eyebrow { color: var(--muted); font-size: 0.95rem; font-weight: 500; margin-bottom: 0.35rem; }
  h1 {
    font-size: var(--fs-hero); font-weight: 700; letter-spacing: -0.035em; line-height: 1.02;
    display: flex; align-items: center; gap: 0.6rem;
  }
  .title-mark {
    display: inline-grid; place-items: center; width: 48px; height: 48px; border-radius: 50%;
    background: var(--tile-butter); color: var(--tile-ink); rotate: -8deg;
    animation: pop 600ms var(--ease-out) 300ms backwards;
  }
  h1:hover .title-mark { rotate: 8deg; transition: rotate var(--dur-3) var(--ease-out); }
  .badge {
    display: inline-grid; place-items: center; min-width: 20px; height: 20px; padding: 0 6px; margin-left: 0.45rem;
    border-radius: 99px; background: var(--brand); color: #fff; font-size: 0.72rem; font-weight: 700; vertical-align: 2px;
  }

  .stats-grid {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.9rem; margin-bottom: 2rem;
  }
  .stat-card {
    display: flex; flex-direction: column; gap: 0.15rem;
    border-radius: 26px; padding: 1.1rem 1.2rem 1.15rem; color: var(--tile-ink);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .stat-card:hover { translate: 0 -3px; box-shadow: var(--shadow); }
  .s-ico {
    width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center;
    background: var(--tile-inner); transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .stat-card:hover .s-ico { rotate: -14deg; scale: 1.1; }
  .num {
    font-size: clamp(1.8rem, 1.3rem + 1.2vw, 2.5rem); font-weight: 700; letter-spacing: -0.035em;
    line-height: 1.1; margin-top: 0.7rem; font-variant-numeric: tabular-nums;
  }
  .stat-card:hover .num { animation: pop 420ms var(--ease-out); }
  .lbl { font-size: 0.82rem; opacity: 0.72; font-weight: 500; }
  .sky { background: var(--tile-sky); }
  .mint { background: var(--tile-mint); }
  .lilac { background: var(--tile-lilac); }
  .butter { background: var(--tile-butter); }
  .peach { background: var(--tile-peach); }

  .sec { font-size: 1.35rem; letter-spacing: -0.025em; margin-bottom: 1rem; }
  .quick-links { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; }
  .link-card {
    position: relative; display: flex; flex-direction: column;
    background: var(--surface); border-radius: 28px; padding: 1.4rem 1.4rem 1.3rem;
    box-shadow: var(--shadow-sm); color: var(--text);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .link-card:hover { translate: 0 -4px; box-shadow: var(--shadow-md); }
  .icon {
    width: 50px; height: 50px; border-radius: 50%; display: grid; place-items: center;
    color: var(--tile-ink); margin-bottom: 1rem;
    transition: rotate var(--dur-3) var(--ease-out), scale var(--dur-3) var(--ease-out);
  }
  .link-card:hover .icon { rotate: -12deg; scale: 1.08; }
  h3 { font-size: 1.05rem; font-weight: 700; letter-spacing: -0.015em; margin-bottom: 0.4rem; padding-right: 2.6rem; }
  p { font-size: 0.86rem; color: var(--muted); line-height: 1.5; }
  .go {
    position: absolute; top: 1.3rem; right: 1.3rem; width: 36px; height: 36px;
    transition: transform var(--dur-3) var(--ease-out), background-color var(--dur-2);
  }
  .link-card:hover .go { background: var(--accent); color: var(--on-accent); transform: rotate(-30deg); }

  @media (max-width: 1000px) {
    .quick-links { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 620px) {
    .quick-links { grid-template-columns: 1fr; }
  }
</style>
