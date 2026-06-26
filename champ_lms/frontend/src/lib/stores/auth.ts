import { writable } from 'svelte/store';
import type { User } from '$lib/api/client';
import { authApi, setToken, clearToken } from '$lib/api/client';

export const user = writable<User | null>(null);
export const authLoading = writable(true);

export async function initAuth() {
	const token = localStorage.getItem('champ_token');
	if (!token) {
		authLoading.set(false);
		return;
	}
	try {
		const me = await authApi.verify();
		user.set(me);
	} catch {
		clearToken();
	} finally {
		authLoading.set(false);
	}
}

export function logout() {
	clearToken();
	user.set(null);
	window.location.href = '/auth/login';
}

// Dev-mode mock login (no Cognito)
export async function devLogin() {
	// In dev the backend accepts any Bearer token when COGNITO_USER_POOL_ID is empty
	setToken('dev-token');
	const me = await authApi.verify();
	user.set(me);
	return me;
}
