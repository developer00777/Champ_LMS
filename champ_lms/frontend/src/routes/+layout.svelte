<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { user, authLoading, initAuth, logout } from '$lib/stores/auth';
	import '../app.css';

	let { children } = $props();

	const publicRoutes = ['/auth/login', '/auth/callback'];

	onMount(async () => {
		await initAuth();
		if (!$user && !publicRoutes.includes($page.url.pathname)) {
			goto('/auth/login');
		}
	});
</script>

{#if $authLoading}
	<div class="loading-screen">
		<div class="spinner"></div>
	</div>
{:else}
	{#if $user}
		<nav class="navbar">
			<a href="/" class="brand">⚡ Champ LMS</a>
			<div class="nav-links">
				<a href="/">Home</a>
				<a href="/my-learning">My Learning</a>
				<a href="/leaderboard">Leaderboard</a>
				<a href="/admin">Admin</a>
			</div>
			<div class="nav-user">
				<span class="points">🔥 {$user.streak_days}d &nbsp; ⭐ {$user.points}pts</span>
				<button onclick={logout} class="btn-ghost">Sign Out</button>
			</div>
		</nav>
	{/if}
	<main>
		{@render children()}
	</main>
{/if}

<style>
	.loading-screen {
		height: 100vh;
		display: flex;
		align-items: center;
		justify-content: center;
		background: #141414;
	}
	.spinner {
		width: 40px;
		height: 40px;
		border: 3px solid #333;
		border-top-color: #e50914;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin { to { transform: rotate(360deg); } }

	.navbar {
		position: fixed;
		top: 0; left: 0; right: 0;
		z-index: 100;
		display: flex;
		align-items: center;
		gap: 2rem;
		padding: 0.75rem 2rem;
		background: linear-gradient(to bottom, rgba(0,0,0,0.9) 0%, transparent 100%);
	}
	.brand { font-size: 1.5rem; font-weight: 800; color: #e50914; }
	.nav-links { display: flex; gap: 1.5rem; font-size: 0.9rem; }
	.nav-links a:hover { color: #ccc; }
	.nav-user { margin-left: auto; display: flex; align-items: center; gap: 1rem; }
	.points { font-size: 0.85rem; color: #aaa; }
	.btn-ghost {
		background: none;
		border: 1px solid #555;
		color: #fff;
		padding: 0.3rem 0.8rem;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.85rem;
	}
	.btn-ghost:hover { border-color: #fff; }
	main { padding-top: 56px; }
</style>
