"""
Admin-managed employee accounts.

Champ LMS is an internal tool: there is no public sign-up. An admin creates
each account with a team, a department and a role, and the system generates the
starting password. The employee signs in with it and is required to set their
own; the admin can read the current password at any time (see
app.core.password_vault for why that is allowed here and how it is contained).
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.core.auth import get_current_user, hash_password, require_admin, verify_password
from app.core import password_vault
from app.models.content_access import ContentAccessRule
from app.models.module import Module
from app.models.user import User
from app.services import content_access

router = APIRouter(tags=["employees"])

# Roles an admin may assign. "ld_lead" is an admin-equivalent (see
# require_admin), so it is grantable but called out separately in the UI.
ASSIGNABLE_ROLES = ("learner", "ld_lead", "admin")

MIN_PASSWORD_LENGTH = 8

# Ambiguous characters are left out: a generated password gets read off a screen
# and typed by hand, so 0/O and 1/l/I cause avoidable support tickets.
_ALPHABET = (
    "ABCDEFGHJKLMNPQRSTUVWXYZ"
    "abcdefghijkmnopqrstuvwxyz"
    "23456789"
    "!@#$%*?"
)


def generate_password(length: int = 12) -> str:
    """
    A random starting password.

    Guarantees at least one upper, one lower, one digit and one symbol so the
    result satisfies any reasonable policy, then fills the rest randomly and
    shuffles, so the guaranteed characters aren't always in the same positions.
    """
    if length < 4:
        raise ValueError("length must be at least 4")
    pools = ("ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnopqrstuvwxyz", "23456789", "!@#$%*?")
    chars = [secrets.choice(p) for p in pools]
    chars += [secrets.choice(_ALPHABET) for _ in range(length - len(pools))]
    # secrets-backed Fisher-Yates; random.shuffle is not cryptographically safe.
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class EmployeeCreateIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1)
    department: str | None = None
    team: str | None = None
    role: str = "learner"
    # Optional: an admin may dictate the starting password instead of
    # generating one. Left unset in the normal flow.
    initial_password: str | None = None


class EmployeeUpdateIn(BaseModel):
    """Every field optional — only what's provided is changed."""
    full_name: str | None = None
    department: str | None = None
    team: str | None = None
    role: str | None = None
    is_active: bool | None = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH)


def _employee_out(user: User, *, include_password: bool) -> dict:
    """
    Serialise an employee for the admin roster.

    `include_password` is passed explicitly by each caller rather than inferred,
    so the readable password can never leak into a non-admin response by
    accident.
    """
    out = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "department": user.department,
        "team": user.team,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "password_changed_at": user.password_changed_at,
        "created_at": user.created_at,
        "points": user.points,
        "level": user.level,
    }
    if include_password:
        recovered = password_vault.decrypt(user.password_recoverable)
        out["current_password"] = recovered
        # Distinguishes "we can't read it" from "there is nothing to read", so
        # the UI can tell the admin to reset rather than implying a bug.
        out["password_available"] = recovered is not None
    return out


def _apply_password(user: User, plain: str) -> None:
    """Set both the auth hash and the admin-readable copy from one plaintext."""
    user.hashed_password = hash_password(plain)
    user.password_recoverable = password_vault.encrypt(plain)


# --------------------------------------------------------------------------
# Admin: roster
# --------------------------------------------------------------------------
@router.get("/admin/employees")
async def list_employees(
    admin: Annotated[User, Depends(require_admin)],
    q: str | None = None,
    department: str | None = None,
    team: str | None = None,
    role: str | None = None,
):
    """Every account, with the current password visible to the admin."""
    users = await User.find_all().to_list()

    if q:
        needle = q.strip().lower()
        users = [
            u for u in users
            if needle in (u.email or "").lower()
            or needle in (u.full_name or "").lower()
        ]
    if department:
        users = [u for u in users if (u.department or "") == department]
    if team:
        users = [u for u in users if (u.team or "") == team]
    if role:
        users = [u for u in users if u.role == role]

    users.sort(key=lambda u: (u.full_name or u.email or "").lower())
    return {
        "employees": [_employee_out(u, include_password=True) for u in users],
        "total": len(users),
        "departments": sorted({u.department for u in users if u.department}),
        "teams": sorted({u.team for u in users if u.team}),
    }


@router.post("/admin/employees", status_code=201)
async def create_employee(
    body: EmployeeCreateIn,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Provision an employee account. Returns the starting password so the admin
    can pass it on; it stays readable on the roster afterwards.
    """
    if body.role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"role must be one of: {', '.join(ASSIGNABLE_ROLES)}",
        )

    email = body.email.strip().lower()
    if await User.find_one(User.email == email):
        raise HTTPException(status_code=409, detail="That email already has an account")

    if body.initial_password is not None:
        if len(body.initial_password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
            )
        starting = body.initial_password
    else:
        starting = generate_password()

    user = User(
        email=email,
        full_name=body.full_name.strip(),
        hashed_password="",  # replaced by _apply_password below
        role=body.role,
        department=(body.department or "").strip() or None,
        team=(body.team or "").strip() or None,
        must_change_password=True,
        created_by_admin_id=admin.id,
    )
    _apply_password(user, starting)
    await user.insert()

    return {
        **_employee_out(user, include_password=True),
        "initial_password": starting,
    }


@router.patch("/admin/employees/{user_id}")
async def update_employee(
    user_id: str,
    body: EmployeeUpdateIn,
    admin: Annotated[User, Depends(require_admin)],
):
    """Change an employee's team, department, role or active state."""
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found")

    if body.role is not None and body.role not in ASSIGNABLE_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"role must be one of: {', '.join(ASSIGNABLE_ROLES)}",
        )

    # Guard against an admin removing their own access and locking the tool.
    if user.id == admin.id:
        if body.role is not None and body.role not in ("admin", "ld_lead"):
            raise HTTPException(
                status_code=422,
                detail="You cannot remove your own admin access.",
            )
        if body.is_active is False:
            raise HTTPException(
                status_code=422, detail="You cannot deactivate your own account."
            )

    if body.full_name is not None:
        user.full_name = body.full_name.strip() or None
    if body.department is not None:
        user.department = body.department.strip() or None
    if body.team is not None:
        user.team = body.team.strip() or None
    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    await user.save()
    return _employee_out(user, include_password=True)


@router.post("/admin/employees/{user_id}/reset-password")
async def reset_employee_password(
    user_id: str,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Issue a fresh random password and require the employee to change it again.
    Used when someone is locked out or a password should be invalidated.
    """
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found")

    new_password = generate_password()
    _apply_password(user, new_password)
    user.must_change_password = True
    user.password_changed_at = None
    await user.save()

    return {
        **_employee_out(user, include_password=True),
        "initial_password": new_password,
    }


@router.delete("/admin/employees/{user_id}")
async def delete_employee(
    user_id: str,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Deactivate an account. Deliberately not a hard delete: attempts, progress
    and leaderboard history reference the user, so removing the row would leave
    those dangling.
    """
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Employee not found")
    if user.id == admin.id:
        raise HTTPException(
            status_code=422, detail="You cannot deactivate your own account."
        )

    user.is_active = False
    await user.save()
    return {"id": user.id, "is_active": user.is_active}


# --------------------------------------------------------------------------
# Employee: change own password
# --------------------------------------------------------------------------
@router.post("/auth/change-password")
async def change_own_password(
    body: ChangePasswordIn,
    user: Annotated[User, Depends(get_current_user)],
):
    """
    Replace the caller's own password.

    Requires the current password, so a stolen token alone can't lock the
    real employee out of their account.
    """
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=422, detail="New password must be different from the current one"
        )

    _apply_password(user, body.new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)
    await user.save()

    return {
        "id": user.id,
        "must_change_password": user.must_change_password,
        "password_changed_at": user.password_changed_at,
    }


# --------------------------------------------------------------------------
# Admin: content targeting
#
# Two levers, described in app/services/content_access.py:
#   * module audience  — teams / departments / roles that can see a module,
#                        and the teams it is required of.
#   * per-person rule  — grant, require or revoke for one individual.
# --------------------------------------------------------------------------
class ModuleAudienceIn(BaseModel):
    """
    Set a module's audience. Passing [] clears a dimension (opening it up);
    omitting a field leaves that dimension untouched.
    """
    audience_teams: list[str] | None = None
    audience_departments: list[str] | None = None
    target_roles: list[str] | None = None
    required_for_teams: list[str] | None = None


class AccessRuleIn(BaseModel):
    user_id: str
    access: str  # grant | required | revoke
    reason: str | None = None


def _clean_list(values: list[str] | None) -> list[str] | None:
    """Trim, drop blanks, de-duplicate case-insensitively, keep order."""
    if values is None:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        v = (v or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def _audience_out(module: Module) -> dict:
    return {
        "id": module.id,
        "title": module.title,
        "category": module.category,
        "is_published": module.is_published,
        "audience_teams": module.audience_teams or [],
        "audience_departments": module.audience_departments or [],
        "target_roles": module.target_roles or [],
        "required_for_teams": module.required_for_teams or [],
        "is_restricted": content_access.is_restricted(module),
    }


@router.get("/admin/content-access/modules")
async def list_module_audiences(admin: Annotated[User, Depends(require_admin)]):
    """
    Every module with its audience, plus the teams/departments available to
    assign (taken from real employee records, so the admin picks from what
    actually exists rather than retyping names).
    """
    modules = await Module.find_all().sort(-Module.created_at).to_list()
    users = await User.find_all().to_list()
    return {
        "modules": [_audience_out(m) for m in modules],
        "teams": sorted({u.team for u in users if u.team}),
        "departments": sorted({u.department for u in users if u.department}),
        "roles": list(ASSIGNABLE_ROLES),
    }


@router.patch("/admin/content-access/modules/{module_id}")
async def set_module_audience(
    module_id: str,
    body: ModuleAudienceIn,
    admin: Annotated[User, Depends(require_admin)],
):
    """Restrict a module to teams/departments/roles, or open it up again."""
    module = await Module.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    if body.target_roles is not None:
        bad = [r for r in body.target_roles if r not in ASSIGNABLE_ROLES]
        if bad:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown role(s): {', '.join(bad)}. Valid: {', '.join(ASSIGNABLE_ROLES)}",
            )

    if body.audience_teams is not None:
        module.audience_teams = _clean_list(body.audience_teams)
    if body.audience_departments is not None:
        module.audience_departments = _clean_list(body.audience_departments)
    if body.target_roles is not None:
        module.target_roles = _clean_list(body.target_roles)
    if body.required_for_teams is not None:
        module.required_for_teams = _clean_list(body.required_for_teams)

    await module.save()
    return _audience_out(module)


@router.get("/admin/content-access/modules/{module_id}/people")
async def module_access_people(
    module_id: str,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    Who can currently see this module and why — audience match, an explicit
    per-person rule, or admin bypass. Lets an admin verify the effect of a
    restriction instead of guessing.
    """
    module = await Module.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    users = await User.find_all().to_list()
    rules = await ContentAccessRule.find(ContentAccessRule.module_id == module_id).to_list()
    by_user = {r.user_id: r for r in rules}

    people = []
    for u in sorted(users, key=lambda x: (x.full_name or x.email or "").lower()):
        rule = by_user.get(u.id)
        override = {module_id: rule.access} if rule else {}
        allowed = content_access.can_access(module, u, override)
        if content_access.is_admin(u):
            why = "admin"
        elif rule:
            why = f"rule: {rule.access}"
        elif content_access.matches_audience(module, u):
            why = "audience" if content_access.is_restricted(module) else "open to everyone"
        else:
            why = "not in audience"
        people.append({
            "user_id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "team": u.team,
            "department": u.department,
            "role": u.role,
            "is_active": u.is_active,
            "can_access": allowed,
            "required": content_access.is_required(module, u, override),
            "rule": rule.access if rule else None,
            "reason": rule.reason if rule else None,
            "why": why,
        })

    return {
        **_audience_out(module),
        "people": people,
        "can_access_count": sum(1 for p in people if p["can_access"]),
    }


@router.put("/admin/content-access/modules/{module_id}/people")
async def set_person_access(
    module_id: str,
    body: AccessRuleIn,
    admin: Annotated[User, Depends(require_admin)],
):
    """Grant, require or revoke this module for one person."""
    valid = (ContentAccessRule.GRANT, ContentAccessRule.REQUIRED, ContentAccessRule.REVOKE)
    if body.access not in valid:
        raise HTTPException(
            status_code=422, detail=f"access must be one of: {', '.join(valid)}"
        )

    module = await Module.get(module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    target = await User.get(body.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Employee not found")

    existing = await ContentAccessRule.find_one(
        ContentAccessRule.user_id == body.user_id,
        ContentAccessRule.module_id == module_id,
    )
    if existing:
        existing.access = body.access
        existing.reason = body.reason
        existing.created_by_admin_id = admin.id
        await existing.save()
        rule = existing
    else:
        rule = ContentAccessRule(
            user_id=body.user_id,
            module_id=module_id,
            access=body.access,
            reason=body.reason,
            created_by_admin_id=admin.id,
        )
        await rule.insert()

    return {
        "module_id": module_id,
        "user_id": rule.user_id,
        "access": rule.access,
        "reason": rule.reason,
    }


@router.delete("/admin/content-access/modules/{module_id}/people/{user_id}")
async def clear_person_access(
    module_id: str,
    user_id: str,
    admin: Annotated[User, Depends(require_admin)],
):
    """Drop a per-person rule, so the module's audience rules apply again."""
    rule = await ContentAccessRule.find_one(
        ContentAccessRule.user_id == user_id,
        ContentAccessRule.module_id == module_id,
    )
    if not rule:
        raise HTTPException(status_code=404, detail="No rule set for that person")
    await rule.delete()
    return {"module_id": module_id, "user_id": user_id, "access": None}


@router.get("/admin/content-access/employees/{user_id}")
async def employee_access_overview(
    user_id: str,
    admin: Annotated[User, Depends(require_admin)],
):
    """
    The catalogue from one employee's point of view — what they can open, what
    is required of them, and where any explicit rule applies.
    """
    target = await User.get(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Employee not found")

    modules = await Module.find_all().sort(-Module.created_at).to_list()
    overrides = await content_access.rules_for_user(user_id)

    items = [
        {
            "module_id": m.id,
            "title": m.title,
            "category": m.category,
            "is_published": m.is_published,
            "is_restricted": content_access.is_restricted(m),
            "can_access": content_access.can_access(m, target, overrides),
            "required": content_access.is_required(m, target, overrides),
            "rule": overrides.get(m.id),
        }
        for m in modules
    ]
    return {
        "user_id": target.id,
        "full_name": target.full_name,
        "email": target.email,
        "team": target.team,
        "department": target.department,
        "role": target.role,
        "modules": items,
        "accessible_count": sum(1 for i in items if i["can_access"]),
        "required_count": sum(1 for i in items if i["required"]),
    }
