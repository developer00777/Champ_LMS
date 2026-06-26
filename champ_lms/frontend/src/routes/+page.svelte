<script lang="ts">
	import { onMount } from 'svelte';
	import { feedApi } from '$lib/api/client';
	import type { FeedResponse } from '$lib/api/client';
	import ContentRow from '$lib/components/ContentRow.svelte';
	import HeroTrailer from '$lib/components/HeroTrailer.svelte';

	let feed: FeedResponse | null = $state(null);
	let error = $state('');

	onMount(async () => {
		try {
			feed = await feedApi.getFeed();
		} catch (e: any) {
			error = e.message;
		}
	});
</script>

<svelte:head><title>Champ LMS — Home</title></svelte:head>

{#if error}
	<div class="error-msg">{error}</div>
{:else if !feed}
	<div class="loading">Loading your feed...</div>
{:else}
	{#if feed.rows[0]?.modules[0]}
		<HeroTrailer module={feed.rows[0].modules[0]} />
	{/if}

	<div class="feed">
		{#each feed.rows as row}
			<ContentRow title={row.row_title} modules={row.modules} />
		{/each}
	</div>
{/if}

<style>
	.feed { padding: 0 2rem 4rem; }
	.loading { padding: 6rem 2rem; color: #aaa; }
	.error-msg { padding: 6rem 2rem; color: #e50914; }
</style>
