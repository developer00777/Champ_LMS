import { browser } from '$app/environment';

const API_URL = import.meta.env.PUBLIC_API_URL || 'http://localhost:8000';

function getToken(): string | null {
	if (!browser) return null;
	return localStorage.getItem('champ_token');
}

export function setToken(token: string) {
	localStorage.setItem('champ_token', token);
}

export function clearToken() {
	localStorage.removeItem('champ_token');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
	const token = getToken();
	const headers: Record<string, string> = {
		'Content-Type': 'application/json',
		...(options.headers as Record<string, string>),
	};
	if (token) headers['Authorization'] = `Bearer ${token}`;

	const res = await fetch(`${API_URL}${path}`, { ...options, headers });

	if (res.status === 401) {
		clearToken();
		if (browser) window.location.href = '/auth/login';
		throw new Error('Unauthorized');
	}

	if (!res.ok) {
		const err = await res.json().catch(() => ({ detail: res.statusText }));
		throw new Error(err.detail || 'Request failed');
	}

	if (res.status === 204) return undefined as T;
	return res.json();
}

export const api = {
	get: <T>(path: string) => request<T>(path),
	post: <T>(path: string, body?: unknown) =>
		request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }),
	patch: <T>(path: string, body?: unknown) =>
		request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }),
	delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

// Typed API calls
export const feedApi = {
	getFeed: () => api.get<FeedResponse>('/feed'),
	getModules: (params?: { category?: string; search?: string }) => {
		const q = new URLSearchParams(params as Record<string, string>).toString();
		return api.get<Module[]>(`/modules${q ? '?' + q : ''}`);
	},
	getModule: (id: string) => api.get<Module>(`/modules/${id}`),
	getStreamUrl: (episodeId: string) => api.get<{ stream_url: string }>(`/episodes/${episodeId}/stream`),
	search: (q: string) => api.get<Module[]>(`/search?q=${encodeURIComponent(q)}`),
};

export const progressApi = {
	upsert: (body: { episode_id: string; watched_seconds: number; total_seconds: number }) =>
		api.post('/progress', body),
	getMe: () => api.get<Progress[]>('/progress/me'),
	getEpisode: (episodeId: string) => api.get<Progress>(`/progress/${episodeId}`),
};

export const authApi = {
	verify: () => api.post<User>('/auth/verify'),
	me: () => api.get<User>('/auth/me'),
};

export const gamificationApi = {
	leaderboard: (department?: string) =>
		api.get<LeaderboardEntry[]>(`/leaderboard${department ? '?department=' + department : ''}`),
	myBadges: () => api.get<Badge[]>('/badges/me'),
	myStreak: () => api.get<{ streak_days: number; points: number }>('/streaks/me'),
};

export const assessmentApi = {
	getForModule: (moduleId: string) => api.get<Assessment[]>(`/assessments/${moduleId}`),
	attempt: (assessmentId: string, answers: Record<string, number>) =>
		api.post<AttemptResult>(`/assessments/${assessmentId}/attempt`, { answers }),
};

export const adminApi = {
	createModule: (body: Partial<Module>) => api.post<Module>('/admin/modules', body),
	updateModule: (id: string, body: Partial<Module>) => api.patch<Module>(`/admin/modules/${id}`, body),
	addEpisode: (moduleId: string, body: Partial<Episode>) =>
		api.post<Episode>(`/admin/modules/${moduleId}/episodes`, body),
	getPresignUrl: (episodeId: string) =>
		api.post<{ upload_url: string; fields: Record<string, string>; s3_key: string }>(
			`/admin/upload/presign?episode_id=${episodeId}`
		),
	generateQuiz: (episodeId: string) => api.post(`/admin/episodes/${episodeId}/generate-quiz`),
	getAnalytics: () => api.get<Analytics>('/admin/analytics'),
	getZoomSessions: () => api.get<ZoomSession[]>('/zoom/sessions'),
	createZoomSession: (body: Partial<ZoomSession>) => api.post<ZoomSession>('/zoom/sessions', body),
	buildModule: (sessionId: string) => api.post(`/zoom/build-module/${sessionId}`),
};

// Types
export interface FeedCard {
	id: string;
	title: string;
	thumbnail_url: string | null;
	category: string | null;
	total_episodes: number;
	completion_percentage: number;
	is_new: boolean;
}

export interface FeedRow {
	row_title: string;
	modules: FeedCard[];
}

export interface FeedResponse {
	rows: FeedRow[];
}

export interface Module {
	id: string;
	title: string;
	description: string | null;
	category: string | null;
	tags: string[] | null;
	target_roles: string[] | null;
	source_type: string;
	thumbnail_url: string | null;
	is_published: boolean;
	total_episodes: number;
	created_at: string;
	episodes: Episode[];
}

export interface Episode {
	id: string;
	module_id: string;
	title: string;
	description: string | null;
	duration_seconds: number | null;
	sequence_order: number;
	thumbnail_key: string | null;
	status: string;
	ai_summary: string | null;
}

export interface Progress {
	episode_id: string;
	watched_seconds: number;
	total_seconds: number | null;
	completed: boolean;
	last_watched_at: string;
}

export interface User {
	id: string;
	email: string;
	full_name: string | null;
	role: string | null;
	department: string | null;
	points: number;
	streak_days: number;
}

export interface LeaderboardEntry {
	rank: number;
	user_id: string;
	full_name: string | null;
	department: string | null;
	points: number;
	streak_days: number;
}

export interface Badge {
	id: string;
	name: string;
	description: string | null;
	icon_url: string | null;
	earned_at: string;
}

export interface Assessment {
	id: string;
	module_id: string;
	episode_id: string | null;
	title: string | null;
	questions: Question[];
	pass_threshold: number;
}

export interface Question {
	question: string;
	options: string[];
	correct_index: number;
	explanation: string;
}

export interface AttemptResult {
	id: string;
	assessment_id: string;
	score: number;
	passed: boolean;
	attempted_at: string;
}

export interface ZoomSession {
	id: string;
	zoom_meeting_id: string | null;
	topic: string | null;
	summary: string | null;
	processed: boolean;
	module_id: string | null;
	created_at: string;
}

export interface Analytics {
	total_users: number;
	published_modules: number;
	episode_completions: number;
	active_enrollments: number;
}
