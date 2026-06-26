<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { setToken } from '$lib/api/client';
	import { authApi } from '$lib/api/client';
	import { user } from '$lib/stores/auth';

	let error = $state('');

	onMount(async () => {
		const code = $page.url.searchParams.get('code');
		if (!code) {
			error = 'No authorization code received';
			return;
		}

		try {
			// Exchange code for tokens via Cognito token endpoint
			const cognitoDomain = import.meta.env.PUBLIC_COGNITO_DOMAIN;
			const clientId = import.meta.env.PUBLIC_COGNITO_CLIENT_ID;
			const redirectUri = `${window.location.origin}/auth/callback`;

			const res = await fetch(`${cognitoDomain}/oauth2/token`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
				body: new URLSearchParams({
					grant_type: 'authorization_code',
					client_id: clientId,
					code,
					redirect_uri: redirectUri,
				}),
			});

			if (!res.ok) throw new Error('Token exchange failed');
			const tokens = await res.json();
			setToken(tokens.id_token);

			const me = await authApi.verify();
			user.set(me);
			goto('/');
		} catch (e: any) {
			error = e.message;
		}
	});
</script>

<div class="callback-page">
	{#if error}
		<p class="error">{error}</p>
		<a href="/auth/login">Back to login</a>
	{:else}
		<div class="spinner"></div>
		<p>Signing you in...</p>
	{/if}
</div>

<style>
	.callback-page {
		min-height: 100vh; display: flex; flex-direction: column;
		align-items: center; justify-content: center; gap: 1rem;
		color: #aaa;
	}
	.spinner {
		width: 40px; height: 40px;
		border: 3px solid #333; border-top-color: #e50914;
		border-radius: 50%; animation: spin 0.8s linear infinite;
	}
	@keyframes spin { to { transform: rotate(360deg); } }
	.error { color: #e50914; }
</style>
