<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { progressApi } from '$lib/api/client';
	import type { Progress } from '$lib/api/client';

	let progressList: Progress[] = $state([]);
	let loading = $state(true);

	onMount(async () => {
		try {
			progressList = await progressApi.getMe();
		} finally {
			loading = false;
		}
	});

	const inProgress = $derived(progressList.filter((p) => !p.completed));
	const completed = $derived(progressList.filter((p) => p.completed));
</script>

<svelte:head><title>My Learning — Champ LMS</title></svelte:head>

<div class="page">
	<h1>My Learning</h1>

	{#if loading}
		<p class="loading">Loading...</p>
	{:else}
		<section>
			<h2>In Progress ({inProgress.length})</h2>
			{#if inProgress.length === 0}
				<p class="empty">Nothing in progress yet. <a href="/">Browse modules</a> to get started.</p>
			{:else}
				<div class="list">
					{#each inProgress as p}
						<div class="item">
							<div class="item-info">
								<p class="episode-id">Episode: {p.episode_id}</p>
								<p class="time">{Math.floor(p.watched_seconds / 60)}m watched</p>
							</div>
							<div class="progress-bar-track" style="width: 200px;">
								<div class="progress-bar-fill" style="width: {p.total_seconds ? Math.min(100,(p.watched_seconds/p.total_seconds)*100) : 0}%"></div>
							</div>
							<button class="btn-resume" onclick={() => goto(`/watch/${p.episode_id}`)}>Resume</button>
						</div>
					{/each}
				</div>
			{/if}
		</section>

		<section>
			<h2>Completed ({completed.length})</h2>
			{#if completed.length === 0}
				<p class="empty">Complete episodes to see them here.</p>
			{:else}
				<div class="list">
					{#each completed as p}
						<div class="item completed">
							<div class="item-info">
								<p class="episode-id">Episode: {p.episode_id}</p>
								<span class="check">✓ Completed</span>
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</section>
	{/if}
</div>

<style>
	.page { max-width: 900px; margin: 0 auto; padding: 2rem; }
	h1 { font-size: 2rem; font-weight: 800; margin-bottom: 2rem; }
	h2 { font-size: 1.1rem; font-weight: 700; margin-bottom: 1rem; color: #aaa; }
	section { margin-bottom: 2.5rem; }
	.loading, .empty { color: #888; font-size: 0.9rem; }
	.empty a { color: #e50914; }

	.list { display: flex; flex-direction: column; gap: 0.75rem; }
	.item {
		display: flex; align-items: center; gap: 1.5rem;
		background: #1f1f1f; border-radius: 8px; padding: 1rem 1.25rem;
	}
	.item.completed { opacity: 0.7; }
	.item-info { flex: 1; }
	.episode-id { font-size: 0.85rem; color: #ccc; font-family: monospace; }
	.time { font-size: 0.75rem; color: #888; }
	.check { font-size: 0.8rem; color: #22c55e; font-weight: 600; }
	.progress-bar-track { height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; }
	.progress-bar-fill { height: 100%; background: #e50914; border-radius: 2px; }
	.btn-resume {
		background: #e50914; color: #fff; border: none;
		padding: 0.4rem 1rem; border-radius: 4px; font-size: 0.85rem; cursor: pointer;
	}
</style>
