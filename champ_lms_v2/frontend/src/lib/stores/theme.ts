import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export type Theme = 'light' | 'dark';

const KEY = 'champ_theme';

// app.html sets data-theme before first paint; start from whatever it chose so
// the store and the page never disagree.
function initial(): Theme {
  if (!browser) return 'light';
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

// Cards and buttons transition their colours for hover; without this they'd
// also fade between themes while the rest of the page has already switched.
function apply(next: Theme) {
  const root = document.documentElement;
  root.classList.add('theme-instant');
  root.dataset.theme = next;
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('theme-instant')));
}

function createThemeStore() {
  const { subscribe, set } = writable<Theme>(initial());
  let current = initial();

  if (browser) {
    // Follow the OS setting until the user picks one explicitly.
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      try { if (localStorage.getItem(KEY)) return; } catch {}
      current = e.matches ? 'dark' : 'light';
      apply(current);
      set(current);
    });
  }

  return {
    subscribe,
    /**
     * Flip the theme in one frame. A view-transition reveal or a colour
     * cross-fade showed a raster snapshot / half-mixed colours mid-switch,
     * which read as blur and flicker.
     */
    toggle() {
      current = current === 'dark' ? 'light' : 'dark';
      apply(current);
      set(current);
      // Storage can be blocked (private mode, site data off); the theme still
      // applies for this visit.
      try { localStorage.setItem(KEY, current); } catch {}
    },
  };
}

export const theme = createThemeStore();
