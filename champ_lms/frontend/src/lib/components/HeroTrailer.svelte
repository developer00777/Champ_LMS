<script lang="ts">
	import { goto } from '$app/navigation';
	import type { FeedCard } from '$lib/api/client';

	let { module }: { module: FeedCard } = $props();
</script>

<div class="hero" style="background-image: url({module.thumbnail_url || '/placeholder.jpg'})">
	<div class="hero-overlay">
		<div class="hero-content">
			{#if module.category}
				<span class="tag">{module.category}</span>
			{/if}
			<h1>{module.title}</h1>
			<p class="meta">{module.total_episodes} episodes</p>
			<div class="actions">
				<button class="btn-primary" onclick={() => goto(`/module/${module.id}`)}>
					▶ Play
				</button>
				<button class="btn-secondary" onclick={() => goto(`/module/${module.id}`)}>
					More Info
				</button>
			</div>
		</div>
	</div>
</div>

<style>
	.hero {
		height: 85vh;
		background-size: cover;
		background-position: center top;
		position: relative;
	}
	.hero-overlay {
		position: absolute;
		inset: 0;
		background: linear-gradient(
			to right,
			rgba(20, 20, 20, 0.95) 0%,
			rgba(20, 20, 20, 0.6) 50%,
			transparent 100%
		),
		linear-gradient(to top, #141414 0%, transparent 40%);
		display: flex;
		align-items: flex-end;
		padding: 0 4rem 8rem;
	}
	.hero-content { max-width: 600px; }
	h1 { font-size: 3rem; font-weight: 800; margin: 0.5rem 0; line-height: 1.1; }
	.meta { color: #aaa; margin-bottom: 1.5rem; font-size: 0.95rem; }
	.actions { display: flex; gap: 1rem; }
	.tag {
		display: inline-block;
		background: rgba(229,9,20,0.3);
		color: #ff6b6b;
		padding: 0.25rem 0.75rem;
		border-radius: 4px;
		font-size: 0.75rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}
	.btn-primary {
		background: #e50914;
		color: #fff;
		border: none;
		padding: 0.75rem 2rem;
		border-radius: 4px;
		font-size: 1rem;
		font-weight: 700;
		cursor: pointer;
	}
	.btn-secondary {
		background: rgba(255,255,255,0.15);
		color: #fff;
		border: none;
		padding: 0.75rem 2rem;
		border-radius: 4px;
		font-size: 1rem;
		font-weight: 700;
		cursor: pointer;
		backdrop-filter: blur(4px);
	}
</style>
