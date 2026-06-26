<script lang="ts">
	import { onMount } from 'svelte';
	import { adminApi } from '$lib/api/client';
	import type { Analytics } from '$lib/api/client';

	let analytics: Analytics | null = $state(null);

	onMount(async () => {
		try { analytics = await adminApi.getAnalytics(); } catch {}
	});
</script>

<svelte:head><title>Admin Dashboard — Champ LMS</title></svelte:head>

<div class="page">
	<h1>L&D Dashboard</h1>

	{#if analytics}
		<div class="stats-grid">
			<div class="stat-card"><p class="val">{analytics.total_users}</p><p class="label">Total Learners</p></div>
			<div class="stat-card"><p class="val">{analytics.published_modules}</p><p class="label">Published Modules</p></div>
			<div class="stat-card"><p class="val">{analytics.episode_completions}</p><p class="label">Episode Completions</p></div>
			<div class="stat-card"><p class="val">{analytics.active_enrollments}</p><p class="label">Active Enrollments</p></div>
		</div>
	{/if}

	<div class="actions">
		<a href="/admin/upload" class="action-card">
			<span class="icon">📤</span>
			<h3>Upload Video</h3>
			<p>Add a new episode to a module</p>
		</a>
		<a href="/admin/zoom" class="action-card">
			<span class="icon">🎙</span>
			<h3>Zoom → Module</h3>
			<p>Convert Zoom recordings into learning modules using AI</p>
		</a>
	</div>
</div>

<style>
	.page { max-width: 1100px; margin: 0 auto; padding: 2rem; }
	h1 { font-size: 2rem; font-weight: 800; margin-bottom: 2rem; }

	.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 2.5rem; }
	.stat-card { background: #1f1f1f; border-radius: 12px; padding: 1.5rem; text-align: center; }
	.val { font-size: 2.5rem; font-weight: 800; color: #e50914; }
	.label { font-size: 0.8rem; color: #888; margin-top: 0.25rem; text-transform: uppercase; letter-spacing: 0.05em; }

	.actions { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; }
	.action-card {
		background: #1f1f1f; border-radius: 12px; padding: 2rem;
		display: block; text-decoration: none; color: #fff;
		transition: background 0.15s;
	}
	.action-card:hover { background: #2a2a2a; }
	.icon { font-size: 2.5rem; display: block; margin-bottom: 1rem; }
	h3 { font-size: 1.1rem; font-weight: 700; margin-bottom: 0.5rem; }
	p { font-size: 0.875rem; color: #888; }
</style>
