import { writable } from 'svelte/store';
import { browser } from '$app/environment';

/**
 * Animation preference. Defaults to full motion even when the OS asks for
 * reduced motion: Windows turns "Show animations" off on many slower
 * machines for performance, and that would silently strip every animation.
 * People who need less motion switch it off in the profile menu; the choice
 * is saved per browser. app.html applies it before first paint.
 */
export type Motion = 'full' | 'reduced';
const KEY = 'champ_motion';

function initial(): Motion {
  if (!browser) return 'full';
  return document.documentElement.dataset.motion === 'reduced' ? 'reduced' : 'full';
}

function createMotionStore() {
  const { subscribe, set } = writable<Motion>(initial());
  return {
    subscribe,
    set(next: Motion) {
      document.documentElement.dataset.motion = next;
      try { localStorage.setItem(KEY, next); } catch {} // storage may be blocked; still applies now
      set(next);
    },
  };
}

export const motion = createMotionStore();

/** True when the user switched animations off in the app. */
export function motionReduced(): boolean {
  return typeof document !== 'undefined' && document.documentElement.dataset.motion === 'reduced';
}
