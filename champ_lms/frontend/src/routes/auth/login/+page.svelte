<script lang="ts">
	import { goto } from '$app/navigation';
	import { devLogin } from '$lib/stores/auth';

	let loading = $state(false);
	let error = $state('');

	const cognitoClientId = import.meta.env.PUBLIC_COGNITO_CLIENT_ID;
	const cognitoDomain = import.meta.env.PUBLIC_COGNITO_DOMAIN;
	const redirectUri = typeof window !== 'undefined' ? `${window.location.origin}/auth/callback` : '';

	const cognitoUrl = cognitoClientId && cognitoDomain
		? `${cognitoDomain}/login?client_id=${cognitoClientId}&response_type=code&scope=openid+email+profile&redirect_uri=${encodeURIComponent(redirectUri)}`
		: null;

	async function handleDevLogin() {
		loading = true;
		try {
			await devLogin();
			goto('/');
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head><title>Sign In — Champ LMS</title></svelte:head>

<div class="login-page">
	<div class="login-card">
		<div class="logo">⚡</div>
		<h1>Champ LMS</h1>
		<p class="subtitle">Your company's learning platform</p>

		{#if error}
			<p class="error">{error}</p>
		{/if}

		{#if cognitoUrl}
			<a href={cognitoUrl} class="btn-primary">Sign in with Company SSO</a>
		{:else}
			<button class="btn-primary" onclick={handleDevLogin} disabled={loading}>
				{loading ? 'Signing in...' : '🛠 Dev Login (local)'}
			</button>
			<p class="dev-note">Set PUBLIC_COGNITO_CLIENT_ID + PUBLIC_COGNITO_DOMAIN for SSO</p>
		{/if}
	</div>
</div>

<style>
	.login-page {
		min-height: 100vh;
		display: flex;
		align-items: center;
		justify-content: center;
		background: radial-gradient(ellipse at 60% 40%, rgba(229,9,20,0.08) 0%, transparent 60%), #141414;
	}
	.login-card {
		background: #1f1f1f;
		border-radius: 16px;
		padding: 3rem 2.5rem;
		text-align: center;
		width: 100%;
		max-width: 380px;
		box-shadow: 0 20px 60px rgba(0,0,0,0.5);
	}
	.logo { font-size: 3rem; margin-bottom: 0.5rem; }
	h1 { font-size: 1.8rem; font-weight: 800; margin-bottom: 0.5rem; }
	.subtitle { color: #888; font-size: 0.9rem; margin-bottom: 2rem; }
	.error { color: #e50914; font-size: 0.85rem; margin-bottom: 1rem; }

	.btn-primary {
		display: block; width: 100%;
		background: #e50914; color: #fff; border: none;
		padding: 0.85rem; border-radius: 8px;
		font-size: 1rem; font-weight: 700; cursor: pointer;
		text-decoration: none; text-align: center;
	}
	.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }
	.dev-note { font-size: 0.72rem; color: #555; margin-top: 1rem; }
</style>
