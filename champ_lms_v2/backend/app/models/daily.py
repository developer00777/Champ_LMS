"""
Daily engagement: an auto-rotating challenge pool and directed peer kudos.

Ported from ChampQuest (Express/Postgres) to this stack, keeping the mechanics
that made them work there and dropping its schema:

  * DailyChallenge / DailyChallengeCompletion — admins author a pool once, and a
    deterministic day-of-year rotation picks the same few for everyone each day.
    No cron job, no per-user generation: the rotation is a pure function of the
    date, so today's set is identical for every learner and reproducible after
    the fact.

  * Kudos — directed recognition from one person to another. This is distinct
    from a SocialPost with post_type="shoutout", which is an undirected feed
    post with no recipient: kudos has a `to_user_id`, awards XP to both parties,
    and weights a leader's recognition higher.

Streaks are deliberately NOT modelled here — User.streak_days and
GamificationService.record_activity already own that, and a second streak system
would drift from the first.
"""
import uuid
from datetime import datetime, timezone
from beanie import Document
from pydantic import Field
from pymongo import IndexModel, ASCENDING, DESCENDING


# How many challenges from the pool are live on any given day. Small on purpose:
# three feels achievable, and a wall of ten reads as a backlog rather than a
# nudge.
DAILY_CHALLENGE_COUNT = 3

# What a challenge asks for. The first three are verified from real progress the
# platform already records; "self_report" is the honour-system escape hatch for
# things the LMS cannot see (ran a huddle, called a customer).
CHALLENGE_KIND_WATCH = "watch_episode"
CHALLENGE_KIND_QUIZ = "pass_quiz"
CHALLENGE_KIND_TEST = "pass_test"
CHALLENGE_KIND_SELF = "self_report"
CHALLENGE_KINDS = (
    CHALLENGE_KIND_WATCH,
    CHALLENGE_KIND_QUIZ,
    CHALLENGE_KIND_TEST,
    CHALLENGE_KIND_SELF,
)

# Kinds the platform can confirm on its own. Anything else is self-attested and
# is labelled as such wherever it is shown, so a self-reported completion is
# never mistaken for a verified one.
AUTO_VERIFIED_KINDS = (
    CHALLENGE_KIND_WATCH,
    CHALLENGE_KIND_QUIZ,
    CHALLENGE_KIND_TEST,
)


class DailyChallenge(Document):
    """
    One challenge in the rotating pool.

    Not a Quest: a Quest tracks incremental progress toward a target for a period
    (watch 2 of 3 episodes) and is seeded in code. A DailyChallenge is authored by
    an admin, is either done today or not, and only exists on the days the
    rotation selects it.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str | None = None
    kind: str = CHALLENGE_KIND_SELF
    reward_xp: int = 20
    reward_points: int = 20

    # None = everyone. Set to scope a challenge to one department, matching how
    # TestSeries.department already gates content.
    department: str | None = None

    # Out of the pool without losing its completion history. Deactivating is
    # always preferred to deleting for that reason.
    active: bool = True

    # * Pins a challenge into every day's set regardless of the rotation. For a
    # * company push that should not wait for its turn to come round.
    always_on: bool = False

    created_by: str | None = None  # users.id
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def auto_verified(self) -> bool:
        return self.kind in AUTO_VERIFIED_KINDS

    class Settings:
        name = "daily_challenges"
        indexes = [
            IndexModel([("active", ASCENDING), ("department", ASCENDING)]),
            # The rotation walks the pool in a stable order; without a
            # deterministic sort the "same three for everyone" guarantee breaks.
            IndexModel([("created_at", ASCENDING)]),
        ]


class DailyChallengeCompletion(Document):
    """
    One learner finishing one challenge on one day.

    period_key (YYYY-MM-DD) is part of a unique index rather than being derived
    from a timestamp at query time: it makes "already done today" a single
    indexed lookup and makes double-claiming a write conflict instead of a race
    two concurrent requests can both win.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    challenge_id: str
    user_id: str
    period_key: str  # YYYY-MM-DD, UTC

    # Snapshot of what was paid out. Kept on the row so a later change to the
    # challenge's reward doesn't rewrite history.
    awarded_xp: int = 0
    awarded_points: int = 0

    # False when the learner attested to it themselves rather than the platform
    # confirming it from real progress.
    verified: bool = False
    # What proved it, for auto-verified kinds: "watch_progress", "test_attempt".
    verified_by: str | None = None

    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "daily_challenge_completions"
        indexes = [
            IndexModel(
                [("challenge_id", ASCENDING), ("user_id", ASCENDING),
                 ("period_key", ASCENDING)],
                unique=True,
            ),
            IndexModel([("user_id", ASCENDING), ("period_key", DESCENDING)]),
        ]


class Kudos(Document):
    """
    Directed peer recognition: one person thanking another, by name.

    Both parties gain: the receiver is the point of the feature, and the giver is
    rewarded a smaller amount so that noticing good work is itself a habit worth
    forming. A leader's kudos carries a multiplier, which is ChampQuest's rule —
    recognition from a manager lands harder, so it is worth more.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_user_id: str
    to_user_id: str
    message: str
    emoji: str = "🎉"

    # 2 when the sender is an admin/ld_lead at the time of sending, else 1.
    # Stored rather than recomputed: someone's role changes, but what their
    # kudos was worth on the day it was given should not.
    xp_multiplier: int = 1
    awarded_xp_to_receiver: int = 0
    awarded_xp_to_giver: int = 0

    # Denormalised so the wall renders without an N+1 lookup per row, and still
    # reads correctly after someone leaves and their user record is deactivated.
    from_name: str | None = None
    to_name: str | None = None
    department: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "kudos"
        indexes = [
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("to_user_id", ASCENDING), ("created_at", DESCENDING)]),
            IndexModel([("from_user_id", ASCENDING), ("created_at", DESCENDING)]),
        ]
