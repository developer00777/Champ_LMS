"""
Who may see which module.

MODEL
-----
A module is either open or restricted:

  * Open — no team, department or role assignment. Visible to everyone.
    This is the default, so modules that predate this feature keep working
    exactly as before rather than vanishing on deploy.
  * Restricted — at least one of `audience_teams` / `audience_departments` /
    `target_roles` is set. A learner needs to match ONE of the populated
    dimensions (they are OR-ed, not AND-ed: "Sales team OR engineering
    department" is the useful reading, and AND-ing them makes most
    combinations match nobody).

Two per-person overrides sit on top, and they beat the audience rules:

  * A GRANT lets one person into a restricted module their team can't see.
  * A REQUIRED behaves like a grant and additionally marks the module
    mandatory for that person.
  * A REVOKE keeps one person out of a module they'd otherwise reach.

REVOKE always wins over GRANT. If an admin has said both, the safer reading of
the intent is "not this person", and a grant left over from months ago should
not silently defeat a deliberate block.

Admins (role admin / ld_lead) bypass all of it — they administer the catalogue,
so they must be able to open anything to check it.

WHERE THIS IS ENFORCED
----------------------
Called from the learner-facing content paths: the module list, the module
detail page, the feed, search, and — most importantly — the stream endpoint
that hands out playback URLs. Filtering a list without gating the stream would
be decoration, not access control: anyone could still play a video by URL.
"""
from __future__ import annotations

from app.models.content_access import ContentAccessRule
from app.models.module import Module
from app.models.user import User

# Roles that administer the catalogue and therefore see everything.
_ADMIN_ROLES = ("admin", "ld_lead")


def is_admin(user: User) -> bool:
    return user.role in _ADMIN_ROLES


def _norm(value: str | None) -> str:
    """Compare audiences case- and whitespace-insensitively.

    Team and department names are typed by hand in the admin UI, so "Sales"
    and "sales " must not become different audiences.
    """
    return (value or "").strip().lower()


def _norm_set(values: list[str] | None) -> set[str]:
    return {_norm(v) for v in (values or []) if _norm(v)}


def is_restricted(module: Module) -> bool:
    """True when the module targets a specific audience rather than everyone."""
    return bool(
        _norm_set(module.audience_teams)
        or _norm_set(module.audience_departments)
        or _norm_set(module.target_roles)
        or _norm_set(module.required_for_teams)
    )


def matches_audience(module: Module, user: User) -> bool:
    """
    Does this user fall inside the module's audience?

    An unrestricted module matches everyone. Otherwise the populated
    dimensions are OR-ed.
    """
    if not is_restricted(module):
        return True

    teams = _norm_set(module.audience_teams)
    if teams and _norm(user.team) in teams:
        return True

    # A module required of a team is necessarily visible to that team, even if
    # the team was never added to audience_teams.
    required_teams = _norm_set(module.required_for_teams)
    if required_teams and _norm(user.team) in required_teams:
        return True

    departments = _norm_set(module.audience_departments)
    if departments and _norm(user.department) in departments:
        return True

    roles = _norm_set(module.target_roles)
    if roles and _norm(user.role) in roles:
        return True

    return False


async def rules_for_user(user_id: str) -> dict[str, str]:
    """
    Every per-person override for one user, as {module_id: access}.

    Fetched in a single query and reused across a request so listing N modules
    doesn't issue N lookups.
    """
    rules = await ContentAccessRule.find(ContentAccessRule.user_id == user_id).to_list()
    resolved: dict[str, str] = {}
    for rule in rules:
        # A revoke is final; never let a later grant overwrite it.
        if resolved.get(rule.module_id) == ContentAccessRule.REVOKE:
            continue
        resolved[rule.module_id] = rule.access
    return resolved


def can_access(
    module: Module,
    user: User,
    overrides: dict[str, str] | None = None,
) -> bool:
    """
    Final say on whether `user` may open `module`.

    `overrides` comes from rules_for_user(); pass it when checking many modules
    so the rules are loaded once.
    """
    if is_admin(user):
        return True

    override = (overrides or {}).get(module.id)
    if override == ContentAccessRule.REVOKE:
        return False
    if override in (ContentAccessRule.GRANT, ContentAccessRule.REQUIRED):
        return True

    return matches_audience(module, user)


async def can_access_module_id(module_id: str, user: User) -> bool:
    """Single-module check that loads what it needs. Missing module -> False."""
    if is_admin(user):
        return True
    module = await Module.get(module_id)
    if not module:
        return False
    return can_access(module, user, await rules_for_user(user.id))


async def filter_visible(modules: list[Module], user: User) -> list[Module]:
    """Keep only the modules `user` may see, preserving order."""
    if is_admin(user):
        return modules
    overrides = await rules_for_user(user.id)
    return [m for m in modules if can_access(m, user, overrides)]


async def visible_module_ids(user: User) -> set[str] | None:
    """
    The ids a learner may see, or None meaning "no restriction applies".

    None lets callers skip filtering entirely for admins, rather than loading
    the whole catalogue to compute a set they'd ignore.
    """
    if is_admin(user):
        return None
    modules = await Module.find_all().to_list()
    overrides = await rules_for_user(user.id)
    return {m.id for m in modules if can_access(m, user, overrides)}


def is_required(
    module: Module,
    user: User,
    overrides: dict[str, str] | None = None,
) -> bool:
    """
    Is this module mandatory for `user` (rather than just available)?

    Per-person REQUIRED wins; otherwise the module is required if the user's
    team is listed in required_for_teams. A REVOKE cancels it — you cannot be
    required to complete something you cannot open.
    """
    override = (overrides or {}).get(module.id)
    if override == ContentAccessRule.REVOKE:
        return False
    if override == ContentAccessRule.REQUIRED:
        return True
    return _norm(user.team) in _norm_set(module.required_for_teams)


async def required_module_ids(user: User) -> set[str]:
    """Ids of every module mandatory for this user."""
    overrides = await rules_for_user(user.id)
    required = {
        module_id for module_id, access in overrides.items()
        if access == ContentAccessRule.REQUIRED
    }
    if _norm(user.team):
        team_required = await Module.find_all().to_list()
        required |= {
            m.id for m in team_required
            if _norm(user.team) in _norm_set(m.required_for_teams)
            and overrides.get(m.id) != ContentAccessRule.REVOKE
        }
    return required
