# Champ LMS v2 — Bunny CDN Architecture

## Why Bunny Over AWS for This Scale

| Concern | AWS (v1) | Bunny (v2) |
|---|---|---|
| Video CDN | CloudFront $0.085/GB | Bunny CDN $0.01/GB (8.5× cheaper) |
| Video transcoding | MediaConvert $0.015/min | Bunny Stream included in storage cost |
| Storage | S3 $0.023/GB | Bunny Storage $0.01/GB |
| DRM / token auth | CloudFront signed URLs (complex) | Bunny Token Auth (single env var) |
| Image optimization | Lambda@Edge | Bunny Optimizer (built-in) |
| DNS | Route 53 $0.50/hosted zone | Bunny DNS free |
| Edge rules (WAF-lite) | WAF $6/mo + rules | Bunny Edge Rules free |
| Monthly total | ~$120–135 | ~$20–35 |

## Bunny Services Used

### 1. Bunny Stream (Video-as-a-Service)
- Replaces: AWS MediaConvert + CloudFront video distribution
- Uploads raw video via API → auto-transcodes to 360p/720p/1080p HLS
- Token-authenticated playback URLs
- Webhook on encode completion → update episode status in DB
- Built-in embed player OR use Video.js with the Bunny HLS URL

### 2. Bunny Storage (Object Storage)
- Replaces: S3 raw-videos, thumbnails, frontend buckets
- Storage zones: `champ-lms-raw`, `champ-lms-thumbs`, `champ-lms-frontend`
- Geo-replication selectable per zone
- FTP + HTTP API for upload/download

### 3. Bunny CDN Pull Zone
- Replaces: CloudFront distribution for static assets
- Pull from Bunny Storage origin
- Custom domain: `cdn.learn.championsgroup.com`
- Edge Rules for VPN IP whitelist + mobile UA block (replaces WAF)

### 4. Bunny Token Auth
- Replaces: CloudFront signed URLs
- HMAC-SHA256 token per video request
- TTL configurable (default 4h)
- IP-bound tokens for extra security

### 5. Bunny Optimizer
- Replaces: Lambda@Edge image transforms
- Auto WebP conversion, resizing via URL params (`?width=400&height=225`)
- Applied to thumbnail pull zone

### 6. Bunny DNS
- Replaces: Route 53
- Free, anycast DNS
- A records for: `learn.`, `api.`, `cdn.`

### 7. Bunny Edge Rules (on Pull Zone)
- VPN IP whitelist: block all IPs not in corporate CIDR
- Mobile UA blocking: block Android/iPhone/iPad
- These are configured in Bunny dashboard or via Bunny API

## Architecture Diagram

```
USERS (desktop + tablet — VPN-filtered by Bunny Edge Rules)
                │ HTTPS
┌───────────────▼────────────────────────────────────────────┐
│  Bunny CDN Pull Zone                                        │
│  cdn.learn.championsgroup.com                               │
│  - Serves SvelteKit static build (Bunny Storage origin)     │
│  - Caches thumbnails (Bunny Optimizer for WebP/resize)      │
│  - Edge Rules: VPN IP whitelist + mobile UA block           │
└───┬──────────────────────────────────────┬─────────────────┘
    │ API calls                            │ Static assets / thumbs
┌───▼──────────────┐          ┌────────────▼────────────────┐
│  Nginx / Caddy   │          │  Bunny Storage               │
│  Reverse proxy   │          │  - champ-lms-frontend        │
│  (VPS/Hetzner)   │          │  - champ-lms-thumbs          │
└───┬──────────────┘          └─────────────────────────────┘
    │
┌───▼──────────────────────────────────────────────────────┐
│  Docker: FastAPI container                                │
│  - JWT auth (self-managed, no Cognito)                    │
│  - Calls Bunny Stream API for video URLs                  │
│  - Generates Bunny token-auth URLs                        │
└───┬─────────┬───────────────────────────────────────────┘
    │         │
┌───▼──┐  ┌──▼───────────────────────────────────────────┐
│Postgres│ │  Redis                                        │
│(Docker)│ │  - Watch progress cache                       │
│        │ │  - Leaderboard sorted sets                    │
└───────┘  └──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Bunny Stream                                            │
│  - Video library per environment                         │
│  - Webhook on encode complete → POST /webhooks/bunny     │
│  - Token-auth HLS playback via pull zone                 │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Zoom webhook → FastAPI → Redis queue → Worker process   │
│  - Claude API for transcript → module JSON               │
│  - Upload recording to Bunny Stream via API              │
└─────────────────────────────────────────────────────────┘
```

## Cost Estimate (30 concurrent users, MVP)

| Service | Config | ~Monthly |
|---|---|---|
| VPS (Hetzner CX22) | 2 vCPU / 4 GB RAM | ~$4.50 |
| Bunny CDN | 500 GB transfer | ~$5 |
| Bunny Stream | 100 GB storage + 500 GB transfer | ~$12 |
| Bunny Storage | 50 GB (thumbs + frontend) | ~$0.50 |
| Postgres (managed, Supabase free or same VPS) | 500 MB DB | ~$0 |
| Redis (same VPS, Docker) | — | ~$0 |
| Domain / TLS (Caddy auto-HTTPS) | — | ~$12/yr |
| Anthropic API | Claude Sonnet | ~$5–15 |
| **Total** | | **~$25–40/mo** |

## Bunny API Keys Needed

1. **Bunny Account API Key** — for Storage + DNS zone management
2. **Bunny Stream API Key** — for video library management  
3. **Bunny Storage Zone Password** — per-zone FTP/HTTP access
4. **Bunny Token Auth Secret** — HMAC key for signed playback URLs
5. **Bunny Stream CDN Hostname** — e.g. `vz-abc123.b-cdn.net`
