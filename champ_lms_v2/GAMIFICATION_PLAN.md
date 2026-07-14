# Champ LMS v2 — Gamification Plan

> Companion to `BUNNY_ARCHITECTURE.md` (canonical infra) and `../MVP_PLAN.md`
> (original vision). This doc covers **only gamification**: what exists, what's
> broken, and a concrete, phased build plan grounded in the actual v2 code
> (SvelteKit + FastAPI + MongoDB/Beanie + Redis + Bunny Stream).
>
> Every file:line reference below is against the current `champ_lms_v2/` tree.

---

## Part 0 — TL;DR

Gamification here is **not greenfield** — roughly 40% is already wired, and a
few pieces are subtly broken. The right framing is **"complete, deepen, and
make it feel good,"** not "build from zero."

**What already works today**
- Points scalar on the user, awarded on episode completion (+10) and quiz pass (+25).
- Streak tracking (day-over-day) in Redis, mirrored to `User.streak_days`.
- Redis sorted-set leaderboard (global + per-department).
- Badge / UserBadge collections + `/badges/me`, `/leaderboard`, `/streaks/me` endpoints.
- Frontend surfaces: nav point/streak pills, a leaderboard page, a "My Learning"
  stats dashboard, per-card progress bars.

**What's broken or missing (the actual work)**
1. **No badges are ever seeded** → `check_and_award_badges` always finds nothing.
   The badge system is dead code until a catalog exists.
2. **`complete_module` (+50) and `first_to_complete` (+200) are defined but never fired** —
   there is no module-completion detection anywhere.
3. **Points are a bare integer with no ledger** — no history, no audit, no way
   to show "where did my points come from," no idempotency guard beyond badges.
4. **Redis leaderboard is ephemeral** — a Redis flush loses all rankings;
   `User.points` survives but is never re-synced back into the sorted set.
5. **The API never tells the client what was earned** — `POST /progress` and the
   quiz-attempt endpoint award points server-side but return nothing about it,
   so the frontend *cannot* show "you earned +10 / unlocked a badge" moments.
6. **`Enrollment.completion_percentage` is never updated** — the collection is
   effectively write-only/unused.
7. **No XP/levels, no quests/missions, no achievements engine, no streak
   recovery, no watch-integrity** (anti-scrub), and **no celebration UI** at all.
8. **A video-observability gap** that constrains everything video-native (see Part 5).

The plan below fixes 1–6 first (cheap, high-leverage, low-risk), then layers on
the video-native and habit mechanics that make it feel like a game.

> **New in v2 (see Part 11):** Parts 1–10 are extrinsic-heavy (points, XP, badges,
> streaks, leaderboards). Part 11 adds a research-backed **extension layer** on top:
> a spaced-repetition memory loop, a real social layer, a spendable economy,
> variable rewards, epic meaning, and learner autonomy. Read it alongside Parts 3
> and 9. It is a superset, not a replacement.

---

## Part 1 — Codebase Evaluation (gamification-relevant)

### Stack (confirmed from code, not the retired v1 plan)
- **Backend:** FastAPI 0.115 + Motor/Beanie 1.27 (**MongoDB, document store — no SQL, no Alembic**), Redis 5.1 (asyncio), JWT HS256 self-managed auth, httpx to Bunny/OpenRouter.
- **Frontend:** SvelteKit 2 / **Svelte 4** (`export let`, stores, `on:` events — *not* runes), `adapter-node`. **No Tailwind, no component library** — hand-rolled CSS with design tokens in `src/app.css`. Only runtime dep is `hls.js`.
- **Video:** Bunny Stream (token-auth HLS), one Bunny video ⇔ one `Episode`.
- **Same-origin in prod:** SvelteKit Node server proxies `/api/*` to internal FastAPI (`frontend/src/hooks.server.ts`).

### The content/learning graph (what gamification attaches to)
```
Module (category, tags, target_roles, source_type: manual|zoom|upload)
  └─ Episode (1:1 Bunny video; duration_seconds, transcript, ai_summary, status)
       └─ WatchProgress (per user: watched_seconds, completed, completed_at)
       └─ Assessment (quiz: questions[], pass_threshold=70)
            └─ AssessmentAttempt (score, passed, answers)
Enrollment (user↔module, completion_percentage)   ← exists but never written
Recommendation (per user: Netflix-style rows)
```
This graph is rich enough to gamify along **four axes**: *watch* (episodes/videos),
*master* (quizzes), *explore* (categories/roles/tags), and *habit* (streaks/daily).

### The existing gamification layer — file map
| Concern | Location | State |
|---|---|---|
| Points table | `backend/app/services/gamification_service.py:10` | Defined; only 2 of 5 actions fire |
| Badge criteria constants | `gamification_service.py:18` | Reference only; DB `Badge.criteria` is the real matcher |
| `award_points` | `gamification_service.py:30` | Works (Redis zincrby + Beanie `Inc` on User) |
| `record_activity` (streak) | `gamification_service.py:46` | Works; awards `streak_7day` at day 7 |
| `get_leaderboard` | `gamification_service.py:81` | Works (Redis-only) |
| `check_and_award_badges` | `gamification_service.py:104` | Works but no catalog to match against |
| User gamification fields | `backend/app/models/user.py:18` | `points`, `streak_days`, `last_activity_at` |
| Badge / UserBadge models | `backend/app/models/gamification.py:8,21` | Exist; UserBadge has unique `(user_id, badge_id)` |
| **Award hook: episode complete** | `backend/app/routers/progress.py:43-50` | Fires `complete_episode` only |
| **Award hook: quiz pass** | `backend/app/routers/assessments.py:68-71` | Fires `pass_quiz` + badge check |
| Gamification API | `backend/app/routers/gamification.py:15,26,46` | `/leaderboard`, `/badges/me`, `/streaks/me` |
| Completion rule | `progress.py:32` | `watched ≥ 0.9 × total` |
| Nav stat pills | `frontend/.../+layout.svelte:38-50` | Points ⭐ + streak 🔥 |
| Leaderboard page | `frontend/.../leaderboard/+page.svelte` | Medals, dept filter, badges row |
| My Learning dash | `frontend/.../my-learning/+page.svelte:27-45` | 4 stat tiles + history |
| Card progress bar | `frontend/.../VideoCard.svelte:50-54` | Red fill overlay |
| Progress store (30s sync) | `frontend/src/lib/stores/player.ts:22-48` | `startTracking`/`updateTime`/`stopTracking` |
| **Video engagement hooks** | `frontend/.../VideoPlayer.svelte:50,55` | `onTimeUpdate`, `onEnded/onComplete` |

### Design system to reuse (don't reinvent)
From `frontend/src/app.css` — dark-only, Netflix-styled:
- `--accent #e50914` (Netflix red), **`--gold #f5c518`** (points), `--success #2ecc71` (completed), streak orange `#ff6b35`.
- Primitives: `.btn-primary`, `.btn-ghost`, `.badge`, `.stat` tile pattern, the `QuizModal` overlay (`QuizModal.svelte:85-102`) as the template for celebration/unlock modals.
- Emoji-as-iconography convention (no icon library).

---

## Part 2 — Design Philosophy (tuned to *this* product)

The MVP vision is **"the Netflix of learning" — a daily, self-driven habit, not a
compliance database.** That dictates the gamification tone:

1. **Reward the behavior you want: finishing micro-content and coming back daily.**
   Watch-time and streaks are the core loop; quizzes prove retention.
2. **Make every reward *felt*, not just recorded.** Today points change silently.
   The single biggest UX win is real-time celebration (toasts, level-ups, unlocks).
3. **Respect the content's nuances.** Modules carry `category`, `tags`,
   `target_roles`, and `source_type` (`zoom` content is fresh/topical). Use these
   to drive *quests* ("finish a Sales module this week") and *role mastery tracks*,
   not just a flat point total.
4. **Video is the atomic unit — gamify the watch itself,** with integrity
   (anti-scrub) so points mean genuine engagement.
5. **Intrinsic > extrinsic.** Levels, mastery, and progress rings should signal
   *competence and growth*, not just a scoreboard. Keep the leaderboard opt-in-feeling
   (department-scoped, weekly resets) so it motivates without demoralizing.

---

## Part 3 — The Gamification System (mechanics)

### 3.1 XP, Points & Levels
Introduce **XP as the progression currency** (points stays as the leaderboard/spendable
score; XP only ever goes up and drives level). This also lets us add a **ledger**.

- **XP ledger** (new collection) — every award is one immutable row: `user_id,
  amount, reason, ref_type, ref_id, created_at`. Fixes "bare integer, no history"
  and gives idempotency (unique `(user_id, reason, ref_id)` blocks double-awards).
- **Levels** — derived from cumulative XP via a curve (e.g. `level = floor(sqrt(xp/50))`),
  with named tiers to fit the brand:
  `Rookie → Regular → Pro → All-Star → Champion → Legend`.
- Level-up is a **celebration moment** (modal + confetti), the strongest retention lever.

### 3.2 Points Economy (expanded — implement the unused actions + new ones)
| Action | Points/XP | Status today |
|---|---|---|
| Complete an episode (genuine watch) | +10 | ✅ fires |
| **Complete a module** (all episodes done) | **+50** | ❌ defined, never fired — **build it** |
| Pass a quiz (≥70%) | +25 | ✅ fires |
| **Perfect quiz (100%)** | **+15 bonus** | 🆕 |
| **Focused-watch bonus** (no scrubbing, ≥95% coverage) | **+5** | 🆕 (needs watch-integrity) |
| **First to complete a new module** | **+200** | ❌ defined, never fired — **build it** |
| 7-day streak | +100 | ✅ fires at day 7 |
| **Daily quest completed** | **+20–50** | 🆕 |
| **Module mastery** (complete + pass module quiz) | **+40** | 🆕 |

### 3.3 Streaks (deepen the habit loop)
- Keep the Redis day-over-day logic (`gamification_service.py:46`).
- Add **`longest_streak`** and **streak freeze / recovery**: each user gets N
  "freezes" (auto-consume to protect a missed day, or a one-tap "repair yesterday"
  within a grace window). This is *the* mechanic that stops a broken streak from
  causing churn.
- **Streak calendar UI** (GitHub-contributions style) on My Learning + a streak-at-risk
  nudge in the nav after ~20h of inactivity.
- Escalating milestone bonuses: 3 / 7 / 14 / 30 / 100 days.

### 3.4 Badges & Achievements (seed a real catalog + a criteria engine)
The models exist; **nothing is seeded**, so step one is a `seed_gamification()`
that populates `Badge.criteria`. Categories:
- **Completion:** First Watch, 10 Episodes, Module Champion, 5 Modules, Category Complete.
- **Mastery:** Quiz Ace (pass 5), Perfectionist (3× 100%), Sharpshooter (5 perfect in a row).
- **Habit:** 5-Day / 30-Day / 100-Day Streak, Early Bird, Weekend Warrior.
- **Explorer:** watch across N categories, complete a `target_role` track, watch a `zoom`-sourced module within 48h of publish ("Fresh Off the Call").
- **Social/competitive:** Top 3 on weekly leaderboard, First to Complete.

Extend the criteria engine (`check_and_award_badges`) beyond exact `type == action`
to support `count`, `distinct_categories`, `within_hours_of_publish`, `streak_length`,
`perfect_quizzes`, `leaderboard_rank`.

### 3.5 Quests / Daily & Weekly Missions (uses content nuances)
New `Quest` + `UserQuest` collections. Generated from the content graph:
- Daily: "Watch 2 episodes", "Pass any quiz", "Keep your streak."
- Weekly: "Complete a module in **{category}**", "Finish a module for **{your role}**",
  "Watch a **fresh Zoom** module."
- Rewards feed XP/points and advance badge criteria. Quests give a reason to open
  the app *today* even when mid-module.

### 3.6 Module Mastery & Role Tracks (make progress meaningful)
- **Wire `Enrollment`** (currently unused): on first episode of a module, create/enroll;
  update `completion_percentage` on every episode completion; mark mastered when all
  episodes done **and** the module quiz passed.
- **Role tracks:** group modules by `target_roles`; show a track progress ring
  ("Sales Onboarding — 4/7 mastered"). This is the intrinsic-motivation backbone.

### 3.7 Leaderboards (fix + extend)
- **Rehydrate Redis from Mongo on startup** (sync `User.points` → sorted set) so a
  Redis flush can't wipe rankings.
- Add **weekly / seasonal** boards (`leaderboard:weekly:{isoweek}`) with a reset +
  a persisted `LeaderboardSnapshot` for history and "last week's winners."
- Keep department scoping (already there) — it's less demoralizing than pure global.

---

## Part 4 — Data Model Changes (MongoDB/Beanie)

> Reminder: schema = Beanie `Document` classes; **every new model must be added to
> `DOCUMENT_MODELS` in `backend/app/models/__init__.py:17`** or Beanie won't init it.
> No migration tooling — indexes are created by `init_beanie()` on startup.

**Extend `User`** (`models/user.py`): add
`xp: int = 0`, `level: int = 1`, `longest_streak: int = 0`, `streak_freezes: int = 3`.
(Existing `points`, `streak_days`, `last_activity_at` stay.)

**Extend `WatchProgress`** (`models/progress.py`): add
`watched_intervals: list[list[int]] = []` (merged [start,end] second-ranges) and
`coverage_pct: float = 0.0` — the anti-scrub signal (Part 5).

**New collections:**
- `XpEvent` — `user_id, amount, reason, ref_type, ref_id, created_at`; unique
  `(user_id, reason, ref_id)` for idempotency. (The ledger.)
- `Quest` — `key, scope(daily|weekly), title, criteria(dict), reward_xp, reward_points, active`.
- `UserQuest` — `user_id, quest_id, period_key, progress, target, completed, completed_at`;
  unique `(user_id, quest_id, period_key)`.
- `LeaderboardSnapshot` — `scope, period_key, entries[], captured_at`.
- (Optional) `ModuleMastery` — or just reuse `Enrollment` + a `mastered_at` field.

**Seed data:** new `seed_gamification()` (badge catalog + base quests), called from
the lifespan in `main.py:13-19` next to `seed_admin()`. Idempotent (upsert by `key`).

---

## Part 5 — The Video-Observability Constraint (read before Part 6)

This is the single most important technical nuance for *video-native* gamification.

`VideoPlayer.svelte` has **two playback paths**:
- **HLS `<video>` path** (`VideoPlayer.svelte:92-99`): `on:timeupdate` (`:50`) and
  `on:ended` (`:55`) fire → we can observe watch position, milestones, scrubbing,
  completion. **All video-native gamification depends on this path.**
- **Bunny iframe path** (`:83-89`): cross-origin `<iframe>` → **no `timeupdate`/`ended`
  at all.** In iframe mode we get *nothing* except whatever the 30s progress loop
  can infer, which itself relies on the `<video>` element. So in pure iframe mode,
  progress/milestones/completion are effectively invisible.

**Decision required (Phase 1 prerequisite). Pick one:**
1. **Standardize on the HLS `<video>` path** for gamified content (token-auth still
   works via `get_token_auth_url`). Simplest; keeps all hooks. **Recommended.**
2. **Integrate the Bunny Player `postMessage`/player.js events** into the iframe so
   `timeupdate`/`ended` surface across the origin boundary. More work; needed only
   if token-auth *must* use the iframe embed.

Until this is resolved, milestone/integrity mechanics only work for HLS-path videos.
Completion via the server 90% rule (`progress.py:32`) is the safe fallback for iframe.

**Anti-scrub / watch integrity:** don't trust "position ≥ 90%." Track actual watched
**intervals** client-side (union of played ranges from `timeupdate`), send them with
progress, and compute `coverage_pct` server-side. Award full episode XP only when
coverage is genuine; award the **focused-watch bonus** when coverage ≥95% with no
large forward jumps. Also validate server-side that `watched_seconds` can't grow
faster than wall-clock between POSTs (cheap cheat guard).

---

## Part 6 — Backend Implementation (concrete hook points)

**Fix-first (Phase 0), all low-risk:**
1. `seed_gamification()` badge/quest catalog → makes the badge engine live.
2. **Redis rehydration on startup** — one pass syncing `User.points` into
   `leaderboard:global` / `leaderboard:dept:*` (in the lifespan, `main.py`).
3. **Return rewards from award paths.** Change `POST /progress` (`progress.py:21`)
   and `POST /assessments/{id}/attempt` (`assessments.py:37`) to return a
   `rewards: {xp, points, level_up?, badges_unlocked[], quest_updates[]}` payload.
   Without this the frontend cannot celebrate anything.

**Build module completion** (the biggest missing award). In the completion branch
`progress.py:43-50`, after upserting `WatchProgress.completed`:
- Recompute the module's completion for this user (count completed episodes vs
  `Module.total_episodes`); update `Enrollment.completion_percentage`.
- If newly 100% → `award_points(user, "complete_module")`, then if the module quiz
  is passed → `"module_mastery"`; check `first_to_complete` (atomic Redis `SETNX`
  `module:first:{module_id}` → award +200 to the winner only).
- Feed all of the above through the **XP ledger** (idempotent) and `check_and_award_badges`.

**Service work** (`gamification_service.py`):
- `award_xp(user, reason, ref, amount)` writing an `XpEvent` + recomputing `level`
  (return `level_up` boolean for the response payload).
- Extend `check_and_award_badges` to the richer criteria types (Part 3.4).
- `advance_quests(user, action, context)` called from both award hooks.
- `record_activity` (`:46`): add `longest_streak`, freeze consumption, milestone bonuses.

**New endpoints** (`routers/gamification.py`):
- `GET /quests/me`, `POST /quests/{id}/claim`
- `GET /me/level` (xp, level, next-level threshold, tier name)
- `GET /leaderboard?period=weekly`
- `GET /me/xp-history` (ledger, for a "where my points came from" view)

**Auth/authority:** everything stays server-authoritative — the client only ever
*displays* rewards (already the case). Keep awards idempotent via the ledger + the
existing `UserBadge` unique index.

---

## Part 7 — Frontend Implementation (SvelteKit / Svelte 4)

### 7.1 New store: `src/lib/stores/gamification.ts`
A reward-event queue. When an API call returns a `rewards` payload, push events
here; components subscribe and animate. Holds: toast queue, pending level-up,
pending badge unlocks, live xp/level/streak. This is the missing "real-time
you-just-earned-X" layer.

### 7.2 New components (reuse tokens + `QuizModal` overlay pattern)
- `PointsToast.svelte` — transient "+10 XP ⭐" bottom-right stack (gold token).
- `RewardBurst.svelte` — lightweight confetti/particle burst (CSS/canvas, no dep).
- `LevelUpModal.svelte` — big celebration on level change (overlay pattern from `QuizModal.svelte:85`).
- `BadgeUnlockModal.svelte` — flip-reveal of a newly earned badge.
- `XpBar.svelte` / level ring — add to nav next to the existing point/streak pills (`+layout.svelte:38-50`).
- `StreakCalendar.svelte` — contribution-grid on My Learning; streak-at-risk banner.
- `QuestPanel.svelte` — daily/weekly missions with progress bars; new `/quests` route or a Home rail.
- `MasteryRing.svelte` — module/role-track progress; drop onto `module/[id]` and Home.

### 7.3 Wiring (exact hook points)
- **Milestones:** in `VideoPlayer.svelte` `onTimeUpdate` (`:50`) accumulate played
  intervals; the 30s `player.ts` sync (`:27-36`) sends `watched_intervals`; when
  `POST /progress` returns rewards → push to the gamification store → toast.
- **Completion celebration:** `VideoPlayer.svelte` `onEnded/onComplete` (`:55`) and
  the watch page's `onEpisodeComplete` (`watch/[id]/+page.svelte:52`) → show
  completion reward + (if returned) level-up/badge modals before the 5s auto-advance.
- **Quiz rewards:** `QuizModal.svelte` already has the score screen — render the
  `rewards` payload there (perfect-quiz bonus, badges).
- **Nav:** extend the existing pills with an XP/level ring; subscribe to the store
  so they animate on change instead of only updating on `me()` refresh.

### 7.4 Design guidance
Stay **inside the existing hand-rolled token system** — it's already coherent and
on-brand. Gold (`--gold`) = XP/points, success green = completion/mastery, streak
orange = streaks, Netflix red = primary actions. Emoji iconography matches the
current style; only add an icon library if the badge catalog grows large.

---

## Part 8 — On "shadcn / frontend skills"

Worth being explicit, because it changes the recommendation:

- **This frontend is Svelte 4 with hand-rolled CSS tokens — not React, not Tailwind.**
  **shadcn/ui is React-only**, so it cannot be used here as-is.
- The nearest equivalent is **shadcn-svelte** (`bits-ui` + `tailwind-variants`),
  but it **requires adopting Tailwind + a runes-era setup** and would sit awkwardly
  next to the existing scoped-CSS components and the Netflix design tokens.
- **Recommendation: do *not* introduce shadcn for this gamification work.** The
  existing design system (`app.css` tokens + `.btn`/`.badge`/`.stat` primitives +
  the `QuizModal` overlay) is enough to build every component in Part 7 with less
  risk and a consistent look. Revisit shadcn-svelte only as part of a deliberate,
  separate "adopt Tailwind + migrate to Svelte 5 runes" initiative — out of scope here.
- For live, version-accurate Svelte/SvelteKit/shadcn-svelte docs during
  implementation, pull them on demand via Context7 rather than trusting memory.

---

## Part 9 — Phased Rollout

**Phase 0 — Foundations & fixes (small, unblocks everything)**
Badge/quest seeding · XP ledger (`XpEvent`) · levels on `User` · Redis rehydration
on startup · **rewards payload returned from `POST /progress` + quiz attempt** ·
wire `Enrollment.completion_percentage`.

**Phase 1 — Video-native XP & celebration**
Resolve the iframe-vs-HLS decision (Part 5) · watch-integrity intervals +
`coverage_pct` · milestone XP · **module completion** (+50) + first-to-complete
(+200) · gamification store + `PointsToast` + completion/level-up/badge modals.

**Phase 2 — Habit loop**
Streak freeze/recovery + `longest_streak` + milestone bonuses · streak calendar +
at-risk nudge · daily/weekly quests (`Quest`/`UserQuest`) + `QuestPanel`.

**Phase 3 — Mastery & competition**
Module mastery + role tracks + `MasteryRing` · achievements catalog with richer
criteria engine · weekly/seasonal leaderboards + `LeaderboardSnapshot` + "last
week's winners."

**Phase 4 — Advanced / social (optional)**
Team/department challenges · shareable achievement cards · seasonal events tied to
freshly-published Zoom modules.

---

## Part 10 — Risks & Notes
- **Iframe observability** (Part 5) gates video-native mechanics — decide early.
- **Anti-gaming** is essential the moment points are visible; ship watch-integrity
  in Phase 1, not later.
- **Redis is not the source of truth** — always mirror to Mongo (`User`, ledger)
  and rehydrate on boot; treat Redis as a fast cache/index only.
- **Idempotency** — the XP ledger's unique `(user_id, reason, ref_id)` + the
  existing `UserBadge` unique index are what keep double-taps and retries safe.
- **Keep it server-authoritative** — the client only displays rewards; never let
  it assert them.

---

## Part 11 — Research-Backed Extensions (v2): Beyond Points, Badges & Streaks

> Added 2026-07-13 from a review of current gamification research: Yu-kai Chou's
> [Octalysis 8 Core Drives](https://yukaichou.com/gamification-examples/octalysis-gamification-framework/),
> Self-Determination Theory in corporate L&D, a
> [Duolingo retention teardown](https://apptitude.io/blog/how-duolingos-streak-mechanic-actually-works/),
> and spaced-repetition / cohort evidence. This part is a **superset on top of
> Parts 1–10**: everything above still holds. This is what to build once the
> PBL + streak foundation (Phases 0–2) is live. Sources are linked in 11.6.

### 11.1 — The core finding

Parts 1–10 are **extrinsic-heavy** (points, XP, levels, badges, leaderboards,
streaks). The research is consistent that this plateaus: overusing leaderboards
and badges can actively *depress* motivation. Two whole layers are missing from
the current plan, and they are where durable engagement lives:

1. A **memory / retention layer** (spaced repetition + retrieval practice). The
   single most evidence-backed learning mechanic, and absent from the plan today.
   It also gives a *daily reason to return that is not just new content*, and it
   is real learning rather than a vanity loop.
2. An **intrinsic / social layer** (Self-Determination Theory: autonomy,
   competence, relatedness). The plan serves competence only. SDT is the durable
   layer; PBL/RAMP only ever drives extrinsic behavior.

### 11.2 — Octalysis gap analysis (mapped to the v2 code)

| Core drive | Status in Parts 1–10 | The gap = the opportunity |
|---|---|---|
| 2. Development & Accomplishment | ✅ Strong | points / XP / levels / badges / mastery |
| 8. Loss & Avoidance | 🟡 Partial | streaks yes; **streak wager** and **skill decay** no |
| 6. Scarcity & Impatience | 🟡 Partial | first-to-complete yes; time-limited events / limited badges no |
| 5. Social Influence & Relatedness | 🔴 Weak | only leaderboards: no friends, duels, cohorts, kudos, mentors |
| 7. Unpredictability & Curiosity | 🔴 Missing | all rewards deterministic: no surprise / variable rewards |
| 4. Ownership & Possession | 🔴 Missing | points are not spendable; no store, avatar, collectibles |
| 1. Epic Meaning & Calling | 🔴 Missing | no purpose / mission tie-in, no expert status |
| 3. Empowerment & Feedback | 🔴 Missing | quizzes give feedback but no creative expression / UGC |

Five of eight drives are weak or absent. That is the map for this part.

### 11.3 — The extension mechanics (grounded in the actual code)

Each maps to concrete collections/services under `backend/app/`. New Beanie
`Document` classes must be registered in `DOCUMENT_MODELS`
(`backend/app/models/__init__.py`), same rule as Part 4.

**1. Spaced-Repetition "Knowledge Health" — the biggest miss, build first.**
Mastery should not be permanent. Give each skill / role-track a **decaying health
meter**; on a spacing schedule the AI service (`services/ai_service.py`, already
wired to OpenRouter/Claude) auto-generates short retrieval questions from
`Episode.transcript` / `ai_summary`; resurfacing them keeps mastery "green".
Traditional training suffers heavy knowledge decay; AI-driven systems can predict
individual decay curves and time retrieval optimally. New `ReviewItem` /
`ReviewSchedule` collections in Mongo; **reuse the existing `Assessment` /
`AssessmentAttempt` engine** to deliver and score reviews. This is the single
highest-value addition in this part.

**2. Streak Wager — proven loss-aversion lever.**
Let a learner bet points that they will hit a weekly goal. Duolingo's streak
wager produced roughly **+14% day-7 retention**. Trivial extension of the Redis
streak state (`gamification_service.record_activity`) plus a `wager` field on the
user (or a small `Wager` document for auditability).

**3. Variable / Surprise Rewards — the missing Unpredictability drive.**
Occasional mystery-box drops, a "lucky episode" bonus, a daily surprise quest.
Implement server-side as a **seeded roll inside `award_points`** so the outcome is
still deterministic per `(user_id, reason, ref_id)` and stays idempotent (Part 10).
Keep the variance ethical (variable-ratio, not slot-machine-abusive).

**4. A real Social layer — the weakest drive.**
Not just leaderboards: **1v1 quiz duels** (reuse the assessment engine),
**learning buddies / cohorts**, **kudos / reactions on episodes**, and a
**mentor system** where high-mastery users in a role track are flagged as experts
others can ask. New `Friendship`, `Duel`, `Cohort`, `Kudos` collections;
department/role data already exists on `User`.

**5. Spendable Economy + Ownership.**
Today points only rank you. Split the currencies (XP = progression, always up;
points = spendable) and add a **store**: streak freezes, cosmetic avatar frames
(`User.avatar_bunny_path` already exists), profile themes, or real perks. New
`StoreItem` + `Purchase` (inventory) collections. Ownership is a core drive with
nothing behind it today.

**6. Epic Meaning via collective goals.**
Aggregate department/company progress into a shared goal ("the Sales team has
mastered 78% of the Q3 playlist") and grant **early / exclusive access** to
freshly published `source_type: "zoom"` modules to top learners ("chosen few").
Uses data already stored; turns solo grinding into contribution to something bigger.

**7. Empowerment / learner-generated content.**
Let learners submit their own ~60-second "tips" (the Bunny upload pipeline already
exists) or an **"explain it back"** (Feynman) recording that the AI grades. The
strongest signal of genuine mastery, and it fills drive #3, which is otherwise empty.

**8. Autonomy — let them choose.**
"Pick your next 3 episodes", selectable difficulty, self-set weekly goals.
Autonomy is the SDT pillar the plan ignores entirely; cheap to add to the feed
and module pages.

### 11.4 — Caveats (do not skip)

- **Balance White Hat vs Black Hat.** Scarcity, unpredictability, and loss
  (wagers, decay, FOMO) drive urgency but cause **burnout** if overused. Duolingo
  deliberately pairs them with streak freezes; do the same. Keep it a *habit*, not
  a *compulsion*.
- **Intrinsic > extrinsic for durability.** The memory layer (#1) and
  autonomy/social (#4, #8) are what make engagement last beyond the novelty of
  points. Lead with those, not with more badges.
- **Still server-authoritative.** Everything here obeys Part 10: the client only
  displays rewards; awards stay idempotent via the ledger + unique indexes.

### 11.5 — Where these slot into the phased rollout (extends Part 9)

- **Phase 2 (habit loop):** streak wager (#2), variable rewards (#3), autonomy
  basics (#8). All cheap extensions of streaks + the feed.
- **Phase 3 (mastery):** spaced-repetition Knowledge Health (#1) alongside module
  mastery and role tracks.
- **Phase 4 (social/competitive):** the social layer (#4) and spendable economy (#5).
- **Phase 5 (new — meaning & creation):** epic-meaning collective goals (#6) and
  learner-generated content (#7).

### 11.6 — Sources

- Octalysis 8 Core Drives — https://yukaichou.com/gamification-examples/octalysis-gamification-framework/
- Duolingo streak / wager teardown — https://apptitude.io/blog/how-duolingos-streak-mechanic-actually-works/
- Duolingo retention tactics — https://www.strivecloud.io/blog/blog-gamification-examples-boost-user-retention-duolingo
- Gamification in learning, 2025 (PBL over-use caution) — https://elearningindustry.com/gamification-in-learning-enhancing-engagement-and-retention-in-2025
- Intrinsic motivation / SDT in gamified learning — https://www.upskillist.com/blog/intrinsic-motivation-in-gamified-learning-key-insights/
- Spaced repetition & retrieval practice, empowered by AI — https://www.researchgate.net/publication/397538205
- Cohort learning vs the curve of forgetting — https://www.intrepidlearning.com/blog/curve-of-forgetting/

---

## Part 12 — Generative UI & the AI-as-Gamification-Engine (v2)

> Added 2026-07-13. Covers dynamically gamifying the UI with generative UI, and
> using the already-wired OpenRouter pipeline (`services/ai_service.py`) as the
> engine behind Parts 3 and 11. Grounded in the v2 stack: **Svelte 4** frontend +
> **OpenRouter** backend. Sources in 12.5.

### 12.1 — The core idea
**Generative UI** = the AI decides *which* UI components to render, and with what
data, per user and per moment, instead of returning only text. The safe pattern
(CopilotKit calls it **"Controlled Generative UI"**) is: you pre-build styled
components, and the AI only *chooses which to show and passes schema-validated
data*. Applied to gamification, the interface rearranges around each learner: a
streak nudge when at-risk, a review card when a skill decays, a fresh-Zoom quest,
a level-up celebration.

### 12.2 — Honest stack fit (read before picking a tool)
- **CopilotKit is React/Angular-first.** v2 is **Svelte 4**, so its components do
  not drop in (same verdict as shadcn in Part 8). Adopting it means a React
  island or a migration: out of scope.
- **Vercel AI SDK generative UI supports Svelte**, but its richest form leans on
  **Svelte 5 runes/snippets**; v2 is Svelte 4.
- **v2 already ships the primitive.** `ai_service.generate_personalized_rows`
  returns UI-shaping JSON (`row_title` + `module_ids`) that the Svelte feed
  renders from a component. That *is* controlled generative UI already.

**Recommendation: do NOT add CopilotKit.** Extend the JSON-spec + Svelte-registry
pattern v2 already has. Low-risk, no framework change, reuses OpenRouter.

### 12.3 — The "gamification director" pattern (concrete)
Add a `GET /me/gamification-feed` endpoint. The AI takes the learner's live state
(points, level, streak, decaying skills, role, department, fresh Zoom modules) and
returns an **ordered, validated JSON list of gamification cards**:

```json
[
  {"type": "streak_at_risk", "hours_left": 4},
  {"type": "review_prompt", "skill": "Objection Handling", "episode_ids": ["..."]},
  {"type": "quest", "title": "Finish a Sales module this week", "reward_xp": 40, "progress": 1, "target": 3},
  {"type": "mastery_ring", "track": "Sales Onboarding", "mastered": 4, "total": 7},
  {"type": "level_up_celebration", "new_level": "Pro"}
]
```

Frontend renders each from a **fixed Svelte component registry**
(`QuestCard`, `StreakNudge`, `ReviewPrompt`, `MasteryRing`, `LevelUpToast` — reuse
the tokens/overlay from Part 7). **Pydantic/Zod-validate the `type` + props** so
the model can only pick known cards with safe data (schema validation is what
makes generative UI safe; the LLM must not inject arbitrary props). Drop this rail
onto Home and My Learning.

### 12.4 — OpenRouter as the gamification engine (extends Part 11)
The AI pipeline already generates quizzes + recommendations from stored
`Episode.transcript` / `ai_summary`. Reuse it (cheap, no new content authoring) to
power the Part 11 mechanics:
- **Spaced-repetition review items** (11.3 #1) — a "review question" mode on
  `generate_quiz`, on a spacing schedule → Knowledge Health.
- **Adaptive difficulty** — the quiz prompt already asks for recall→application→
  analysis; gate the tier shown by learner performance.
- **AI daily/weekly quests** (11.3 #4) — extend `generate_personalized_rows`
  (already points/streak-aware) to emit missions by role/dept/weak-skill.
- **AI "explain it back" grading** (11.3 #7) — grade free-text answers → deepest
  mastery signal + the Empowerment drive.
- **AI mastery-track assembly** — `build_module_from_zoom` already tags
  `target_roles`; auto-assemble role tracks from those tags.

**Admin/creator side (the video-input + AI screen).** Creators are users too:
- **Creator Impact dashboard** — replace the flat analytics counts with felt
  impact ("your modules drove 1,240 completions, 89 badges, 12k learner-XP").
- **Content-quality signals** — per-module completion %, quiz pass rate, and
  **drop-off point** so creators compete on quality and know what to fix.
- **Publishing cadence streak** — reward regular fresh content (feeds the
  scarcity/fresh-Zoom lever).

**One insight ties Parts 11 + 12 together:** the AI is both the *content engine*
(auto-generating quests, reviews, adaptive quizzes) and the *UI director*
(deciding which gamification card renders for whom, when). CopilotKit is the
polished React version of this; v2 builds the same pattern natively and lighter.

### 12.5 — Sources
- The Developer's Guide to Generative UI (2026), CopilotKit — https://www.copilotkit.ai/blog/the-developer-s-guide-to-generative-ui-in-2026
- AG-UI protocol — https://www.copilotkit.ai/ag-ui
- Vercel AI SDK — Svelte generative UI — https://ai-sdk.dev/docs/getting-started/svelte
- Vercel open-sources JSON render engine for Svelte + React generative UI — https://otuny.com/insights/vercel-open-sources-json-render-engineering-generative-ui-for-svelte-and-react
- Generative UI 2026: interfaces that build themselves around each user — https://zeeframes.com/insights/generative-ui-2026-interfaces-that-build-themselves-around-each-user
- Combining Generative AI, Gamification, and UX for personalized learning (Springer) — https://link.springer.com/chapter/10.1007/978-3-032-08366-1_25
