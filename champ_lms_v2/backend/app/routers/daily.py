"""
Daily engagement router: the rotating challenge pool and peer kudos.

Ported from ChampQuest's challenges.js and its kudos endpoints, adapted to this
codebase's auth, gamification service and Mongo models. The mechanics kept:
deterministic daily rotation, once-per-day completion, XP to both sides of a
kudos, and a leader's recognition counting double.
"""
from datetime import datetime, timezone
from typing import Annotated

import redis.asyncio as aioredis
from beanie.operators import In, Set
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.core.auth import get_current_user, require_admin
from app.core.redis import get_redis
from app.models.daily import (
    CHALLENGE_KINDS,
    CHALLENGE_KIND_SELF,
    DailyChallenge,
    DailyChallengeCompletion,
    Kudos,
)
from app.models.social import Notification
from app.models.user import User
from app.services import daily_service
from app.services.bunny_storage import bunny_storage
from app.services.gamification_service import GamificationService

router = APIRouter(tags=["daily"])

# XP the receiver of a kudos gains, before the sender's multiplier.
KUDOS_XP_RECEIVER = 15
# XP the sender gains. Deliberately smaller than the receiver's: recognising
# good work should be rewarded, but not enough to make farming kudos worthwhile.
KUDOS_XP_GIVER = 5
# Per-day cap on how many kudos one person can send. Without it, the cheapest
# way to the top of the leaderboard is to spam praise.
KUDOS_DAILY_LIMIT = 5
MAX_KUDOS_MESSAGE = 280


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class ChallengeIn(BaseModel):
    title: str
    description: str | None = None
    kind: str = CHALLENGE_KIND_SELF
    reward_xp: int = Field(default=20, ge=0, le=500)
    reward_points: int = Field(default=20, ge=0, le=500)
    department: str | None = None
    always_on: bool = False


class ChallengeUpdateIn(BaseModel):
    title: str | None = None
    description: str | None = None
    kind: str | None = None
    reward_xp: int | None = Field(default=None, ge=0, le=500)
    reward_points: int | None = Field(default=None, ge=0, le=500)
    department: str | None = None
    always_on: bool | None = None
    active: bool | None = None


class KudosIn(BaseModel):
    to_user_id: str
    message: str
    emoji: str | None = None


# --------------------------------------------------------------------------
# Learner — daily challenges
# --------------------------------------------------------------------------
@router.get("/daily/challenges")
async def my_daily_challenges(user: Annotated[User, Depends(get_current_user)]):
    """
    Today's rotated challenges for this learner, with completion state.

    Auto-verified challenges report `claimable` only when the underlying work is
    genuinely done, so the client never has to decide that for itself.
    """
    pool = await daily_service.todays_pool(user.department)
    done = await daily_service.completions_for(user.id)

    items = []
    for c in pool:
        if c.auto_verified:
            satisfied, _ = await daily_service.verify_from_progress(user.id, c.kind)
        else:
            satisfied = True  # self-report: claimable whenever they say so
        items.append(daily_service.challenge_view(c, done.get(c.id), satisfied))

    completed = sum(1 for i in items if i["completed_today"])
    return {
        "period_key": daily_service.period_key(),
        "total": len(items),
        "completed": completed,
        "challenges": items,
    }


@router.post("/daily/challenges/{challenge_id}/complete")
async def complete_challenge(
    challenge_id: str,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    """
    Claim a challenge for today.

    Three gates, in order: the challenge must actually be in today's rotation
    (otherwise someone with an old id could farm a retired challenge), an
    auto-verified challenge must be backed by real progress, and the unique index
    on (challenge, user, day) settles any race two concurrent clicks create.
    """
    challenge = await DailyChallenge.get(challenge_id)
    if not challenge or not challenge.active:
        raise HTTPException(status_code=404, detail="Challenge not found")

    if challenge.department and user.department != challenge.department:
        raise HTTPException(
            status_code=403, detail="This challenge is not available to you"
        )

    todays = await daily_service.todays_pool(user.department)
    if not any(c.id == challenge_id for c in todays):
        raise HTTPException(
            status_code=409,
            detail="That challenge is not part of today's set.",
        )

    verified = False
    verified_by = None
    if challenge.auto_verified:
        satisfied, evidence = await daily_service.verify_from_progress(
            user.id, challenge.kind
        )
        if not satisfied:
            raise HTTPException(
                status_code=409,
                detail="You haven't completed the activity for this challenge yet today.",
            )
        verified, verified_by = True, evidence

    completion = DailyChallengeCompletion(
        challenge_id=challenge.id,
        user_id=user.id,
        period_key=daily_service.period_key(),
        awarded_xp=challenge.reward_xp,
        awarded_points=challenge.reward_points,
        verified=verified,
        verified_by=verified_by,
    )
    try:
        await completion.insert()
    except DuplicateKeyError:
        # The unique index did its job: they already claimed this today.
        raise HTTPException(
            status_code=409, detail="You've already completed this challenge today."
        )

    # Reward after the completion row is safely written, so a failure in the
    # gamification layer cannot pay out twice on a retry.
    gamification = GamificationService(redis)
    points = await gamification.award_points_amount(
        user.id, challenge.reward_points, user.department or ""
    )
    xp_info = await gamification.award_xp_amount(
        user.id, "daily_challenge", challenge.reward_xp,
        ref_type="daily_challenge", ref_id=challenge.id,
    )
    # Completing a challenge is learning activity, so it should keep a streak
    # alive exactly like watching an episode does.
    streak = await gamification.record_activity(user.id)

    return {
        "completed": True,
        "challenge_id": challenge.id,
        "verified": verified,
        "awarded_xp": challenge.reward_xp,
        "awarded_points": challenge.reward_points,
        "points": points,
        "xp": xp_info,
        "streak_days": streak,
    }


# --------------------------------------------------------------------------
# Learner — streak
# --------------------------------------------------------------------------
@router.get("/daily/streak")
async def my_streak_detail(
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    """
    Streak detail for the widget: current run, personal best, freezes left, and
    whether today already counts.

    `active_today` is what lets the UI say "keep it going" instead of implying
    the learner still owes something they have already done.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    last_activity = await redis.get(f"last_activity:{user.id}")
    cached = await redis.get(f"streak:{user.id}")
    streak = int(cached) if cached is not None else user.streak_days

    return {
        "streak_days": streak,
        "longest_streak": max(user.longest_streak or 0, streak),
        "streak_freezes": user.streak_freezes,
        "last_activity_date": last_activity,
        "active_today": last_activity == today,
    }


# --------------------------------------------------------------------------
# Learner — kudos
# --------------------------------------------------------------------------
@router.get("/daily/kudos")
async def kudos_wall(
    user: Annotated[User, Depends(get_current_user)],
    limit: int = 30,
    mine: bool = False,
):
    """
    Recent kudos. `mine=true` narrows to recognition this person received.

    Names are read off the kudos row rather than joined from users, so the wall
    still renders correctly for someone who has since been deactivated.
    """
    limit = max(1, min(limit, 100))
    query = (
        Kudos.find(Kudos.to_user_id == user.id) if mine else Kudos.find_all()
    )
    rows = await query.sort(-Kudos.created_at).limit(limit).to_list()

    # One lookup for the avatars, rather than one per row.
    user_ids = list({r.from_user_id for r in rows} | {r.to_user_id for r in rows})
    users = {
        u.id: u for u in await User.find(In(User.id, user_ids)).to_list()
    } if user_ids else {}

    def avatar(uid: str) -> str | None:
        u = users.get(uid)
        return bunny_storage.avatar_url(u.avatar_bunny_path) if u else None

    return [
        {
            "id": r.id,
            "from_user_id": r.from_user_id,
            "to_user_id": r.to_user_id,
            "from_name": r.from_name or (users.get(r.from_user_id).full_name if users.get(r.from_user_id) else None),
            "to_name": r.to_name or (users.get(r.to_user_id).full_name if users.get(r.to_user_id) else None),
            "from_avatar_url": avatar(r.from_user_id),
            "to_avatar_url": avatar(r.to_user_id),
            "message": r.message,
            "emoji": r.emoji,
            "xp_multiplier": r.xp_multiplier,
            "department": r.department,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/daily/kudos", status_code=201)
async def send_kudos(
    body: KudosIn,
    user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
):
    """
    Recognise a colleague.

    Both sides gain XP, weighted x2 when a leader is the sender. A daily send
    limit keeps recognition meaningful rather than a leaderboard exploit.
    """
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Write a short message")
    if len(message) > MAX_KUDOS_MESSAGE:
        raise HTTPException(
            status_code=422,
            detail=f"Keep it under {MAX_KUDOS_MESSAGE} characters",
        )
    if body.to_user_id == user.id:
        raise HTTPException(status_code=422, detail="You can't send kudos to yourself")

    recipient = await User.get(body.to_user_id)
    if not recipient or not recipient.is_active:
        raise HTTPException(status_code=404, detail="That person wasn't found")

    # Daily cap, counted from the durable record rather than a Redis key, so a
    # cache flush doesn't hand out a fresh allowance.
    since = datetime.combine(
        datetime.now(timezone.utc).date(), datetime.min.time(), tzinfo=timezone.utc
    )
    sent_today = await Kudos.find(
        Kudos.from_user_id == user.id, Kudos.created_at >= since
    ).count()
    if sent_today >= KUDOS_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"You've sent your {KUDOS_DAILY_LIMIT} kudos for today. More tomorrow.",
        )

    multiplier = 2 if user.role in ("admin", "ld_lead") else 1
    receiver_xp = KUDOS_XP_RECEIVER * multiplier

    kudos = Kudos(
        from_user_id=user.id,
        to_user_id=recipient.id,
        message=message,
        emoji=(body.emoji or "🎉")[:8],
        xp_multiplier=multiplier,
        awarded_xp_to_receiver=receiver_xp,
        awarded_xp_to_giver=KUDOS_XP_GIVER,
        from_name=user.full_name or user.email,
        to_name=recipient.full_name or recipient.email,
        department=recipient.department,
    )
    await kudos.insert()

    gamification = GamificationService(redis)
    await gamification.award_xp_amount(
        recipient.id, "kudos_received", receiver_xp, ref_type="kudos", ref_id=kudos.id
    )
    await gamification.award_points_amount(
        recipient.id, receiver_xp, recipient.department or ""
    )
    await gamification.award_xp_amount(
        user.id, "kudos_given", KUDOS_XP_GIVER, ref_type="kudos_given", ref_id=kudos.id
    )

    await Notification(
        user_id=recipient.id,
        notif_type="shoutout",
        title=f"{kudos.emoji} {kudos.from_name} recognised your work",
        body=message,
        ref_type="kudos",
        ref_id=kudos.id,
    ).insert()

    return {
        "id": kudos.id,
        "to_name": kudos.to_name,
        "message": kudos.message,
        "emoji": kudos.emoji,
        "xp_multiplier": multiplier,
        "awarded_xp_to_receiver": receiver_xp,
        "awarded_xp_to_giver": KUDOS_XP_GIVER,
        "kudos_left_today": max(0, KUDOS_DAILY_LIMIT - sent_today - 1),
    }


@router.get("/daily/kudos/recipients")
async def kudos_recipients(user: Annotated[User, Depends(get_current_user)]):
    """
    Who this person can recognise: active colleagues, themselves excluded.

    Scoped to their own department when they have one, since that is who a
    learner actually works with and an all-company picker is unusable at scale.
    """
    query = {"is_active": True}
    if user.department:
        query["department"] = user.department
    people = await User.find(query).sort(+User.full_name).limit(300).to_list()
    return [
        {
            "id": p.id,
            "full_name": p.full_name or p.email,
            "employee_code": p.employee_code,
            "department": p.department,
            "avatar_url": bunny_storage.avatar_url(p.avatar_bunny_path),
        }
        for p in people if p.id != user.id
    ]


# --------------------------------------------------------------------------
# Admin — challenge pool
# --------------------------------------------------------------------------
@router.get("/admin/daily/challenges")
async def list_challenges_admin(admin: Annotated[User, Depends(require_admin)]):
    """The whole pool, plus a preview of which are live today."""
    pool = await DailyChallenge.find_all().sort(+DailyChallenge.created_at).to_list()
    live_ids = {c.id for c in daily_service.rotate([c for c in pool if c.active])}

    completions: dict[str, int] = {}
    for c in pool:
        completions[c.id] = await DailyChallengeCompletion.find(
            DailyChallengeCompletion.challenge_id == c.id
        ).count()

    return {
        "daily_count": daily_service.DAILY_CHALLENGE_COUNT,
        "active_count": sum(1 for c in pool if c.active),
        "challenges": [
            {
                "id": c.id,
                "title": c.title,
                "description": c.description,
                "kind": c.kind,
                "reward_xp": c.reward_xp,
                "reward_points": c.reward_points,
                "department": c.department,
                "active": c.active,
                "always_on": c.always_on,
                "auto_verified": c.auto_verified,
                "live_today": c.id in live_ids,
                "completion_count": completions.get(c.id, 0),
                "created_at": c.created_at,
            }
            for c in pool
        ],
    }


@router.post("/admin/daily/challenges", status_code=201)
async def create_challenge(
    body: ChallengeIn, admin: Annotated[User, Depends(require_admin)]
):
    if body.kind not in CHALLENGE_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"kind must be one of {', '.join(CHALLENGE_KINDS)}",
        )
    if not body.title.strip():
        raise HTTPException(status_code=422, detail="Title required")

    challenge = DailyChallenge(
        title=body.title.strip(),
        description=(body.description or "").strip() or None,
        kind=body.kind,
        reward_xp=body.reward_xp,
        reward_points=body.reward_points,
        department=(body.department or "").strip() or None,
        always_on=body.always_on,
        created_by=admin.id,
    )
    await challenge.insert()
    return {"id": challenge.id, "title": challenge.title, "active": challenge.active}


@router.patch("/admin/daily/challenges/{challenge_id}")
async def update_challenge(
    challenge_id: str,
    body: ChallengeUpdateIn,
    admin: Annotated[User, Depends(require_admin)],
):
    challenge = await DailyChallenge.get(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    data = body.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"] not in CHALLENGE_KINDS:
        raise HTTPException(status_code=422, detail="Invalid kind")

    for field, value in data.items():
        setattr(challenge, field, value)
    challenge.updated_at = datetime.now(timezone.utc)
    await challenge.save()
    return {"id": challenge.id, "updated": True}


@router.delete("/admin/daily/challenges/{challenge_id}")
async def delete_challenge(
    challenge_id: str, admin: Annotated[User, Depends(require_admin)]
):
    """
    Remove a challenge from the pool.

    Deactivates rather than deletes once anyone has completed it: dropping the
    document would orphan those completion rows and silently rewrite people's
    history. A never-completed challenge is safe to delete outright.
    """
    challenge = await DailyChallenge.get(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    used = await DailyChallengeCompletion.find(
        DailyChallengeCompletion.challenge_id == challenge_id
    ).count()
    if used:
        await challenge.update(Set({DailyChallenge.active: False}))
        return {"deleted": False, "deactivated": True, "completions": used}

    await challenge.delete()
    return {"deleted": True, "deactivated": False, "completions": 0}
