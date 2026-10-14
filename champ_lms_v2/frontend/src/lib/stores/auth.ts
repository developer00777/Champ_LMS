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
      if (localStorage.getItem('champ_token')) {
        try {
          const user = await api.me();
          set({ user, loading: false, error: null });
          return;
        } catch {
          localStorage.removeItem('champ_token');
        }
      }
      // Local dev: no valid session, so sign straight in as the DEV_LOGIN_EMAIL
      // account. import.meta.env.DEV is false in `vite build`, so this whole
      // block is stripped from the production bundle. Skipped after an
      // explicit sign-out (see logout).
      if (import.meta.env.DEV && !sessionStorage.getItem('champ_dev_login_off')) {
        try {
          const { access_token } = await api.devLogin();
          localStorage.setItem('champ_token', access_token);
          const user = await api.me();
          set({ user, loading: false, error: null });
          // Don't leave a freshly signed-in dev sitting on the sign-in form.
          if (location.pathname === '/auth/login') goto('/');
          return;
        } catch {
          // Backend not set up for dev login — fall through to the normal form.
          localStorage.removeItem('champ_token');
        }
      }
      set({ user: null, loading: false, error: null });
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

    // Re-fetch the current user without touching the token. Used after the
    // user changes something about their own account (e.g. their password)
    // so cached fields like must_change_password stop being stale.
    async refresh() {
      if (!browser) return;
      if (!localStorage.getItem('champ_token')) return;
      try {
        const user = await api.me();
        update(s => ({ ...s, user }));
      } catch {
        // Leave the cached user in place: a transient failure here shouldn't
        // look like a sign-out.
      }
    },

    logout() {
      localStorage.removeItem('champ_token');
      // Let a dev sign out and use another account without being auto-signed
      // back in on the next reload. Cleared when the tab closes.
      if (import.meta.env.DEV) sessionStorage.setItem('champ_dev_login_off', '1');
      set({ user: null, loading: false, error: null });
      goto('/auth/login');
    },
  };
}

export const auth = createAuthStore();
export const isLoggedIn = derived(auth, $a => !!$a.user);
export const isAdmin = derived(auth, $a => $a.user?.role === 'admin' || $a.user?.role === 'ld_lead');
