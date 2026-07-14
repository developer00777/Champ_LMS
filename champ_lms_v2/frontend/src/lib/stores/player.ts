import { writable } from 'svelte/store';
import { api, type RewardSummary } from '$lib/api/client';
import { handleReward, gamification } from '$lib/stores/gamification';

interface PlayerState {
  episodeId: string | null;
  watchedSeconds: number;
  totalSeconds: number;
}

function normalizeReward(resp: any): RewardSummary | undefined {
  if (!resp) return undefined;
  if (resp && typeof resp === 'object' && 'rewards' in resp) {
    return resp.rewards as RewardSummary;
  }
  // If the endpoint returns the RewardSummary directly
  if (resp && (resp.total_points !== undefined || resp.episode || resp.module_completion)) {
    return resp as RewardSummary;
  }
  return undefined;
}

function rewardFromResponse(resp: any) {
  const rewards = normalizeReward(resp);
  if (rewards) {
    handleReward(rewards);
    gamification.rehydrate();
  }
  return rewards;
}

function createPlayerStore() {
  const { subscribe, update } = writable<PlayerState>({
    episodeId: null,
    watchedSeconds: 0,
    totalSeconds: 0,
  });

  let syncInterval: ReturnType<typeof setInterval> | null = null;

  function getState(): PlayerState {
    let current: PlayerState = { episodeId: null, watchedSeconds: 0, totalSeconds: 0 };
    const unsub = subscribe(s => { current = s; });
    unsub();
    return current;
  }

  async function flush() {
    const current = getState();
    if (!current.episodeId || current.totalSeconds <= 0) return;
    const resp = await api.updateProgress(current.episodeId, current.watchedSeconds, current.totalSeconds);
    rewardFromResponse(resp);
  }

  return {
    subscribe,

    startTracking(episodeId: string) {
      update(s => ({ ...s, episodeId, watchedSeconds: 0, totalSeconds: 0 }));

      if (syncInterval) clearInterval(syncInterval);
      syncInterval = setInterval(() => {
        flush().catch(() => {/* silent — offline resilience */});
      }, 30_000);
    },

    updateTime(watchedSeconds: number, totalSeconds: number) {
      update(s => ({ ...s, watchedSeconds, totalSeconds }));
    },

    async complete() {
      await flush();
      if (syncInterval) {
        clearInterval(syncInterval);
        syncInterval = null;
      }
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
