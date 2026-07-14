# Champ LMS v2 — Improvement Ideation

> Generated from review of `GAMIFICATION_PLAN.md`, `BUNNY_ARCHITECTURE.md`, and the current v2 frontend/backend code.
>
> This document intentionally splits “functional/product” improvements from “gamification” improvements so we can prioritize fixes that are real product gaps versus motivational-system work.

---

## 1. Functional / Product Improvements

These are non-gamification gaps or friction points that reduce the core learning experience.

### 1.1 Content Discovery & Search
- **Persistent search page.** Search currently exists in the API but there is no dedicated `/search` route in the frontend. Add a search bar in nav that drops to a results page.
- **Filter & sort on Home.** Today the feed is AI-generated rows only. Add category chips and “Continue watching” / “New releases” / “For your role” filters.
- **Empty-state targeting.** When a learner finishes a module, surface the next recommended module immediately instead of returning to a generic home.
- **Episode-level recommendations.** On the watch page, show “Up next” and “Replay for review” directly under the player.

### 1.2 Watch Experience
- **Resume from exact timestamp.** API returns `watched_seconds`, but the player appears to start from the beginning. Use `episodeProgress` to seek on load.
- **Closed-captions / transcript panel.** Transcripts are already generated (`Episode.transcript`); expose them as a side panel for accessibility and note-taking.
- **Playback speed & quality controls.** Standard learning-video controls missing from the custom player.
- **Mobile-optimized player and nav.** Current nav collapses only partially; a bottom sheet for nav or a hamburger menu would help small screens.
- **Cast / picture-in-picture support.** Shallow win for modern video expectations.

### 1.3 Assessment & Learning Integrity
- **Quiz retake policy.** Currently `AssessmentAttempt` may allow infinite retakes; define a max-attempts / cooldown policy.
- **Per-question explanations on pass.** The quiz result already shows explanations; surface a “Review mistakes only” mode.
- **Confidence scoring.** Ask learner to rate confidence per answer; use it to weight spaced-repetition scheduling later.
- **Anti-scrub / watch-integrity (functional first).** Before treating completion as real, track watched intervals and reject huge forward jumps. This is a correctness issue, not just gamification.

### 1.4 Admin / Creator Experience
- **Edit existing module metadata.** Right now upload/build flows create content; editing titles, descriptions, thumbnails, sequence order is not exposed.
- **Episode reordering / delete.** Add drag-and-drop reordering to the module page.
- **Content analytics for creators.** Replace flat analytics counts with completion funnel (started / 50% / completed / passed quiz), drop-off timestamps, and quiz pass rate per module.
- **Publishing workflow.** Schedule publish, visibility (all / role-restricted / department-only), and draft state.
- **AI module polish.** Allow admin to regenerate AI summary, quiz, or thumbnail from the module page.

### 1.5 Social / Collaborative Learning
- **Comments / Q&A per episode.** Learning is often questions-driven; threaded Q&A under each episode.
- **Share progress / certificate.** Learners can share completion of a module.

### 1.6 Reliability & Observability
- **Client error boundaries.** SvelteKit error boundaries for route failures.
- **Offline resilience.** Queue progress sync when connection returns; currently it silently fails.
- **Rate limiting & abuse protection.** Public auth endpoints and leaderboard endpoints need limits.
- **Health-check depth.** Backend `/health` should verify MongoDB/Redis connectivity.

---

## 2. Gamification Improvements (Short to Long Term)

These map to the phases in `GAMIFICATION_PLAN.md` plus the research-backed extension layer (Octalysis / SDT).

### 2.1 Foundational Layer (must-haves before anything else)
- **Seed a real badge catalog.** Without it the entire badge engine is dead code.
- **Introduce XP + levels.** Split XP (progression/always-up) from points (leaderboard/spendable). Levels: Rookie, Regular, Pro, All-Star, Champion, Legend.
- **Immutable XP ledger.** Every point/XP award is one row; prevents double-awards and answers “where did my points come from.”
- **Return rewards payload from API calls.** Without this the frontend cannot celebrate anything.
- **Wire `Enrollment.completion_percentage`.** Make module completion actually detectable.
- **Redis leaderboard rehydration.** Treat Redis as cache, not source of truth.

### 2.2 Watch-Integrity & Video-Native Rewards
- **Track watched intervals client-side.** Union of played ranges; send to backend; compute `coverage_pct`.
- **Focused-watch bonus.** +5 XP if coverage >= 95% and no large forward jumps.
- **Milestone XP.** Small XP awards at 25%, 50%, 75% watch progress.
- **Decide iframe vs HLS path.** The iframe path blocks all watch events. Standardize on HLS for gamified content.

### 2.3 Celebration & Feedback Layer
- **Reward-event store + toast system.** Real-time “+10 XP” / “+25 points” / badge unlocked / level up.
- **Level-up modal with confetti burst.** The strongest retention lever in the plan.
- **Badge unlock reveal.** Flip/reveal card animation.
- **Streak milestone popups.** 3 / 7 / 14 / 30 / 100 day bonuses.
- **Nav stat updates that animate.** Gold points, fire streak, and a new XP/level ring should react in real time.

### 2.4 Habit Loop Layer
- **Streak calendar (GitHub-contributions heatmap).** Visible on My Learning.
- **Streak freezes & repair.** One-tap repair within grace window; freezes auto-consume.
- **Streak-at-risk nudge.** After ~20 hours of inactivity show a banner.
- **Quest / mission system.** Daily (“Watch 2 episodes”, “Pass a quiz”) and weekly (“Complete a Sales module”).
- **Streak wager.** Bet points on hitting a weekly goal; proven retention lever.

### 2.5 Mastery & Role Tracks
- **Module mastery.** Completion + passing module quiz => mastered; unlock mastery ring and role-track progress.
- **Role tracks.** Group modules by `target_roles`; progress ring per role (“Sales Onboarding 4/7 mastered”).
- **Mastery decay / spaced repetition.** Skills fade; AI-generated retrieval questions resurface weak topics.
- **First-to-complete race.** First learner to finish a newly published module gets bonus points.

### 2.6 Social & Competitive Layer
- **Weekly / seasonal leaderboards.** Reset each week; persist snapshots for history.
- **1v1 quiz duels.** Reuse assessment engine; real-time or async challenges.
- **Learning buddies / cohorts.** Small groups with shared progress.
- **Kudos & reactions.** Episode-level reactions to build relatedness.
- **Mentor flagging.** High-mastery users flagged as experts others can ask.

### 2.7 Economy, Ownership & Meaning Layer
- **Spendable points economy.** Split XP vs points; add a store for streak freezes, avatar frames, profile themes.
- **Variable rewards.** Mystery-box drops, “lucky episode,” daily surprise quest.
- **Epic meaning / collective goals.** Department progress bars toward shared goals; early access to fresh Zoom modules for top learners.
- **Creator publishing cadence streak.** Reward admins for consistent fresh content.
- **Learner autonomy.** “Pick your next 3 episodes,” self-set weekly goals, difficulty selection.

### 2.8 Generative / AI-Driven Layer
- **AI “gamification director.”** A `/me/gamification-feed` endpoint that returns an ordered set of cards (streak at risk, review prompt, quest, mastery ring, level-up celebration) rendered from a fixed Svelte component registry.
- **Adaptive difficulty quizzes.** Gate question tiers by learner performance.
- **AI “explain it back” grading.** Free-text explanation submissions graded by the existing OpenRouter pipeline.
- **Auto-assembled role tracks.** Build tracks from `target_roles` tags automatically.

---

## 3. Recommended Implementation Order

1. **Week 1 — Foundations.** XP/levels, ledger, badge/quest seeding, rewards payload, Redis rehydration.
2. **Week 2 — Celebration.** Toast system, level-up modal, confetti, reward wiring to player & quiz.
3. **Week 3 — Habit.** Streak calendar, streak freeze/repair, quest panel.
4. **Week 4 — Mastery.** Module mastery, role tracks, first-to-complete.
5. **Month 2+ — Advanced.** Social duels, economy/store, spaced repetition, generative feed.

---

## 4. Design Principles for the UI Layer

- Stay inside existing CSS tokens (`--gold`, `--success`, `#ff6b35`, `--accent`, `--surface`, `--bg`).
- Do **not** introduce Tailwind or shadcn for this work; the existing hand-rolled system is sufficient.
- Keep components in `src/lib/components/`; keep state in `src/lib/stores/`.
- Use Svelte 4 patterns (`export let`, stores, `on:` events, `createEventDispatcher`) consistent with the rest of the app.
- Use emoji iconography to match current convention until the badge catalog becomes large.
- Always make rewards feel synchronous in the UI even if backend calls are async; queue them, never drop them.
