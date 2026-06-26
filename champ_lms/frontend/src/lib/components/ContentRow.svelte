<script lang="ts">
	import type { FeedCard } from '$lib/api/client';
	import VideoCard from './VideoCard.svelte';

	let { title, modules }: { title: string; modules: FeedCard[] } = $props();

	let scrollEl: HTMLDivElement = $state(null as any);

	function scroll(dir: 1 | -1) {
		scrollEl.scrollBy({ left: dir * 400, behavior: 'smooth' });
	}
</script>

<div class="row">
	<h2>{title}</h2>
	<div class="scroll-wrapper">
		<button class="arrow left" onclick={() => scroll(-1)}>‹</button>
		<div class="cards" bind:this={scrollEl}>
			{#each modules as mod}
				<VideoCard module={mod} />
			{/each}
		</div>
		<button class="arrow right" onclick={() => scroll(1)}>›</button>
	</div>
</div>

<style>
	.row { margin-bottom: 2.5rem; }
	h2 { font-size: 1.15rem; font-weight: 700; margin-bottom: 0.75rem; color: #e5e5e5; }
	.scroll-wrapper { position: relative; }
	.cards {
		display: flex;
		gap: 0.5rem;
		overflow-x: auto;
		scroll-snap-type: x mandatory;
		scrollbar-width: none;
		padding-bottom: 0.5rem;
	}
	.cards::-webkit-scrollbar { display: none; }
	.arrow {
		position: absolute;
		top: 50%;
		transform: translateY(-50%);
		background: rgba(0,0,0,0.7);
		border: none;
		color: #fff;
		font-size: 2rem;
		width: 2.5rem;
		height: 5rem;
		cursor: pointer;
		z-index: 10;
		border-radius: 4px;
		display: flex;
		align-items: center;
		justify-content: center;
		opacity: 0;
		transition: opacity 0.2s;
	}
	.scroll-wrapper:hover .arrow { opacity: 1; }
	.left { left: -1.25rem; }
	.right { right: -1.25rem; }
</style>
