# Champ LMS v2 — Deployment Plan (Railway + Bunny)

This is the canonical v2 plan. If any other doc, comment, or script disagrees
with this file, this file wins.

**One line:** Railway hosts the entire app (frontend, backend, Postgres,
Redis). Bunny hosts only video and thumbnails. No VPS, no custom domain, no
DNS, no VPN/Caddy layer — all of that was part of an earlier v1 plan and does
not apply to v2.

## Split: Railway hosts the app, Bunny hosts video/media

| Concern | Host | Why |
|---|---|---|
| SvelteKit frontend | Railway (Node server, `adapter-node`) | Free `*.up.railway.app` HTTPS domain, no custom domain needed |
| FastAPI backend | Railway (Docker) | Same — free HTTPS subdomain, git-push deploys |
| Postgres | Railway plugin | Managed, backed up, injects `DATABASE_URL` automatically |
| Redis | Railway plugin | Managed, injects `REDIS_URL` automatically |
| Video (raw + transcoded) | Bunny Stream | Auto-transcodes to HLS, token-authenticated playback, ~8x cheaper than CloudFront |
| Thumbnails | Bunny Storage + CDN pull zone | Cheap object storage + edge caching, image optimization via URL params |

No custom domain is purchased or required anywhere in this setup. Railway's
`*.up.railway.app` subdomains and Bunny's `*.b-cdn.net` subdomains both come
with free, valid HTTPS out of the box.

### Explicitly NOT part of v2

These existed in earlier iterations of the plan and were removed. Do not
reintroduce them without a deliberate decision to change the architecture:

- **No VPS** — the backend does not run on a self-managed server.
- **No Caddy / reverse proxy layer** — Railway terminates TLS itself.
- **No Bunny DNS zone / nameserver changes** — nothing needs a custom domain.
- **No VPN CIDR allowlisting** — access control is JWT-based at the app layer, not network-based.
- **No frontend deploy to Bunny Storage** — the frontend is a Node server on Railway (`adapter-node`), not a static build pushed to a CDN.
- **No AWS (S3 / CloudFront / MediaConvert / MongoDB)** — fully replaced by Bunny (video/thumbnails) and Railway (Postgres/Redis).

## Bunny Services Used

### 1. Bunny Stream (Video-as-a-Service)
- Uploads raw video via API → auto-transcodes to 360p/720p/1080p HLS
- Token-authenticated playback URLs (HMAC-SHA256, TTL configurable)
- Webhook on encode completion → `POST /webhooks/bunny` updates episode status in DB
- Served via Bunny's own `vz-xxxxx.b-cdn.net` hostname — no custom domain needed

### 2. Bunny Storage (thumbnails only)
- Storage zone: `champ-lms-thumbs`
- The frontend build itself is **not** deployed here — it runs as a Node
  server on Railway instead (see `frontend/Dockerfile`, `adapter-node`)

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
┌──▼─────────────────────────────┐      ┌────────────────────────────┐
│ Railway: SvelteKit (Node)      │      │ Bunny CDN Pull Zone         │
│ champ-lms-frontend.up.railway  │      │ champ-lms-cdn.b-cdn.net     │
│  .app                          │      │ (thumbnails only)           │
└──────────────┬──────────────────┘      └──────────────┬─────────────┘
               │ API calls                               │ origin pull
               │                                ┌─────────▼──────────┐
┌──────────────▼──────────────────┐             │ Bunny Storage        │
│ Railway: FastAPI (Docker)       │             │ champ-lms-thumbs      │
│ champ-lms-backend.up.railway.app│             └───────────────────────┘
│ - JWT auth (self-managed)       │
│ - Calls Bunny Stream API        │
│ - Generates Bunny token-auth URLs│
└──────┬──────────────┬────────────┘
       │              │
┌──────▼─────┐  ┌─────▼──────────┐
│ Railway     │  │ Railway         │
│ Postgres    │  │ Redis           │
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
| Railway (backend + frontend + Postgres + Redis) | Hobby/starter usage | ~$5–20 (usage-based) |
| Bunny CDN | 500 GB transfer | ~$5 |
| Bunny Stream | 100 GB storage + 500 GB transfer | ~$12 |
| Bunny Storage | ~5 GB (thumbnails) | ~$0.10 |
| OpenRouter API | cheap model (Gemini Flash / DeepSeek) | ~$5–15 |
| **Total** | | **~$25–50/mo** |

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
3. **Railway project**: create one Railway project with four services — `backend` (Docker), `frontend` (Docker), `Postgres` (plugin), `Redis` (plugin).
4. **Env vars** — set on the `backend` service (see `backend/.env.example`):
   - `DATABASE_URL` → reference `${{Postgres.DATABASE_URL}}`
   - `REDIS_URL` → reference `${{Redis.REDIS_URL}}`
   - All `BUNNY_*` values from steps 1–2
   - `CORS_ORIGINS` → the frontend service's Railway domain
   - `OPENROUTER_API_KEY`, `ZOOM_*` as needed
5. **Env vars** — set on the `frontend` service:
   - `VITE_API_URL` (build-time) → the backend service's Railway domain
6. **Deploy**: `railway link` each of `backend/` and `frontend/` to its Railway service, then `make deploy`.
7. **Migrate**: `make migrate` (or run once via `railway run` against the backend service) to apply Alembic migrations against the Railway Postgres instance.
8. **Bunny Stream webhook**: point it at `<backend-railway-domain>/webhooks/bunny`.

## Deploying (day-to-day)

```bash
# One-time Bunny setup (thumbnail storage zone + CDN pull zone)
make setup-bunny

# Push both services to Railway (requires `railway login`, and each
# directory linked to its Railway service via `railway link`)
make deploy
```

Set `CORS_ORIGINS` on the backend service to the frontend's Railway domain,
and `VITE_API_URL` as a build-time variable on the frontend service pointing
at the backend's Railway domain.
