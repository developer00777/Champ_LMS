<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { page } from '$app/stores';
  import {
    api, type AdminCourse, type AdminCourseItem, type CourseItemKind, type CourseSection,
  } from '$lib/api/client';
  import { uploads, startVideoUpload, hasActiveUploads } from '$lib/stores/course-uploads';
  import { clock, runtime } from '$lib/utils/transcribe';
  import { icons, kindLabel } from '$lib/components/course/icons';
  import VideoInspector from '$lib/components/course/admin/VideoInspector.svelte';
  import QuizInspector from '$lib/components/course/admin/QuizInspector.svelte';
  import TestInspector from '$lib/components/course/admin/TestInspector.svelte';
  import NotesInspector from '$lib/components/course/admin/NotesInspector.svelte';
  import AccessPanel from '$lib/components/course/admin/AccessPanel.svelte';
  import InsertMenu from '$lib/components/course/admin/InsertMenu.svelte';

  $: id = $page.params.id;

  let course: AdminCourse | null = null;
  let error = '';
  let notice = '';
  let warnings: string[] = [];
  let view: 'canvas' | 'access' = 'canvas';
  let accessTestId: string | null = null;
  let selectedId: string | null = null;
  let insKey: string | null = null;
  let pendingInsert: { section_id: string; index: number } | null = null;
  let confirmDelete: string | null = null;
  let mapFull = false;
  let mapEl: HTMLElement;
  let fileInput: HTMLInputElement;
  let dragId: string | null = null;
  let dropHint: { id?: string; after?: boolean; section?: string } | null = null;
  let dzHot = false;
  let title = '';
  let description = '';

  async function load() {
    try {
      const c = await api.adminCourse(id);
      course = c;
      if (!titleFocused) title = c.title;
      if (!descFocused) description = c.description ?? '';
      if (selectedId && !c.items.some(i => i.id === selectedId)) selectedId = null;
    } catch (e: any) { error = e.message; }
  }

  // While anything is uploading, encoding or being transcribed, keep the
  // canvas fresh. Bunny's webhook normally flips a video to ready; asking
  // Bunny directly covers the case where the webhook never arrives.
  let poll: ReturnType<typeof setInterval>;
  let lastBunnyCheck = 0;
  async function tick() {
    if (!course || document.visibilityState !== 'visible') return;
    const busy = course.items.some(i => i.kind === 'video' && (i.status !== 'ready' || i.transcript_status === 'processing'))
      || hasActiveUploads();
    if (!busy) return;
    if (Date.now() - lastBunnyCheck > 20_000) {
      lastBunnyCheck = Date.now();
      const encoding = course.items.filter(i => i.kind === 'video' && i.has_remote_video && i.status === 'processing');
      await Promise.all(encoding.map(i => api.episodeStatus(i.ref_id).catch(() => null)));
    }
    await load();
  }

  function beforeUnload(e: BeforeUnloadEvent) {
    if (hasActiveUploads()) { e.preventDefault(); e.returnValue = ''; }
  }
  function onFullscreen() { if (!document.fullscreenElement) mapFull = false; }

  onMount(() => {
    load();
    poll = setInterval(tick, 8000);
    window.addEventListener('beforeunload', beforeUnload);
    document.addEventListener('fullscreenchange', onFullscreen);
  });
  onDestroy(() => {
    clearInterval(poll);
    if (typeof window !== 'undefined') {
      window.removeEventListener('beforeunload', beforeUnload);
      document.removeEventListener('fullscreenchange', onFullscreen);
    }
  });

  $: sections = course
    ? course.sections.map(s => ({ ...s, items: course!.items.filter(i => i.section_id === s.id) }))
    : [];
  $: selected = course?.items.find(i => i.id === selectedId) ?? null;
  $: counts = course
    ? (['video', 'quiz', 'test', 'notes'] as CourseItemKind[]).map(k => [k, course!.items.filter(i => i.kind === k).length] as const)
    : [];
  $: totalRuntime = course ? course.items.reduce((a, i) => a + (i.kind === 'video' ? i.duration_seconds ?? 0 : 0), 0) : 0;

  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const KIND_WORDS: Record<CourseItemKind, [string, string]> = {
    video: ['video', 'videos'], quiz: ['quiz', 'quizzes'], test: ['test', 'tests'], notes: ['notes page', 'notes pages'],
  };

  function meta(it: AdminCourseItem): string {
    if (it.kind === 'video') {
      const up = $uploads[it.id];
      if (up && (up.stage === 'queued' || up.stage === 'uploading')) return `Uploading ${Math.round(up.progress * 100)}%`;
      if (up?.stage === 'failed') return 'Upload failed';
      if (it.status === 'pending' && !it.has_remote_video) return 'No video file yet';
      if (it.status !== 'ready') return it.status === 'failed' ? 'Encoding failed' : 'Encoding on Bunny…';
      if (up?.transcript === 'working' || it.transcript_status === 'processing') return 'Writing transcript and notes…';
      const t = it.transcript_source === 'auto' ? 'auto' : it.transcript_source === 'manual' ? 'edited' : it.transcript_status === 'failed' ? 'failed' : 'none';
      const n = it.notes_source === 'ai' ? 'AI draft' : it.notes_source === 'manual' ? 'written by you' : 'none';
      return `Transcript ${t} · Notes ${n}`;
    }
    if (it.kind === 'quiz') {
      const eps = course!.items.filter(i => i.kind === 'video' && it.source_episode_ids.includes(i.ref_id))
        .map(i => (i.kind === 'video' ? i.episode_number : 0));
      return `${it.questions.length ? plural(it.questions.length, 'question', 'questions') : 'No questions yet'}`
        + ` · ${eps.length ? `from episode${eps.length > 1 ? 's' : ''} ${eps.join(', ')}` : 'no episodes chosen'}`
        + ` · pass ${it.pass_threshold}%${it.must_pass ? ' · must pass' : ''}`;
    }
    if (it.kind === 'test') {
      return `${it.question_count ? plural(it.question_count, 'question', 'questions') : 'No questions yet'}`
        + `${it.duration_minutes ? ` · ${it.duration_minutes} min` : ''} · pass ${it.pass_threshold}% · you approve each attempt`
        + (it.pending_requests ? ` · ${it.pending_requests} waiting` : '');
    }
    return `${it.source === 'ai' ? 'AI draft' : 'Written by you'}${it.attachment_name ? ' · 1 PDF attached' : ''}`;
  }

  function progressOf(it: AdminCourseItem): number | null {
    if (it.kind !== 'video') return null;
    const up = $uploads[it.id];
    if (up && (up.stage === 'queued' || up.stage === 'uploading')) return up.progress;
    if (up?.transcript === 'working') return up.transcriptProgress;
    return null;
  }

  // ---- details -----------------------------------------------------------
  let titleFocused = false;
  let descFocused = false;
  let detailTimer: ReturnType<typeof setTimeout>;
  function saveDetails() {
    clearTimeout(detailTimer);
    detailTimer = setTimeout(async () => {
      if (!course) return;
      try {
        const r = await api.updateCourse(course.id, { title: title.trim() || 'Untitled course', description: description.trim() || null });
        course = { ...course, title: r.title, description: r.description };
      } catch (e: any) { error = e.message; }
    }, 600);
  }

  async function togglePublish() {
    if (!course) return;
    error = ''; notice = ''; warnings = [];
    try {
      const r = await api.updateCourse(course.id, { is_published: !course.is_published });
      course = r; warnings = r.warnings ?? [];
      notice = r.is_published
        ? (r.can_watch_count ? `Published. ${plural(r.can_watch_count, 'person', 'people')} can watch it now.` : 'Published. Nobody can watch yet: add people in Access.')
        : 'Unpublished. Learners no longer see this course.';
    } catch (e: any) { error = e.message; }
  }

  // ---- structure ---------------------------------------------------------
  async function saveStructure(nextSections: CourseSection[], nextItems: AdminCourseItem[]) {
    if (!course) return;
    const before = course;
    course = { ...course, sections: nextSections, items: nextItems };
    try {
      course = await api.setCourseStructure(course.id, nextSections, nextItems.map(i => ({ id: i.id, section_id: i.section_id })));
    } catch (e: any) {
      course = before;
      error = e.status === 409 ? e.message : `Couldn't save the new order: ${e.message}`;
      if (e.status === 409) load();
    }
  }

  function addSection() {
    if (!course) return;
    const s = { id: crypto.randomUUID(), title: `Section ${course.sections.length + 1}` };
    saveStructure([...course.sections, s], course.items);
  }

  let renameTimer: ReturnType<typeof setTimeout>;
  function renameSection(sid: string, value: string) {
    if (!course) return;
    const next = course.sections.map(s => (s.id === sid ? { ...s, title: value } : s));
    course = { ...course, sections: next };
    clearTimeout(renameTimer);
    renameTimer = setTimeout(() => course && value.trim() && saveStructure(course.sections, course.items), 700);
  }

  function deleteSection(sid: string) {
    if (!course) return;
    if (course.items.some(i => i.section_id === sid)) { error = 'Move or remove the items in this section first.'; return; }
    if (course.sections.length === 1) { error = 'A course needs at least one section.'; return; }
    saveStructure(course.sections.filter(s => s.id !== sid), course.items);
  }

  // ---- adding ------------------------------------------------------------
  function openInserter(key: string) { insKey = insKey === key ? null : key; }

  async function add(kind: CourseItemKind, section_id: string, index: number) {
    insKey = null; error = '';
    if (kind === 'video') { pendingInsert = { section_id, index }; fileInput.click(); return; }
    try {
      const it = await api.addCourseItem(course!.id, { kind, section_id, index });
      await load();
      selectedId = it.id;
      if (kind === 'quiz' && it.kind === 'quiz' && !it.source_episode_ids.length) {
        notice = 'Tick the episodes this quiz should be written from, then write the questions.';
      }
    } catch (e: any) { error = e.message; }
  }

  const prettify = (name: string) => {
    const t = name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' ').replace(/\s+/g, ' ').trim();
    return t ? t[0].toUpperCase() + t.slice(1) : 'Untitled episode';
  };

  async function addVideos(files: File[], target: { section_id: string; index: number } | null) {
    if (!course || !files.length) return;
    const videos = files.filter(f => f.type.startsWith('video/') || /\.(mp4|mov|m4v|webm|mkv)$/i.test(f.name));
    if (!videos.length) { error = 'Only video files can go here.'; return; }
    const last = course.sections[course.sections.length - 1];
    const section_id = target?.section_id ?? last.id;
    let index = target?.index ?? course.items.filter(i => i.section_id === section_id).length;
    error = '';
    let firstId: string | null = null;
    for (const file of videos) {
      try {
        const it = await api.addCourseItem(course.id, { kind: 'video', section_id, index: index++, title: prettify(file.name) });
        startVideoUpload(it.id, it.ref_id, file, load);
        firstId = firstId ?? it.id;
      } catch (e: any) { error = `${file.name}: ${e.message}`; break; }
    }
    await load();
    if (firstId) selectedId = firstId;
    notice = `${plural(videos.length, 'video', 'videos')} added. Each uploads to Bunny while its transcript is written here. Keep this tab open until they finish.`;
  }

  function onFiles(e: Event) {
    const files = [...((e.target as HTMLInputElement).files ?? [])];
    (e.target as HTMLInputElement).value = '';
    addVideos(files, pendingInsert);
    pendingInsert = null;
  }

  // ---- deleting ----------------------------------------------------------
  async function remove(it: AdminCourseItem) {
    if (!course) return;
    confirmDelete = null; error = '';
    try {
      course = await api.deleteCourseItem(course.id, it.id);
      if (selectedId === it.id) selectedId = null;
      notice = `Deleted “${it.title}”.`;
    } catch (e: any) { error = e.message; }
  }

  // ---- drag and drop -----------------------------------------------------
  function dragStart(e: DragEvent, it: AdminCourseItem) {
    dragId = it.id;
    e.dataTransfer?.setData('text/plain', it.id);
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
  }
  function dragOverCard(e: DragEvent, it: AdminCourseItem) {
    if (!dragId) return;
    e.preventDefault();
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    dropHint = it.id === dragId ? null : { id: it.id, after: e.clientY > r.top + r.height / 2 };
  }
  function dragOverLane(e: DragEvent, sid: string) {
    e.preventDefault();
    if (!dragId) { dropHint = { section: sid }; return; }
    if (!(e.target as HTMLElement).closest('.card')) dropHint = { section: sid };
  }
  function dropOnLane(e: DragEvent, sid: string) {
    e.preventDefault();
    const files = [...(e.dataTransfer?.files ?? [])];
    const hint = dropHint;
    dropHint = null; dzHot = false;
    if (!dragId && files.length) {
      addVideos(files, { section_id: sid, index: course!.items.filter(i => i.section_id === sid).length });
      return;
    }
    if (!dragId || !course) return;
    const moving = course.items.find(i => i.id === dragId)!;
    const rest = course.items.filter(i => i.id !== dragId);
    let at: number;
    let section = sid;
    if (hint?.id) {
      const target = rest.findIndex(i => i.id === hint.id);
      section = rest[target].section_id;
      at = target + (hint.after ? 1 : 0);
    } else {
      const inLane = rest.map((i, n) => (i.section_id === sid ? n : -1)).filter(n => n >= 0);
      at = inLane.length ? inLane[inLane.length - 1] + 1 : insertionForEmpty(rest, sid);
    }
    rest.splice(at, 0, { ...moving, section_id: section } as AdminCourseItem);
    dragId = null;
    saveStructure(course.sections, rest);
  }
  // Where an item lands in the flat list when dropped into an empty section.
  function insertionForEmpty(list: AdminCourseItem[], sid: string) {
    const order = course!.sections.map(s => s.id);
    const earlier = new Set(order.slice(0, order.indexOf(sid)));
    let at = 0;
    list.forEach((i, n) => { if (earlier.has(i.section_id)) at = n + 1; });
    return at;
  }
  function dragEnd() { dragId = null; dropHint = null; }

  function dropZoneDrop(e: DragEvent) {
    e.preventDefault(); dzHot = false;
    addVideos([...(e.dataTransfer?.files ?? [])], null);
  }

  // ---- map ---------------------------------------------------------------
  async function toggleMapFull() {
    mapFull = !mapFull;
    try {
      if (mapFull && mapEl.requestFullscreen) await mapEl.requestFullscreen();
      else if (!mapFull && document.fullscreenElement) await document.exitFullscreen();
    } catch { /* fullscreen refused: the CSS overlay still covers the page */ }
  }
  function pick(itemId: string) {
    selectedId = itemId; insKey = null; view = 'canvas';
    if (mapFull) toggleMapFull();
  }

  function openTestAccess(testId: string) { accessTestId = testId; view = 'access'; }
  function onKey(e: KeyboardEvent) {
    if (e.key !== 'Escape') return;
    if (insKey) insKey = null; else if (confirmDelete) confirmDelete = null; else if (mapFull) toggleMapFull();
  }
</script>

<svelte:head><title>{course?.title ?? 'Course'} · Canvas — Champ LMS</title></svelte:head>
<svelte:window on:keydown={onKey} on:click={e => { if (insKey && !(e.target instanceof Element && e.target.closest('.ins'))) insKey = null; }} />

<input bind:this={fileInput} type="file" accept="video/*" multiple hidden on:change={onFiles} />

{#if !course}
  {#if error}<p class="error">{error}</p>{:else}<p class="muted">Loading the canvas…</p>{/if}
{:else}
  <div class="cv">
    <header class="cv-head">
      <div class="cv-title">
        <a href="/admin/courses" class="crumb">{@html icons.back} Courses</a>
        <input class="title-in" type="text" bind:value={title} on:input={saveDetails}
          on:focus={() => (titleFocused = true)} on:blur={() => (titleFocused = false)} aria-label="Course title" maxlength="200" />
        <div class="cv-meta">
          {#if course.format === 'series'}<span class="pill series">{@html icons.play} Series view</span>
          {:else if course.format === 'course'}<span class="pill course">{@html icons.panel} Full course view</span>
          {:else}<span class="pill">Empty</span>{/if}
          {#if course.is_published}<span class="pill ok">Published</span>{:else}<span class="pill">Draft</span>{/if}
          <span class="mono">{counts.map(([k, n]) => plural(n, KIND_WORDS[k][0], KIND_WORDS[k][1])).join(' · ')} · {runtime(totalRuntime)}</span>
        </div>
      </div>
      <div class="cv-actions">
        <a class="btn ghost" href="/course/{course.id}" target="_blank" rel="noopener">{@html icons.eye} Preview as learner</a>
        <button class="btn" class:on={view === 'access'} on:click={() => (view = view === 'access' ? 'canvas' : 'access')}>
          {@html icons.key} {course.can_watch_count ? plural(course.can_watch_count, 'person can', 'people can') + ' watch' : 'Nobody can watch yet'}
        </button>
        <button class="btn primary" on:click={togglePublish}>{course.is_published ? 'Unpublish' : 'Publish'}</button>
      </div>
    </header>

    {#if notice}<div class="banner ok">{notice}<button class="icon-btn" on:click={() => (notice = '')} aria-label="Dismiss">{@html icons.x}</button></div>{/if}
    {#each warnings as w}<div class="banner warn">{w}</div>{/each}
    {#if error}<div class="banner bad">{error}<button class="icon-btn" on:click={() => (error = '')} aria-label="Dismiss">{@html icons.x}</button></div>{/if}

    <div class="tabs" role="tablist">
      <button class:on={view === 'canvas'} on:click={() => (view = 'canvas')}>Canvas</button>
      <button class:on={view === 'access'} on:click={() => (view = 'access')}>Access</button>
    </div>

    {#if view === 'access'}
      <AccessPanel {course} focusTestId={accessTestId} onChanged={load} />
    {:else}
      <div class="fmt-hint">
        <div class="fmt-mini" aria-hidden="true"><span class="fs" class:on={course.format === 'series'}>SERIES</span><span class="fc" class:on={course.format === 'course'}>COURSE</span></div>
        <div>
          {#if course.format === 'series'}<b>Only videos so far</b>, so learners get the Netflix-style series player. Add an AI quiz, a test or notes and it becomes a full course with a course map.
          {:else if course.format === 'course'}<b>Mixed content</b>, so learners get the full course player with the course map on the left, notes and a synced transcript.
          {:else}<b>Empty course.</b> Drop videos below to start.{/if}
        </div>
      </div>

      <div class="cv-grid">
        <aside class="panel map" class:is-full={mapFull} bind:this={mapEl} aria-label="Course map">
          <div class="panel-h">
            <span>{mapFull ? `${course.title} · course map` : 'Course map'}</span>
            <button class="icon-btn" on:click={toggleMapFull} aria-label={mapFull ? 'Exit full screen' : 'Full screen map'}>{@html mapFull ? icons.shrink : icons.expand}</button>
          </div>
          <div class="map-body">
            {#each sections as s, si (s.id)}
              <div class="m-sec">
                <div class="m-sec-h"><span>{si + 1}. {s.title}</span><span class="mono">{s.items.length}</span></div>
                {#each s.items as it (it.id)}
                  <button class="m-item k-{it.kind}" class:sel={selectedId === it.id} on:click={() => pick(it.id)}>
                    <span class="ti">{@html icons[it.kind]}</span>
                    <span class="lbl-t">{it.title}</span>
                    <span class="m-dur">{it.kind === 'video' && it.duration_seconds ? clock(it.duration_seconds) : ''}</span>
                  </button>
                {:else}
                  <div class="hint pad">Empty</div>
                {/each}
              </div>
            {/each}
          </div>
        </aside>

        <section class="board" aria-label="Canvas">
          <div class="dropzone" class:hot={dzHot} role="region" aria-label="Drop videos"
            on:dragover|preventDefault={() => { if (!dragId) dzHot = true; }} on:dragleave={() => (dzHot = false)} on:drop={dropZoneDrop}>
            <span class="dz-ico">{@html icons.upload}</span>
            <div class="dz-t"><b>Drop videos here</b><span>Each file becomes an episode at the end of the last section. Its transcript and notes are drafted automatically.</span></div>
            <button class="btn" on:click={() => { pendingInsert = null; fileInput.click(); }}>Choose videos</button>
          </div>

          {#each sections as s, si (s.id)}
            <div class="lane" class:drop-end={dropHint?.section === s.id} role="list"
              on:dragover={e => dragOverLane(e, s.id)} on:drop={e => dropOnLane(e, s.id)}>
              <div class="lane-h">
                <span class="lane-no">{si + 1}</span>
                <input class="lane-title" type="text" value={s.title} aria-label="Section title" maxlength="200"
                  on:input={e => renameSection(s.id, e.currentTarget.value)} />
                <span class="lane-meta mono">{plural(s.items.length, 'item', 'items')} · {runtime(s.items.reduce((a, i) => a + (i.kind === 'video' ? i.duration_seconds ?? 0 : 0), 0))}</span>
                <button class="icon-btn" on:click={() => deleteSection(s.id)} aria-label="Delete section">{@html icons.x}</button>
              </div>

              {#each s.items as it, i (it.id)}
                {#if i === 0}
                  <div class="ins" class:open={insKey === `${s.id}:0`}>
                    <button class="ins-btn" on:click|stopPropagation={() => openInserter(`${s.id}:0`)} aria-label="Add here">{@html icons.plus}</button>
                    {#if insKey === `${s.id}:0`}
                      <InsertMenu onPick={k => add(k, s.id, 0)} />
                    {/if}
                  </div>
                {/if}
                <!-- The card is a draggable list item that also selects on click or Enter; its own buttons stay separate controls. -->
                <!-- svelte-ignore a11y-no-noninteractive-tabindex a11y-no-noninteractive-element-interactions -->
                <div class="card k-{it.kind}" class:sel={selectedId === it.id}
                  class:dragging={dragId === it.id}
                  class:drop-before={dropHint?.id === it.id && !dropHint.after}
                  class:drop-after={dropHint?.id === it.id && dropHint.after}
                  draggable="true" role="listitem"
                  on:dragstart={e => dragStart(e, it)} on:dragover={e => dragOverCard(e, it)} on:dragend={dragEnd}
                  on:click={() => (selectedId = it.id)} on:keydown={e => (e.key === 'Enter' || e.key === ' ') && (selectedId = it.id)} tabindex="0">
                  <span class="grip" aria-hidden="true">{@html icons.grip}</span>
                  <span class="c-ico">{@html icons[it.kind]}</span>
                  <div class="c-body">
                    <div class="c-kind">
                      {it.kind === 'video' ? `Episode ${it.episode_number ?? ''}` : kindLabel[it.kind]}
                      {#if it.kind === 'video' && it.duration_seconds}<span class="mono">· {clock(it.duration_seconds)}</span>{/if}
                    </div>
                    <div class="c-title">{it.title}</div>
                    <div class="c-meta">{meta(it)}</div>
                    {#if progressOf(it) !== null}
                      <div class="bar" class:ok={$uploads[it.id]?.transcript === 'working'}><i style="width:{Math.round((progressOf(it) ?? 0) * 100)}%"></i></div>
                    {/if}
                  </div>
                  {#if confirmDelete === it.id}
                    <div class="confirm" on:click|stopPropagation role="presentation">
                      <span>{it.kind === 'video' ? 'Deletes the video from Bunny too.' : it.kind === 'test' ? 'Deletes its attempts and requests too.' : 'Delete permanently?'}</span>
                      <button class="btn sm danger" on:click={() => remove(it)}>Delete</button>
                      <button class="btn sm ghost" on:click={() => (confirmDelete = null)}>Keep</button>
                    </div>
                  {:else}
                    <button class="icon-btn c-del" on:click|stopPropagation={() => (confirmDelete = it.id)} aria-label="Delete {it.title}">{@html icons.x}</button>
                  {/if}
                </div>
                {#if i < s.items.length - 1}
                  <div class="ins" class:open={insKey === `${s.id}:${i + 1}`}>
                    <button class="ins-btn" on:click|stopPropagation={() => openInserter(`${s.id}:${i + 1}`)} aria-label="Add here">{@html icons.plus}</button>
                    {#if insKey === `${s.id}:${i + 1}`}
                      <InsertMenu onPick={k => add(k, s.id, i + 1)} />
                    {/if}
                  </div>
                {/if}
              {/each}

              {#if !s.items.length}<div class="lane-empty">Empty section. Drag items here, or add something below.</div>{/if}

              <div class="ins last" class:open={insKey === `${s.id}:end`}>
                <button class="ins-btn" on:click|stopPropagation={() => openInserter(`${s.id}:end`)}>{@html icons.plus}<span>Add to this section</span></button>
                {#if insKey === `${s.id}:end`}
                  <InsertMenu onPick={k => add(k, s.id, s.items.length)} />
                {/if}
              </div>
            </div>
          {/each}
          <button class="add-sec" on:click={addSection}>{@html icons.plus} Add section</button>
        </section>

        <aside class="panel insp" aria-label="Details">
          {#if selected}
            <div class="panel-h">
              <span class="row tight"><span class="ti k-{selected.kind}">{@html icons[selected.kind]}</span>
                {selected.kind === 'video' ? `Episode ${selected.episode_number ?? ''}` : kindLabel[selected.kind]}</span>
              <button class="icon-btn" on:click={() => (selectedId = null)} aria-label="Close details">{@html icons.x}</button>
            </div>
            {#key selected.id}
              {#if selected.kind === 'video'}<VideoInspector item={selected} onReload={load} />
              {:else if selected.kind === 'quiz'}<QuizInspector {course} item={selected} onReload={load} />
              {:else if selected.kind === 'test'}<TestInspector {course} item={selected} onReload={load} onOpenAccess={() => selected && openTestAccess(selected.ref_id)} />
              {:else}<NotesInspector item={selected} onReload={load} />{/if}
            {/key}
          {:else}
            <div class="panel-h"><span>Course details</span></div>
            <div class="insp-body">
              <label class="field"><span>Description</span>
                <textarea rows="4" bind:value={description} on:input={saveDetails}
                  on:focus={() => (descFocused = true)} on:blur={() => (descFocused = false)}></textarea></label>
              <div class="setting">
                <div><b>Access</b><span>{course.can_watch_count ? `${plural(course.can_watch_count, 'person', 'people')} can watch.` : 'Nobody can watch or take tests until you add them.'}</span></div>
                <button class="btn sm" on:click={() => (view = 'access')}>Manage</button>
              </div>
              <p class="hint">Select an item on the canvas to edit it here. Drag cards to reorder them or move them between sections.</p>
            </div>
          {/if}
        </aside>
      </div>
    {/if}
  </div>
{/if}

<style>
  .muted { color: var(--muted); }
  .error { color: #ff6b6b; }
  .cv {
    --c-video: #6ea8ff; --c-quiz: #b596ff; --c-test: #f5c518; --c-notes: #48d0c7;
    --ok: #2ecc71; --warn: #f0a540; --bad: #ff6b70;
    display: grid; gap: 0.9rem;
  }
  .cv :global(.mono) { font-family: ui-monospace, 'JetBrains Mono', Consolas, monospace; font-variant-numeric: tabular-nums; }
  .cv :global(svg) { flex: none; }
  .cv-head { display: flex; gap: 1rem; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; }
  .cv-title { display: grid; gap: 0.25rem; flex: 1; min-width: 0; }
  .crumb { display: inline-flex; gap: 0.3rem; align-items: center; font-size: 0.8rem; color: var(--muted); }
  .title-in {
    font: inherit; font-size: 1.6rem; font-weight: 800; color: var(--text); background: transparent;
    border: 1px solid transparent; border-radius: 8px; padding: 0.1rem 0.4rem; margin-left: -0.45rem; width: 100%;
  }
  .title-in:hover, .title-in:focus { border-color: var(--border-hover); outline: none; }
  .cv-meta { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; font-size: 0.8rem; color: var(--text-secondary); }
  .cv-actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }

  .cv :global(.btn) {
    display: inline-flex; align-items: center; gap: 0.4rem; height: 34px; padding: 0 0.9rem; border-radius: 8px;
    border: 1px solid var(--border-hover); background: var(--surface2); color: var(--text); font-weight: 600; font-size: 0.82rem;
    white-space: nowrap; cursor: pointer;
  }
  .cv :global(.btn:hover:not(:disabled)) { background: var(--surface3); }
  .cv :global(.btn.primary) { background: var(--accent); border-color: var(--accent); color: #fff; }
  .cv :global(.btn.primary:hover:not(:disabled)) { background: var(--accent-hover); }
  .cv :global(.btn.ghost) { background: transparent; }
  .cv :global(.btn.danger) { background: #c0262d; border-color: #c0262d; color: #fff; }
  .cv :global(.btn.sm) { height: 28px; padding: 0 0.65rem; font-size: 0.76rem; }
  .cv :global(.btn.on) { border-color: var(--text); }
  .cv :global(.btn:disabled) { opacity: 0.5; cursor: not-allowed; }
  .cv :global(.icon-btn) { display: inline-grid; place-items: center; width: 28px; height: 28px; border-radius: 7px; color: var(--muted); font-size: 1rem; }
  .cv :global(.icon-btn:hover) { background: var(--surface2); color: var(--text); }
  .cv :global(.pill) {
    display: inline-flex; align-items: center; gap: 0.3rem; height: 22px; padding: 0 9px; border-radius: 99px;
    font-size: 0.72rem; font-weight: 600; background: var(--surface3); color: var(--text-secondary); white-space: nowrap;
  }
  .cv :global(.pill.ok) { background: rgba(46, 204, 113, 0.14); color: var(--ok); }
  .cv :global(.pill.warn) { background: rgba(240, 165, 64, 0.14); color: var(--warn); }
  .cv :global(.pill.bad) { background: rgba(255, 91, 98, 0.13); color: var(--bad); }
  .cv :global(.pill.series) { background: rgba(110, 168, 255, 0.15); color: var(--c-video); }
  .cv :global(.pill.course) { background: rgba(181, 150, 255, 0.15); color: var(--c-quiz); }

  .banner { display: flex; gap: 0.75rem; align-items: center; justify-content: space-between; padding: 0.6rem 0.9rem; border-radius: 10px; font-size: 0.85rem; }
  .banner.ok { background: rgba(46, 204, 113, 0.1); }
  .banner.warn { background: rgba(240, 165, 64, 0.12); }
  .banner.bad { background: rgba(255, 91, 98, 0.12); color: #ffb3b6; }
  .tabs { display: flex; gap: 1.2rem; border-bottom: 1px solid var(--border); }
  .tabs button { padding: 0.4rem 0 0.6rem; font-weight: 600; font-size: 0.9rem; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .tabs button.on { color: var(--text); border-color: var(--accent); }

  .fmt-hint { display: flex; gap: 0.8rem; align-items: center; padding: 0.6rem 0.9rem; border-radius: 12px; border: 1px dashed var(--border-hover); background: var(--surface); font-size: 0.85rem; color: var(--text-secondary); }
  .fmt-hint b { color: var(--text); }
  .fmt-mini { display: flex; gap: 0.35rem; flex: none; }
  .fmt-mini span { display: grid; place-items: center; width: 46px; height: 28px; border-radius: 5px; border: 1px solid var(--border-hover); font-size: 0.58rem; font-weight: 700; letter-spacing: 0.05em; color: var(--muted); }
  .fmt-mini .fs.on { color: var(--c-video); border-color: currentColor; }
  .fmt-mini .fc.on { color: var(--c-quiz); border-color: currentColor; }

  .cv-grid { display: grid; gap: 0.9rem; grid-template-columns: minmax(0, 1fr); }
  @media (min-width: 980px) { .cv-grid { grid-template-columns: 230px minmax(0, 1fr); } .cv-grid .insp { grid-column: 1 / -1; } }
  @media (min-width: 1280px) {
    .cv-grid { grid-template-columns: 230px minmax(0, 1fr) 380px; align-items: start; }
    .cv-grid .insp { grid-column: auto; position: sticky; top: 80px; max-height: calc(100vh - 96px); overflow: auto; }
    .cv-grid .map { position: sticky; top: 80px; max-height: calc(100vh - 96px); overflow: auto; }
  }
  .panel { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; min-width: 0; }
  .panel-h {
    display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; padding: 0.6rem 0.6rem 0.6rem 0.9rem;
    border-bottom: 1px solid var(--border); font-weight: 600; font-size: 0.85rem;
    position: sticky; top: 0; background: var(--surface); z-index: 2; border-radius: 12px 12px 0 0;
  }
  .row.tight { display: flex; gap: 0.5rem; align-items: center; }

  .map-body { padding: 0.5rem; }
  .m-sec + .m-sec { margin-top: 0.5rem; }
  .m-sec-h { display: flex; justify-content: space-between; padding: 0.35rem 0.4rem 0.25rem; font-size: 0.66rem; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase; color: var(--muted); }
  .m-item { display: flex; align-items: center; gap: 0.5rem; width: 100%; padding: 0.4rem 0.5rem; border-radius: 7px; text-align: left; font-size: 0.8rem; color: var(--text-secondary); }
  .m-item:hover, .m-item.sel { background: var(--surface2); color: var(--text); }
  .m-item.sel { font-weight: 600; }
  .lbl-t { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .m-dur { font-size: 0.7rem; color: var(--muted); font-variant-numeric: tabular-nums; }
  .pad { padding: 0.3rem 0.5rem; }
  .map.is-full { position: fixed; inset: 0; z-index: 300; border-radius: 0; max-height: none !important; overflow: auto; }
  .map:fullscreen { overflow: auto; }
  .map.is-full .map-body { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1rem; padding: 1.25rem 1rem; align-items: start; }
  .map.is-full .m-sec { margin: 0; background: var(--surface2); border-radius: 12px; padding: 0.6rem; }
  .map.is-full .m-item { background: var(--surface); margin-top: 0.4rem; padding: 0.65rem; font-size: 0.88rem; }

  .cv :global(.k-video) { --kc: var(--c-video); }
  .cv :global(.k-quiz) { --kc: var(--c-quiz); }
  .cv :global(.k-test) { --kc: var(--c-test); }
  .cv :global(.k-notes) { --kc: var(--c-notes); }
  .cv :global(.ti) { color: var(--kc, var(--muted)); display: inline-flex; }
  .cv :global(.c-ico) {
    display: grid; place-items: center; width: 34px; height: 34px; border-radius: 9px; font-size: 1.05rem; flex: none;
    color: var(--kc); background: color-mix(in srgb, var(--kc) 15%, transparent);
  }

  .board { display: grid; gap: 0.9rem; min-width: 0; }
  .dropzone { display: flex; gap: 0.9rem; align-items: center; flex-wrap: wrap; padding: 1rem; border-radius: 12px; border: 1.5px dashed var(--border-hover); background: var(--surface); }
  .dropzone.hot { border-color: var(--c-video); background: color-mix(in srgb, var(--c-video) 8%, var(--surface)); }
  .dz-ico { display: grid; place-items: center; width: 42px; height: 42px; border-radius: 10px; font-size: 1.25rem; color: var(--c-video); background: color-mix(in srgb, var(--c-video) 14%, transparent); flex: none; }
  .dz-t { flex: 1; min-width: 200px; display: grid; }
  .dz-t span { font-size: 0.8rem; color: var(--text-secondary); }
  .lane { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 0.6rem 0.75rem 0.75rem; }
  .lane.drop-end { box-shadow: inset 0 -3px 0 var(--accent); }
  .lane-h { display: flex; align-items: center; gap: 0.6rem; padding-bottom: 0.3rem; }
  .lane-no { font-size: 0.72rem; color: var(--muted); font-variant-numeric: tabular-nums; }
  .lane-title { flex: 1; min-width: 0; font: inherit; font-weight: 700; font-size: 1rem; color: var(--text); background: transparent; border: 1px solid transparent; border-radius: 7px; padding: 0.2rem 0.4rem; }
  .lane-title:hover, .lane-title:focus { border-color: var(--border-hover); outline: none; }
  .lane-meta { font-size: 0.74rem; color: var(--muted); white-space: nowrap; }
  .lane-empty { padding: 1rem; text-align: center; font-size: 0.8rem; color: var(--muted); border: 1px dashed var(--border-hover); border-radius: 8px; }

  .card { position: relative; display: flex; gap: 0.6rem; align-items: flex-start; padding: 0.6rem 0.6rem 0.6rem 0.35rem; border-radius: 10px; border: 1px solid var(--border); background: var(--bg); cursor: pointer; }
  .card:hover { border-color: var(--border-hover); }
  .card.sel { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(229, 9, 20, 0.18); }
  .card.dragging { opacity: 0.4; }
  .card.drop-before { box-shadow: 0 -3px 0 var(--accent); }
  .card.drop-after { box-shadow: 0 3px 0 var(--accent); }
  .grip { color: var(--muted); padding-top: 0.45rem; cursor: grab; }
  .c-body { flex: 1; min-width: 0; display: grid; gap: 1px; }
  .c-kind { font-size: 0.66rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
  .c-kind .mono { text-transform: none; letter-spacing: 0; }
  .c-title { font-weight: 600; overflow-wrap: anywhere; }
  .c-meta { font-size: 0.76rem; color: var(--text-secondary); }
  .c-del { opacity: 0; }
  .card:hover .c-del, .card.sel .c-del, .card:focus-within .c-del { opacity: 1; }
  @media (hover: none) { .c-del { opacity: 1; } }
  .confirm { display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap; font-size: 0.74rem; color: var(--text-secondary); max-width: 260px; justify-content: flex-end; }
  .bar { height: 4px; border-radius: 9px; background: var(--surface3); overflow: hidden; margin-top: 0.35rem; }
  .bar i { display: block; height: 100%; background: var(--c-video); transition: width 0.4s; }
  .bar.ok i { background: var(--ok); }

  .ins { position: relative; height: 14px; display: flex; align-items: center; justify-content: center; }
  .ins::before { content: ''; position: absolute; left: 44px; right: 10px; top: 50%; border-top: 1px dashed var(--border-hover); opacity: 0; }
  .ins-btn { position: relative; z-index: 1; display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--surface); border: 1px solid var(--border-hover); color: var(--text-secondary); font-size: 0.8rem; opacity: 0; }
  .ins:hover::before, .ins:hover .ins-btn, .ins.open .ins-btn, .ins.open::before, .ins-btn:focus-visible { opacity: 1; }
  @media (hover: none) { .ins-btn { opacity: 0.8; } }
  .ins.last { height: 40px; }
  .ins.last::before { display: none; }
  .ins.last .ins-btn { opacity: 1; width: auto; height: 30px; border-radius: 99px; padding: 0 0.8rem; gap: 0.35rem; display: inline-flex; align-items: center; font-size: 0.8rem; font-weight: 600; }
  .board :global(.ins-menu) { position: absolute; z-index: 20; top: calc(100% + 2px); left: 50%; transform: translateX(-50%); display: grid; gap: 2px; width: min(300px, 80vw); padding: 0.4rem; background: var(--surface); border: 1px solid var(--border-hover); border-radius: 12px; box-shadow: var(--shadow-lg); }
  .board :global(.ins-menu button) { display: flex; gap: 0.6rem; align-items: center; padding: 0.5rem; border-radius: 8px; text-align: left; }
  .board :global(.ins-menu button:hover) { background: var(--surface2); }
  .board :global(.ins-menu b) { display: block; font-size: 0.85rem; }
  .board :global(.ins-menu small) { display: block; font-size: 0.72rem; color: var(--muted); line-height: 1.35; }
  .add-sec { height: 44px; border-radius: 12px; border: 1.5px dashed var(--border-hover); color: var(--text-secondary); font-weight: 600; display: inline-flex; gap: 0.4rem; align-items: center; justify-content: center; }
  .add-sec:hover { border-color: var(--text-secondary); color: var(--text); }

  /* inspector internals (child components) */
  .cv :global(.insp-body) { padding: 0.9rem; display: grid; gap: 0.85rem; }
  .cv :global(.field) { display: grid; gap: 0.35rem; font-size: 0.76rem; font-weight: 600; color: var(--text-secondary); min-width: 0; }
  .cv :global(.field input[type='text']), .cv :global(.field input[type='number']), .cv :global(.field select),
  .cv :global(.insp-body textarea), .cv :global(.qlist input[type='text']), .cv :global(.inline input) {
    font: inherit; font-weight: 400; font-size: 0.85rem; color: var(--text); background: var(--bg);
    border: 1px solid var(--border-hover); border-radius: 8px; padding: 0.45rem 0.6rem; width: 100%; min-width: 0;
  }
  .cv :global(.insp-body textarea) { resize: vertical; line-height: 1.55; }
  .cv :global(textarea.mono) { font-size: 0.76rem; }
  .cv :global(.field input[type='range']) { accent-color: var(--accent); }
  .cv :global(.row) { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
  .cv :global(.row.end) { justify-content: flex-end; }
  .cv :global(.row.between) { justify-content: space-between; }
  .cv :global(.grow) { flex: 1; min-width: 0; }
  .cv :global(.hint) { font-size: 0.76rem; color: var(--muted); font-weight: 400; line-height: 1.45; }
  .cv :global(.okmsg) { font-size: 0.8rem; color: var(--ok); }
  .cv :global(.insp-body .error) { font-size: 0.8rem; color: var(--bad); }
  .cv :global(.poster) {
    position: relative; aspect-ratio: 16/9; border-radius: 10px; display: grid; place-items: center; max-width: 100%;
    background-color: #111018; background-size: cover; background-position: center;
    background-image: radial-gradient(110% 90% at 18% 12%, rgba(229, 9, 20, 0.75), transparent 62%);
  }
  .cv :global(.poster-ico) { font-size: 1.6rem; color: #fff; }
  .cv :global(.poster .dur) { position: absolute; right: 8px; bottom: 6px; font-size: 0.7rem; background: rgba(0, 0, 0, 0.6); color: #fff; padding: 1px 6px; border-radius: 4px; }
  .cv :global(.kv) { display: grid; grid-template-columns: auto 1fr; gap: 0.35rem 0.9rem; font-size: 0.8rem; }
  .cv :global(.kv > span) { color: var(--muted); }
  .cv :global(.kv > b) { font-weight: 500; overflow-wrap: anywhere; display: flex; gap: 0.35rem; flex-wrap: wrap; align-items: center; }
  .cv :global(.subtabs) { display: flex; gap: 1rem; border-bottom: 1px solid var(--border); }
  .cv :global(.subtabs button) { padding: 0.3rem 0 0.5rem; font-weight: 600; font-size: 0.82rem; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .cv :global(.subtabs button.on) { color: var(--text); border-color: var(--accent); }
  .cv :global(.src-row) { display: flex; gap: 0.5rem; align-items: center; justify-content: space-between; flex-wrap: wrap; }
  .cv :global(.chk) { display: flex; gap: 0.5rem; align-items: center; padding: 0.2rem 0; font-size: 0.82rem; font-weight: 400; color: var(--text); }
  .cv :global(.chk input) { accent-color: var(--accent); width: 15px; height: 15px; }
  .cv :global(.chk .muted) { color: var(--muted); }
  .cv :global(.setting) { display: flex; gap: 0.75rem; align-items: flex-start; justify-content: space-between; padding-top: 0.65rem; border-top: 1px solid var(--border); }
  .cv :global(.setting b) { display: block; font-size: 0.82rem; font-weight: 600; }
  .cv :global(.setting span) { font-size: 0.76rem; color: var(--muted); }
  .cv :global(.tgl) { position: relative; width: 36px; height: 20px; border-radius: 99px; background: var(--surface3); flex: none; }
  .cv :global(.tgl::after) { content: ''; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%; background: #fff; transition: transform 0.15s; }
  .cv :global(.tgl.on) { background: var(--ok); }
  .cv :global(.tgl.on::after) { transform: translateX(16px); }
  .cv :global(.stepper) { display: inline-flex; align-items: center; border: 1px solid var(--border-hover); border-radius: 8px; overflow: hidden; flex: none; }
  .cv :global(.stepper button) { width: 30px; height: 30px; color: var(--text-secondary); }
  .cv :global(.stepper button:hover) { background: var(--surface2); }
  .cv :global(.stepper b) { min-width: 30px; text-align: center; font-variant-numeric: tabular-nums; }
  .cv :global(.lock-row) { display: flex; gap: 0.6rem; align-items: flex-start; padding: 0.65rem 0.75rem; border-radius: 10px; background: rgba(240, 165, 64, 0.1); font-size: 0.8rem; line-height: 1.45; }
  .cv :global(.lock-row > svg) { color: var(--warn); margin-top: 2px; font-size: 1rem; }
  .cv :global(.lock-row a) { color: var(--warn); font-weight: 600; }
  .cv :global(.gen-load) { display: flex; gap: 0.6rem; align-items: center; padding: 0.75rem; border-radius: 10px; background: color-mix(in srgb, var(--c-quiz) 11%, transparent); color: var(--c-quiz); font-weight: 600; font-size: 0.82rem; }
  .cv :global(.spin) { width: 13px; height: 13px; border-radius: 50%; border: 2px solid currentColor; border-right-color: transparent; animation: cvspin 0.8s linear infinite; display: inline-block; }
  @keyframes -global-cvspin { to { transform: rotate(360deg); } }
  .cv :global(.qlist) { list-style: none; margin: 0; padding: 0; display: grid; gap: 0.6rem; counter-reset: q; }
  .cv :global(.qlist > li) { border: 1px solid var(--border); border-radius: 10px; padding: 0.6rem; display: grid; gap: 0.4rem; counter-increment: q; }
  .cv :global(.q-top) { display: flex; gap: 0.4rem; align-items: center; }
  .cv :global(.q-top::before) { content: counter(q); font-size: 0.72rem; color: var(--muted); min-width: 14px; }
  .cv :global(.qlist ul) { list-style: none; margin: 0 0 0 1.25rem; padding: 0; display: grid; gap: 0.25rem; }
  .cv :global(.qlist ul li) { display: flex; gap: 0.45rem; align-items: center; }
  .cv :global(.qlist ul input) { padding: 0.3rem 0.5rem !important; font-size: 0.8rem !important; }
  .cv :global(.opt) { width: 18px; height: 18px; border-radius: 50%; border: 1.5px solid var(--border-hover); display: grid; place-items: center; font-size: 0.7rem; flex: none; }
  .cv :global(.opt.ok) { background: var(--ok); border-color: var(--ok); color: #fff; }
  .cv :global(.q-src) { margin-left: 1.25rem; font-size: 0.72rem; color: var(--muted); }
  .cv :global(.parsed) { display: grid; gap: 0.45rem; padding: 0.7rem; border-radius: 10px; background: var(--surface2); font-size: 0.82rem; }
  .cv :global(.inline) { display: inline-flex; gap: 0.4rem; align-items: center; font-size: 0.8rem; color: var(--muted); }
  .cv :global(.inline input) { width: 70px !important; }
  .cv :global(.filechip) { display: flex; gap: 0.6rem; align-items: center; padding: 0.55rem 0.7rem; border: 1px solid var(--border); border-radius: 10px; font-size: 0.8rem; }
  .cv :global(.toolbar) { display: flex; gap: 2px; align-items: center; padding: 3px; border: 1px solid var(--border-hover); border-bottom: 0; border-radius: 8px 8px 0 0; background: var(--surface2); }
  .cv :global(.toolbar button) { width: 28px; height: 24px; border-radius: 5px; font-weight: 700; font-size: 0.8rem; color: var(--text-secondary); }
  .cv :global(.toolbar button:hover) { background: var(--surface); }
  .cv :global(.toolbar .saved) { margin-left: auto; padding-right: 0.4rem; font-size: 0.72rem; color: var(--muted); }
  .cv :global(textarea.with-toolbar) { border-radius: 0 0 8px 8px !important; }
</style>
