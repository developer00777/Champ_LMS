const BASE = import.meta.env.VITE_API_URL ?? '/api';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem('champ_token');
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err.detail ?? 'Request failed');
  }
  return res.json();
}

export const api = {
  // Auth
  login: (email: string, password: string) => {
    const form = new URLSearchParams({ username: email, password });
    return request<{ access_token: string }>('/auth/token', {
      method: 'POST',
      body: form.toString(),
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
  },
  register: (body: { email: string; full_name: string; password: string; department?: string }) =>
    request('/auth/register', { method: 'POST', body: JSON.stringify(body) }),
  me: () => request<User>('/auth/me'),

  // Content
  feed: () => request<FeedRow[]>('/feed'),
  modules: (params?: { category?: string; q?: string }) => {
    const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
    return request<Module[]>(`/modules${qs}`);
  },
  module: (id: string) => request<ModuleDetail>(`/modules/${id}`),
  streamUrl: (episodeId: string) => request<StreamUrlResponse>(`/episodes/${episodeId}/stream`),
  search: (q: string) => request<SearchResult>(`/search?q=${encodeURIComponent(q)}`),

  // Progress
  updateProgress: (episodeId: string, watchedSeconds: number, totalSeconds: number) =>
    request('/progress', {
      method: 'POST',
      body: JSON.stringify({ episode_id: episodeId, watched_seconds: watchedSeconds, total_seconds: totalSeconds }),
    }),
  myProgress: () => request<ProgressEntry[]>('/progress/me'),
  episodeProgress: (episodeId: string) => request<ProgressEntry>(`/progress/${episodeId}`),

  // Gamification
  leaderboard: (department?: string) =>
    request<LeaderboardEntry[]>(`/leaderboard${department ? `?department=${department}` : ''}`),
  myBadges: () => request<Badge[]>('/badges/me'),
  myStreak: () => request<StreakData>('/streaks/me'),

  // Admin
  createModule: (body: { title: string; description?: string; category?: string; tags?: string[] }) =>
    request<{ id: string }>('/admin/modules', { method: 'POST', body: JSON.stringify(body) }),
  publishModule: (id: string) =>
    request(`/admin/modules/${id}/publish`, { method: 'PATCH' }),
  addEpisode: (moduleId: string, body: { title: string; description?: string; sequence_order: number }) =>
    request<{ id: string }>(`/admin/modules/${moduleId}/episodes`, { method: 'POST', body: JSON.stringify(body) }),
  analytics: () => request<AnalyticsData>('/admin/analytics'),

  // Zoom
  zoomSessions: () => request<ZoomSession[]>('/zoom/sessions'),
  addZoomSession: (body: { topic: string; summary: string; transcript: string; zoom_meeting_id?: string }) =>
    request('/zoom/sessions', { method: 'POST', body: JSON.stringify(body) }),
  buildModule: (sessionId: string) =>
    request(`/zoom/sessions/${sessionId}/build-module`, { method: 'POST' }),

  // Assessments
  getAssessment: (moduleId: string) => request<AssessmentData>(`/assessments/${moduleId}`),
  submitAttempt: (assessmentId: string, answers: number[]) =>
    request<AttemptResult>(`/assessments/${assessmentId}/attempt`, {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),
};

// Types
export interface User {
  id: string; email: string; full_name: string | null;
  role: string; department: string | null; points: number; streak_days: number;
}
export interface Module {
  id: string; title: string; description: string | null;
  category: string | null; tags: string[] | null;
  thumbnail_url: string | null; total_episodes: number; is_published: boolean;
}
export interface Episode {
  id: string; title: string; description: string | null;
  duration_seconds: number | null; sequence_order: number;
  status: string; thumbnail_url: string | null;
}
export interface ModuleDetail extends Module { episodes: Episode[]; }
export interface FeedRow { row_title: string; modules: Module[]; }
export interface StreamUrlResponse { stream_url: string; embed_url: string; expires_in: number; }
export interface SearchResult { modules: Module[]; episodes: { id: string; title: string; module_id: string }[]; }
export interface ProgressEntry {
  episode_id: string; watched_seconds: number; total_seconds: number;
  completed?: boolean; last_watched_at?: string;
}
export interface LeaderboardEntry {
  rank: number; user_id: string; full_name: string | null;
  department: string | null; points: number; streak_days: number;
}
export interface Badge {
  badge_id: string; name: string; description: string | null;
  icon_url: string | null; earned_at: string;
}
export interface StreakData { streak_days: number; last_activity_date: string | null; points: number; }
export interface ZoomSession {
  id: string; topic: string; processed: boolean;
  module_id: string | null; created_at: string;
}
export interface AnalyticsData {
  total_users: number; published_modules: number;
  episode_completions: number; total_enrollments: number;
}
export interface AssessmentData {
  id: string; title: string | null;
  questions: { question: string; options: string[] }[];
}
export interface AttemptResult {
  score: number; passed: boolean; pass_threshold: number;
  feedback: { question: string; correct: boolean; correct_answer: string; explanation: string | null }[];
}
