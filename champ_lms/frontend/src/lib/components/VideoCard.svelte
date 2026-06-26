<script lang="ts">
	import { goto } from '$app/navigation';
	import type { FeedCard } from '$lib/api/client';

	let { module }: { module: FeedCard } = $props();
</script>

<div class="card" onclick={() => goto(`/module/${module.id}`)} role="button" tabindex="0"
	 onkeydown={(e) => e.key === 'Enter' && goto(`/module/${module.id}`)}>
	<div class="thumbnail">
		{#if module.thumbnail_url}
			<img src={module.thumbnail_url} alt={module.title} loading="lazy" />
		{:else}
			<div class="placeholder">{module.title[0]}</div>
		{/if}

		{#if module.is_new}
			<span class="badge-new">NEW</span>
		{/if}

		{#if module.completion_percentage > 0}
			<div class="progress-bar-track">
				<div class="progress-bar-fill" style="width: {module.completion_percentage}%"></div>
			</div>
		{/if}
	</div>

	<div class="info">
		<p class="title">{module.title}</p>
		{#if module.category}
			<span class="category">{module.category}</span>
		{/if}
		<span class="eps">{module.total_episodes} episodes</span>
	</div>
</div>

<style>
	.card {
		flex: 0 0 220px;
		cursor: pointer;
		scroll-snap-align: start;
		transition: transform 0.2s;
	}
	.card:hover { transform: scale(1.05); z-index: 5; }

	.thumbnail {
		position: relative;
		width: 220px;
		height: 130px;
		border-radius: 6px;
		overflow: hidden;
		background: #2a2a2a;
	}
	img { width: 100%; height: 100%; object-fit: cover; }
	.placeholder {
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 3rem;
		font-weight: 800;
		color: #555;
	}
	.badge-new {
		position: absolute;
		top: 6px;
		left: 6px;
		background: #e50914;
		color: #fff;
		font-size: 0.65rem;
		font-weight: 800;
		padding: 0.15rem 0.4rem;
		border-radius: 3px;
		letter-spacing: 0.05em;
	}
	.progress-bar-track {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		height: 3px;
		background: rgba(255,255,255,0.2);
	}
	.progress-bar-fill {
		height: 100%;
		background: #e50914;
	}

	.info { padding: 0.5rem 0.25rem; }
	.title { font-size: 0.85rem; font-weight: 600; color: #e5e5e5; margin-bottom: 0.25rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.category { font-size: 0.7rem; color: #ff6b6b; font-weight: 600; text-transform: uppercase; margin-right: 0.5rem; }
	.eps { font-size: 0.7rem; color: #888; }
</style>
