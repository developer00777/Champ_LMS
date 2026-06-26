<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { feedApi, assessmentApi } from '$lib/api/client';
	import type { Module, Episode, Assessment } from '$lib/api/client';
	import VideoPlayer from '$lib/components/VideoPlayer.svelte';
	import QuizModal from '$lib/components/QuizModal.svelte';

	let module: Module | null = $state(null);
	let currentEpisode: Episode | null = $state(null);
	let streamUrl = $state('');
	let assessment: Assessment | null = $state(null);
	let showQuiz = $state(false);
	let loading = $state(true);
	let error = $state('');

	// /watch/[moduleId]?ep=[episodeId]
	const moduleId = $derived($page.params.id);
	const episodeId = $derived($page.url.searchParams.get('ep') || '');

	onMount(async () => {
		try {
			module = await feedApi.getModule(moduleId);
			const ep = episodeId
				? module.episodes.find((e) => e.id === episodeId)
				: module.episodes[0];
			if (!ep) { error = 'Episode not found'; return; }
			await loadEpisode(ep);
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	});

	async function loadEpisode(ep: Episode) {
		currentEpisode = ep;
		const res = await feedApi.getStreamUrl(ep.id);
		streamUrl = res.stream_url;
		// Pre-fetch quiz if available
		try {
			const quizzes = await assessmentApi.getForModule(moduleId);
			assessment = quizzes.find((a) => a.episode_id === ep.id) ?? null;
		} catch { assessment = null; }
	}

	function handleEpisodeEnd() {
		if (assessment) {
			showQuiz = true;
		} else {
			advanceEpisode();
		}
	}

	function advanceEpisode() {
		if (!module || !currentEpisode) return;
		const idx = module.episodes.findIndex((e) => e.id === currentEpisode!.id);
		const next = module.episodes[idx + 1];
		if (next) {
			goto(`/watch/${moduleId}?ep=${next.id}`);
			loadEpisode(next);
		}
	}

	function handleQuizComplete(passed: boolean) {
		showQuiz = false;
		advanceEpisode();
	}
</script>

<svelte:head>
	<title>{currentEpisode?.title || 'Watch'} — Champ LMS</title>
</svelte:head>

{#if loading}
	<div class="loading">Loading episode...</div>
{:else if error}
	<div class="error">{error}</div>
{:else if module && currentEpisode}
	<div class="watch-layout">
		<div class="player-section">
			<div class="breadcrumb">
				<a href="/module/{moduleId}">{module.title}</a>
				<span>›</span>
				<span>Episode {currentEpisode.sequence_order} of {module.total_episodes}</span>
			</div>

			{#if streamUrl}
				<VideoPlayer
					{streamUrl}
					episodeId={currentEpisode.id}
					onEnded={handleEpisodeEnd}
				/>
			{/if}

			<div class="episode-info">
				<h1>{currentEpisode.title}</h1>
				{#if currentEpisode.ai_summary}
					<p class="summary">{currentEpisode.ai_summary}</p>
				{:else if currentEpisode.description}
					<p class="summary">{currentEpisode.description}</p>
				{/if}
			</div>
		</div>

		<aside class="episode-list">
			<h3>Episodes</h3>
			{#each module.episodes as ep}
				<button
					class="ep-item"
					class:active={ep.id === currentEpisode.id}
					onclick={() => { loadEpisode(ep); goto(`/watch/${moduleId}?ep=${ep.id}`); }}
				>
					<span class="ep-num">{ep.sequence_order}</span>
					<div class="ep-meta">
						<p class="ep-title">{ep.title}</p>
						{#if ep.duration_seconds}
							<span class="ep-dur">{Math.floor(ep.duration_seconds / 60)}m</span>
						{/if}
					</div>
					{#if ep.status !== 'ready'}
						<span class="ep-status">{ep.status}</span>
					{/if}
				</button>
			{/each}
		</aside>
	</div>

	{#if showQuiz && assessment}
		<QuizModal
			{assessment}
			onClose={() => { showQuiz = false; advanceEpisode(); }}
			onComplete={handleQuizComplete}
		/>
	{/if}
{/if}

<style>
	.loading, .error { padding: 6rem 2rem; color: #aaa; }
	.error { color: #e50914; }

	.watch-layout {
		display: grid;
		grid-template-columns: 1fr 320px;
		gap: 2rem;
		max-width: 1400px;
		margin: 0 auto;
		padding: 1.5rem 2rem;
		min-height: calc(100vh - 56px);
	}

	.breadcrumb { font-size: 0.85rem; color: #aaa; margin-bottom: 1rem; display: flex; gap: 0.5rem; }
	.breadcrumb a { color: #e50914; }

	.episode-info { margin-top: 1.5rem; }
	h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: 0.5rem; }
	.summary { color: #aaa; font-size: 0.9rem; line-height: 1.6; }

	.episode-list { background: #1a1a1a; border-radius: 8px; padding: 1.25rem; height: fit-content; }
	h3 { font-size: 0.9rem; font-weight: 700; margin-bottom: 1rem; color: #aaa; text-transform: uppercase; letter-spacing: 0.05em; }

	.ep-item {
		display: flex; align-items: flex-start; gap: 0.75rem;
		width: 100%; background: none; border: none; color: #fff;
		padding: 0.75rem; border-radius: 6px; text-align: left;
		cursor: pointer; transition: background 0.15s;
		margin-bottom: 0.25rem;
	}
	.ep-item:hover { background: rgba(255,255,255,0.06); }
	.ep-item.active { background: rgba(229,9,20,0.15); }
	.ep-num { font-size: 0.75rem; color: #888; min-width: 18px; margin-top: 2px; }
	.ep-title { font-size: 0.85rem; font-weight: 500; line-height: 1.3; }
	.ep-dur { font-size: 0.75rem; color: #888; }
	.ep-status { font-size: 0.7rem; color: #f59e0b; margin-left: auto; }
</style>
