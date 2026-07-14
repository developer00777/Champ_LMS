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
    request<RewardSummary | { rewards?: RewardSummary; level_up?: boolean; new_level?: number }>('/progress', {
      method: 'POST',
      body: JSON.stringify({ episode_id: episodeId, watched_seconds: watchedSeconds, total_seconds: totalSeconds }),
    }),
  myProgress: () => request<ProgressEntry[]>('/progress/me'),
  episodeProgress: (episodeId: string) => request<ProgressEntry>(`/progress/${episodeId}`),

  // Gamification
  leaderboard: (department?: string) =>
    request<LeaderboardEntry[]>(`/leaderboard${department ? `?department=${department}` : ''}`),
  moduleLeaderboard: (moduleId: string) =>
    request<ModuleLeaderboard>(`/leaderboard/modules/${moduleId}`),
  myBadges: () => request<Badge[]>('/badges/me'),
  myStreak: () => request<StreakData>('/streaks/me'),
  levelInfo: () => request<LevelInfo>('/me/level'),
  xpHistory: (limit = 20) => request<XpEvent[]>(`/me/xp-history?limit=${limit}`),
  quests: () => request<Quest[]>('/quests/me'),
  upsellingTrack: () => request<UpskillingTrack>('/me/upselling-track'),
  activityFeed: (limit = 20) => request<ActivityItem[]>(`/activity/recent?limit=${limit}`),
  shareAchievement: (type: string, refId: string) =>
    request<SharePayload>('/share/achievement', {
      method: 'POST',
      body: JSON.stringify({ type, ref_id: refId }),
    }),

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

  // Learning Paths
  paths: (params?: { department?: string; path_type?: string }) => {
    const qs = params ? '?' + new URLSearchParams(params as Record<string, string>).toString() : '';
    return request<PathSummary[]>(`/paths${qs}`);
  },
  path: (id: string) => request<PathDetail>(`/paths/${id}`),
  enrollPath: (id: string) => request(`/paths/${id}/enroll`, { method: 'POST' }),
  advancePath: (id: string) => request(`/paths/${id}/advance`, { method: 'POST' }),

  // Challenges
  challenges: (department?: string) =>
    request<ChallengeSummary[]>(`/challenges${department ? `?department=${department}` : ''}`),
  challenge: (id: string) => request<ChallengeDetail>(`/challenges/${id}`),
  createTeam: (challengeId: string, name: string) =>
    request<{ id: string }>(`/challenges/${challengeId}/teams`, { method: 'POST', body: JSON.stringify({ name }) }),
  joinTeam: (challengeId: string, teamId: string) =>
    request(`/challenges/${challengeId}/join`, { method: 'POST', body: JSON.stringify({ team_id: teamId }) }),
  challengeLeaderboard: (challengeId: string) =>
    request<{ challenge_id: string; entries: ChallengeLeaderboardEntry[] }>(`/challenges/${challengeId}/leaderboard`),

  // Social
  socialFeed: (department?: string, limit = 30) =>
    request<SocialPostItem[]>(`/social/feed?limit=${limit}${department ? `&department=${department}` : ''}`),
  createPost: (body: { post_type: string; body: string; team_id?: string; ref_type?: string; ref_id?: string }) =>
    request<{ id: string }>('/social/posts', { method: 'POST', body: JSON.stringify(body) }),
  toggleLike: (postId: string) =>
    request<{ liked: boolean; like_count: number }>(`/social/posts/${postId}/like`, { method: 'POST' }),
  notifications: (unreadOnly = false) =>
    request<NotificationItem[]>(`/notifications${unreadOnly ? '?unread_only=true' : ''}`),
  markNotificationRead: (id: string) =>
    request(`/notifications/${id}/read`, { method: 'POST' }),
  markAllNotificationsRead: () =>
    request('/notifications/read-all', { method: 'POST' }),
};

// Types
export interface User {
  id: string; email: string; full_name: string | null;
  role: string; department: string | null; points: number; streak_days: number;
  xp: number; level: number;
}
export interface RewardEntry {
  type: string;
  points: number;
  xp: number;
  name: string;
}
export interface RewardSummary {
  total_points: number;
  total_xp: number;
  episode?: RewardEntry;
  module_completion?: RewardEntry & { bonus_points?: number };
  first_to_complete?: RewardEntry;
  module_mastery?: RewardEntry;
  perfect_quiz?: RewardEntry;
  badge?: { badge_id: string; name: string };
  level_up?: boolean;
  new_level?: number;
}
export interface LevelInfo {
  level: number; xp: number; xp_to_next_level: number;
  tier: string; next_tier: string | null;
}
export interface XpEvent {
  id: string; reason: string; amount: number;
  created_at: string; ref_id?: string | null;
}
export interface Quest {
  quest_id: string; title: string; description: string | null;
  scope: 'daily' | 'weekly' | 'monthly';
  target: number; progress: number; completed: boolean;
  xp_reward: number; points_reward: number;
}
export interface UpskillingTrack {
  type: string; track: string;
  total_modules: number; mastered_modules: number;
  mastery_percentage: number;
  modules: {
    module_id: string; title: string;
    status: 'not_started' | 'in_progress' | 'completed' | 'mastered';
    progress: number;
  }[];
  rank_in_department: number;
}
export interface SharePayload {
  type: string; ref_id: string; user_name: string;
  share_text: string; share_url: string;
  badge?: string;
}
export interface ActivityItem {
  id: string; type: string; message: string;
  points?: number; xp?: number; created_at: string;
  metadata?: Record<string, any>;
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
  feedback: { question: string; correct: boolean; correct_answer: string; explanation: string | null; your_answer?: string }[];
  rewards?: RewardSummary;
}
export interface ModuleLeaderboard {
  module_id: string; module_title: string; total_points: number;
  entries: LeaderboardEntry[];
}

// * Learning Path types
export interface PathSummary {
  id: string; key: string; title: string; description: string | null;
  department: string | null; path_type: string; variant: string;
  total_modules: number; total_nodes: number;
}
export interface PathNode {
  sequence: number; module_id: string; node_type: string;
  unlock_rule: string; is_summit: boolean; title: string;
  module_title: string | null; module_category: string | null;
  thumbnail_url: string | null; total_episodes: number;
  progress_pct: number; mastered: boolean;
  status: 'locked' | 'unlocked' | 'in_progress' | 'completed' | 'mastered';
}
export interface PathDetail extends PathSummary {
  nodes: PathNode[]; current_node: number;
  unlocked_nodes: number[]; mastered_nodes: number[];
  total_nodes: number; mastered_count: number;
  completion_percentage: number;
  started_at: string; completed_at: string | null;
}

// * Challenge types
export interface ChallengeSummary {
  id: string; key: string; title: string; description: string | null;
  challenge_type: string; department: string | null; team_size: number;
  criteria: Record<string, any>; reward_xp: number; reward_points: number;
  start_at: string; end_at: string | null;
  total_teams: number; my_team_id: string | null;
}
export interface ChallengeTeam {
  id: string; name: string; department: string | null;
  captain_id: string | null; member_count: number;
  members: { id: string; name: string | null; department: string | null }[];
  progress: number; target: number; completed: boolean; completed_at: string | null;
}
export interface ChallengeDetail extends ChallengeSummary {
  teams: ChallengeTeam[];
}
export interface ChallengeLeaderboardEntry {
  rank: number; team_id: string; team_name: string;
  department: string | null; member_count: number;
  progress: number; target: number; completed: boolean; completed_at: string | null;
}

// * Social types
export interface SocialPostItem {
  id: string; post_type: string; body: string;
  user_id: string; user_name: string | null; user_department: string | null;
  team_id: string | null; ref_type: string | null; ref_id: string | null;
  likes: string[]; liked_by_me: boolean; created_at: string;
}
export interface NotificationItem {
  id: string; type: string; title: string; body: string | null;
  ref_type: string | null; ref_id: string | null;
  read: boolean; created_at: string;
}
