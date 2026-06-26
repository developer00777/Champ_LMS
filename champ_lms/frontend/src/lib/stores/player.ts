import { writable } from 'svelte/store';
import { progressApi } from '$lib/api/client';

export const currentEpisodeId = writable<string | null>(null);

let syncInterval: ReturnType<typeof setInterval> | null = null;
let lastSynced = 0;

export function startProgressSync(episodeId: string, getProgress: () => { watched: number; total: number }) {
	currentEpisodeId.set(episodeId);

	if (syncInterval) clearInterval(syncInterval);

	syncInterval = setInterval(async () => {
		const { watched, total } = getProgress();
		if (watched === lastSynced || total === 0) return;
		lastSynced = watched;
		try {
			await progressApi.upsert({
				episode_id: episodeId,
				watched_seconds: Math.floor(watched),
				total_seconds: Math.floor(total),
			});
		} catch {
			// Silent — progress sync is best-effort
		}
	}, 30_000);
}

export function stopProgressSync() {
	if (syncInterval) {
		clearInterval(syncInterval);
		syncInterval = null;
	}
	lastSynced = 0;
}
