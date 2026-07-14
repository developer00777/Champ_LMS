from typing import Annotated
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from beanie.operators import In, Inc
from app.core.auth import get_current_user
from app.core.redis import get_redis
from app.models.user import User
from app.models.enrollment import Enrollment
from app.models.team import Team, TeamChallenge, TeamProgress
from app.services.gamification_service import GamificationService
import redis.asyncio as aioredis

router = APIRouter(prefix="/challenges", tags=["challenges"])


SEED_CHALLENGES = [
    {"key": "sales_onboarding_sprint", "title": "Sales Onboarding Sprint", "description": "First team to all finish the Sales onboarding path wins!", "challenge_type": "onboarding_sprint", "department": "sales", "team_size": 4, "criteria": {"type": "team_complete_modules", "count": 2}, "reward_xp": 100, "reward_points": 50},
    {"key": "eng_mastery_climb", "title": "Engineering Mastery Climb", "description": "Which eng team summits the ridge first?", "challenge_type": "dept_race", "department": "engineering", "team_size": 3, "criteria": {"type": "team_complete_modules", "count": 2}, "reward_xp": 120, "reward_points": 60},
    {"key": "leadership_summit_race", "title": "Leadership Summit Race", "description": "Coaches race to the summit together.", "challenge_type": "dept_race", "department": "leadership", "team_size": 4, "criteria": {"type": "team_complete_modules", "count": 1}, "reward_xp": 80, "reward_points": 40},
    {"key": "product_discovery_sprint", "title": "Product Discovery Sprint", "description": "PMs team up to master customer discovery + roadmap.", "challenge_type": "dept_race", "department": "product", "team_size": 3, "criteria": {"type": "team_complete_modules", "count": 2}, "reward_xp": 90, "reward_points": 45},
    {"key": "ops_resilience_challenge", "title": "Ops Resilience Challenge", "description": "Ops teams race to complete incident response runbooks.", "challenge_type": "dept_race", "department": "ops", "team_size": 4, "criteria": {"type": "team_complete_modules", "count": 2}, "reward_xp": 90, "reward_points": 45},
    {"key": "onboarding_101_sprint", "title": "Company 101 Onboarding Sprint", "description": "New hires team up to finish onboarding together.", "challenge_type": "onboarding_sprint", "department": "onboarding", "team_size": 5, "criteria": {"type": "team_complete_modules", "count": 1}, "reward_xp": 70, "reward_points": 35},
]


async def seed_challenges() -> None:
    """Idempotent upsert of challenge catalog. Called on startup."""
    for spec in SEED_CHALLENGES:
        existing = await TeamChallenge.find_one(TeamChallenge.key == spec["key"])
        if existing:
            for k, v in spec.items():
                if getattr(existing, k, None) != v:
                    setattr(existing, k, v)
            await existing.save()
            continue
        await TeamChallenge(**spec).insert()


@router.get("")
async def list_challenges(
    user: Annotated[User, Depends(get_current_user)],
    department: str | None = None,
):
    filters = [TeamChallenge.active == True]  # noqa: E712
    if department:
        filters.append(TeamChallenge.department == department)
    challenges = await TeamChallenge.find(*filters).to_list()

    result = []
    for c in challenges:
        teams = await Team.find(Team.challenge_id == c.id).to_list()
        my_team = next((t for t in teams if user.id in t.member_ids), None)
        result.append({
            "id": c.id,
            "key": c.key,
            "title": c.title,
            "description": c.description,
            "challenge_type": c.challenge_type,
            "department": c.department,
            "team_size": c.team_size,
            "criteria": c.criteria,
            "reward_xp": c.reward_xp,
            "reward_points": c.reward_points,
            "start_at": c.start_at.isoformat(),
            "end_at": c.end_at.isoformat() if c.end_at else None,
            "total_teams": len(teams),
            "my_team_id": my_team.id if my_team else None,
        })
    return result


@router.get("/{challenge_id}")
async def get_challenge(
    challenge_id: str,
    user: Annotated[User, Depends(get_current_user)],
):
    challenge = await TeamChallenge.get(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    teams = await Team.find(Team.challenge_id == challenge_id).to_list()
    team_ids = [t.id for t in teams]
    progress_records = {
        p.team_id: p
        for p in await TeamProgress.find(In(TeamProgress.challenge_id, [challenge_id])).to_list()
    } if team_ids else {}

    # Hydrate team members
    all_member_ids = [mid for t in teams for mid in t.member_ids]
    members = {u.id: u for u in await User.find(In(User.id, all_member_ids)).to_list()} if all_member_ids else {}

    teams_out = []
    for t in teams:
        p = progress_records.get(t.id)
        team_members = [
            {"id": members[mid].id, "name": members[mid].full_name, "department": members[mid].department}
            for mid in t.member_ids if mid in members
        ]
        teams_out.append({
            "id": t.id,
            "name": t.name,
            "department": t.department,
            "captain_id": t.captain_id,
            "member_count": len(t.member_ids),
            "members": team_members,
            "progress": p.progress if p else 0,
            "target": p.target if p else challenge.criteria.get("count", 1),
            "completed": p.completed if p else False,
            "completed_at": p.completed_at.isoformat() if p and p.completed_at else None,
        })

    return {
        "id": challenge.id,
        "key": challenge.key,
        "title": challenge.title,
        "description": challenge.description,
        "challenge_type": challenge.challenge_type,
        "department": challenge.department,
        "team_size": challenge.team_size,
        "criteria": challenge.criteria,
        "reward_xp": challenge.reward_xp,
        "reward_points": challenge.reward_points,
        "teams": teams_out,
    }


class CreateTeamBody(BaseModel):
    name: str


@router.post("/{challenge_id}/teams", status_code=201)
async def create_team(
    challenge_id: str,
    body: CreateTeamBody,
    user: Annotated[User, Depends(get_current_user)],
):
    challenge = await TeamChallenge.get(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    # Check if user already in a team for this challenge
    existing_teams = await Team.find(Team.challenge_id == challenge_id).to_list()
    for t in existing_teams:
        if user.id in t.member_ids:
            raise HTTPException(status_code=400, detail="Already in a team for this challenge")

    team = Team(
        name=body.name,
        department=user.department,
        member_ids=[user.id],
        captain_id=user.id,
        challenge_id=challenge_id,
    )
    await team.insert()

    # Create progress record
    target = challenge.criteria.get("count", 1)
    await TeamProgress(
        challenge_id=challenge_id,
        team_id=team.id,
        progress=0,
        target=target,
    ).insert()

    return {"id": team.id, "name": team.name, "challenge_id": challenge_id}


class JoinTeamBody(BaseModel):
    team_id: str


@router.post("/{challenge_id}/join")
async def join_team(
    challenge_id: str,
    body: JoinTeamBody,
    user: Annotated[User, Depends(get_current_user)],
):
    challenge = await TeamChallenge.get(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")

    # Check if already in a team
    existing_teams = await Team.find(Team.challenge_id == challenge_id).to_list()
    for t in existing_teams:
        if user.id in t.member_ids:
            raise HTTPException(status_code=400, detail="Already in a team for this challenge")

    team = await Team.get(body.team_id)
    if not team or team.challenge_id != challenge_id:
        raise HTTPException(status_code=404, detail="Team not found")
    if len(team.member_ids) >= challenge.team_size:
        raise HTTPException(status_code=400, detail="Team is full")

    team.member_ids.append(user.id)
    await team.save()
    return {"joined": True, "team_id": team.id}


@router.get("/{challenge_id}/leaderboard")
async def challenge_leaderboard(
    challenge_id: str,
    user: Annotated[User, Depends(get_current_user)],
):
    challenge = await TeamChallenge.get(challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    progress_records = await TeamProgress.find(
        TeamProgress.challenge_id == challenge_id
    ).sort(-TeamProgress.progress).to_list()
    team_ids = [p.team_id for p in progress_records]
    teams = {t.id: t for t in await Team.find(In(Team.id, team_ids)).to_list()} if team_ids else {}

    result = []
    for rank, p in enumerate(progress_records, 1):
        t = teams.get(p.team_id)
        if not t:
            continue
        result.append({
            "rank": rank,
            "team_id": t.id,
            "team_name": t.name,
            "department": t.department,
            "member_count": len(t.member_ids),
            "progress": p.progress,
            "target": p.target,
            "completed": p.completed,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
        })
    return {"challenge_id": challenge_id, "entries": result}


async def update_team_progress(user_id: str, module_id: str) -> None:
    """
    Called when a user completes a module. Increments progress for all teams
    the user belongs to where the challenge criteria is team_complete_modules.
    Publishes to Redis for real-time updates.
    """
    redis = await get_redis()
    teams = await Team.find(In(Team.member_ids, [user_id])).to_list()
    for team in teams:
        challenge = await TeamChallenge.get(team.challenge_id)
        if not challenge or not challenge.active:
            continue
        if challenge.criteria.get("type") != "team_complete_modules":
            continue

        progress = await TeamProgress.find_one(
            TeamProgress.challenge_id == challenge.id,
            TeamProgress.team_id == team.id,
        )
        if not progress or progress.completed:
            continue

        # Count total module completions by all team members
        all_member_ids = team.member_ids
        completions = await Enrollment.find(
            In(Enrollment.user_id, all_member_ids),
            Enrollment.completion_percentage >= 100,
        ).count()

        progress.progress = min(completions, progress.target)
        if progress.progress >= progress.target and not progress.completed:
            progress.completed = True
            progress.completed_at = datetime.now(timezone.utc)
            # Award rewards to all team members
            svc = GamificationService(redis)
            for mid in team.member_ids:
                member = await User.get(mid)
                if member:
                    if challenge.reward_xp > 0:
                        await svc.award_xp_amount(
                            mid, "challenge_complete", challenge.reward_xp,
                            ref_type="challenge", ref_id=f"{challenge.id}:{team.id}",
                        )
                    if challenge.reward_points > 0:
                        await svc.award_points_amount(mid, challenge.reward_points, member.department or "")

        await progress.save()
        # Publish to Redis for real-time updates
        await redis.publish(
            f"team_progress:{team.id}",
            f'{{"progress": {progress.progress}, "target": {progress.target}, "completed": {str(progress.completed).lower()}}}',
        )
