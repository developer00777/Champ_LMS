import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';
import { goto } from '$app/navigation';
import { api, type User } from '$lib/api/client';

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
}

function createAuthStore() {
  const { subscribe, set, update } = writable<AuthState>({
    user: null,
    loading: true,
    error: null,
  });

  return {
    subscribe,

    async init() {
      if (!browser) return;
      const token = localStorage.getItem('champ_token');
      if (!token) {
        update(s => ({ ...s, loading: false }));
        return;
      }
      try {
        const user = await api.me();
        set({ user, loading: false, error: null });
      } catch {
        localStorage.removeItem('champ_token');
        set({ user: null, loading: false, error: null });
      }
    },

    async login(email: string, password: string) {
      update(s => ({ ...s, loading: true, error: null }));
      try {
        const { access_token } = await api.login(email, password);
        localStorage.setItem('champ_token', access_token);
        const user = await api.me();
        set({ user, loading: false, error: null });
        goto('/');
      } catch (e: any) {
        update(s => ({ ...s, loading: false, error: e.message }));
        throw e;
      }
    },

    logout() {
      localStorage.removeItem('champ_token');
      set({ user: null, loading: false, error: null });
      goto('/auth/login');
    },
  };
}

export const auth = createAuthStore();
export const isLoggedIn = derived(auth, $a => !!$a.user);
export const isAdmin = derived(auth, $a => $a.user?.role === 'admin' || $a.user?.role === 'ld_lead');
