<script lang="ts">
  import { onDestroy, onMount, tick } from 'svelte';
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
  import Thumb from '$lib/components/Thumb.svelte';
  import { clock, runtime } from '$lib/utils/transcribe';

  $: id = $page.params.id;

  let course: CourseView | null = null;
  let error = '';
  let currentId: string | null = null;
  let mode: 'browse' | 'watch' = 'browse'; // series only
  let tab: 'overview' | 'notes' | 'transcript' | 'qna' = 'transcript';
  let sideTab: 'episodes' | 'transcript' | 'notes' | 'qna' = 'episodes';
  let mapOpen = true;
  let mapFull = false;
  let theater = false;
  let stageEl: HTMLElement;
  let mapEl: HTMLElement;
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

  async function load(keepPosition = true) {
    try {
      const c = await api.course(id);
      course = c;
      try { seenNotes = new Set(JSON.parse(localStorage.getItem(seenKey()) ?? '[]')); } catch { seenNotes = new Set(); }
      if (!keepPosition || !currentId || !c.items.some(i => i.id === currentId)) {
        const q = $page.url.searchParams;
        const wanted = c.items.find(i => i.id === q.get('item') || i.ref_id === q.get('ref'));
        currentId = (wanted ?? resumeItem(c))?.id ?? null;
        if (wanted && c.format === 'series') mode = 'watch';
      }
    } catch (e: any) { error = e.status === 404 ? "This course isn't available to you." : e.message; }
  }
  onMount(() => { load(false); document.addEventListener('fullscreenchange', onFs); });
  onDestroy(() => { if (typeof document !== 'undefined') document.removeEventListener('fullscreenchange', onFs); });

  function isDone(i: CourseItemView) { return i.kind === 'notes' ? seenNotes.has(i.id) : i.done; }
  function resumeItem(c: CourseView) {
    return c.items.find(i => !i.locked && !(i.kind === 'notes' ? seenNotes.has(i.id) : i.done)) ?? c.items[0];
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
  $: if (current && current.kind === 'video' && current.ref_id !== loadedFor && (course?.format !== 'series' || mode === 'watch')) openVideo(current);
  async function openVideo(item: CourseItemView) {
    loadedFor = item.ref_id; stream = null; streamError = ''; segments = []; segmentsSource = null; time = 0; questions = [];
    api.episodeQuestions(id, item.ref_id).then(q => { if (loadedFor === item.ref_id) questions = q; }).catch(() => { /* Q&A is optional */ });
    try { stream = await api.streamUrl(item.ref_id); }
    catch (e: any) { streamError = e.status === 425 ? 'This video is still processing. Try again in a few minutes.' : e.message; }
    if (item.has_transcript) {
      try { const t = await api.courseTranscript(id, item.ref_id); segments = t.segments; segmentsSource = t.source; } catch { /* transcript is optional */ }
    }
  }

  $: if (current?.kind === 'notes' && !seenNotes.has(current.id)) {
    seenNotes.add(current.id); seenNotes = seenNotes;
    try { localStorage.setItem(seenKey(), JSON.stringify([...seenNotes])); } catch { /* private mode */ }
  }

  function go(item: CourseItemView | null) {
    if (!item || item.locked) return;
    currentId = item.id;
    if (mapFull) toggleMapFull();
    if (course?.format === 'series') mode = 'watch';
    const url = new URL($page.url); url.searchParams.set('item', item.id); url.searchParams.delete('ref');
    goto(url.pathname + url.search, { replaceState: true, noScroll: true, keepFocus: true });
  }

  // The player's Q&A button: leave full screen, open the Q&A tab, and pin the
  // question box to the moment the video was paused at.
  async function openQna(at: number) {
    if (theater) await toggleTheater();
    if (course?.format === 'series') sideTab = 'qna'; else tab = 'qna';
    await tick();
    qnaRef?.focusAsk(at);
  }

  async function openAttachment(item: CourseItemView) {
    try {
      const blob = await api.noteAttachment(id, item.ref_id);
      window.open(URL.createObjectURL(blob), '_blank', 'noopener');
    } catch (e: any) { error = e.message; }
  }

  // ---- full screen ---------------------------------------------------------
  function onFs() { if (!document.fullscreenElement) { theater = false; mapFull = false; } }
  async function toggleTheater() {
    theater = !theater;
    if (theater) mapOpen = false;
    try {
      if (theater && stageEl?.requestFullscreen) await stageEl.requestFullscreen();
      else if (!theater && document.fullscreenElement) await document.exitFullscreen();
    } catch { /* not allowed here: the CSS version still fills the window */ }
    if (!theater) mapOpen = true;
  }
  async function toggleMapFull() {
    mapFull = !mapFull; mapOpen = true;
    try {
      if (mapFull && mapEl?.requestFullscreen) await mapEl.requestFullscreen();
      else if (!mapFull && document.fullscreenElement) await document.exitFullscreen();
    } catch { /* CSS overlay fallback */ }
  }

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
  <div class="sk">
    <div class="ui-skeleton" style="height:240px;border-radius:32px"></div>
    <div class="sk-row">
      <div class="ui-skeleton" style="height:420px;border-radius:28px"></div>
      <div class="ui-skeleton" style="height:420px;border-radius:28px"></div>
    </div>
  </div>
{:else if !course.items.length}
  <div class="empty-state ui-rise"><span class="es-ico">{@html icons.video}</span><h2>{course.title}</h2><p class="muted">There's nothing in this course yet.</p>{#if $isAdmin}<a class="btn primary" href="/admin/courses/{course.id}">Open the canvas</a>{/if}</div>

<!-- =================== SERIES (Netflix-style) =================== -->
{:else if course.format === 'series'}
  <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: course.title }]} />
  {#if $isAdmin}<div class="admin-bar">Previewing as a learner. <a href="/admin/courses/{course.id}">Back to the canvas</a></div>{/if}
  {#if mode === 'browse'}
    {@const resume = resumeItem(course)}
    {@const heroImg = (!course.thumbnail_has_text && course.thumbnail_url) || videos[0]?.thumbnail_url}
    <section class="s-hero ui-rise" class:with-poster={course.thumbnail_has_text && course.thumbnail_url}
      style={heroImg ? `--img:url(${heroImg})` : ''}>
      {#if course.thumbnail_has_text && course.thumbnail_url}
        <!-- A text design already shows the title, so it sits beside this one rather than behind it. -->
        <img class="s-poster" src={course.thumbnail_url} alt="" />
      {/if}
      <div class="s-hero-in">
        <span class="fbadge">Series</span>
        <h1>{course.title}</h1>
        <p class="meta">{videos.length} episodes · {runtime(course.runtime_seconds)}{course.category ? ` · ${course.category}` : ''}</p>
        {#if course.description}<p class="desc">{course.description}</p>{/if}
        <button class="btn primary" on:click={() => go(resume)}>{@html icons.play} {doneCount ? `Resume episode ${resume.episode_number}` : 'Play episode 1'}</button>
      </div>
    </section>
    {#each course.sections as s, si (s.id)}
      {#if course.sections.length > 1}<h3 class="season">Season {si + 1} · {s.title}</h3>{:else}<h2 class="row-h">Episodes</h2>{/if}
      <ol class="eps">
        {#each sectionItems(s.id) as v, vi (v.id)}
          {@const pct = v.completed ? 100 : v.duration_seconds ? Math.min(100, Math.round(((v.watched_seconds ?? 0) / v.duration_seconds) * 100)) : 0}
          <li class="ui-rise" style="--i:{Math.min(vi + 2, 12)}">
            <button class="ep" on:click={() => go(v)}>
              <span class="ep-n">{v.episode_number}</span>
              <span class="ep-th">{#if v.thumbnail_url}<Thumb src={v.thumbnail_url} />{/if}{@html icons.play}<i style="width:{pct}%"></i></span>
              <span class="ep-b"><b>{v.title}</b>{#if v.description}<span>{v.description}</span>{/if}</span>
              <span class="ep-d">{clock(v.duration_seconds)}</span>
            </button>
          </li>
        {/each}
      </ol>
    {/each}
  {:else if current}
    <div class="w-top">
      <button class="btn ghost" on:click={() => { mode = 'browse'; loadedFor = null; }}>{@html icons.back} {course.title}</button>
      <span class="muted">Episode {current.episode_number} of {videos.length}</span>
    </div>
    <div class="w-grid">
      <div class="stage-col" bind:this={stageEl} class:theater>
        {#key current.id}
          {#if stream}
            <VideoPlayer bind:this={playerRef} episodeId={current.ref_id} streamUrl={stream.stream_url} embedUrl={stream.embed_url}
              startAt={current.completed ? 0 : current.watched_seconds ?? 0}
              skipLimitSeconds={skipLimit(current)} furthestStart={current.watched_seconds ?? 0}
              clipStart={current.clip_start ?? 0} clipEnd={current.clip_end ?? null}
              captions={segments} onQna={openQna} qnaCount={questions.length}
              onTime={t => (time = t)} onComplete={() => load()} onAutoAdvance={() => next && go(next)} />
          {:else}
            <div class="player-ph">{streamError || 'Loading video…'}</div>
          {/if}
        {/key}
        <button class="fs-btn" on:click={toggleTheater} aria-label={theater ? 'Exit full screen' : 'Full screen'}>{@html theater ? icons.shrink : icons.expand}</button>
      </div>
      <aside class="w-side">
        <div class="subtabs">
          <button class:on={sideTab === 'episodes'} on:click={() => (sideTab = 'episodes')}>Episodes</button>
          <button class:on={sideTab === 'transcript'} on:click={() => (sideTab = 'transcript')}>Transcript</button>
          <button class:on={sideTab === 'notes'} on:click={() => (sideTab = 'notes')}>Notes</button>
          <button class:on={sideTab === 'qna'} on:click={() => (sideTab = 'qna')}>Q&amp;A{questions.length ? ` (${questions.length})` : ''}</button>
        </div>
        <div class="w-side-b">
          {#if sideTab === 'episodes'}
            {#each videos as v (v.id)}
              <button class="w-ep" class:cur={v.id === current.id} on:click={() => go(v)}>
                <span class="ep-th sm">{#if v.thumbnail_url}<Thumb src={v.thumbnail_url} />{/if}{@html icons.play}</span>
                <span class="ep-b"><b>{v.episode_number}. {v.title}</b><span class="mono">{clock(v.duration_seconds)}{v.completed ? ' · watched' : ''}</span></span>
              </button>
            {/each}
          {:else if sideTab === 'transcript'}
            <Transcript {segments} source={segmentsSource} {time} onSeek={t => playerRef?.seek(t)} />
          {:else if sideTab === 'qna'}
            <QnaPanel bind:this={qnaRef} courseId={course.id} episodeId={current.ref_id} {questions} {time} isAdmin={$isAdmin}
              onSeek={t => playerRef?.seek(t)} onChange={q => (questions = q)} />
          {:else}
            <p class="src">{current.notes_source === 'ai' ? 'AI notes, reviewed by your admin' : current.notes ? 'Written by your admin' : ''}</p>
            <NotesView source={current.notes} />
          {/if}
        </div>
      </aside>
    </div>
    <div class="w-meta"><h2>{current.title}</h2>{#if current.description}<p class="muted">{current.description}</p>{/if}</div>
  {/if}

<!-- =================== COURSE (full course player) =================== -->
{:else}
  <Breadcrumbs items={[{ label: 'Home', href: '/' }, { label: course.title }]} />
  {#if $isAdmin}<div class="admin-bar">Previewing as a learner. <a href="/admin/courses/{course.id}">Back to the canvas</a></div>{/if}
  <div class="cp" class:map-closed={!mapOpen} class:theater bind:this={stageEl}>
    <aside class="cmap ui-rise" class:is-full={mapFull} bind:this={mapEl} aria-label="Course map">
      <div class="cmap-h">
        <div class="row">
          <h3>{course.title}</h3>
          <span class="row tight">
            <button class="icon-btn" on:click={toggleMapFull} aria-label={mapFull ? 'Exit full screen map' : 'Full screen map'}>{@html mapFull ? icons.shrink : icons.expand}</button>
            {#if !mapFull}<button class="icon-btn" on:click={() => (mapOpen = false)} aria-label="Hide course map">{@html icons.panel}</button>{/if}
          </span>
        </div>
        <div class="bar"><i style="width:{Math.round((doneCount / course.items.length) * 100)}%"></i></div>
        <span class="hint mono">{doneCount} of {course.items.length} done · {runtime(course.runtime_seconds)} of video</span>
      </div>
      <div class="cmap-body">
        {#each course.sections as s, si (s.id)}
          {@const list = sectionItems(s.id)}
          <div class="c-sec">
            <div class="c-sec-h">{si + 1}. {s.title}<span>{list.filter(isDone).length}/{list.length}</span></div>
            {#each list as it (it.id)}
              <button class="mi" class:cur={it.id === currentId} class:done={isDone(it)} class:locked={it.locked} on:click={() => go(it)}
                title={it.locked ? 'Pass the quiz before this to unlock it' : ''}>
                <span class="mi-st">{@html it.locked ? icons.lock : isDone(it) ? icons.check : ''}</span>
                <span class="mi-t"><span>{it.title}</span><small class="k-{it.kind}"><span class="ti">{@html icons[it.kind]}</span>{sub(it)}</small></span>
                <span class="mi-r">{it.kind === 'video' ? clock(it.duration_seconds) : it.kind === 'test' && it.duration_minutes ? `${it.duration_minutes}m` : ''}</span>
              </button>
            {/each}
          </div>
        {/each}
      </div>
    </aside>

    <div class="cmain ui-rise" style="--i:1">
      {#if current}
        <div class="crumb">
          <span class="row tight">
            {#if !mapOpen}<button class="btn sm" on:click={() => (mapOpen = true)}>{@html icons.panel} Course map</button>{/if}
            <span>{sectionTitle} › {current.kind === 'video' ? `Episode ${current.episode_number}` : kindLabel[current.kind]}</span>
          </span>
          <span class="row tight">
            <button class="btn sm ghost" on:click={() => go(prev)} disabled={!prev || prev.locked}>{@html icons.back} Previous</button>
            <button class="btn sm" on:click={() => go(next)} disabled={!next || next.locked}>Next {@html icons.next}</button>
          </span>
        </div>

        {#if current.locked}
          <div class="box locked-box"><h2><span class="lk">{@html icons.lock}</span> Locked</h2><p class="muted">Pass the quiz before this item to unlock it.</p></div>
        {:else if current.kind === 'video'}
          <div class="player-wrap">
            {#key current.id}
              {#if stream}
                <VideoPlayer bind:this={playerRef} episodeId={current.ref_id} streamUrl={stream.stream_url} embedUrl={stream.embed_url}
                  startAt={current.completed ? 0 : current.watched_seconds ?? 0}
                  skipLimitSeconds={skipLimit(current)} furthestStart={current.watched_seconds ?? 0}
                  clipStart={current.clip_start ?? 0} clipEnd={current.clip_end ?? null}
                  captions={segments} onQna={openQna} qnaCount={questions.length}
                  onTime={t => (time = t)} onComplete={() => load()} onAutoAdvance={() => next && next.kind === 'video' && go(next)} />
              {:else}
                <div class="player-ph">{streamError || 'Loading video…'}</div>
              {/if}
            {/key}
            <div class="player-tools">
              {#if theater}<button class="icon-btn light" on:click={() => (mapOpen = !mapOpen)} aria-label="Course map">{@html icons.panel}</button>{/if}
              <button class="icon-btn light" on:click={toggleTheater} aria-label={theater ? 'Exit full screen' : 'Full screen with course map'}>{@html theater ? icons.shrink : icons.expand}</button>
            </div>
          </div>
          <div class="ltabs">
            <button class:on={tab === 'overview'} on:click={() => (tab = 'overview')}>Overview</button>
            <button class:on={tab === 'notes'} on:click={() => (tab = 'notes')}>Notes</button>
            <button class:on={tab === 'transcript'} on:click={() => (tab = 'transcript')}>Transcript</button>
            <button class:on={tab === 'qna'} on:click={() => (tab = 'qna')}>Q&amp;A{questions.length ? ` (${questions.length})` : ''}</button>
          </div>
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
            <div class="overview">
              <h2>{current.title}</h2>
              {#if current.description}<p>{current.description}</p>{/if}
              {#if course.description}<p class="muted">{course.description}</p>{/if}
              <div class="facts">
                <span class="pill">{videos.length} videos</span>
                <span class="pill">{course.items.filter(i => i.kind === 'quiz').length} AI quizzes</span>
                <span class="pill">{course.items.filter(i => i.kind === 'notes').length} notes</span>
                <span class="pill">{course.items.filter(i => i.kind === 'test').length} tests</span>
                <span class="pill">{runtime(course.runtime_seconds)}</span>
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
    </div>
  </div>
{/if}

<style>
  .muted { color: var(--muted); }
  .hint { font-size: 0.76rem; color: var(--muted); }
  .mono { font-family: ui-monospace, Consolas, monospace; font-variant-numeric: tabular-nums; }
  .row { display: flex; gap: 0.5rem; align-items: center; justify-content: space-between; }
  .row.tight { justify-content: flex-start; gap: 0.35rem; }
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
  .sk-row { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 1.2rem; }
  @media (max-width: 920px) { .sk-row { grid-template-columns: 1fr; } }
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
  .btn.ghost { background: transparent; }
  .btn.ghost:hover:not(:disabled) { background: var(--surface2); }
  .btn.sm { height: 34px; padding: 0 0.85rem; font-size: 0.8rem; }
  .btn:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn :global(svg) { transition: translate var(--dur-2) var(--ease-out); }
  .btn:hover:not(:disabled) :global(svg) { translate: 2px 0; }
  .btn.ghost:hover:not(:disabled) :global(svg:first-child) { translate: -2px 0; }
  .icon-btn {
    display: inline-grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; color: var(--muted); font-size: 1.05rem;
    transition: background-color var(--dur-2), color var(--dur-2), scale var(--dur-2) var(--ease-out);
  }
  .icon-btn:hover { background: var(--surface2); color: var(--text); scale: 1.08; }
  .icon-btn.light { color: #fff; background: rgba(0, 0, 0, 0.5); }
  .icon-btn.light:hover { background: rgba(0, 0, 0, 0.7); color: #fff; }
  .pill {
    display: inline-flex; align-items: center; height: 30px; padding: 0 12px; border-radius: 99px; font-size: 0.78rem; font-weight: 600;
    background: var(--surface2); color: var(--text-secondary);
    animation: pop 420ms var(--ease-out) backwards;
  }
  .facts .pill:nth-child(1) { background: var(--tile-sky); color: var(--tile-ink); animation-delay: 100ms; }
  .facts .pill:nth-child(2) { background: var(--tile-lilac); color: var(--tile-ink); animation-delay: 150ms; }
  .facts .pill:nth-child(3) { background: var(--tile-mint); color: var(--tile-ink); animation-delay: 200ms; }
  .facts .pill:nth-child(4) { background: var(--tile-butter); color: var(--tile-ink); animation-delay: 250ms; }
  .facts .pill:nth-child(5) { animation-delay: 300ms; }
  .eyebrow { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  .src { font-size: 0.76rem; color: var(--muted); margin-bottom: 0.4rem; }
  .k-video { --kc: var(--info); } .k-quiz { --kc: var(--violet); } .k-test { --kc: var(--gold); } .k-notes { --kc: var(--teal); }
  .ti { color: var(--kc, var(--muted)); display: inline-flex; }

  /* series */
  .s-hero {
    border-radius: 32px; min-height: 240px; display: flex; align-items: flex-end; padding: 1.75rem; margin-bottom: 1.5rem; color: #f4f4f6;
    background: linear-gradient(to right, rgba(12, 12, 14, 0.94) 30%, rgba(12, 12, 14, 0.3)), var(--img, linear-gradient(135deg, #2a2233, #14141a)), #121214;
    background-size: cover; background-position: center; box-shadow: var(--shadow-md);
    transition: background-size 900ms var(--ease-out);
  }
  .s-hero-in { max-width: 560px; display: grid; gap: 0.7rem; justify-items: start; }
  .s-hero.with-poster { position: relative; }
  .s-poster {
    position: absolute; right: 2rem; top: 50%; transform: translateY(-50%); width: min(42%, 480px);
    aspect-ratio: 16 / 9; object-fit: cover; border-radius: 18px;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.08);
  }
  .with-poster .s-hero-in { max-width: min(560px, 52%); }
  @media (max-width: 860px) { .s-poster { display: none; } .with-poster .s-hero-in { max-width: 560px; } }
  .fbadge {
    font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; padding: 0.3rem 0.75rem; border-radius: 99px;
    background: var(--tile-lilac); color: var(--tile-ink); animation: pop 520ms var(--ease-out) 250ms backwards;
  }
  .s-hero h1 { font-size: clamp(1.8rem, 1.2rem + 2vw, 2.8rem); font-weight: 700; letter-spacing: -0.035em; line-height: 1.05; }
  .s-hero .meta { color: rgba(244, 244, 246, 0.75); font-size: 0.9rem; }
  .s-hero .desc { color: rgba(244, 244, 246, 0.85); line-height: 1.55; }
  .s-hero .btn.primary { background: #f4f4f6; color: #121214; margin-top: 0.4rem; }
  .s-hero .btn.primary:hover { background: #fff; }
  .row-h { font-size: 1.45rem; letter-spacing: -0.025em; margin-bottom: 0.8rem; }
  .season { font-size: 0.74rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin: 1.6rem 0 0.7rem 0.3rem; }
  .eps { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.6rem; }
  .ep {
    display: grid; grid-template-columns: 34px 180px minmax(0, 1fr) auto; gap: 1rem; align-items: center; width: 100%;
    padding: 0.6rem 1.1rem 0.6rem 0.6rem; border-radius: 24px; text-align: left; background: var(--surface); box-shadow: var(--shadow-sm);
    transition: translate var(--dur-3) var(--ease-out), box-shadow var(--dur-3) var(--ease-out);
  }
  .ep:hover { translate: 4px 0; box-shadow: var(--shadow); }
  .ep-n { font-size: 1.5rem; font-weight: 700; color: var(--muted); text-align: center; letter-spacing: -0.03em; transition: color var(--dur-2); }
  .ep:hover .ep-n { color: var(--text); }
  .ep-th {
    position: relative; aspect-ratio: 16/9; border-radius: 18px; display: grid; place-items: center; color: var(--tile-ink); font-size: 1.3rem; overflow: hidden;
    background-color: var(--tile-lilac);
  }
  .ep:hover .ep-th :global(.thumb-media), .w-ep:hover .ep-th :global(.thumb-media) { scale: 1.06; }
  .ep-th :global(svg) {
    position: relative; z-index: 1;
    width: 38px; height: 38px; padding: 10px; border-radius: 50%; background: var(--surface); color: var(--text);
    transition: scale var(--dur-3) var(--ease-out);
  }
  .ep:hover .ep-th :global(svg), .w-ep:hover .ep-th :global(svg) { scale: 1.15; }
  .ep-th i { position: absolute; z-index: 1; left: 0; bottom: 0; height: 4px; background: var(--brand); transform-origin: left; animation: grow 1s var(--ease-out) 400ms backwards; }
  @keyframes grow { from { transform: scaleX(0); } }
  .ep-th.sm { width: 104px; flex: none; font-size: 0.95rem; border-radius: 14px; }
  .ep-th.sm :global(svg) { width: 28px; height: 28px; padding: 7px; }
  .ep-b { display: grid; gap: 2px; min-width: 0; }
  .ep-b b { font-weight: 600; }
  .ep-b span { font-size: 0.82rem; color: var(--text-secondary); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .ep-d { font-size: 0.8rem; color: var(--muted); font-variant-numeric: tabular-nums; }
  @media (max-width: 620px) { .ep { grid-template-columns: 110px minmax(0, 1fr); } .ep-n, .ep-d { display: none; } }
  .w-top { display: flex; gap: 0.8rem; align-items: center; flex-wrap: wrap; margin-bottom: 0.8rem; }
  .w-grid { display: grid; gap: 1rem; grid-template-columns: minmax(0, 1fr); }
  @media (min-width: 1080px) { .w-grid { grid-template-columns: minmax(0, 1fr) 360px; align-items: start; } }
  .stage-col { position: relative; }
  .stage-col.theater { position: fixed; inset: 0; z-index: 250; background: #000; display: grid; place-items: center; }
  .stage-col.theater :global(.player-wrap) { width: min(100vw, calc(100vh * 16 / 9)); border-radius: 0; }
  .fs-btn {
    position: absolute; top: 12px; right: 12px; z-index: 5; display: grid; place-items: center; width: 38px; height: 38px; border-radius: 50%;
    color: #fff; background: rgba(0, 0, 0, 0.5); transition: background-color var(--dur-2), scale var(--dur-2) var(--ease-out);
  }
  .fs-btn:hover { background: rgba(0, 0, 0, 0.72); scale: 1.08; }
  .w-side { background: var(--surface); border-radius: 28px; overflow: hidden; box-shadow: var(--shadow-sm); animation: rise 520ms var(--ease-out) 120ms backwards; }
  .subtabs, .ltabs { display: flex; gap: 0.25rem; padding: 0.3rem; border-radius: 999px; background: var(--surface2); width: fit-content; max-width: 100%; }
  .subtabs { margin: 0.7rem 0.7rem 0; }
  .subtabs button, .ltabs button {
    height: 36px; padding: 0 1rem; border-radius: 999px; font-weight: 600; font-size: 0.85rem; color: var(--muted);
    transition: background-color var(--dur-2) var(--ease-out), color var(--dur-2), box-shadow var(--dur-2);
  }
  .subtabs button:hover, .ltabs button:hover { color: var(--text); }
  .subtabs button.on, .ltabs button.on { color: var(--text); background: var(--surface); box-shadow: var(--shadow-sm); }
  .w-side-b { padding: 0.6rem; max-height: 540px; overflow: auto; }
  .w-ep {
    display: flex; gap: 0.7rem; align-items: center; width: 100%; padding: 0.45rem; border-radius: 18px; text-align: left;
    transition: background-color var(--dur-2), translate var(--dur-2) var(--ease-out);
  }
  .w-ep:hover { background: var(--surface2); translate: 2px 0; }
  .w-ep.cur { background: var(--tile-lilac); color: var(--tile-ink); }
  .w-ep.cur .ep-b span { color: inherit; opacity: 0.7; }
  .w-meta { margin-top: 1.2rem; display: grid; gap: 0.35rem; }
  .w-meta h2 { font-size: 1.5rem; letter-spacing: -0.025em; }
  .player-ph {
    aspect-ratio: 16/9; border-radius: 28px; background: #0b0b0d; display: grid; place-items: center; color: rgba(244, 244, 246, 0.7);
    padding: 1rem; text-align: center;
  }

  /* course player */
  .cp { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 1.2rem; align-items: start; }
  .cp.map-closed { grid-template-columns: minmax(0, 1fr); }
  .cp.map-closed .cmap { display: none; }
  @media (max-width: 920px) { .cp { grid-template-columns: minmax(0, 1fr); } }
  .cmap { background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-sm); position: sticky; top: 80px; max-height: calc(100vh - 96px); overflow: auto; }
  @media (max-width: 920px) { .cmap { position: static; max-height: none; } }
  .cmap-h { position: sticky; top: 0; z-index: 1; background: var(--bg-alt); padding: 1rem 1rem 0.9rem; display: grid; gap: 0.55rem; }
  .cmap-h h3 { font-size: 1.05rem; font-weight: 700; letter-spacing: -0.015em; }
  .bar { height: 6px; border-radius: 9px; background: var(--surface3); overflow: hidden; }
  .bar i { display: block; height: 100%; border-radius: inherit; background: var(--success); transform-origin: left; animation: grow 1s var(--ease-out) 300ms backwards; transition: width var(--dur-3) var(--ease-out); }
  .cmap-body { padding: 0.5rem; }
  .c-sec { padding: 0.25rem 0; }
  .c-sec-h { display: flex; justify-content: space-between; gap: 0.5rem; padding: 0.55rem 0.55rem 0.3rem; font-weight: 600; font-size: 0.86rem; }
  .c-sec-h span {
    font-weight: 600; font-size: 0.72rem; color: var(--text-secondary); font-variant-numeric: tabular-nums;
    background: var(--surface2); border-radius: 99px; padding: 0.1rem 0.5rem;
  }
  .mi {
    display: grid; grid-template-columns: 22px minmax(0, 1fr) auto; gap: 0.6rem; align-items: start; width: 100%; padding: 0.55rem 0.6rem;
    border-radius: 16px; text-align: left; font-size: 0.86rem;
    transition: background-color var(--dur-2), translate var(--dur-2) var(--ease-out);
  }
  .mi:hover:not(.locked) { background: var(--surface2); translate: 2px 0; }
  .mi.cur { background: var(--tile-lilac); color: var(--tile-ink); }
  .mi.cur .mi-t small, .mi.cur .mi-r { color: inherit; opacity: 0.7; }
  .mi.locked { opacity: 0.55; cursor: not-allowed; }
  .mi-st {
    display: grid; place-items: center; width: 20px; height: 20px; border-radius: 50%; border: 1.5px solid var(--border-hover);
    font-size: 0.7rem; margin-top: 1px; color: var(--muted); transition: background-color var(--dur-2), border-color var(--dur-2);
  }
  .mi.done .mi-st { background: var(--success); border-color: var(--success); color: var(--on-accent); animation: pop 420ms var(--ease-out) backwards; }
  .mi.locked .mi-st { border: 0; color: var(--warn); }
  .mi-t { display: grid; gap: 1px; }
  .mi-t small { display: flex; gap: 0.3rem; align-items: center; font-size: 0.73rem; color: var(--muted); }
  .mi-r { font-size: 0.72rem; color: var(--muted); padding-top: 2px; font-variant-numeric: tabular-nums; }
  .cmap.is-full { position: fixed; inset: 0; z-index: 260; border-radius: 0; max-height: none; }
  .cmap:fullscreen { overflow: auto; }
  .cmap.is-full .cmap-body { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1rem; padding: 1.2rem 1rem; align-items: start; }
  .cmap.is-full .c-sec { background: var(--surface2); border-radius: 22px; padding: 0.6rem; }
  .cmap.is-full .mi { background: var(--surface); margin-top: 0.35rem; }
  .cmain { min-width: 0; display: grid; gap: 1rem; }
  .crumb { display: flex; gap: 0.6rem; align-items: center; justify-content: space-between; flex-wrap: wrap; font-size: 0.84rem; color: var(--text-secondary); font-weight: 500; }
  .player-wrap { position: relative; }
  .player-tools { position: absolute; top: 12px; right: 12px; z-index: 5; display: flex; gap: 0.35rem; }
  .overview { display: grid; gap: 0.55rem; padding: 1.4rem 1.5rem; border-radius: 28px; background: var(--surface); box-shadow: var(--shadow-sm); }
  .overview h2 { font-size: 1.45rem; letter-spacing: -0.025em; }
  .facts { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-top: 0.4rem; }
  .more-notes { margin-top: 1.2rem; display: grid; gap: 0.4rem; justify-items: start; }
  .filechip {
    display: flex; gap: 0.6rem; align-items: center; padding: 0.6rem 0.9rem 0.6rem 0.6rem; border-radius: 18px; font-size: 0.86rem;
    text-align: left; background: var(--surface); box-shadow: var(--shadow-sm); margin-top: 0.4rem;
    transition: translate var(--dur-2) var(--ease-out), box-shadow var(--dur-2);
  }
  .filechip:hover { translate: 0 -2px; box-shadow: var(--shadow); }
  .filechip .ti { width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: var(--tile-mint); color: var(--tile-ink); }
  .box { background: var(--surface); border-radius: 28px; box-shadow: var(--shadow-sm); padding: 1.6rem; display: grid; gap: 0.75rem; animation: rise 480ms var(--ease-out) backwards; }
  .box h2 { display: flex; gap: 0.5rem; align-items: center; font-size: 1.4rem; letter-spacing: -0.02em; }
  .lk {
    width: 40px; height: 40px; border-radius: 50%; display: inline-grid; place-items: center;
    background: var(--tile-butter); color: var(--tile-ink); animation: wiggle 600ms var(--ease-out) 300ms;
  }

  /* full screen: the player fills the screen, the map becomes a drawer */
  .cp.theater { position: fixed; inset: 0; z-index: 250; background: #000; gap: 0; grid-template-columns: minmax(0, 1fr); padding: 0; }
  .cp.theater:not(.map-closed) { grid-template-columns: 320px minmax(0, 1fr); }
  .cp.theater .cmap { position: static; max-height: 100vh; height: 100vh; border-radius: 0; border: 0; box-shadow: none; }
  .cp.theater .cmain { height: 100vh; display: grid; place-items: center; padding: 0; }
  .cp.theater .cmain > :not(.player-wrap) { display: none; }
  .cp.theater .player-wrap { width: min(100%, calc(100vh * 16 / 9)); }
  .cp.theater .player-wrap :global(.player-wrap) { border-radius: 0; }
  @media (max-width: 760px) { .cp.theater:not(.map-closed) { grid-template-columns: minmax(0, 1fr); } .cp.theater:not(.map-closed) .cmain { display: none; } }
</style>
