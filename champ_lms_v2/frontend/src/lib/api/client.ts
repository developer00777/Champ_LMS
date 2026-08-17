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
  publishModule: (id: string, publish = true) =>
    request<{ module_id: string; published: boolean }>(
      `/admin/modules/${id}/publish?publish=${publish}`, { method: 'PATCH' }),
  // sequence_order omitted = append after the last episode
  addEpisode: (moduleId: string, body: { title: string; description?: string; sequence_order?: number }) =>
    request<{ id: string; title: string; sequence_order: number; total_episodes: number }>(
      `/admin/modules/${moduleId}/episodes`, { method: 'POST', body: JSON.stringify(body) }),
  analytics: () => request<AnalyticsData>('/admin/analytics'),

  // Admin — extend an existing module after it was created
  adminModule: (id: string) => request<AdminModuleDetail>(`/admin/modules/${id}`),
  updateModule: (id: string, body: ModuleEditBody) =>
    request<AdminModuleDetail>(`/admin/modules/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  updateEpisode: (episodeId: string, body: { title?: string; description?: string | null; sequence_order?: number }) =>
    request<{ id: string; title: string; sequence_order: number; status: string }>(
      `/admin/episodes/${episodeId}`, { method: 'PATCH', body: JSON.stringify(body) }),
  reorderEpisodes: (moduleId: string, episodeIds: string[]) =>
    request<{ module_id: string; order: { id: string; sequence_order: number }[] }>(
      `/admin/modules/${moduleId}/episodes/reorder`,
      { method: 'PATCH', body: JSON.stringify({ episode_ids: episodeIds }) }),

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

  // Admin — content library + permanent deletion
  adminContent: () => request<AdminContent>('/admin/content'),
  previewEpisodeDelete: (episodeId: string) =>
    request<EpisodeDeletePreview>(`/admin/episodes/${episodeId}/delete-preview`),
  previewModuleDelete: (moduleId: string) =>
    request<ModuleDeletePreview>(`/admin/modules/${moduleId}/delete-preview`),
  // confirm must equal the id — a guard against an accidental DELETE
  deleteEpisodePermanently: (episodeId: string) =>
    request<PurgeResult>(`/admin/episodes/${episodeId}?confirm=${encodeURIComponent(episodeId)}`,
      { method: 'DELETE' }),
  deleteModulePermanently: (moduleId: string) =>
    request<PurgeResult>(`/admin/modules/${moduleId}?confirm=${encodeURIComponent(moduleId)}`,
      { method: 'DELETE' }),

  // Test Series — admin
  parseTestPdf: async (file: File, useAi = false): Promise<ParsedPdf> => {
    // multipart: let the browser set Content-Type so the boundary is correct
    const form = new FormData();
    form.append('file', file);
    form.append('use_ai', String(useAi));
    const token = localStorage.getItem('champ_token');
    const res = await fetch(`${BASE}/admin/test-series/parse-pdf`, {
      method: 'POST',
      body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, err.detail ?? 'Upload failed');
    }
    return res.json();
  },
  createTestSeries: (body: TestSeriesCreate, source?: { filename?: string; parser?: string }) => {
    const qs = new URLSearchParams();
    if (source?.filename) qs.set('source_filename', source.filename);
    if (source?.parser) qs.set('source_parser', source.parser);
    const suffix = qs.toString() ? `?${qs}` : '';
    return request<AdminTest>(`/admin/test-series${suffix}`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
  // * parse a second PDF against an existing test — returns a draft flagged for
  // * duplicates; nothing is saved until appendTestQuestions is called
  parseTestPdfForTest: async (testId: string, file: File, useAi = false): Promise<ParsedPdfForTest> => {
    const form = new FormData();
    form.append('file', file);
    form.append('use_ai', String(useAi));
    const token = localStorage.getItem('champ_token');
    const res = await fetch(`${BASE}/admin/test-series/${testId}/parse-pdf`, {
      method: 'POST',
      body: form,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, err.detail ?? 'Upload failed');
    }
    return res.json();
  },
  appendTestQuestions: (
    testId: string,
    questions: TestQuestionDraft[],
    source?: { filename?: string | null; parser?: string | null },
  ) =>
    request<AppendResult>(`/admin/test-series/${testId}/questions`, {
      method: 'POST',
      body: JSON.stringify({
        questions,
        source_filename: source?.filename ?? null,
        source_parser: source?.parser ?? null,
      }),
    }),
  deleteTestQuestion: (testId: string, questionId: string) =>
    request<AdminTest>(`/admin/test-series/${testId}/questions/${questionId}`, { method: 'DELETE' }),

  adminTestList: () => request<AdminTestSummary[]>('/admin/test-series'),
  adminTest: (id: string) => request<AdminTest>(`/admin/test-series/${id}`),
  updateTestSeries: (id: string, body: Partial<TestSeriesCreate> & { shuffle_questions?: boolean }) =>
    request<AdminTest>(`/admin/test-series/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  publishTestSeries: (id: string, publish = true) =>
    request<{ id: string; is_published: boolean }>(
      `/admin/test-series/${id}/publish?publish=${publish}`, { method: 'PATCH' }),
  deleteTestSeries: (id: string) =>
    request<{ deleted: string }>(`/admin/test-series/${id}`, { method: 'DELETE' }),
  testResults: (id: string) => request<TestResults>(`/admin/test-series/${id}/results`),
  analyzeAttemptAdmin: (attemptId: string) =>
    request<{ attempt_id: string; ai_analysis: AiAnalysis }>(
      `/admin/test-series/attempts/${attemptId}/analyze`, { method: 'POST' }),

  // Test Series — learner
  testSeries: () => request<LearnerTest[]>('/test-series'),
  takeTest: (id: string) => request<TestPaper>(`/test-series/${id}/take`),
  submitTest: (id: string, answers: Record<string, number | null>) =>
    request<TestResult>(`/test-series/${id}/submit`, {
      method: 'POST',
      body: JSON.stringify({ answers }),
    }),
  myTestAttempts: () => request<MyAttempt[]>('/test-series/attempts/me'),
  testAttempt: (attemptId: string) => request<AttemptDetail>(`/test-series/attempts/${attemptId}`),
  attemptAnalysis: (attemptId: string) =>
    request<{ attempt_id: string; ai_analysis: AiAnalysis }>(
      `/test-series/attempts/${attemptId}/analysis`, { method: 'POST' }),

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

// * Admin content library / permanent deletion types
export interface AdminEpisodeRow {
  id: string; title: string; sequence_order: number; status: string;
  duration_seconds: number | null;
  bunny_video_guid: string | null; has_remote_video: boolean;
  thumbnail_bunny_path: string | null; thumbnail_url: string | null;
}
export interface AdminModuleRow {
  id: string; title: string; category: string | null;
  is_published: boolean; total_episodes: number; live_episode_count: number;
  created_at: string; episodes: AdminEpisodeRow[];
}
export interface AdminContent {
  modules: AdminModuleRow[];
  orphan_episodes: { id: string; title: string; module_id: string; bunny_video_guid: string | null }[];
}
export interface EpisodeDeletePreview {
  scope: 'episode'; episode_id: string; title: string;
  module_id: string; module_title: string | null;
  bunny_video_guid: string | null; has_remote_video: boolean;
  thumbnail_bunny_path: string | null;
  episodes: number; watch_progress: number;
  assessments: number; assessment_attempts: number;
  xp_events_preserved: boolean;
}
export interface ModuleDeletePreview {
  scope: 'module'; module_id: string; module_title: string;
  is_published: boolean; episodes: number; remote_videos: number;
  episode_titles: string[]; enrollments: number;
  watch_progress: number; assessments: number; assessment_attempts: number;
  xp_events_preserved: boolean;
}
export interface PurgeResult {
  scope: 'episode' | 'module';
  episode_id?: string; module_id?: string;
  remote: { episode_id: string; asset: string; guid?: string | null; path?: string; status: string; detail?: string }[];
  deleted: {
    episodes: number; watch_progress: number;
    assessments: number; assessment_attempts: number;
    redis_keys?: number; enrollments?: number;
  };
  enrollments_recomputed?: number;
  xp_events_preserved: boolean;
}

// * Admin module editor — extend/edit a module after it was created
export interface AdminEpisodeDetail {
  id: string; title: string; description: string | null;
  sequence_order: number; status: string; duration_seconds: number | null;
  bunny_video_guid: string | null; has_remote_video: boolean;
  thumbnail_url: string | null; created_at: string;
}
export interface AdminModuleDetail {
  id: string; title: string; description: string | null;
  category: string | null; tags: string[] | null; target_roles: string[] | null;
  module_type: string; target_department: string | null;
  points_weight: number; is_published: boolean; total_episodes: number;
  source_type: string; created_at: string;
  episodes: AdminEpisodeDetail[];
}
export interface ModuleEditBody {
  title?: string; description?: string | null; category?: string | null;
  tags?: string[] | null; target_roles?: string[] | null;
  module_type?: string; target_department?: string | null; is_published?: boolean;
}

// * Test Series types
export interface TestQuestionDraft {
  id?: string;
  question: string;
  options: string[];
  correct_index: number | null;
  explanation: string | null;
  topic: string | null;
  marks: number;
  scorable?: boolean;
}
export interface ParsedPdf {
  source_filename: string | null;
  source_parser: string;
  extracted_characters: number;
  detected_questions: number;
  unscorable_count: number;
  warnings: string[];
  questions: TestQuestionDraft[];
}
// * a second PDF parsed against an existing test — same shape as ParsedPdf plus
// * duplicate flags against the questions already in that test
export interface ParsedPdfForTest extends ParsedPdf {
  test_id: string;
  test_title: string;
  existing_questions: number;
  duplicate_count: number;
  questions: (TestQuestionDraft & { duplicate_of_existing?: boolean })[];
}
export interface AppendResult extends AdminTest {
  added: number;
  unpublished_by_this_change: boolean;
  existing_attempts: number;
  notice: string | null;
}
export interface TestSeriesCreate {
  title: string;
  description?: string | null;
  category?: string | null;
  department?: string | null;
  pass_threshold?: number;
  duration_minutes?: number | null;
  max_attempts?: number | null;
  questions: TestQuestionDraft[];
}
export interface AdminTest {
  id: string; title: string; description: string | null;
  category: string | null; department: string | null;
  pass_threshold: number; duration_minutes: number | null;
  max_attempts: number | null; shuffle_questions: boolean;
  is_published: boolean; is_ready: boolean;
  unscorable_count: number; total_marks: number; total_questions: number;
  source_filename: string | null; source_parser: string | null;
  created_at: string; questions: TestQuestionDraft[];
}
export interface AdminTestSummary {
  id: string; title: string; category: string | null; department: string | null;
  is_published: boolean; is_ready: boolean; unscorable_count: number;
  total_questions: number; pass_threshold: number; duration_minutes: number | null;
  source_filename: string | null; created_at: string;
  attempt_count: number; average_score: number | null; pass_rate: number | null;
}
export interface LearnerTest {
  id: string; title: string; description: string | null;
  category: string | null; department: string | null;
  total_questions: number; total_marks: number; pass_threshold: number;
  duration_minutes: number | null; max_attempts: number | null;
  my_attempts: number; attempts_left: number | null;
  my_best_score: number | null; passed: boolean;
}
export interface TestPaper {
  id: string; title: string; description: string | null;
  duration_minutes: number | null; pass_threshold: number; total_marks: number;
  attempt_number: number; max_attempts: number | null;
  questions: { id: string; question: string; options: string[]; topic: string | null; marks: number }[];
}
export interface BreakdownRow {
  question_id: string; question: string; options: string[];
  your_index: number | null; your_answer: string | null;
  correct_index: number; correct_answer: string;
  correct: boolean; explanation: string | null;
  topic: string | null; marks: number;
}
export interface TopicStat { correct: number; total: number; accuracy: number; }
export interface TestResult {
  attempt_id: string; score: number; passed: boolean; pass_threshold: number;
  marks_earned: number; marks_total: number;
  correct_count: number; total_questions: number;
  breakdown: BreakdownRow[]; topic_stats: Record<string, TopicStat>;
  rewards?: { pass?: RewardEntry; perfect_quiz?: RewardEntry | null; badges_unlocked?: string[] } | null;
}
export interface AiAnalysis {
  summary: string;
  weak_areas: { topic: string; accuracy: number; why: string; action: string }[];
  strengths: string[];
  recommendations: string[];
  suggested_focus: string;
  generated_by?: string;
}
export interface AttemptDetail {
  attempt_id: string; test_id: string; test_title: string;
  score: number; passed: boolean; pass_threshold: number | null;
  marks_earned: number; marks_total: number;
  correct_count: number; total_questions: number; submitted_at: string;
  breakdown: BreakdownRow[]; topic_stats: Record<string, TopicStat>;
  ai_analysis: AiAnalysis | null;
}
export interface MyAttempt {
  attempt_id: string; test_id: string; test_title: string;
  score: number; passed: boolean;
  correct_count: number; total_questions: number; submitted_at: string;
}
export interface TestResultRow {
  attempt_id: string; user_id: string;
  full_name: string | null; email: string | null; department: string | null;
  score: number; marks_earned: number; marks_total: number;
  correct_count: number; total_questions: number; passed: boolean;
  submitted_at: string; breakdown: BreakdownRow[];
  topic_stats: Record<string, TopicStat>;
  has_ai_analysis: boolean; ai_analysis: AiAnalysis | null;
}
export interface TestResults {
  test_id: string; title: string; pass_threshold: number;
  total_questions: number; attempt_count: number;
  average_score: number | null; pass_rate: number | null;
  cohort_topic_stats: Record<string, TopicStat>;
  attempts: TestResultRow[];
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
