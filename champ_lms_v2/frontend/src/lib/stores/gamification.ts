import { writable, derived } from 'svelte/store';
import { browser } from '$app/environment';
import {
  api,
  type RewardSummary,
  type LevelInfo,
  type Quest,
  type UpskillingTrack,
  type ActivityItem,
} from '$lib/api/client';

export interface GamificationState {
  levelInfo: LevelInfo | null;
  quests: Quest[];
  upselling: UpskillingTrack | null;
  activity: ActivityItem[];
  loading: boolean;
  error: string | null;
}

function createGamificationStore() {
  const { subscribe, set, update } = writable<GamificationState>({
    levelInfo: null,
    quests: [],
    upselling: null,
    activity: [],
    loading: false,
    error: null,
  });

  return {
    subscribe,

    async load() {
      if (!browser) return;
      update(s => ({ ...s, loading: true, error: null }));
      try {
        const [levelInfo, quests, upselling] = await Promise.all([
          api.levelInfo().catch(() => null),
          api.quests().catch(() => []),
          api.upsellingTrack().catch(() => null),
        ]);
        update(s => ({ ...s, levelInfo, quests, upselling, loading: false }));
      } catch (e: any) {
        update(s => ({ ...s, loading: false, error: e.message }));
      }
    },

    async loadActivity(limit = 20) {
      if (!browser) return;
      try {
        const activity = await api.activityFeed(limit);
        update(s => ({ ...s, activity }));
      } catch {}
    },

    /** Call after any action that returns rewards (progress, quiz). */
    async rehydrate() {
      await this.load();
    },
  };
}

export const gamification = createGamificationStore();

/** Queue of reward summaries to show in a modal/toast sequence. */
function createRewardQueue() {
  const { subscribe, update } = writable<RewardSummary[]>([]);
  return {
    subscribe,
    push(reward: RewardSummary) {
      update(list => [...list, reward]);
    },
    shift() {
      update(list => list.slice(1));
    },
    clear() {
      update(() => []);
    },
  };
}

export const rewardQueue = createRewardQueue();

/** Derived boolean for whether at least one level-up is pending. */
export const hasLevelUp = derived(rewardQueue, $q => $q.some(r => r.level_up));

/** Helper to enqueue a RewardSummary returned by backend. */
export function handleReward(reward?: RewardSummary) {
  if (!reward) return;
  rewardQueue.push(reward);
}
