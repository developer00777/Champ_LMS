# Champ LMS v2 — Frontend Design Handoff

> **For:** the frontend/product designer picking up Champ LMS v2.
> **From:** engineering. Everything below was read out of the current codebase on the
> `employee-profiles-and-bulk-upload` branch, not from a spec or a wish list.
>
> **What we want back:** ideas and direction — not pixel-perfect redlines yet. Where you
> disagree with a framing below, say so; these are engineering's observations, and the
> design call is yours.
>
> **One note on branches:** this document lives on `main`, but every count and file path in
> it was verified against the `employee-profiles-and-bulk-upload` branch, which is one
> commit ahead. That branch adds the `/settings` screen and the avatar / level-badge work in
> the nav. So on `main` today you will find **23** route files, not 24, and no `/settings`.
> Nothing else in §3 differs. Everything here is where the product is heading; ask us and we
> will point you at the branch.

---

## 0. TL;DR — the ten-minute version

Champ LMS is an **internal, admin-provisioned learning platform** built to feel like a
streaming service rather than a compliance database. The engineering surface is broad and
mostly works: 24 routes, video streaming, quizzes, XP/levels/badges/quests, learning paths,
team challenges, PDF-driven test series, AI coaching, bulk employee onboarding.

The problem is **not missing features. It is that the UI grew feature-by-feature, so the
product now reads as several different products sharing a nav bar.** Concretely, and each of
these is verified in §3:

1. There are **two competing red brand colors** split cleanly along feature lines.
2. Only **6 of 24 routes** have any responsive handling at all.
3. Icons are **emoji**, everywhere, including the primary nav.
4. There is **no design system, no component library, and no brand asset** — not even a font
   or a favicon.
5. Several core screens render **placeholder content as if it were real content**
   ("Episode", "Episode") because the API never sends a title.

The highest-value thing you can do is **not** restyle screens one by one. It is to decide
what this product *is* visually, and give us a small system that makes the next twenty
screens consistent by default.

---

## 1. What the product actually is

**Champ LMS** is an internal learning platform for Champion. The founding idea, from
`MVP_PLAN.md`, is *"the Netflix of Champion LMS"* — binge-worthy micro-content (2–10 minute
lessons), AI-personalized rows, and gamified daily habits. Explicitly **not** a compliance
database. The goal is a self-driven daily learning habit.

Some product constraints that materially shape design:

- **Internal and closed.** There is no public sign-up; it was deliberately removed. Admins
  provision every account. The login page tells users to *"Ask your administrator."* So
  there is **no marketing surface, no onboarding funnel, and no acquisition flow** to design.
  Every visitor is already an employee who has been told to be here.
- **Two very different audiences share one app**: learners and admins (see §2).
- **Attendance is partly mandated.** Admins assign required modules to teams and individuals.
  This is a real tension worth designing for: the product wants to feel voluntary and
  binge-worthy, but part of it is genuinely assigned homework. Right now those two ideas sit
  in the same undifferentiated list.
- **Video is the primary content type**, served via Bunny Stream (HLS, `hls.js`).

### Audience reality check

Worth knowing before you design for "Gen Z bingeing": the current demo data shows categories
like Finance, Sales, Onboarding, Leadership, Engineering, with modules like *"Reading a P&L
in Ten Minutes"* and *"Your First Week: Company 101"*. This is **corporate professional
content**. The Netflix framing is about *pacing and pull* — short, sequenced, autoplay-ish,
"one more" — and probably should not be read as a mandate for literal entertainment styling.
Calibrating that is one of the main things we want your opinion on (see §7, Q1).

---

## 2. The two audiences

### Learner (default role)
Nav: Home · My Learning · Paths · Challenges · Tests · Leaderboard

Their loop is: land on Home → pick or resume a module → watch episodes → pass a quiz → earn
XP/points/badges → keep a streak → climb a leaderboard → progress along a learning path.

### Admin (`isAdmin`, sees an extra ⚙️ Admin nav item)
Admin lives at `/admin/*` and covers: content upload (video, TUS resumable), module and
episode management, employee CRUD **and bulk spreadsheet upload**, team-based content
targeting and per-person access control, Zoom session import, and the whole test-series
system (build from PDF/DOCX, review results, AI coaching).

**This is the single biggest structural design question in the product.** Admin is not a
small settings corner — it is roughly half the routes and by far the most information-dense
part of the app. Yet it is rendered inside the same learner chrome: same top nav, same
1400px centered container, same styling vocabulary. An admin doing bulk employee onboarding
or reviewing test results is doing dense, tabular, operational work while wearing a UI built
for browsing video thumbnails.

Options worth your consideration: a distinct admin shell (sidebar, wider/fluid container,
denser type scale, table-first components), versus keeping one shell and just introducing
proper data-dense components. We have no attachment to either.

---

## 3. Current state — verified findings

Everything in this section was checked against the code. Counts are real.

### 3.1 There are two brand reds

`frontend/src/app.css` defines the design tokens, including:

```css
--accent: #e50914;   /* Netflix red */
--gold:   #f5c518;   /* IMDb gold */
```

But across the Svelte files, the most-used hardcoded color is **`#e05260` (31 occurrences)**,
a soft coral-red that is **not a token**, followed by `#ffc107` (16 occurrences), an amber
that is also not a token and is not `--gold`.

The split is not random. `#e05260` appears in exactly these nine files:

```
routes/tests/+page.svelte
routes/tests/[id]/+page.svelte
routes/tests/result/[attemptId]/+page.svelte
routes/admin/tests/+page.svelte
routes/admin/tests/new/+page.svelte
routes/admin/tests/[id]/+page.svelte
routes/admin/tests/[id]/results/+page.svelte
routes/admin/content/+page.svelte
routes/admin/modules/[id]/+page.svelte
```

In other words: **the original streaming surface uses the harsh Netflix red `#e50914`, and
the entire newer test-series + content-admin surface uses the softer coral `#e05260`.** Two
generations of work, two identities, one app. Same story for gold vs amber.

Deciding which red is *the* red — or replacing both with something that is actually
Champion's — is probably the single highest-leverage call you can make, because it is
currently a one-line token change plus a mechanical find-and-replace.

### 3.2 Almost nothing is responsive

Only **6 of 24 route files** contain a single `@media` query. Including components, there are
**11 media queries in the entire frontend**, and 5 of them are the same `max-width: 768px`.

Files with *any* responsive handling:

```
routes/+layout.svelte                       (the nav)
routes/+page.svelte                         (home)
routes/tests/result/[attemptId]/+page.svelte
routes/admin/tests/+page.svelte
routes/admin/tests/[id]/results/+page.svelte
routes/admin/content/+page.svelte
lib/components/VideoCard.svelte
lib/components/HeroTrailer.svelte
lib/components/ContentRow.svelte
```

Files with **zero** responsive handling include several of the most-used learner screens:

```
routes/my-learning/+page.svelte     0 media queries
routes/leaderboard/+page.svelte     0
routes/settings/+page.svelte        0
routes/admin/employees/+page.svelte 0
```

The nav does degrade on mobile (it hides icons and the profile name below 768px), but it is
still a single horizontal row of 7+ items — it will be cramped. There is no hamburger, no
bottom nav, no drawer.

**We need your call on how much mobile matters.** The original MVP plan assumed
"desktop + tablet — VPN-gated." If that is still true, we should say so and stop pretending;
if learners are expected to watch 5-minute lessons on a phone, then mobile is a first-class
requirement and a lot of §3.2 becomes urgent.

### 3.3 Emoji as the icon system

There is no icon library. Icons are literal emoji characters in markup, including the
primary navigation:

```svelte
<span class="nav-icon">🏠</span> Home
<span class="nav-icon">📚</span> My Learning
<span class="nav-icon">🥾</span> Paths
<span class="nav-icon">🏁</span> Challenges
<span class="nav-icon">📝</span> Tests
<span class="nav-icon">🏆</span> Leaderboard
<span class="nav-icon">⚙️</span> Admin
```

Emoji also carry meaning elsewhere: 🔥 for streak, ⭐ for points, ✓ for complete, 🏆 for badges.

The practical problems: emoji render differently per OS and browser (the app looks materially
different on Windows vs macOS vs Android), they cannot inherit color or be restyled, they are
inconsistent in weight and baseline, they read as informal in a corporate context, and screen
readers announce them literally. A hiking boot for "Paths" is also just not a legible
metaphor.

Recommending a proper icon set — and telling us which one — would be a concrete, immediately
actionable win.

### 3.4 No brand assets at all

- **`frontend/static/` exists and is completely empty.** No logo file, no favicon, no OG
  image, no illustration assets — anywhere in the repo.
- **No custom font.** The entire app is the system stack:
  `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', sans-serif`.
- The "logo" is **CSS text**: the word `CHAMP` in white next to `LMS` in accent red, at
  `font-weight: 900`.

So there is genuinely no visual identity to inherit or respect. This is unusual, and it is
mostly good news for you: **you are not constrained by an existing brand.** If Champion has
brand guidelines, colors, or a typeface we should be honoring, we do not currently have them
and would like them.

### 3.5 Placeholder content shipped as real content

On **My Learning**, the Watch History list renders every row with the literal text
`Episode` — no title, no thumbnail, no module name. Two rows in a row both say "Episode",
distinguished only by a progress bar.

This is worth understanding precisely, because it is **not a CSS bug you can design around.**
The API shape is the constraint. `/progress/me` returns:

```ts
export interface ProgressEntry {
  episode_id: string; watched_seconds: number; total_seconds: number;
  completed?: boolean; last_watched_at?: string;
}
```

There is no title, no thumbnail, no module reference in the payload — so the UI has literally
nothing to display, and hardcodes the word "Episode". Fixing this properly requires a
**backend change** to enrich the endpoint. That is fine and we are happy to do it; we flag it
so you design the row you actually want (thumbnail + module + episode title + time
remaining + resume) and we will make the API match, rather than you constraining the design
to today's thin payload.

The same caution applies generally: **if a screen looks empty, check whether the data exists
before designing around its absence.** Ask us.

### 3.6 Content thumbnails are gradient placeholders

Every video card currently shows a flat CSS gradient with a play triangle. The home page is
therefore a grid of abstract colored rectangles. In a product whose entire premise is
"browsable, binge-worthy, Netflix-like," **thumbnails are the core visual unit and they do
not exist yet.**

Worth deciding: do modules get real uploaded artwork (an admin burden, but rich), auto-
generated video stills (cheap, inconsistent), or a designed systematic treatment —
category-driven color + typographic title cards — that looks deliberate rather than
placeholder? The third option may be the sweet spot for an internal tool and is a great thing
for you to explore.

### 3.7 Rows with one item

On Home, "Continue Watching," "Trending in Finance," and "Trending in Onboarding" each
render a **single card** in a horizontal carousel built for many, complete with prev/next
arrows. The result is one small card and a vast field of empty black.

This is what a Netflix layout does at low content volume, and an internal LMS will *always*
have low content volume compared to Netflix. The carousel pattern may simply be wrong here.
A denser grid, or a layout that adapts when a row has fewer than N items, would likely serve
this content library far better. Designing for the **realistic content volume** — dozens of
modules, not thousands — is a key ask.

### 3.8 Motion exists but ignores accessibility

Motion is almost entirely CSS: **28 CSS `transition:` declarations** across the app (7 of
them the blunt `transition: all`), and only **2 Svelte transition directives** in total
(one `transition:fade`, one `transition:scale`). There is **zero**
`prefers-reduced-motion` handling anywhere.

So there is no motion *system* to speak of — just per-component hover tweens. That is
actually an opportunity: any motion language you propose would be additive rather than a
retrofit. Please specify its reduced-motion behavior.

### 3.9 Accessibility is thin

Across all routes and components there are **18 total** `aria-*` or `alt=` attributes. Focus
styling is actually handled globally and reasonably (`:focus-visible` with a 2px accent
outline), which is a good foundation — but labeling, alt text, and the emoji-as-meaning
problem in §3.3 all need attention. Note also that `--muted: #888899` on `--bg: #0a0a0f` is
the color used for a lot of secondary text; please sanity-check contrast as you go.

### 3.10 Credit where due

To be fair to the existing code, several things are done thoughtfully and should be
**preserved**, not swept away:

- Dialogs are **custom modals, not native `confirm()`** — there is exactly one `alert()` in
  the whole app (`admin/zoom`). A code comment explicitly explains they avoided native
  confirms because they block the page.
- The token architecture in `app.css` is sound (surfaces, borders, radii, shadows, states) —
  it is *under-used*, not badly designed.
- `:focus-visible` is handled globally.
- The must-change-password banner is deliberately a **nudge, not a lockout**, with a comment
  explaining that learners should still reach their learning first. That is good product
  instinct worth carrying forward.
- Empty and loading states **do exist** in places (My Learning has a real empty state with a
  CTA). They are inconsistent, not absent.

---

## 4. Technical constraints you should design within

You do not need to write code, but these shape what is cheap versus expensive.

| Thing | Reality |
|---|---|
| Framework | SvelteKit 2 + Svelte 4, TypeScript, Vite |
| Styling | Plain CSS in `<style>` blocks, scoped per component. **No Tailwind, no CSS-in-JS.** |
| Tokens | CSS custom properties in `src/app.css` |
| Components | ~14 hand-rolled components in `lib/components/`. **No component library.** |
| Icons | Emoji (see §3.3) |
| Video | Bunny Stream HLS via `hls.js`, custom player |
| Theme | **Dark only.** No light mode, no theme switching. |
| Deploy | Node adapter, single container on Railway |

Implications:

- **Adding a component library is a real decision, not a freebie.** Svelte 4 narrows the
  options. If you want one, tell us and we will evaluate; otherwise assume we hand-build to
  your spec.
- **A token-level change is cheap. A per-screen restyle is expensive.** Anything you can
  express as tokens, shared classes, or a component contract will land across 24 routes
  almost for free. That is the highest-leverage form for your output to take.
- **Dark-only is the current assumption, not a decision anyone defended.** If you think this
  product should have a light mode — plausible for a corporate tool used in bright offices,
  and for reading dense admin tables — say so early, because retrofitting it later across 25
  hand-styled routes is genuinely painful.

---

## 5. Screen inventory

Learner:

| Route | Purpose |
|---|---|
| `/` | Home — hero trailer + category rows |
| `/my-learning` | Stats, required modules, watch history |
| `/paths` | Learning paths, gated node progression |
| `/challenges` | Team challenges |
| `/tests` | Test series list |
| `/tests/[id]` | Take a test |
| `/tests/result/[attemptId]` | Score + AI coaching feedback |
| `/leaderboard` | Ranking, badges, department filter |
| `/module/[id]` | Module detail + episode list |
| `/watch/[id]` | Video player + quiz modal |
| `/settings` | Profile, avatar |
| `/auth/login`, `/auth/change-password` | Auth |

Admin:

| Route | Purpose |
|---|---|
| `/admin` | Dashboard |
| `/admin/content` | Content management, deletion |
| `/admin/content-access` | Team/person content targeting |
| `/admin/employees` | Employee CRUD + **bulk spreadsheet upload** |
| `/admin/upload` | Video upload (TUS resumable) |
| `/admin/modules/[id]` | Module + episode editing |
| `/admin/tests`, `/tests/new`, `/tests/[id]` | Test series build (PDF/DOCX ingest) |
| `/admin/tests/[id]/results` | Results + AI coaching |
| `/admin/zoom` | Zoom session import |

Components: `HeroTrailer`, `ContentRow`, `VideoCard`, `VideoPlayer`, `QuizModal`,
`RewardModal`, `LevelBadge`, `Avatar`, `QuestList`, `SkillTrail`, `UpskillingTrack`,
`ShareAchievement`.

### Screenshots

`champ-home.png`, `champ-mylearning.png`, `champ-leaderboard.png`, and `champ-landing.png`
are committed at the repo root.

⚠️ **These are stale** — they predate the current branch. They show a 3-item nav, whereas the
app now has 7+ nav items plus avatars, level badges, and a password banner. Treat them as
evidence of *visual language*, not of current information architecture. Ask us for fresh
captures of any screen you want to see as it stands today; that is a two-minute job.

---

## 6. Where we would most value your thinking

Roughly in order of leverage.

1. **Visual identity.** One red, one gold, a typeface, a logo, a favicon. Resolve §3.4 and
   the `#e50914` vs `#e05260` split in §3.1. Cheap for us to apply, transforms everything.
2. **A small design system.** Tokens, type scale, spacing scale, and specs for the ~10
   components that actually recur: card, row/list item, stat tile, table, modal, form field,
   button set, badge/pill, progress indicator, empty state. This is the thing that makes the
   *next* twenty screens consistent without you drawing them.
3. **Learner vs admin shell.** §2. Does admin get its own denser environment?
4. **Home at realistic content volume.** §3.7. What replaces one-card carousels?
5. **Content thumbnails.** §3.6. What is the systematic treatment?
6. **Icon system.** §3.3. Which set, and what do Paths / Challenges / Tests actually look like?
7. **Mobile posture.** §3.2. Is this desktop-first with graceful degradation, or genuinely
   responsive? A clear answer unblocks a lot.
8. **Making required-vs-voluntary legible.** §1. Assigned work and browsable content
   currently look identical.
9. **Gamification tone.** XP, levels, badges, quests, streaks, and reward modals all exist.
   The visual language for celebration is currently emoji and accent-red. How loud should
   this be for adult professionals? Genuinely open.
10. **Empty, loading, and error states as a system.** They exist inconsistently (§3.10);
    make them deliberate.

---

## 7. Open questions for you

1. **How literal should "Netflix" be?** Is that a pacing metaphor, or a styling mandate? Our
   read is the former (§1), but this is your call and it changes everything downstream.
2. **Dark-only, or add light?** (§4) Cheap now, painful later.
3. **Does mobile matter?** (§3.2)
4. **Component library, or hand-build to spec?** (§4)
5. **Does Champion have existing brand guidelines** — colors, typeface, logo — that we should
   be honoring? We could not find any in the repo.
6. **How much should this feel like "work"?** It is assigned corporate training wearing an
   entertainment costume. That tension is unresolved, and resolving it is a design decision
   more than an engineering one.

---

## 8. Practical notes

- **The design tokens are the fastest lever.** `frontend/src/app.css`. Changing values there
  propagates instantly; the blocker is the hardcoded colors in §3.1, which we will sweep once
  you have picked the palette.
- **Do not design around missing data without asking** (§3.5). Several screens look sparse
  because of API payload shape, not because the data does not exist. Backend changes to
  enrich endpoints are expected and welcome.
- **Deliverables in any form are fine** — Figma, annotated screenshots, a written direction,
  or scrappy sketches. Direction and rationale are more useful to us right now than polish.
- **Prioritize.** If you only have time for one thing, do §6.1 and §6.2 — identity plus a
  small system. Those two make everything after them cheaper.

---

*Prepared by engineering from the `employee-profiles-and-bulk-upload` branch. Every count,
color, and file path above was verified against the code at the time of writing; if something
does not match what you see, the code has moved — ask and we will re-check.*
