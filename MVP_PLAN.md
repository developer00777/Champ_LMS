# Champion LMS — MVP Architecture & Build Plan

## Vision Recap
"The Netflix of Champion LMS" — a binge-worthy, Gen Z streaming experience for company-internal learning. Micro-content (2–10 min bursts), AI-personalized playlists, Zoom→Module pipeline, and gamified daily habits. Not a compliance database. A self-driven daily learning habit.

---

## Part 1 — AWS Infrastructure (30 concurrent users, 50 GB+ video)

### Sizing rationale
- 30 concurrent users streaming video = ~30 × 3–5 Mbps = ~90–150 Mbps sustained bandwidth
- 50 GB initial video content, growing — S3 + CloudFront is the right answer (not self-hosted)
- API workload: FastAPI + async = 1 t3.medium handles 30 concurrent users comfortably for MVP
- DB: RDS PostgreSQL t3.micro (free tier eligible) is sufficient for MVP

### AWS Services Stack

```
┌─────────────────────────────────────────────────────────────────┐
│  USERS (desktop + tablet — VPN-gated)                           │
└────────────────┬────────────────────────────────────────────────┘
                 │ HTTPS
┌────────────────▼────────────────────────────────────────────────┐
│  CloudFront CDN                                                 │
│  - Serves SvelteKit static build (S3 origin)                    │
│  - Signed URLs for HLS video segments (MediaConvert output)     │
│  - Caches thumbnails & static assets                            │
└────┬───────────────────────────────────────┬────────────────────┘
     │ API calls                             │ Video HLS segments
┌────▼───────────┐                ┌──────────▼──────────────────┐
│  ALB            │                │  S3 Buckets                 │
│  (App Load      │                │  - champ-lms-raw-videos     │
│   Balancer)     │                │    (upload target)          │
└────┬───────────┘                │  - champ-lms-hls            │
     │                            │    (MediaConvert output)    │
┌────▼────────────────────────┐   │  - champ-lms-frontend       │
│  ECS Fargate                │   │    (SvelteKit build)        │
│  FastAPI container          │   │  - champ-lms-thumbnails     │
│  (1 task = 0.5 vCPU, 1 GB) │   └─────────────────────────────┘
│  Auto-scales 1→4 tasks      │
└────┬────────────────────────┘   ┌─────────────────────────────┐
     │                            │  AWS MediaConvert            │
┌────▼────────────────────────┐   │  - Transcode raw MP4→HLS    │
│  RDS PostgreSQL             │   │  - 360p / 720p / 1080p      │
│  t3.micro (MVP)             │   │  - Auto-triggerso  via Lambda  │
│  Multi-AZ NOT needed MVP    │   │    on S3 upload event       │
└────────────────────────────┘   └─────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  ElastiCache Redis (cache.t3.micro)                             │
│  - Session tokens / JWT blacklist                               │
│  - Watch progress cache (flush to DB every 30s)                 │
│  - Leaderboard rankings                                         │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  AWS Cognito                                                    │
│  - User auth / MFA (required per security spec)                 │
│  - JWT tokens passed to FastAPI                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SQS + Lambda                                                   │
│  - Zoom webhook → SQS → Lambda → FastAPI AI pipeline            │
│  - MediaConvert completion → Lambda → update DB status          │
└─────────────────────────────────────────────────────────────────┘
```

### Cost estimate (30 concurrent users, MVP)
| Service | Config | ~Monthly |
|---|---|---|
| ECS Fargate | 1–2 tasks (0.5vCPU/1GB) | ~$15–30 |
| RDS PostgreSQL | t3.micro, 20GB | ~$15 |
| ElastiCache Redis | cache.t3.micro | ~$12 |
| S3 | 100GB (50GB + growth) | ~$2.50 |
| CloudFront | 500GB transfer/month | ~$42 |
| MediaConvert | ~100 min/mo initial | ~$1 |
| ALB | 1 ALB | ~$16 |
| Cognito | <50K MAU | Free tier |
| **Total** | | **~$100–120/mo** |

Video streaming cost dominates as content grows — CloudFront at $0.085/GB is the right trade-off vs. self-hosting at this scale.

---

## Part 2 — Project Structure

```
champ_lms/
├── backend/                    # Python FastAPI
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py       # Pydantic Settings (env vars)
│   │   │   ├── auth.py         # Cognito JWT verification
│   │   │   ├── db.py           # SQLAlchemy async engine
│   │   │   └── redis.py        # Redis client
│   │   ├── models/             # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   ├── module.py
│   │   │   ├── content.py      # episodes/videos
│   │   │   ├── progress.py
│   │   │   ├── gamification.py # badges, points, streaks
│   │   │   └── zoom_session.py
│   │   ├── schemas/            # Pydantic request/response
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── content.py      # browse, search, stream URLs
│   │   │   ├── modules.py      # CRUD for learning modules
│   │   │   ├── progress.py     # watch progress, completion
│   │   │   ├── recommendations.py
│   │   │   ├── gamification.py
│   │   │   ├── zoom.py         # webhook + module creation
│   │   │   ├── admin.py        # L&D leader dashboard
│   │   │   └── assessments.py
│   │   ├── services/
│   │   │   ├── video_service.py      # S3 presigned + CloudFront signed URLs
│   │   │   ├── ai_service.py         # Claude API for Zoom→module pipeline
│   │   │   ├── recommendation_service.py
│   │   │   └── zoom_service.py
│   │   └── workers/
│   │       └── zoom_processor.py     # SQS consumer
│   ├── alembic/                # DB migrations
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                   # SvelteKit
│   ├── src/
│   │   ├── lib/
│   │   │   ├── components/
│   │   │   │   ├── ContentRow.svelte      # Netflix-style carousel row
│   │   │   │   ├── VideoCard.svelte       # thumbnail + title + progress bar
│   │   │   │   ├── VideoPlayer.svelte     # HLS.js player
│   │   │   │   ├── HeroTrailer.svelte     # auto-play hero section
│   │   │   │   ├── ProgressBadge.svelte   # "Step 1 of 3" marker
│   │   │   │   ├── Leaderboard.svelte
│   │   │   │   ├── BadgeCard.svelte
│   │   │   │   ├── QuizModal.svelte
│   │   │   │   └── ModuleBuilder.svelte   # Zoom→Module UI
│   │   │   ├── stores/
│   │   │   │   ├── auth.ts
│   │   │   │   ├── player.ts             # watch progress sync
│   │   │   │   └── recommendations.ts
│   │   │   └── api/
│   │   │       └── client.ts             # typed fetch wrapper
│   │   └── routes/
│   │       ├── +layout.svelte
│   │       ├── +page.svelte              # Home — Netflix feed
│   │       ├── watch/[id]/+page.svelte   # Video player page
│   │       ├── module/[id]/+page.svelte  # Module detail
│   │       ├── my-learning/+page.svelte  # Progress & streaks
│   │       ├── leaderboard/+page.svelte
│   │       ├── admin/
│   │       │   ├── +page.svelte          # L&D Dashboard
│   │       │   ├── upload/+page.svelte   # Video upload
│   │       │   └── zoom/+page.svelte     # Zoom→Module builder
│   │       └── auth/
│   │           └── callback/+page.svelte # Cognito callback
│   ├── static/
│   └── package.json
│
├── infrastructure/             # AWS CDK or Terraform (optional, document here)
│   └── notes.md
│
└── docker-compose.yml          # Local dev (FastAPI + Postgres + Redis)
```

---

## Part 3 — Database Schema

```sql
-- Users (supplemental to Cognito)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cognito_sub VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(100),           -- e.g. "sales", "engineering", "onboarding"
    department VARCHAR(100),
    avatar_url TEXT,
    points INTEGER DEFAULT 0,
    streak_days INTEGER DEFAULT 0,
    last_activity_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Learning Modules (containers — a "series")
CREATE TABLE modules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    description TEXT,
    category VARCHAR(100),       -- "sales", "leadership", "onboarding" etc.
    tags TEXT[],                 -- for AI tagging / recommendation engine
    target_roles TEXT[],         -- roles this module is recommended for
    created_by UUID REFERENCES users(id),
    source_type VARCHAR(50),     -- "manual" | "zoom" | "upload"
    zoom_session_id UUID,
    thumbnail_url TEXT,
    is_published BOOLEAN DEFAULT false,
    total_episodes INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Episodes (individual micro-videos — "episodes in a series")
CREATE TABLE episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module_id UUID REFERENCES modules(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    duration_seconds INTEGER,
    sequence_order INTEGER NOT NULL,
    s3_raw_key TEXT,             -- raw upload path
    hls_manifest_key TEXT,       -- CloudFront HLS path (set after MediaConvert)
    thumbnail_key TEXT,
    status VARCHAR(50) DEFAULT 'processing',  -- processing|ready|failed
    transcript TEXT,             -- stored for AI use
    ai_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Watch Progress (synced from Redis every 30s)
CREATE TABLE watch_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    episode_id UUID REFERENCES episodes(id) ON DELETE CASCADE,
    watched_seconds INTEGER DEFAULT 0,
    total_seconds INTEGER,
    completed BOOLEAN DEFAULT false,
    completed_at TIMESTAMPTZ,
    last_watched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, episode_id)
);

-- Module Enrollments
CREATE TABLE enrollments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    module_id UUID REFERENCES modules(id),
    enrolled_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    completion_percentage FLOAT DEFAULT 0,
    UNIQUE(user_id, module_id)
);

-- Zoom Sessions (raw data from Zoom webhook)
CREATE TABLE zoom_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zoom_meeting_id VARCHAR(255),
    topic VARCHAR(500),
    summary TEXT,                -- from Zoom AI companion
    transcript TEXT,             -- full transcript
    recording_url TEXT,
    processed BOOLEAN DEFAULT false,
    module_id UUID REFERENCES modules(id),  -- set after AI processing
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Badges
CREATE TABLE badges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    icon_url TEXT,
    criteria JSONB             -- {"type": "complete_module", "module_id": "..."} etc.
);

CREATE TABLE user_badges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    badge_id UUID REFERENCES badges(id),
    earned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, badge_id)
);

-- Assessments (quizzes)
CREATE TABLE assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module_id UUID REFERENCES modules(id),
    episode_id UUID REFERENCES episodes(id),  -- nullable = module-level quiz
    title VARCHAR(500),
    questions JSONB NOT NULL,   -- [{question, options[], correct_index, explanation}]
    pass_threshold INTEGER DEFAULT 70,  -- percentage
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE assessment_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    assessment_id UUID REFERENCES assessments(id),
    score INTEGER,
    passed BOOLEAN,
    answers JSONB,
    attempted_at TIMESTAMPTZ DEFAULT NOW()
);

-- Recommendations (persisted AI output, refreshed daily)
CREATE TABLE recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) UNIQUE,
    rows JSONB NOT NULL,   -- [{row_title, module_ids[]}]
    generated_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Part 4 — FastAPI Backend: Key Endpoints

### Authentication (Cognito-delegated)
```
POST /auth/verify          — verify Cognito JWT, upsert user in DB
GET  /auth/me              — current user profile
```

### Content / Browse (the Netflix feed)
```
GET  /feed                 — personalized rows for home screen
                             (Trending, New Releases, For You, Continue Watching)
GET  /modules              — list all published modules (search + filter)
GET  /modules/{id}         — module detail + episode list
GET  /episodes/{id}/stream — returns CloudFront signed URL for HLS manifest
GET  /search               — full-text search across modules + episodes
```

### Progress
```
POST /progress             — upsert watch progress (called every 30s from player)
GET  /progress/me          — all in-progress + completed
GET  /progress/{episode_id} — resume position for a specific episode
```

### Zoom Integration Pipeline
```
POST /zoom/webhook         — receives Zoom webhook (recording.completed event)
POST /zoom/sessions        — manually add Zoom summary + transcript
POST /zoom/build-module    — triggers AI pipeline to create module from session
GET  /zoom/sessions        — list processed/pending sessions
```

### AI Module Builder (admin)
```
POST /admin/modules        — create module manually
POST /admin/modules/{id}/episodes — add episode to module
POST /admin/upload/presign — get S3 presigned URL for direct browser upload
POST /admin/episodes/{id}/generate-quiz — AI-generate quiz from transcript
GET  /admin/analytics      — L&D leader dashboard data
```

### Gamification
```
GET  /leaderboard          — top users by points (department or global)
GET  /badges/me            — user's earned badges
GET  /streaks/me           — current streak data
```

### Assessments
```
GET  /assessments/{module_id}     — get quiz for module
POST /assessments/{id}/attempt    — submit quiz attempt
```

---

## Part 5 — Zoom → Module AI Pipeline (Core Feature)

This is the key differentiator. When a Zoom meeting ends:

```
Zoom Meeting Ends
       │
       ▼ (Zoom webhook: recording.completed)
POST /zoom/webhook
       │
       ▼
SQS Queue (decoupled — webhook returns 200 immediately)
       │
       ▼
Lambda / Background Worker (zoom_processor.py)
       │
       ├─1. Download transcript + summary from Zoom API
       │
       ├─2. Call Claude API with prompt:
       │     "Given this Zoom meeting transcript and summary,
       │      create a structured learning module.
       │      Output: {title, description, category, tags,
       │      target_roles, episodes: [{title, key_points,
       │      duration_estimate, quiz_questions[]}]}"
       │
       ├─3. Create Module + Episode records in DB
       │      (status = "pending_video")
       │
       ├─4. If recording URL present:
       │     - Download Zoom recording to S3 raw bucket
       │     - Trigger MediaConvert job (MP4 → HLS adaptive)
       │     - On MediaConvert completion: update episode.status = "ready"
       │
       └─5. Notify admin via WebSocket or polling that module is ready to review
               Admin can edit titles, publish, or discard
```

**Claude API prompt structure (ai_service.py):**
```python
ZOOM_MODULE_PROMPT = """
You are a learning design expert. Given the Zoom meeting transcript and AI summary below,
create a structured microlearning module following these rules:
- Max 5 episodes per module
- Each episode covers ONE concept (2-10 min equivalent)
- Episode titles must be action-oriented ("How to...", "Understanding...")
- Generate 3 quiz questions per episode (multiple choice, with explanations)
- Tag with relevant skills and target roles

Transcript: {transcript}
Summary: {summary}

Return valid JSON matching this schema:
{schema}
"""
```

---

## Part 6 — SvelteKit Frontend: Key Pages & Components

### Home Page (`/`) — The Netflix Feed
```
┌─────────────────────────────────────────────────────┐
│  HERO TRAILER (auto-muted, featured module)         │
│  [▶ PLAY]  [RESUME Episode 2]                       │
├─────────────────────────────────────────────────────┤
│  Continue Watching ─────────────────────────── ›   │
│  [card][card][card][card|cut]                        │
├─────────────────────────────────────────────────────┤
│  Trending in Sales ─────────────────────────── ›   │
│  [card][card][card][card|cut]                        │
├─────────────────────────────────────────────────────┤
│  New Releases ──────────────────────────────── ›   │
│  [card][card][card][card|cut]                        │
├─────────────────────────────────────────────────────┤
│  Recommended for You ───────────────────────── ›   │
│  [card][card][card][card|cut]                        │
└─────────────────────────────────────────────────────┘
```

Each card (`VideoCard.svelte`) shows:
- Thumbnail
- Title + category tag beneath (never cover-art only — per "Hotflix" carousel rules)
- Red progress bar overlay (% complete)
- Duration badge

### Video Player (`/watch/[id]`)
- HLS.js for adaptive bitrate streaming from CloudFront signed URLs
- Auto-advance to next episode ("Next episode in 5s...")
- "Step 2 of 5" progress marker
- 30-second progress sync via `fetch('/progress', {method:'POST'})`
- Quiz modal injection at episode end

### Admin — Zoom Module Builder (`/admin/zoom`)
```
┌─────────────────────────────────────────────────────┐
│  Zoom Sessions  [+ Add Manual Session]              │
├─────────────────────────────────────────────────────┤
│  ● Sales Training - June 24     [Build Module ▶]   │
│    Summary: "Covered Q3 pipeline..."                │
│                                                     │
│  ● Onboarding - June 22         [Review Draft ✓]   │
│    3 episodes • 2 quizzes                           │
└─────────────────────────────────────────────────────┘
```

When "Build Module" is clicked: AI pipeline runs, shows loading state, then returns editable draft.

---

## Part 7 — Video Streaming Technical Detail

### Upload Flow (Admin)
1. Admin clicks Upload → SvelteKit calls `POST /admin/upload/presign`
2. FastAPI returns S3 presigned URL (expires 15 min) — direct browser-to-S3 upload (no server bandwidth)
3. On S3 upload completion, S3 event triggers Lambda
4. Lambda submits MediaConvert job: raw MP4 → HLS (360p, 720p, 1080p ABR)
5. MediaConvert writes `.m3u8` + segments to `champ-lms-hls` bucket
6. MediaConvert completion event → Lambda → FastAPI updates episode status to "ready"

### Playback Flow (Learner)
1. SvelteKit calls `GET /episodes/{id}/stream`
2. FastAPI generates CloudFront **signed URL** (time-limited, 4-hour TTL) for the HLS manifest
3. HLS.js in browser streams adaptively — CloudFront edge serves segments
4. No direct S3 access ever — all video behind CloudFront signed URLs

### Security Note
- S3 bucket policy: block all public access
- CloudFront origin access control (OAC) only allows CloudFront to read S3
- Signed URLs prevent sharing outside VPN session

---

## Part 8 — Security Implementation

Per the Champion LMS security spec:
- **VPN-only access**: Enforce at ALB level via IP whitelist (corporate VPN CIDR) or AWS WAF rule
- **MFA**: Cognito with TOTP/SMS MFA enabled
- **No downloads**: HLS streaming (segments are temporary, no single downloadable file) + signed URLs expire
- **Screen recording protection**: Enforced at policy/DRM level — for MVP, use Widevine DRM via CloudFront (note: adds complexity, defer to v1.1 if needed). MVP: legal/policy notice + session audit logging
- **Session monitoring**: All API calls logged to CloudWatch with user_id + action
- **JWT validation**: FastAPI middleware validates Cognito JWT on every request
- **No mobile access** (per spec): Enforce `User-Agent` check + WAF rules for mobile browsers in admin settings

---

## Part 9 — Gamification System

### Points Economy
| Action | Points |
|---|---|
| Complete an episode | +10 |
| Complete a module | +50 |
| Pass a quiz (≥70%) | +25 |
| 7-day streak | +100 bonus |
| First to complete new module | +200 (exclusivity bonus) |

### Streaks
- Redis key: `streak:{user_id}` with TTL reset logic
- "Daily habit" — completing any episode counts
- Streak displayed on profile and home page

### Leaderboard
- Redis sorted set: `leaderboard:global` and `leaderboard:dept:{dept}`
- Refreshed on every points award
- Top 10 shown on leaderboard page

### Badges (MVP set)
- First Watch, 5-Day Streak, Module Champion, Quiz Ace, Early Bird (first to complete)

---

## Part 10 — MVP Feature Scope & Phasing

### Phase 1 — Foundation (Weeks 1–3)
- [ ] AWS infrastructure setup (ECS, RDS, Redis, S3, CloudFront, Cognito, MediaConvert)
- [ ] FastAPI skeleton with Cognito auth middleware
- [ ] Database schema + Alembic migrations
- [ ] S3 upload → MediaConvert → HLS pipeline (Lambda automation)
- [ ] Episode CRUD + status tracking
- [ ] SvelteKit scaffold with auth flow (Cognito hosted UI → callback)

### Phase 2 — Core Learning Experience (Weeks 4–6)
- [ ] Home feed API (`/feed` — hardcoded rows first, AI later)
- [ ] Netflix-style home page with ContentRow carousels
- [ ] HLS.js video player with progress sync
- [ ] Module + episode detail pages
- [ ] Watch progress persistence (Redis → Postgres)
- [ ] "Continue Watching" row
- [ ] Admin: manual module/episode creation + video upload

### Phase 3 — Zoom Integration + AI (Weeks 7–9)
- [ ] Zoom webhook endpoint + SQS queue
- [ ] AI module builder service (Claude API)
- [ ] Zoom session admin UI — review + publish generated modules
- [ ] AI quiz generation from episode transcripts
- [ ] Quiz modal in video player

### Phase 4 — Gamification + Analytics (Weeks 10–12)
- [ ] Points system + streak tracking
- [ ] Leaderboard page
- [ ] Badge award logic + badge display
- [ ] L&D admin dashboard (completion rates, skill gaps, active learners)
- [ ] AI-personalized recommendation rows
- [ ] Assessment pre/post module flow

---

## Part 11 — Key Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Video streaming | AWS MediaConvert + CloudFront HLS | ABR, no server cost, scales to 1000s of users without change |
| Auth | AWS Cognito | MFA built-in, handles session management, integrates with ALB |
| Frontend | SvelteKit | SSR for SEO/performance, reactive stores perfect for real-time progress |
| Backend | FastAPI async | Handles 30 concurrent users on 1 instance, async for S3/DB calls |
| AI pipeline | Claude API (claude-sonnet-4-6) | Best structured output for learning design, tool use for JSON schema |
| Video player | HLS.js | Works on all desktop browsers, handles adaptive streaming natively |
| Caching | Redis (ElastiCache) | Watch progress hot path, leaderboard sorted sets, session data |
| DB | PostgreSQL (RDS) | JSONB for flexible quiz/recommendation data, solid ACID guarantees |
| Zoom processing | SQS + Lambda | Decoupled, no webhook timeout risk, retryable |

---

## Part 12 — Environment Variables

```bash
# FastAPI
DATABASE_URL=postgresql+asyncpg://...
REDIS_URL=redis://...
AWS_REGION=ap-south-1
S3_RAW_BUCKET=champ-lms-raw-videos
S3_HLS_BUCKET=champ-lms-hls
S3_THUMBNAILS_BUCKET=champ-lms-thumbnails
CLOUDFRONT_DOMAIN=https://dXXXX.cloudfront.net
CLOUDFRONT_KEY_PAIR_ID=...
CLOUDFRONT_PRIVATE_KEY=...   # for signed URLs
COGNITO_USER_POOL_ID=...
COGNITO_CLIENT_ID=...
COGNITO_REGION=ap-south-1
MEDIACONVERT_ENDPOINT=...
MEDIACONVERT_ROLE_ARN=...
ANTHROPIC_API_KEY=...         # Claude for AI module builder
ZOOM_WEBHOOK_SECRET=...
SQS_ZOOM_QUEUE_URL=...

# SvelteKit
PUBLIC_API_URL=https://api.champ-lms.internal
PUBLIC_COGNITO_DOMAIN=...
PUBLIC_COGNITO_CLIENT_ID=...
PUBLIC_CLOUDFRONT_DOMAIN=...
```

---

## Part 13 — Local Development Setup

```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: champlms
      POSTGRES_USER: dev
      POSTGRES_PASSWORD: dev
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  api:
    build: ./backend
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://dev:dev@db/champlms
      REDIS_URL: redis://redis:6379
      # AWS services use localstack or real AWS creds for video
    volumes:
      - ./backend:/app
    depends_on: [db, redis]

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    environment:
      PUBLIC_API_URL: http://localhost:8000
    volumes:
      - ./frontend:/app
```

For local video testing: use real S3/MediaConvert (no localstack equivalent for MediaConvert). Upload small test videos to AWS even in dev.

---

---

## Part 14 — AWS Architecture PRD (Deployment Specification)

### 14.1 — Pre-requisites

| Item | Detail |
|---|---|
| AWS Account | Billing alert at $150/month threshold |
| AWS CLI | Configured locally (`aws configure`, region `ap-south-1`) |
| Domain | `learn.championsgroup.com` in Route 53 or external DNS |
| SSL Certificate | ACM cert provisioned in `us-east-1` (CloudFront) + `ap-south-1` (ALB) |
| VPN CIDR | Corporate VPN IP range noted — used for ALB WAF whitelist |

---

### 14.2 — Step 1: VPC & Networking

```
VPC: 10.0.0.0/16 (ap-south-1)
├── Public Subnet A  (10.0.1.0/24)  — AZ a  → ALB
├── Public Subnet B  (10.0.2.0/24)  — AZ b  → ALB
├── Private Subnet A (10.0.3.0/24)  — AZ a  → ECS, RDS, Redis
├── Private Subnet B (10.0.4.0/24)  — AZ b  → ECS, RDS, Redis
└── NAT Gateway (public subnet A)   → private subnets outbound
```

- VPC Flow Logs → CloudWatch log group `/champ-lms/vpc-flow` (security requirement)
- Internet Gateway attached to public subnets
- Route tables: public → IGW, private → NAT Gateway

---

### 14.3 — Step 2: S3 Buckets

| Bucket | Purpose | Public Access |
|---|---|---|
| `champ-lms-raw-videos` | Admin upload target (raw MP4) | Blocked |
| `champ-lms-hls` | MediaConvert HLS output | Blocked (CloudFront OAC only) |
| `champ-lms-frontend` | SvelteKit static build | Blocked (CloudFront OAC only) |
| `champ-lms-thumbnails` | Episode thumbnails | Blocked (CloudFront OAC only) |

- All buckets: Block Public Access = ON
- `champ-lms-hls`: versioning enabled
- `champ-lms-raw-videos`: lifecycle rule → delete raw after 30 days post-processing

---

### 14.4 — Step 3: Cognito User Pool

```
Region: ap-south-1
MFA: TOTP — required (not optional)
Password policy: min 10 chars, require symbols
App client:
  - Grant type: Authorization code
  - Callback URL: https://learn.championsgroup.com/auth/callback
  - Sign-out URL: https://learn.championsgroup.com/auth/logout
  - Hosted UI: champ-lms.auth.ap-south-1.amazoncognito.com
Custom attributes:
  - department (string)
  - role (string)
```

JWT tokens passed to FastAPI on every request — validated via Cognito JWKS endpoint.

---

### 14.5 — Step 4: RDS PostgreSQL + ElastiCache Redis

**RDS PostgreSQL 16**
```
Instance:       db.t3.micro
Storage:        20 GB gp3 (auto-scaling to 100 GB)
Subnet group:   private subnets only
No public access
Security group: allow port 5432 from ECS task security group only
Backup:         7-day automated backup, 1am UTC window
```

**ElastiCache Redis 7**
```
Node:           cache.t3.micro
Subnet group:   private subnets only
No public access
Security group: allow port 6379 from ECS task security group only
```

After provisioning: run Alembic migrations via ECS one-off task or bastion EC2.

---

### 14.6 — Step 5: MediaConvert + Lambda Pipeline

```
MediaConvert Queue: champ-lms-queue (ap-south-1, on-demand)
IAM Role for MediaConvert:
  - s3:GetObject on champ-lms-raw-videos
  - s3:PutObject on champ-lms-hls

Lambda #1 — trigger-mediaconvert
  Trigger:  S3 ObjectCreated on champ-lms-raw-videos
  Action:   Submit MediaConvert job
  Output:   HLS at 360p / 720p / 1080p → champ-lms-hls/{episode_id}/
  Runtime:  Python 3.12

Lambda #2 — mediaconvert-completion
  Trigger:  EventBridge rule (MediaConvert job state = COMPLETE)
  Action:   PATCH /episodes/{id} → status = "ready", hls_manifest_key set
  Runtime:  Python 3.12
```

HLS output path convention: `champ-lms-hls/{episode_id}/index.m3u8`

---

### 14.7 — Step 6: CloudFront Distributions

**Distribution 1 — Frontend**
```
Origin:         champ-lms-frontend S3 (OAC — no public S3)
Default root:   index.html
Custom error:   404 → /index.html, 200 (SvelteKit client-side routing)
SSL:            ACM cert (us-east-1)
Price class:    PriceClass_100 (US + Europe + India)
Domain:         learn.championsgroup.com → CNAME this distribution
```

**Distribution 2 — Video HLS**
```
Origin:         champ-lms-hls S3 (OAC)
Path pattern:   /hls/*
Signed URLs:    YES — CloudFront key pair
  TTL:          4 hours per signed URL
  Private key:  stored in AWS Secrets Manager
SSL:            ACM cert (us-east-1)
Domain:         cdn.learn.championsgroup.com → CNAME this distribution
```

Signed URL generation lives in `backend/app/services/video_service.py` using `cloudfront-signer`.

---

### 14.8 — Step 7: ECS Fargate (FastAPI Backend)

```
ECR Repository:  champ-lms-api
ECS Cluster:     champ-lms (Fargate)

Task Definition:
  CPU:    0.5 vCPU
  RAM:    1 GB
  Image:  {account}.dkr.ecr.ap-south-1.amazonaws.com/champ-lms-api:latest
  Port:   8000
  Env vars: injected from SSM Parameter Store + Secrets Manager
  Logs:   CloudWatch log group /champ-lms/api

Service:
  Desired tasks:    1
  Auto-scaling:     1 → 4 tasks
  Scale-out:        CPU > 70% for 2 consecutive minutes
  Scale-in:         CPU < 30% for 5 consecutive minutes
  Health check:     GET /health → HTTP 200
  Deployment:       Rolling update (min 50% healthy)
```

---

### 14.9 — Step 8: ALB + WAF (VPN-gated entry point)

```
ALB: champ-lms-alb (public subnets A + B)
Listener: HTTPS 443
  → Target Group: champ-lms-ecs (port 8000, health check /health)
SSL: ACM cert (ap-south-1)

WAF (WebACL attached to ALB):
  Rule 1 — VPN IP Whitelist:
    Allow: [corporate VPN CIDR block]
    Default action: Block → 403 Forbidden
  Rule 2 — Block Mobile User-Agents:
    Match: User-Agent contains Android|iPhone|iPad|Mobile
    Action: Block → 403 Forbidden
  Rule 3 — Rate limit:
    100 requests / 5 minutes per IP (brute-force protection)

ALB access logs → s3://champ-lms-alb-logs/
```

Route 53: `api.learn.championsgroup.com` → ALB DNS name (A record alias)

---

### 14.10 — Step 9: SQS + Zoom Lambda

```
SQS Queue: champ-lms-zoom-processing
  Visibility timeout:  300 seconds
  Message retention:   4 days
  Dead-letter queue:   champ-lms-zoom-dlq
    Max receive count: 3 (retry 3× before DLQ)

Lambda: zoom-processor
  Trigger:   SQS champ-lms-zoom-processing (batch size 1)
  Timeout:   5 minutes
  Runtime:   Python 3.12
  Secrets:   ZOOM_WEBHOOK_SECRET, ANTHROPIC_API_KEY → Secrets Manager
  Actions:
    1. Download transcript + summary from Zoom API
    2. Call Claude API → structured module JSON
    3. Create Module + Episode records via FastAPI internal call
    4. Download Zoom recording → champ-lms-raw-videos (triggers Lambda #1)
    5. Notify admin via DB flag (admin polls /zoom/sessions)
```

FastAPI `POST /zoom/webhook` validates Zoom signature → pushes to SQS → returns 200 immediately.

---

### 14.11 — Step 10: Frontend Deployment

```bash
# Build
npm run build

# Deploy to S3
aws s3 sync ./build s3://champ-lms-frontend --delete

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id <DISTRIBUTION_1_ID> \
  --paths "/*"
```

Route 53: `learn.championsgroup.com` → CloudFront Distribution 1 (CNAME or A alias)

---

### 14.12 — IAM Roles Summary

| Role | Used By | Permissions |
|---|---|---|
| `champ-lms-ecs-task` | ECS Fargate tasks | S3 (raw + thumbnails presign), Secrets Manager read, CloudWatch logs, SQS send |
| `champ-lms-mediaconvert` | MediaConvert service | S3 GetObject (raw), S3 PutObject (hls) |
| `champ-lms-lambda-trigger` | Lambda #1 + #2 | S3 read, MediaConvert submit, CloudWatch logs, SSM read |
| `champ-lms-zoom-lambda` | Zoom processor Lambda | SQS receive/delete, Secrets Manager read, S3 PutObject (raw), CloudWatch logs |

All roles: least-privilege — no `*` actions, no `*` resources.

---

### 14.13 — Secrets Manager Keys

| Secret Name | Value |
|---|---|
| `champ-lms/db-password` | RDS master password |
| `champ-lms/cloudfront-private-key` | CloudFront key pair private key (PEM) |
| `champ-lms/anthropic-api-key` | Claude API key |
| `champ-lms/zoom-webhook-secret` | Zoom webhook verification token |
| `champ-lms/cognito-client-secret` | Cognito app client secret |

---

### 14.14 — Launch Order

```
Step 1   VPC + subnets + NAT Gateway + security groups
Step 2   S3 buckets (4) + bucket policies
Step 3   Cognito User Pool + app client + hosted UI
Step 4   RDS PostgreSQL → run Alembic migrations
Step 5   ElastiCache Redis
Step 6   MediaConvert queue + IAM role + Lambda #1 + Lambda #2
Step 7   CloudFront Distribution 2 (video HLS) + generate CloudFront key pair
Step 8   ECR repo → build + push Docker image
Step 9   ECS cluster + task definition + service
Step 10  ALB + target group + WAF rules → wire to ECS
Step 11  CloudFront Distribution 1 (frontend)
Step 12  SQS queue + DLQ + Zoom processor Lambda
Step 13  Frontend build → S3 sync → CloudFront invalidation
Step 14  Route 53 DNS records (api + learn + cdn subdomains)
Step 15  Smoke test: login → browse → stream video → admin upload
```

---

### 14.15 — Monthly Cost Estimate (MVP, 30 concurrent users)

| Service | Config | ~Monthly |
|---|---|---|
| ECS Fargate | 1–2 tasks (0.5 vCPU / 1 GB) | ~$15–30 |
| RDS PostgreSQL | db.t3.micro, 20 GB gp3 | ~$15 |
| ElastiCache Redis | cache.t3.micro | ~$12 |
| S3 | 100 GB (raw + HLS + assets) | ~$2.50 |
| CloudFront | 500 GB transfer/month | ~$42 |
| MediaConvert | ~100 min/month initial | ~$1 |
| ALB | 1 ALB | ~$16 |
| NAT Gateway | ~100 GB/month | ~$8 |
| WAF | 1 WebACL + 3 rules | ~$6 |
| Cognito | <50K MAU | Free tier |
| Lambda | <1M invocations/month | Free tier |
| Secrets Manager | 5 secrets | ~$2.50 |
| **Total** | | **~$120–135/mo** |

---

## Summary: What Gets Built in MVP

1. **Netflix-style home feed** — carousel rows (Continue Watching, Trending, For You, New Releases)
2. **HLS video player** — adaptive streaming from CloudFront, progress sync, auto-advance
3. **Zoom → Module pipeline** — webhook → AI (Claude) → structured module draft → admin review → publish
4. **AI quiz generation** — from episode transcripts, injected at episode end
5. **Gamification** — points, streaks, leaderboard, badges
6. **Admin dashboard** — upload videos, build modules, see analytics, manage Zoom sessions
7. **VPN-gated auth** — Cognito MFA, signed video URLs, session audit logging
8. **30 concurrent users** — ECS Fargate auto-scaling, CloudFront absorbs video load
9. **50+ GB video** — S3 + MediaConvert ABR, scales without infrastructure change
