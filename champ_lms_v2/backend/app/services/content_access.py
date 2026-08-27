"""
Who may see which piece of content.

Covers both kinds of content in the catalogue — learning modules and test
series — because the rules are the same for both and an admin thinks about
them in one place. A test series carries the same audience fields as a module
(`audience_teams` / `audience_departments` / `target_roles` /
`required_for_teams`), so every function here takes either.

MODEL
-----
Content is either open or restricted:

  * Open — no team, department or role assignment. Visible to everyone.
    This is the default, so content that predates this feature keeps working
    exactly as before rather than vanishing on deploy.
  * Restricted — at least one of `audience_teams` / `audience_departments` /
    `target_roles` is set. A learner needs to match ONE of the populated
    dimensions (they are OR-ed, not AND-ed: "Sales team OR engineering
    department" is the useful reading, and AND-ing them makes most
    combinations match nobody).

Two per-person overrides sit on top, and they beat the audience rules:

  * A GRANT lets one person into restricted content their team can't see.
  * A REQUIRED behaves like a grant and additionally marks the content
    mandatory for that person.
  * A REVOKE keeps one person out of content they'd otherwise reach.

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

The same applies to tests: the test list is filtered, and /take and /submit are
both gated. Hiding a test from the list while leaving /submit open would let
anyone post a submission to a test they were never meant to sit.
"""
from __future__ import annotations

from app.models.content_access import ContentAccessRule
from app.models.module import Module
from app.models.test_series import TestSeries
from app.models.user import User

# Anything carrying the audience fields: a Module or a TestSeries. Named rather
# than spelled out at every call site, since every function here takes either.
Content = Module | TestSeries

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


def _departments(content: Content) -> set[str]:
    """
    Every department this content targets.

    A TestSeries has a legacy single `department` string from before audiences
    existed. It is folded in here as one more department rather than checked
    separately, so a test with both an old department and a new audience list
    behaves like one audience instead of two gates that can disagree.
    """
    departments = _norm_set(getattr(content, "audience_departments", None))
    legacy = _norm(getattr(content, "department", None))
    if legacy:
        departments.add(legacy)
    return departments


def is_restricted(content: Content) -> bool:
    """True when the content targets a specific audience rather than everyone."""
    return bool(
        _norm_set(content.audience_teams)
        or _departments(content)
        or _norm_set(content.target_roles)
        or _norm_set(content.required_for_teams)
    )


def matches_audience(content: Content, user: User) -> bool:
    """
    Does this user fall inside the content's audience?

    Unrestricted content matches everyone. Otherwise the populated dimensions
    are OR-ed.
    """
    if not is_restricted(content):
        return True

    teams = _norm_set(content.audience_teams)
    if teams and _norm(user.team) in teams:
        return True

    # Content required of a team is necessarily visible to that team, even if
    # the team was never added to audience_teams.
    required_teams = _norm_set(content.required_for_teams)
    if required_teams and _norm(user.team) in required_teams:
        return True

    departments = _departments(content)
    if departments and _norm(user.department) in departments:
        return True

    roles = _norm_set(content.target_roles)
    if roles and _norm(user.role) in roles:
        return True

    return False


async def rules_for_user(
    user_id: str,
    kind: str = ContentAccessRule.KIND_MODULE,
) -> dict[str, str]:
    """
    Every per-person override for one user on one kind of content,
    as {content_id: access}.

    Scoped by kind so a module rule can never be read as a rule about a test.
    Defaults to modules because that is what every existing caller means.

    Fetched in a single query and reused across a request so listing N items
    doesn't issue N lookups.
    """
    rules = await ContentAccessRule.find(
        ContentAccessRule.user_id == user_id,
        ContentAccessRule.content_kind == kind,
    ).to_list()
    resolved: dict[str, str] = {}
    for rule in rules:
        # A revoke is final; never let a later grant overwrite it.
        if resolved.get(rule.content_id) == ContentAccessRule.REVOKE:
            continue
        resolved[rule.content_id] = rule.access
    return resolved


async def test_rules_for_user(user_id: str) -> dict[str, str]:
    """Per-person overrides for one user's test series."""
    return await rules_for_user(user_id, ContentAccessRule.KIND_TEST)


def can_access(
    content: Content,
    user: User,
    overrides: dict[str, str] | None = None,
) -> bool:
    """
    Final say on whether `user` may open `content`.

    `overrides` comes from rules_for_user(); pass it when checking many items
    so the rules are loaded once. It must be the overrides for this content's
    own kind — the caller picks the kind, not this function, because it has no
    way to tell a Module id from a TestSeries id.
    """
    if is_admin(user):
        return True

    override = (overrides or {}).get(content.id)
    if override == ContentAccessRule.REVOKE:
        return False
    if override in (ContentAccessRule.GRANT, ContentAccessRule.REQUIRED):
        return True

    return matches_audience(content, user)


async def can_access_module_id(module_id: str, user: User) -> bool:
    """Single-module check that loads what it needs. Missing module -> False."""
    if is_admin(user):
        return True
    module = await Module.get(module_id)
    if not module:
        return False
    return can_access(module, user, await rules_for_user(user.id))


async def can_access_test(test: TestSeries, user: User) -> bool:
    """Single-test check. Loads that user's test rules."""
    if is_admin(user):
        return True
    return can_access(test, user, await test_rules_for_user(user.id))


async def filter_visible(modules: list[Module], user: User) -> list[Module]:
    """Keep only the modules `user` may see, preserving order."""
    if is_admin(user):
        return modules
    overrides = await rules_for_user(user.id)
    return [m for m in modules if can_access(m, user, overrides)]


async def filter_visible_tests(
    tests: list[TestSeries], user: User
) -> list[TestSeries]:
    """Keep only the tests `user` may sit, preserving order."""
    if is_admin(user):
        return tests
    overrides = await test_rules_for_user(user.id)
    return [t for t in tests if can_access(t, user, overrides)]


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
    content: Content,
    user: User,
    overrides: dict[str, str] | None = None,
) -> bool:
    """
    Is this content mandatory for `user` (rather than just available)?

    Per-person REQUIRED wins; otherwise it is required if the user's team is
    listed in required_for_teams. A REVOKE cancels it — you cannot be required
    to complete something you cannot open.
    """
    override = (overrides or {}).get(content.id)
    if override == ContentAccessRule.REVOKE:
        return False
    if override == ContentAccessRule.REQUIRED:
        return True
    return _norm(user.team) in _norm_set(content.required_for_teams)


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


async def required_test_ids(user: User) -> set[str]:
    """Ids of every test series mandatory for this user."""
    overrides = await test_rules_for_user(user.id)
    required = {
        test_id for test_id, access in overrides.items()
        if access == ContentAccessRule.REQUIRED
    }
    if _norm(user.team):
        tests = await TestSeries.find_all().to_list()
        required |= {
            t.id for t in tests
            if _norm(user.team) in _norm_set(t.required_for_teams)
            and overrides.get(t.id) != ContentAccessRule.REVOKE
        }
    return required
