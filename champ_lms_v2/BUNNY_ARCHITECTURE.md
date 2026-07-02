# Champ LMS v2 — Deployment Plan (Railway + Bunny)

This is the canonical v2 plan. If any other doc, comment, or script disagrees
with this file, this file wins.

**One line:** Railway hosts the entire app as **one service, one container**
(SvelteKit + FastAPI together, MongoDB + Redis as plugins). Bunny hosts only
video and thumbnails. No VPS, no custom domain, no DNS, no VPN/Caddy layer —
all of that was part of an earlier v1 plan and does not apply to v2.

## Split: Railway hosts the app, Bunny hosts video/media

| Concern | Host | Why |
|---|---|---|
| SvelteKit + FastAPI (combined) | Railway, **one service** (Docker) | Single free `*.up.railway.app` HTTPS domain, one deploy, no CORS between frontend/backend |
| MongoDB | Railway plugin | Managed, backed up, injects `MONGO_URL` automatically. App data layer (Beanie ODM over Motor) — users, modules, episodes, progress, badges, assessments, etc. |
| Redis | Railway plugin | Managed, injects `REDIS_URL` automatically. Leaderboard sorted sets, streak counters, a short-lived progress cache — not the source of truth for app data. |
| Video (raw + transcoded) | Bunny Stream | Auto-transcodes to HLS, token-authenticated playback, ~8x cheaper than CloudFront. Video bytes never touch MongoDB or Redis — the DB only stores the Bunny video GUID/status pointer. |
| Thumbnails | Bunny Storage + CDN pull zone | Cheap object storage + edge caching, image optimization via URL params |

No custom domain is purchased or required anywhere in this setup. Railway's
`*.up.railway.app` subdomain and Bunny's `*.b-cdn.net` subdomains both come
with free, valid HTTPS out of the box.

### One container, two processes

The frontend and backend are **not** two Railway services — they run in a
single container, started together by `start.sh`:

- **FastAPI/uvicorn** binds `127.0.0.1:8000` — internal only, never exposed
  outside the container.
- **SvelteKit's Node server** (`adapter-node`) binds Railway's public `$PORT`
  and is the *only* process reachable from the internet.
- `frontend/src/hooks.server.ts` proxies any request under `/api/*` to the
  internal FastAPI process, stripping the `/api` prefix (same rewrite the
  Vite dev server already does in `vite.config.ts` for local dev).
- `frontend/src/lib/api/client.ts` already calls `${VITE_API_URL ?? '/api'}`,
  so no frontend code needed to change — same-origin `/api` calls work
  identically in dev and in production.
- Because everything is same-origin in production, **CORS only matters for
  local dev** (SvelteKit dev server on `:5173` calling FastAPI on `:8000`
  directly, outside the Vite proxy).

`start.sh` starts uvicorn in the background, polls `/health` until it's up,
then `exec`s the Node server as PID 1 so Railway's restart/shutdown signals
reach it directly.

### Explicitly NOT part of v2

These existed in earlier iterations of the plan and were removed. Do not
reintroduce them without a deliberate decision to change the architecture:

- **No VPS** — the backend does not run on a self-managed server.
- **No Caddy / reverse proxy layer** — Railway terminates TLS itself.
- **No Bunny DNS zone / nameserver changes** — nothing needs a custom domain.
- **No VPN CIDR allowlisting** — access control is JWT-based at the app layer, not network-based.
- **No frontend deploy to Bunny Storage** — the frontend is a Node server bundled into the same container as the backend, not a static build pushed to a CDN.
- **No separate frontend/backend Railway services** — one Railway service, one Dockerfile, one container. Don't recreate `backend/railway.json` / `frontend/railway.json` / per-directory Dockerfiles; the root `Dockerfile` and `railway.json` are the only ones that exist.
- **No AWS (S3 / CloudFront / MediaConvert)** — fully replaced by Bunny (video/thumbnails) and Railway (MongoDB/Redis).
- **No PostgreSQL / SQLAlchemy / Alembic** — the app migrated (2026-07-02) from Postgres to MongoDB via Beanie/Motor. There is no `alembic/` directory, no `DATABASE_URL`, no `asyncpg` — don't reintroduce them. Schema is defined by the Beanie `Document` classes in `backend/app/models/`; indexes are created automatically by `init_beanie()` on startup, no separate migration step.

## Bunny Services Used

### 1. Bunny Stream (Video-as-a-Service)
- Uploads raw video via API → auto-transcodes to 360p/720p/1080p HLS
- Token-authenticated playback URLs (HMAC-SHA256, TTL configurable)
- Webhook on encode completion → `POST /webhooks/bunny` updates episode status in DB
- Served via Bunny's own `vz-xxxxx.b-cdn.net` hostname — no custom domain needed

### 2. Bunny Storage (thumbnails only)
- Storage zone: `champ-lms-thumbs`
- The frontend build itself is **not** deployed here — it's bundled into the
  same container as the backend and served by SvelteKit's Node server

### 3. Bunny CDN Pull Zone
- Pulls from the `champ-lms-thumbs` storage zone
- Free `*.b-cdn.net` hostname (no custom domain)
- Bunny Optimizer for on-the-fly WebP conversion / resizing (`?width=&height=`)
- Optional edge rule: block mobile User-Agents (thumbnails are desktop-only)

### 4. Bunny Token Auth
- HMAC-SHA256 token per video request, configurable TTL (default 4h)

## Architecture Diagram

```
USERS
   │ HTTPS
┌──▼──────────────────────────────────────┐      ┌────────────────────────────┐
│ Railway: ONE service, ONE container      │      │ Bunny CDN Pull Zone         │
│ champ-lms.up.railway.app                 │      │ champ-lms-cdn.b-cdn.net     │
│                                           │      │ (thumbnails only)           │
│ ┌───────────────────────────────────┐    │      └──────────────┬─────────────┘
│ │ SvelteKit Node server ($PORT)     │    │                     │ origin pull
│ │  - public entry point             │    │            ┌─────────▼──────────┐
│ │  - proxies /api/* internally  ────┼──┐ │            │ Bunny Storage        │
│ └───────────────────────────────────┘  │ │            │ champ-lms-thumbs      │
│ ┌───────────────────────────────────┐  │ │            └───────────────────────┘
│ │ FastAPI/uvicorn (127.0.0.1:8000)  │◄─┘ │
│ │  - internal only, not public      │    │
│ │  - JWT auth (self-managed)        │    │
│ │  - Calls Bunny Stream API         │    │
│ │  - Generates Bunny token-auth URLs│    │
│ └──────┬──────────────┬─────────────┘    │
└────────┼──────────────┼──────────────────┘
         │              │
┌────────▼───┐  ┌───────▼────────┐
│ Railway     │  │ Railway         │
│ MongoDB     │  │ Redis           │
│ (plugin)    │  │ (plugin)        │
└─────────────┘  └─────────────────┘

┌─────────────────────────────────────────────────┐
│  Bunny Stream                                    │
│  - Video library                                 │
│  - Webhook on encode complete → backend webhook  │
│  - Token-auth HLS playback                       │
└───────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Zoom webhook → FastAPI → Redis queue → worker   │
│  - OpenRouter (Claude/Gemini/etc) for transcript  │
│    → module JSON                                  │
│  - Upload recording to Bunny Stream via API       │
└───────────────────────────────────────────────────┘
```

## Cost Estimate (30 concurrent users, MVP)

| Service | Config | ~Monthly |
|---|---|---|
| Railway (one service + MongoDB + Redis) | Hobby/starter usage | ~$5–15 (usage-based) |
| Bunny CDN | 500 GB transfer | ~$5 |
| Bunny Stream | 100 GB storage + 500 GB transfer | ~$12 |
| Bunny Storage | ~5 GB (thumbnails) | ~$0.10 |
| OpenRouter API | cheap model (Gemini Flash / DeepSeek) | ~$5–15 |
| **Total** | | **~$25–45/mo** |

No domain registration cost — everything runs on free provider subdomains.

## Bunny API Keys Needed

1. **Bunny Account API Key** — for Storage zone management
2. **Bunny Stream API Key** — for video library management
3. **Bunny Storage Zone Password** — HTTP API access for the thumbs zone
4. **Bunny Token Auth Secret** — HMAC key for signed playback URLs
5. **Bunny Stream CDN Hostname** — e.g. `vz-abc123.b-cdn.net`

## First-time setup order

1. **Bunny dashboard**: create a Bunny Stream video library manually (no API for library creation) → note its ID and `vz-xxxxx.b-cdn.net` hostname → enable Token Authentication → copy the secret.
2. **Bunny setup script**: `make setup-bunny` — creates the thumbnail storage zone + CDN pull zone, verifies the Stream library, prints the values to copy into env vars.
3. **Railway project**: create one Railway project with three services — the app (Docker, root `Dockerfile`), `MongoDB` (plugin), `Redis` (plugin).
4. **Env vars** — set on the app service (see `backend/.env.example`):
   - `MONGODB_URL` → reference `${{MongoDB.MONGO_URL}}` (or leave unset — `config.py` falls back to Railway's `MONGO_URL` automatically)
   - `REDIS_URL` → reference `${{Redis.REDIS_URL}}`
   - All `BUNNY_*` values from steps 1–2
   - `CORS_ORIGINS` → `http://localhost:5173` (production doesn't need it — same origin)
   - `OPENROUTER_API_KEY`, `ZOOM_*` as needed
5. **Deploy**: `railway link` this directory to the Railway service, then `make deploy`. No migration step needed — `init_beanie()` creates indexes automatically against the Railway MongoDB instance on startup.
6. **Bunny Stream webhook**: point it at `<railway-domain>/api/webhooks/bunny-stream`.

## Deploying (day-to-day)

```bash
# One-time Bunny setup (thumbnail storage zone + CDN pull zone)
make setup-bunny

# Push the combined service to Railway (requires `railway login`, and this
# directory linked to the Railway service via `railway link`)
make deploy
```
