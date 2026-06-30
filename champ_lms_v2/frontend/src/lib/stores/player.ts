import { writable } from 'svelte/store';
import { api } from '$lib/api/client';

interface PlayerState {
  episodeId: string | null;
  watchedSeconds: number;
  totalSeconds: number;
}

function createPlayerStore() {
  const { subscribe, update } = writable<PlayerState>({
    episodeId: null,
    watchedSeconds: 0,
    totalSeconds: 0,
  });

  let syncInterval: ReturnType<typeof setInterval> | null = null;

  return {
    subscribe,

    startTracking(episodeId: string) {
      update(s => ({ ...s, episodeId, watchedSeconds: 0 }));

      // Sync progress to server every 30 seconds
      if (syncInterval) clearInterval(syncInterval);
      syncInterval = setInterval(() => {
        let current: PlayerState = { episodeId: null, watchedSeconds: 0, totalSeconds: 0 };
        const unsub = this.subscribe(s => { current = s; });
        unsub();

        if (current.episodeId && current.totalSeconds > 0) {
          api.updateProgress(current.episodeId, current.watchedSeconds, current.totalSeconds)
            .catch(() => {/* silent — offline resilience */});
        }
      }, 30_000);
    },

    updateTime(watchedSeconds: number, totalSeconds: number) {
      update(s => ({ ...s, watchedSeconds, totalSeconds }));
    },

    stopTracking() {
      if (syncInterval) {
        clearInterval(syncInterval);
        syncInterval = null;
      }
    },
  };
}

export const player = createPlayerStore();
