"""
Daily challenge rotation and auto-verification.

The rotation is a pure function of the date and the pool, which is the whole
trick ported from ChampQuest: no scheduler, no nightly job, no per-user
generation. Today's set can be computed on any machine, at any time, and asked
for retrospectively — "what was live last Tuesday" is answerable without having
stored it.
"""
from datetime import date, datetime, timezone

from app.models.daily import (
    AUTO_VERIFIED_KINDS,
    CHALLENGE_KIND_QUIZ,
    CHALLENGE_KIND_SELF,
    CHALLENGE_KIND_TEST,
    CHALLENGE_KIND_WATCH,
    DAILY_CHALLENGE_COUNT,
    DailyChallenge,
    DailyChallengeCompletion,
)


def period_key(when: date | None = None) -> str:
    """
    The day a completion belongs to, as YYYY-MM-DD in UTC.

    UTC rather than local time so a distributed team all rolls over together;
    the alternative is someone in one timezone getting two shots at a challenge
    the person beside them gets one of.
    """
    return (when or datetime.now(timezone.utc).date()).isoformat()


def day_index(when: date | None = None) -> int:
    """
    Ordinal day used to seed the rotation.

    `toordinal` (days since year 1) rather than day-of-year, because day-of-year
    resets to 1 each January and would replay the same challenges in the same
    order every year — and, worse, jump discontinuously across New Year on a leap
    year. A monotonic count just keeps walking.
    """
    return (when or datetime.now(timezone.utc).date()).toordinal()


def rotate(pool: list[DailyChallenge], when: date | None = None,
           count: int = DAILY_CHALLENGE_COUNT) -> list[DailyChallenge]:
    """
    Pick today's challenges from the pool.

    Walks a window of `count` consecutive items, starting at an offset derived
    from the date, wrapping around the end. Two consequences worth knowing:
    the window advances by one per day, so a challenge stays around for a few
    days and then leaves; and every challenge in the pool is guaranteed a turn,
    which random selection cannot promise.

    `always_on` challenges are prepended and excluded from the rotation, so
    pinning one does not silently eat a rotating slot.
    """
    pinned = [c for c in pool if c.always_on]
    rotating = [c for c in pool if not c.always_on]

    slots = max(0, count - len(pinned))
    if not rotating or slots == 0:
        return pinned[:count] if pinned else []

    # Never show the same challenge twice in one day: with a pool smaller than
    # the window, the modulo would wrap onto itself.
    take = min(slots, len(rotating))
    start = day_index(when) % len(rotating)
    picked = [rotating[(start + i) % len(rotating)] for i in range(take)]
    return pinned + picked


async def todays_pool(department: str | None, when: date | None = None) -> list[DailyChallenge]:
    """
    The active challenges visible to someone in `department`, already rotated.

    Department-scoped challenges are additive: a learner sees the company-wide
    pool plus their own department's, which means two people in different
    departments legitimately see different sets.
    """
    query = DailyChallenge.find(DailyChallenge.active == True)  # noqa: E712
    all_active = await query.sort(+DailyChallenge.created_at).to_list()

    visible = [
        c for c in all_active
        if c.department is None or (department and c.department == department)
    ]
    return rotate(visible, when)


async def completions_for(user_id: str, when: date | None = None
                          ) -> dict[str, DailyChallengeCompletion]:
    """Today's completions for one user, keyed by challenge_id."""
    rows = await DailyChallengeCompletion.find(
        DailyChallengeCompletion.user_id == user_id,
        DailyChallengeCompletion.period_key == period_key(when),
    ).to_list()
    return {r.challenge_id: r for r in rows}


async def verify_from_progress(user_id: str, kind: str, when: date | None = None
                               ) -> tuple[bool, str | None]:
    """
    Check whether a learner has already done, today, what an auto-verified
    challenge asks for.

    Returns (satisfied, evidence). The point is that these challenges cannot be
    claimed by pressing a button: the platform looks at what actually happened.
    Imported lazily to keep this module importable from the models layer without
    dragging the whole progress stack in.
    """
    if kind not in AUTO_VERIFIED_KINDS:
        return False, None

    start = datetime.combine(
        (when or datetime.now(timezone.utc).date()), datetime.min.time(),
        tzinfo=timezone.utc,
    )

    if kind == CHALLENGE_KIND_WATCH:
        from app.models.progress import WatchProgress
        hit = await WatchProgress.find(
            WatchProgress.user_id == user_id,
            WatchProgress.completed == True,  # noqa: E712
            WatchProgress.completed_at >= start,
        ).first_or_none()
        return (hit is not None), "watch_progress" if hit else None

    if kind == CHALLENGE_KIND_QUIZ:
        from app.models.assessment import AssessmentAttempt
        hit = await AssessmentAttempt.find(
            AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.passed == True,  # noqa: E712
            AssessmentAttempt.attempted_at >= start,
        ).first_or_none()
        return (hit is not None), "assessment_attempt" if hit else None

    if kind == CHALLENGE_KIND_TEST:
        from app.models.test_series import TestAttempt
        hit = await TestAttempt.find(
            TestAttempt.user_id == user_id,
            TestAttempt.passed == True,  # noqa: E712
            TestAttempt.submitted_at >= start,
        ).first_or_none()
        return (hit is not None), "test_attempt" if hit else None

    return False, None


def challenge_view(c: DailyChallenge, done: DailyChallengeCompletion | None,
                   claimable: bool) -> dict:
    """
    One challenge as the learner's client sees it.

    `claimable` is computed server-side rather than left to the UI: for an
    auto-verified challenge it means the underlying work is done and the reward
    is waiting, and the client must not be able to decide that for itself.
    """
    return {
        "id": c.id,
        "title": c.title,
        "description": c.description,
        "kind": c.kind,
        "reward_xp": c.reward_xp,
        "reward_points": c.reward_points,
        "auto_verified": c.auto_verified,
        "always_on": c.always_on,
        "department": c.department,
        "completed_today": done is not None,
        "completed_at": done.completed_at if done else None,
        "verified": done.verified if done else False,
        # For an auto-verified challenge: the work is done, press to collect.
        # For a self-report challenge: always true, it is an honour-system claim.
        "claimable": claimable and done is None,
    }

# Starter pool, so the feature is not an empty panel on first run. Seeded by
# title (there is no natural key on a challenge), and only ever inserted — an
# admin who edits or retires a seeded challenge keeps their change, because
# re-syncing it on every boot would silently undo their work.
SEED_CHALLENGES = [
    {"title": "Watch one episode today", "kind": CHALLENGE_KIND_WATCH,
     "description": "Finish any episode from your learning list.",
     "reward_xp": 20, "reward_points": 20},
    {"title": "Pass a quiz", "kind": CHALLENGE_KIND_QUIZ,
     "description": "Pass the quiz on any module you're working through.",
     "reward_xp": 30, "reward_points": 30},
    {"title": "Clear a test series", "kind": CHALLENGE_KIND_TEST,
     "description": "Pass any published test series.",
     "reward_xp": 50, "reward_points": 50},
    {"title": "Teach someone something", "kind": CHALLENGE_KIND_SELF,
     "description": "Share one thing you learned with a colleague.",
     "reward_xp": 15, "reward_points": 15},
    {"title": "Review your weakest topic", "kind": CHALLENGE_KIND_SELF,
     "description": "Revisit the topic your last test flagged as weakest.",
     "reward_xp": 20, "reward_points": 20},
    {"title": "Recognise a teammate", "kind": CHALLENGE_KIND_SELF,
     "description": "Send kudos to someone who helped you this week.",
     "reward_xp": 15, "reward_points": 15},
]


async def seed_daily_challenges() -> None:
    """
    Insert the starter pool if it is missing. Idempotent and non-destructive.

    Deliberately does NOT update existing rows: unlike the badge catalog, these
    are meant to be edited by admins, so treating code as the source of truth
    would fight them every restart.
    """
    for spec in SEED_CHALLENGES:
        existing = await DailyChallenge.find_one(DailyChallenge.title == spec["title"])
        if existing:
            continue
        await DailyChallenge(**spec).insert()
