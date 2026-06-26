<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { feedApi, progressApi } from '$lib/api/client';
	import type { Module, Progress } from '$lib/api/client';

	let module: Module | null = $state(null);
	let progressMap: Record<string, Progress> = $state({});
	let loading = $state(true);
	let error = $state('');

	const moduleId = $derived($page.params.id);

	onMount(async () => {
		try {
			[module] = await Promise.all([feedApi.getModule(moduleId)]);
			const progs = await progressApi.getMe();
			for (const p of progs) progressMap[p.episode_id] = p;
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	});

	function getResumeEpisode(): string | null {
		if (!module) return null;
		const inProgress = module.episodes.find((ep) => {
			const p = progressMap[ep.id];
			return p && !p.completed;
		});
		return inProgress?.id ?? module.episodes[0]?.id ?? null;
	}

	function play() {
		const epId = getResumeEpisode();
		if (epId) goto(`/watch/${moduleId}?ep=${epId}`);
	}
</script>

<svelte:head>
	<title>{module?.title || 'Module'} — Champ LMS</title>
</svelte:head>

{#if loading}
	<div class="loading">Loading...</div>
{:else if error}
	<div class="error">{error}</div>
{:else if module}
	<div class="hero" style="background-image: url({module.thumbnail_url || ''})">
		<div class="hero-overlay">
			<div class="hero-content">
				{#if module.category}<span class="tag">{module.category}</span>{/if}
				<h1>{module.title}</h1>
				{#if module.description}<p class="desc">{module.description}</p>{/if}
				<p class="meta">{module.total_episodes} episodes</p>
				{#if module.tags?.length}
					<div class="tags">
						{#each module.tags as tag}<span class="chip">{tag}</span>{/each}
					</div>
				{/if}
				<button class="btn-primary" onclick={play}>▶ Play</button>
			</div>
		</div>
	</div>

	<div class="episodes-section">
		<h2>Episodes</h2>
		<div class="episode-grid">
			{#each module.episodes as ep, i}
				{@const prog = progressMap[ep.id]}
				<div class="ep-card" onclick={() => goto(`/watch/${moduleId}?ep=${ep.id}`)} role="button" tabindex="0" onkeydown={(e) => e.key === 'Enter' && goto(`/watch/${moduleId}?ep=${ep.id}`)}>
					<div class="ep-num-badge">{ep.sequence_order}</div>
					<div class="ep-body">
						<p class="ep-title">{ep.title}</p>
						{#if ep.description}<p class="ep-desc">{ep.description}</p>{/if}
						<div class="ep-footer">
							{#if ep.duration_seconds}
								<span class="dur">{Math.floor(ep.duration_seconds / 60)}m</span>
							{/if}
							{#if prog?.completed}
								<span class="completed-badge">✓ Completed</span>
							{:else if prog && prog.watched_seconds > 0}
								<span class="progress-text">{Math.floor((prog.watched_seconds / (prog.total_seconds || 1)) * 100)}% watched</span>
							{/if}
						</div>
						{#if prog && prog.watched_seconds > 0 && prog.total_seconds}
							<div class="progress-bar-track" style="margin-top: 0.5rem;">
								<div class="progress-bar-fill" style="width: {Math.min(100, (prog.watched_seconds / prog.total_seconds) * 100)}%"></div>
							</div>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	</div>
{/if}

<style>
	.loading, .error { padding: 6rem 2rem; color: #aaa; }
	.error { color: #e50914; }

	.hero {
		min-height: 500px;
		background-size: cover;
		background-position: center;
		background-color: #1a1a1a;
		position: relative;
	}
	.hero-overlay {
		position: absolute; inset: 0;
		background: linear-gradient(to right, rgba(20,20,20,0.95) 0%, rgba(20,20,20,0.6) 60%, transparent 100%);
		display: flex; align-items: flex-end;
		padding: 3rem 4rem;
	}
	.hero-content { max-width: 580px; }
	h1 { font-size: 2.5rem; font-weight: 800; margin: 0.5rem 0; }
	.desc { color: #ccc; margin-bottom: 0.75rem; line-height: 1.5; font-size: 0.95rem; }
	.meta { color: #aaa; font-size: 0.9rem; margin-bottom: 0.75rem; }
	.tag { display: inline-block; background: rgba(229,9,20,0.3); color: #ff6b6b; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 0.5rem; }
	.tags { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1rem; }
	.chip { background: rgba(255,255,255,0.1); padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem; color: #ccc; }
	.btn-primary { background: #e50914; color: #fff; border: none; padding: 0.75rem 2rem; border-radius: 4px; font-size: 1rem; font-weight: 700; cursor: pointer; margin-top: 0.5rem; }

	.episodes-section { padding: 2rem 4rem 4rem; max-width: 1200px; margin: 0 auto; }
	h2 { font-size: 1.2rem; font-weight: 700; margin-bottom: 1.25rem; }

	.episode-grid { display: flex; flex-direction: column; gap: 0.75rem; }
	.ep-card {
		display: flex; gap: 1rem; align-items: flex-start;
		background: #1f1f1f; border-radius: 8px; padding: 1rem 1.25rem;
		cursor: pointer; transition: background 0.15s;
	}
	.ep-card:hover { background: #2a2a2a; }
	.ep-num-badge {
		min-width: 36px; height: 36px;
		background: #2a2a2a; border-radius: 50%;
		display: flex; align-items: center; justify-content: center;
		font-size: 0.85rem; font-weight: 700; color: #aaa;
	}
	.ep-body { flex: 1; }
	.ep-title { font-size: 0.95rem; font-weight: 600; margin-bottom: 0.25rem; }
	.ep-desc { font-size: 0.82rem; color: #888; margin-bottom: 0.5rem; }
	.ep-footer { display: flex; align-items: center; gap: 1rem; }
	.dur { font-size: 0.8rem; color: #888; }
	.completed-badge { font-size: 0.75rem; color: #22c55e; font-weight: 600; }
	.progress-text { font-size: 0.75rem; color: #f59e0b; }
	.progress-bar-track { height: 2px; background: rgba(255,255,255,0.1); border-radius: 1px; }
	.progress-bar-fill { height: 100%; background: #e50914; border-radius: 1px; }
</style>
