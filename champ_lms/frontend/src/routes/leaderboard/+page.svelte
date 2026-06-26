<script lang="ts">
	import { onMount } from 'svelte';
	import { gamificationApi } from '$lib/api/client';
	import type { LeaderboardEntry, Badge } from '$lib/api/client';
	import { user } from '$lib/stores/auth';

	let entries: LeaderboardEntry[] = $state([]);
	let badges: Badge[] = $state([]);
	let streak = $state(0);
	let points = $state(0);
	let loading = $state(true);

	onMount(async () => {
		try {
			[entries, badges] = await Promise.all([
				gamificationApi.leaderboard(),
				gamificationApi.myBadges(),
			]);
			const streakData = await gamificationApi.myStreak();
			streak = streakData.streak_days;
			points = streakData.points;
		} finally {
			loading = false;
		}
	});
</script>

<svelte:head><title>Leaderboard — Champ LMS</title></svelte:head>

<div class="page">
	{#if loading}
		<p class="loading">Loading...</p>
	{:else}
		<div class="stats-bar">
			<div class="stat"><span class="stat-val">🔥 {streak}</span><span class="stat-label">Day Streak</span></div>
			<div class="stat"><span class="stat-val">⭐ {points}</span><span class="stat-label">Total Points</span></div>
			<div class="stat"><span class="stat-val">🏅 {badges.length}</span><span class="stat-label">Badges</span></div>
		</div>

		{#if badges.length > 0}
			<section class="badges-section">
				<h2>My Badges</h2>
				<div class="badges-grid">
					{#each badges as badge}
						<div class="badge-card" title={badge.description || ''}>
							<div class="badge-icon">{badge.icon_url ? '' : '🏆'}</div>
							<p class="badge-name">{badge.name}</p>
						</div>
					{/each}
				</div>
			</section>
		{/if}

		<section>
			<h2>Global Leaderboard</h2>
			<div class="leaderboard">
				{#each entries as entry}
					<div class="entry" class:me={$user && entry.user_id === $user.id}>
						<span class="rank">
							{entry.rank === 1 ? '🥇' : entry.rank === 2 ? '🥈' : entry.rank === 3 ? '🥉' : `#${entry.rank}`}
						</span>
						<div class="user-info">
							<p class="name">{entry.full_name || 'Champion'}</p>
							{#if entry.department}<p class="dept">{entry.department}</p>{/if}
						</div>
						<div class="right">
							<span class="pts">⭐ {entry.points}</span>
							<span class="streak">🔥 {entry.streak_days}d</span>
						</div>
					</div>
				{/each}
			</div>
		</section>
	{/if}
</div>

<style>
	.page { max-width: 800px; margin: 0 auto; padding: 2rem; }
	.loading { color: #aaa; padding: 4rem 0; }
	h2 { font-size: 1.15rem; font-weight: 700; margin-bottom: 1rem; }

	.stats-bar { display: flex; gap: 1.5rem; margin-bottom: 2.5rem; }
	.stat { background: #1f1f1f; border-radius: 12px; padding: 1.25rem 2rem; flex: 1; text-align: center; }
	.stat-val { display: block; font-size: 1.6rem; font-weight: 800; margin-bottom: 0.25rem; }
	.stat-label { font-size: 0.8rem; color: #888; text-transform: uppercase; letter-spacing: 0.05em; }

	.badges-section { margin-bottom: 2.5rem; }
	.badges-grid { display: flex; flex-wrap: wrap; gap: 1rem; }
	.badge-card { background: #1f1f1f; border-radius: 8px; padding: 1rem; text-align: center; min-width: 100px; }
	.badge-icon { font-size: 2rem; margin-bottom: 0.4rem; }
	.badge-name { font-size: 0.75rem; font-weight: 600; color: #ccc; }

	.leaderboard { display: flex; flex-direction: column; gap: 0.5rem; }
	.entry {
		display: flex; align-items: center; gap: 1rem;
		background: #1f1f1f; border-radius: 8px; padding: 0.9rem 1.25rem;
		transition: background 0.15s;
	}
	.entry.me { background: rgba(229,9,20,0.12); border: 1px solid rgba(229,9,20,0.3); }
	.rank { font-size: 1.1rem; min-width: 2.5rem; text-align: center; font-weight: 700; }
	.user-info { flex: 1; }
	.name { font-size: 0.95rem; font-weight: 600; }
	.dept { font-size: 0.75rem; color: #888; }
	.right { display: flex; gap: 1rem; font-size: 0.85rem; color: #ccc; }
	.pts { font-weight: 700; }
</style>
