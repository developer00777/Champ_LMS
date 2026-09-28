/**
 * Pending test requests, for admins.
 *
 * The admin shell polls this so a new request pops up on whatever admin screen
 * is open. Requests already shown (or put off with "Decide later") are
 * remembered for the browser session, so the pop-up interrupts once per
 * request rather than on every poll.
 */
import { writable, get } from 'svelte/store';
import { browser } from '$app/environment';
import { api, type TestRequestRow } from '$lib/api/client';

const SEEN_KEY = 'champ_seen_test_requests';
const POLL_MS = 10_000;

export const pendingRequests = writable<TestRequestRow[]>([]);
// The request open in the approval dialog, if any.
export const activeRequest = writable<TestRequestRow | null>(null);

function seen(): Set<string> {
  try { return new Set(JSON.parse(sessionStorage.getItem(SEEN_KEY) ?? '[]')); } catch { return new Set(); }
}
function markSeen(id: string) {
  const s = seen(); s.add(id);
  try { sessionStorage.setItem(SEEN_KEY, JSON.stringify([...s])); } catch { /* private mode */ }
}

export async function refreshRequests(): Promise<TestRequestRow[]> {
  const rows = await api.testRequests('pending');
  pendingRequests.set(rows);
  // Pop up the oldest request nobody has looked at yet.
  if (!get(activeRequest)) {
    const fresh = rows.find(r => !seen().has(r.id));
    if (fresh) { markSeen(fresh.id); activeRequest.set(fresh); }
  }
  return rows;
}

export function openRequest(r: TestRequestRow) {
  markSeen(r.id);
  activeRequest.set(r);
}

export function closeRequest() {
  activeRequest.set(null);
}

let timer: ReturnType<typeof setInterval> | null = null;
function onVisible() { if (document.visibilityState === 'visible') refreshRequests().catch(() => {}); }

export function startRequestPolling() {
  if (!browser || timer) return;
  refreshRequests().catch(() => {});
  timer = setInterval(() => { if (document.visibilityState === 'visible') refreshRequests().catch(() => {}); }, POLL_MS);
  document.addEventListener('visibilitychange', onVisible);
}

export function stopRequestPolling() {
  if (!browser) return;
  if (timer) clearInterval(timer);
  timer = null;
  document.removeEventListener('visibilitychange', onVisible);
}
