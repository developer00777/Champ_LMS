<script lang="ts">
  import { tick } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { api, type CourseItemView, type CourseView, type EpisodeQuestion, type TranscriptSegment } from '$lib/api/client';
  import { isAdmin } from '$lib/stores/auth';
  import VideoPlayer from '$lib/components/VideoPlayer.svelte';
  import NotesView from '$lib/components/course/NotesView.svelte';
  import Transcript from '$lib/components/course/Transcript.svelte';
  import CourseQuiz from '$lib/components/course/CourseQuiz.svelte';
  import CourseTestStep from '$lib/components/course/CourseTestStep.svelte';
  import QnaPanel from '$lib/components/course/QnaPanel.svelte';
  import { icons, kindLabel } from '$lib/components/course/icons';
  import Breadcrumbs from '$lib/components/Breadcrumbs.svelte';
  import WatchLayout from '$lib/components/watch/WatchLayout.svelte';
  import WatchTabs from '$lib/components/watch/WatchTabs.svelte';
  import WatchInfo from '$lib/components/watch/WatchInfo.svelte';
  import PlaylistItem from '$lib/components/watch/PlaylistItem.svelte';
  import StagePlaceholder from '$lib/components/watch/StagePlaceholder.svelte';
  import CourseOverview from '$lib/components/watch/CourseOverview.svelte';
  import { clock, runtime } from '$lib/utils/transcribe';

  $: id = $page.params.id;

  let course: CourseView | null = null;
  let error = '';
  let currentId: string | null = null;
  let tab = 'transcript';
  let layoutRef: WatchLayout;
  let playerRef: VideoPlayer;
  let time = 0;
  let stream: { stream_url: string; embed_url: string } | null = null;
  let streamError = '';
  let segments: TranscriptSegment[] = [];
  let segmentsSource: string | null = null;
  let questions: EpisodeQuestion[] = [];
  let qnaRef: QnaPanel;
  let seenNotes = new Set<string>();

  const seenKey = () => `champ_seen_notes_${id}`;

  // A learner may skip ahead at most this far past the furthest point they have
  // reached in a course video (the server holds recorded progress to the same
  // 300 s: backend MAX_SKIP_SECONDS). Lifted once the episode is finished, so a
  // rewatch is free, and for admins previewing the course.
  const COURSE_MAX_SKIP_SECONDS = 5 * 60;
  const skipLimit = (item: CourseItemView) => ($isAdmin || item.completed ? null : COURSE_MAX_SKIP_SECONDS);

  // Load the course; the address decides between the course page and the
  // player (see `overview` below).
  let loadedCourse = '';
  $: if (id && id !== loadedCourse) { loadedCourse = id; course = null; error = ''; currentId = null; load(false); }

  async function load(keepPosition = true) {
    try {
      const c = await api.course(id);
      course = c;
      try { seenNotes = new Set(JSON.parse(localStorage.getItem(seenKey()) ?? '[]')); } catch { seenNotes = new Set(); }
      if (!keepPosition || !currentId || !c.items.some(i => i.id === currentId)) {
        const q = $page.url.searchParams;
        const wanted = c.items.find(i => i.id === q.get('item') || i.ref_id === q.get('ref'));
        const pick = (wanted ?? resumeItem(c)) ?? null;
        if (overview) currentId = pick?.id ?? null; else select(pick);
      }
    } catch (e: any) { error = e.status === 404 ? "This course isn't available to you." : e.message; }
  }

  // /course/{id} on its own is the course page (course cards and the
  // breadcrumb's course link). ?item= / ?ref= open that step in the player;
  // ?play=1 (Start / Resume buttons) opens the player where the learner left off.
  $: urlItem = $page.url.searchParams.get('item') || $page.url.searchParams.get('ref');
  $: play = $page.url.searchParams.has('play');
  $: overview = !urlItem && !play;
  $: if (course && course.items.length && play && !urlItem) select(resumeItem(course));
  // Back / Forward change the address without calling select(): follow it,
  // so the player always shows the step the address names.
  $: if (course && urlItem) {
    const it = course.items.find(i => i.id === urlItem || i.ref_id === urlItem);
    if (it && it.id !== currentId) currentId = it.id;
  }
  // Coming back to the course page: drop the open video (its stream link can
  // expire) and refresh progress, so Resume starts from where the learner
  // really is and the skip limit counts from their real furthest point.
  let wasOverview = true;
  $: if (overview !== wasOverview) {
    wasOverview = overview;
    if (overview && course) { loadedFor = null; stream = null; load(); }
  }

  function isDone(i: CourseItemView) { return i.kind === 'notes' ? seenNotes.has(i.id) : i.done; }
  function resumeItem(c: CourseView) {
    return c.items.find(i => !i.locked && !(i.kind === 'notes' ? seenNotes.has(i.id) : i.done)) ?? c.items[0];
  }
  // The next item can be a quiz, test or notes page, which has no episode number.
  function resumeLabel(c: CourseView): string {
    if (!c.items.some(isDone)) return 'Start course';
    if (c.items.every(isDone)) return 'Watch again';
    const r = resumeItem(c);
    return r.kind === 'video' && r.episode_number ? `Resume episode ${r.episode_number}` : `Continue: ${kindLabel[r.kind] ?? r.title}`;
  }

  $: current = course?.items.find(i => i.id === currentId) ?? null;
  $: idx = course && current ? course.items.indexOf(current) : -1;
  $: prev = course && idx > 0 ? course.items[idx - 1] : null;
  $: next = course && idx >= 0 && idx < course.items.length - 1 ? course.items[idx + 1] : null;
  $: videos = course?.items.filter(i => i.kind === 'video') ?? [];
  $: doneCount = course ? course.items.filter(isDone).length : 0;
  $: sectionTitle = course && current ? course.sections.find(s => s.id === current!.section_id)?.title ?? '' : '';

  // Load the stream and transcript whenever a different video is on screen.
  let loadedFor: string | null = null;
  $: if (current && current.kind === 'video' && current.ref_id !== loadedFor && !overview) openVideo(current);
  async function openVideo(item: CourseItemView) {
    loadedFor = item.ref_id; stream = null; streamError = ''; segments = []; segmentsSource = null; time = 0; questions = [];
    api.episodeQuestions(id, item.ref_id).then(q => { if (loadedFor === item.ref_id) questions = q; }).catch(() => { /* Q&A is optional */ });
    // Every await checks the learner is still on this video: if they clicked on
    // quickly, a slow reply for the old one must not load into the new player
    // (it would play the old video and record its progress as the new one's).
    try {
      const s = await api.streamUrl(item.ref_id);
      if (loadedFor !== item.ref_id) return;
      stream = s;
    } catch (e: any) {
      if (loadedFor !== item.ref_id) return;
      streamError = e.status === 425 ? 'This video is still processing. Try again in a few minutes.' : e.message;
    }
    if (item.has_transcript) {
      try {
        const t = await api.courseTranscript(id, item.ref_id);
        if (loadedFor !== item.ref_id) return;
        segments = t.segments; segmentsSource = t.source;
      } catch { /* transcript is optional */ }
    }
  }

  $: if (current?.kind === 'notes' && !seenNotes.has(current.id)) {
    seenNotes.add(current.id); seenNotes = seenNotes;
    try { localStorage.setItem(seenKey(), JSON.stringify([...seenNotes])); } catch { /* private mode */ }
  }

  function go(item: CourseItemView | null) {
    if (!item || item.locked) return;
    select(item);
  }
  // Show an item and record it in the address bar, so a reload, a shared link
  // or the back button returns to the same step.
  let urlPending = '';
  $: if (urlItem) urlPending = '';
  function select(item: CourseItemView | null) {
    if (!item) return;
    currentId = item.id;
    const url = new URL($page.url);
    const q = url.searchParams;
    if (q.get('item') === item.id && !q.has('ref') && !q.has('play')) return;
    if (urlPending === url.pathname + item.id) return; // already on its way
    urlPending = url.pathname + item.id;
    // Leaving the course page is a real step, so Back returns to it; moving
    // between items in the player just updates the address.
    const fromOverview = !q.get('item') && !q.get('ref') && !q.has('play');
    q.set('item', item.id); q.delete('ref'); q.delete('play'); q.delete('view');
    goto(url.pathname + url.search, { replaceState: !fromOverview, noScroll: !fromOverview, keepFocus: true });
  }

  // The player's Q&A button: leave full screen, open the Q&A tab, and pin the
  // question box to the moment the video was paused at.
  async function openQna(at: number) {
    await layoutRef?.exitTheater();
    tab = 'qna';
    await tick();
    qnaRef?.focusAsk(at);
  }

  async function openAttachment(item: CourseItemView) {
    try {
      const blob = await api.noteAttachment(id, item.ref_id);
      window.open(URL.createObjectURL(blob), '_blank', 'noopener');
    } catch (e: any) { error = e.message; }
  }

  const isSeries = (c: CourseView) => c.format === 'series';
  const watchedPct = (v: CourseItemView) =>
    v.completed ? 100 : v.duration_seconds ? Math.min(100, Math.round(((v.watched_seconds ?? 0) / v.duration_seconds) * 100)) : 0;
  function context(c: CourseView, it: CourseItemView): string {
    const where = it.kind === 'video' ? `Episode ${it.episode_number} of ${videos.length}` : kindLabel[it.kind] ?? it.title;
    const sec = c.sections.length > 1 ? sectionTitle : '';
    return sec ? `${sec} › ${where}` : where;
  }
  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'transcript', label: 'Transcript' },
    { id: 'notes', label: 'Notes' },
    { id: 'qna', label: 'Q&A' },
  ];
  $: tabList = tabs.map(t => (t.id === 'qna' && questions.length ? { ...t, label: `Q&A (${questions.length})` } : t));

  const sectionItems = (sid: string) => course?.items.filter(i => i.section_id === sid) ?? [];
  const fmtSize = (n?: number | null) => (n ? (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`) : '');
  function sub(i: CourseItemView): string {
    if (i.kind === 'video') return `Episode ${i.episode_number}`;
    if (i.kind === 'quiz') return `AI quiz · ${i.question_count} questions${i.passed ? ' · passed' : ''}`;
    if (i.kind === 'notes') return `Notes${i.attachment_name ? ' + PDF' : ''}`;
    const s = i.state;
    return `Test · ${i.passed ? 'passed' : s === 'approved' ? `${i.attempts_left} attempt${i.attempts_left === 1 ? '' : 's'} ready` : s === 'pending' ? 'waiting for approval' : s === 'not_allowed' ? 'not open to you' : 'needs approval'}`;
  }
</script>

<svelte:head><title>{course?.title ?? 'Course'} — Champ LMS</title></svelte:head>

{#if error && !course}
  <div class="empty-state ui-rise"><span class="es-ico danger">{@html icons.lock}</span><h2>{error}</h2><p class="muted">Courses appear once your admin opens them to you.</p><a href="/" class="btn">{@html icons.back} Back home</a></div>
{:else if !course}
  <!-- Same shape as the watch layout: player + title on the left, playlist on the right. -->
  <div class="sk-row">
    <div class="sk">
      <div class="ui-skeleton" style="aspect-ratio:16/9;border-radius:28px"></div>
      <div class="ui-skeleton" style="height:28px;width:55%;border-radius:10px"></div>
    </div>
    <div class="ui-skeleton" style="height:420px;border-radius:28px"></div>
  </div>
{:else if !course.items.length}
  <div class="empty-state ui-rise"><span class="es-ico">{@html icons.video}</span><h2>{course.title}</h2><p class="muted">There's nothing in this course yet.</p>{#if $isAdmin}<a class="btn primary" href="/admin/courses/{course.id}">Open the canvas</a>{/if}</div>

<!-- =================== Course page (the breadcrumb's course link) =================== -->
{:else if overview}
  <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: course.title }]} />
  {#if $isAdmin}<div class="admin-bar">Previewing as a learner. <a href="/admin/courses/{course.id}">Back to the canvas</a></div>{/if}
  <CourseOverview
    title={course.title}
    badge={isSeries(course) ? 'Series' : 'Course'}
    description={course.description}
    thumb={course.thumbnail_url ?? videos[0]?.thumbnail_url ?? null}
    meta={[`${videos.length} episode${videos.length === 1 ? '' : 's'}`, runtime(course.runtime_seconds), course.category].filter(Boolean).join(' · ')}
    done={doneCount} total={course.items.length}
    resumeLabel={resumeLabel(course)}
    onResume={() => course && go(resumeItem(course))}
    onOpen={key => go(course?.items.find(i => i.id === key) ?? null)}
    sections={course.sections.map((s, si) => ({
      title: course && course.sections.length > 1
        ? (isSeries(course) ? `Season ${si + 1} · ${s.title}` : `${si + 1}. ${s.title}`)
        : (course && isSeries(course) ? 'Episodes' : 'Course content'),
      rows: sectionItems(s.id).map(it => ({
        key: it.id, title: it.title, sub: sub(it), kind: it.kind, thumb: it.thumbnail_url,
        duration: it.kind === 'video' ? clock(it.duration_seconds) : it.kind === 'test' && it.duration_minutes ? `${it.duration_minutes}m` : '',
        done: isDone(it), locked: it.locked, lockedHint: 'Pass the quiz before this to unlock it',
        progress: it.kind === 'video' ? watchedPct(it) : 0,
      })),
    }))}
  />

<!-- =================== One standard watch layout for every course (series or full) =================== -->
{:else}
  <!-- Home › Course (the course page) › current step -->
  <Breadcrumbs items={[
    { label: 'Home', href: '/' },
    { label: course.title, href: `/course/${course.id}` },
    ...(current ? [{ label: current.title }] : []),
  ]} />
  {#if $isAdmin}<div class="admin-bar">Previewing as a learner. <a href="/admin/courses/{course.id}">Back to the canvas</a></div>{/if}
  <WatchLayout bind:this={layoutRef}
    context={current ? context(course, current) : ''}
    onPrev={() => go(prev)} onNext={() => go(next)}
    prevDisabled={!prev || prev.locked} nextDisabled={!next || next.locked}
    stage={!!current && current.kind === 'video' && !current.locked}
    sideLabel={isSeries(course) ? 'Episodes' : 'Course map'}
    sideTitle={course.title}
    sideProgress={Math.round((doneCount / course.items.length) * 100)}
    sideMeta={isSeries(course)
      ? `${doneCount} of ${videos.length} watched · ${runtime(course.runtime_seconds)}`
      : `${doneCount} of ${course.items.length} done · ${runtime(course.runtime_seconds)} of video`}
  >
    <svelte:fragment slot="stage">
      {#if current && current.kind === 'video'}
        {#key current.id}
          {#if stream}
            <VideoPlayer bind:this={playerRef} episodeId={current.ref_id} streamUrl={stream.stream_url} embedUrl={stream.embed_url}
              startAt={current.completed ? 0 : current.watched_seconds ?? 0}
              skipLimitSeconds={skipLimit(current)} furthestStart={current.watched_seconds ?? 0}
              clipStart={current.clip_start ?? 0} clipEnd={current.clip_end ?? null} edits={current.edits ?? null}
              captions={segments} onQna={openQna} qnaCount={questions.length}
              onFullscreen={() => layoutRef?.toggleTheater()}
              onTime={t => (time = t)} onComplete={() => load()}
              onAutoAdvance={() => next && next.kind === 'video' && !next.locked && go(next)} />
          {:else}
            <StagePlaceholder busy={!streamError} message={streamError || 'Loading video…'} />
          {/if}
        {/key}
      {/if}
    </svelte:fragment>

    <svelte:fragment slot="side">
      {#each course.sections as s, si (s.id)}
        {@const list = sectionItems(s.id)}
        {#if course.sections.length > 1}
          <div class="c-sec-h">{isSeries(course) ? `Season ${si + 1} · ${s.title}` : `${si + 1}. ${s.title}`}<span>{list.filter(isDone).length}/{list.length}</span></div>
        {/if}
        {#each list as it (it.id)}
          <PlaylistItem
            title={it.title} sub={sub(it)} kind={it.kind} thumb={it.thumbnail_url}
            duration={it.kind === 'video' ? clock(it.duration_seconds) : it.kind === 'test' && it.duration_minutes ? `${it.duration_minutes}m` : ''}
            current={it.id === currentId} done={isDone(it)} locked={it.locked}
            lockedHint="Pass the quiz before this to unlock it"
            progress={it.kind === 'video' ? watchedPct(it) : 0}
            on:click={() => go(it)} />
        {/each}
      {/each}
    </svelte:fragment>

    {#if current}
        {#if current.locked}
          <div class="box locked-box"><h2><span class="lk">{@html icons.lock}</span> Locked</h2><p class="muted">Pass the quiz before this item to unlock it.</p></div>
        {:else if current.kind === 'video'}
          <WatchInfo title={current.title}
            eyebrow={`Episode ${current.episode_number} · ${course.title}`}
            facts={[clock(current.duration_seconds), ...(current.completed ? ['Watched'] : [])]} />
          <WatchTabs tabs={tabList} bind:active={tab} />
          {#if tab === 'transcript'}
            <Transcript {segments} source={segmentsSource} {time} onSeek={t => playerRef?.seek(t)} />
          {:else if tab === 'qna'}
            <QnaPanel bind:this={qnaRef} courseId={course.id} episodeId={current.ref_id} {questions} {time} isAdmin={$isAdmin}
              onSeek={t => playerRef?.seek(t)} onChange={q => (questions = q)} />
          {:else if tab === 'notes'}
            <p class="src">{current.notes_source === 'ai' ? 'AI notes, reviewed by your admin' : current.notes ? 'Written by your admin' : ''}</p>
            <NotesView source={current.notes} />
            {#if course.items.some(i => i.kind === 'notes')}
              <div class="more-notes"><span class="eyebrow">Course notes</span>
                {#each course.items.filter(i => i.kind === 'notes') as n (n.id)}
                  <button class="filechip" on:click={() => go(n)}><span class="ti k-notes">{@html icons.notes}</span><b>{n.title}</b>{@html icons.next}</button>
                {/each}
              </div>
            {/if}
          {:else}
            <div class="overview ui-panel">
              {#if current.description}<p>{current.description}</p>{/if}
              {#if course.description}<p class="muted">{course.description}</p>{/if}
              <div class="facts">
                <span class="ui-pill sky fact">{videos.length} videos</span>
                <span class="ui-pill lilac fact">{course.items.filter(i => i.kind === 'quiz').length} AI quizzes</span>
                <span class="ui-pill mint fact">{course.items.filter(i => i.kind === 'notes').length} notes</span>
                <span class="ui-pill butter fact">{course.items.filter(i => i.kind === 'test').length} tests</span>
                <span class="ui-pill fact">{runtime(course.runtime_seconds)}</span>
              </div>
            </div>
          {/if}
        {:else if current.kind === 'quiz'}
          {#key current.id}
            <CourseQuiz courseId={course.id} item={current} nextTitle={next?.title ?? null} onDone={() => load()} onNext={() => go(next)} />
          {/key}
        {:else if current.kind === 'test'}
          <CourseTestStep courseId={course.id} item={current} onChanged={() => load()} />
        {:else}
          <article class="box">
            <p class="src">{current.source === 'ai' ? 'AI draft, reviewed by your admin' : 'Written by your admin'}</p>
            <h2>{current.title}</h2>
            <NotesView source={current.body} />
            {#if current.attachment_name}
              <button class="filechip" on:click={() => current && openAttachment(current)}>
                <span class="ti k-notes">{@html icons.file}</span><b class="mono">{current.attachment_name}</b><span class="hint">PDF · {fmtSize(current.attachment_size)}</span>
              </button>
            {/if}
          </article>
        {/if}
    {/if}
  </WatchLayout>
{/if}

<style>
  .muted { color: var(--muted); }
  .hint { font-size: 0.76rem; color: var(--muted); }
  .mono { font-family: ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; }
  .empty-state {
    max-width: 640px; margin: 2rem auto 0; padding: 3rem 1.5rem; text-align: center; display: grid; gap: 0.7rem; justify-items: center;
    border-radius: 32px; background: var(--surface); box-shadow: var(--shadow-sm);
  }
  .es-ico {
    width: 64px; height: 64px; border-radius: 50%; display: grid; place-items: center; font-size: 1.5rem;
    background: var(--tile-sky); color: var(--tile-ink); animation: pop 520ms var(--ease-out);
  }
  .es-ico.danger { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger); }
  .sk { display: grid; gap: 1.2rem; }
  .sk-row { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 1.2rem; }
  @media (max-width: 1079px) { .sk-row { grid-template-columns: 1fr; } }
  .admin-bar {
    display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;
    margin-bottom: 1rem; padding: 0.6rem 0.75rem 0.6rem 1.1rem; border-radius: 999px;
    background: var(--tile-butter); color: var(--tile-ink); font-size: 0.86rem; font-weight: 500;
    animation: rise 420ms var(--ease-out) backwards;
  }
  .admin-bar a {
    margin-left: auto; height: 32px; display: inline-flex; align-items: center; padding: 0 0.9rem; border-radius: 999px;
    background: var(--accent); color: var(--on-accent); font-weight: 600; font-size: 0.82rem;
    transition: translate var(--dur-2) var(--ease-out);
  }
  .admin-bar a:hover { translate: 0 -1px; }
  .btn {
    display: inline-flex; align-items: center; gap: 0.4rem; height: 42px; padding: 0 1.2rem; border-radius: 999px;
    font-weight: 600; font-size: 0.88rem; background: var(--surface2); color: var(--text); white-space: nowrap;
    transition: background-color var(--dur-2) var(--ease-out), translate var(--dur-2) var(--ease-out), box-shadow var(--dur-2);
  }
  .btn:hover:not(:disabled) { background: var(--surface3); translate: 0 -1px; }
  .btn.primary { background: var(--accent); color: var(--on-accent); }
  .btn.primary:hover:not(:disabled) { background: var(--accent-hover); box-shadow: var(--shadow); }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn :global(svg) { transition: translate var(--dur-2) var(--ease-out); }
  .btn:hover:not(:disabled) :global(svg) { translate: 2px 0; }
  /* .ui-pill (app.css) with the tile colours; same size as the facts under the video title. */
  .fact { height: 30px; padding: 0 0.8rem; font-size: 0.8rem; animation: pop 420ms var(--ease-out) backwards; }
  .facts .fact:nth-child(1) { animation-delay: 100ms; }
  .facts .fact:nth-child(2) { animation-delay: 150ms; }
  .facts .fact:nth-child(3) { animation-delay: 200ms; }
  .facts .fact:nth-child(4) { animation-delay: 250ms; }
  .facts .fact:nth-child(5) { animation-delay: 300ms; }
  .eyebrow { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  .src { font-size: 0.76rem; color: var(--muted); margin-bottom: 0.4rem; }
  .k-notes { --kc: var(--teal); }
  .ti { color: var(--kc, var(--muted)); display: inline-flex; }

  /* playlist section headers (the rows themselves are PlaylistItem) */
  .c-sec-h { display: flex; justify-content: space-between; gap: 0.5rem; padding: 0.7rem 0.55rem 0.3rem; font-weight: 600; font-size: 0.86rem; }
  .c-sec-h span {
    font-weight: 600; font-size: 0.72rem; color: var(--text-secondary); font-variant-numeric: tabular-nums;
    background: var(--surface2); border-radius: 99px; padding: 0.1rem 0.5rem;
  }
  .overview { display: grid; gap: 0.55rem; padding: 1.4rem 1.5rem; line-height: 1.55; }
  .facts { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.4rem; }
  .more-notes { margin-top: 1.2rem; display: grid; gap: 0.4rem; justify-items: start; }
  .filechip {
    display: flex; gap: 0.6rem; align-items: center; padding: 0.6rem 0.9rem 0.6rem 0.6rem; border-radius: 18px; font-size: 0.86rem;
    text-align: left; background: var(--surface); box-shadow: var(--shadow-sm); margin-top: 0.4rem;
    transition: translate var(--dur-2) var(--ease-out), box-shadow var(--dur-2);
  }
  .filechip:hover { translate: 0 -2px; box-shadow: var(--shadow); }
  .filechip .ti { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-mint); color: var(--tile-ink); }
  .box { background: var(--surface); border-radius: var(--radius-xl); box-shadow: var(--shadow-sm); padding: 1.6rem; display: grid; gap: 0.75rem; animation: rise 480ms var(--ease-out) backwards; }
  .box h2 { display: flex; gap: 0.5rem; align-items: center; font-size: 1.4rem; letter-spacing: -0.02em; }
  .lk {
    width: 40px; height: 40px; border-radius: 50%; display: inline-grid; place-items: center;
    background: var(--tile-butter); color: var(--tile-ink); animation: wiggle 600ms var(--ease-out) 300ms;
  }
</style>
