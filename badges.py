"""Badges — the gamification layer.

Each badge has a stable `key`, display metadata, and a `check(user_data) -> bool`
function. The user_data dict is built once by `gather_user_data` in routes/badges.py
and passed to every check, so checks are pure-function and trivially testable.

Design choices:

  - Badges reward planning BEHAVIOR, not academic performance. We don't have an
    "all A's" badge because that creates a bad incentive (and exposes grades
    in a leaderboardable way later).

  - Earned-at is persisted only the FIRST time a badge fires. Re-earning isn't
    a thing — once earned, the timestamp is locked in `earned_badges`.

  - Checks are intentionally cheap. None of them run sub-queries or call out
    to other services. Everything lives in the data dict.

  - The catalog ordering controls display order in the UI. Three tiers, four
    per tier max — keeps the UI readable without scrolling on first viewport.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class BadgeDef:
    """One badge definition. The frontend doesn't need this class — it gets a
    dict-shaped catalog via the API — but having it typed keeps the service
    honest about what each badge requires."""
    key: str
    title: str
    description: str
    tier: str
    check: Callable[[dict], bool]


# ---------- check functions ----------
# Each gets the same user_data shape (see gather_user_data in routes/badges.py).
# They live as module-level functions rather than lambdas so tracebacks are
# readable and tests can target them directly.

def _check_first_module(d: dict) -> bool:
    return d["total_entries"] >= 1


def _check_first_year(d: dict) -> bool:
    """≥20 MC placed across Year 1 (both semesters)."""
    y1_mcs = d["mcs_by_year"].get(1, 0)
    return y1_mcs >= 20


def _check_full_map(d: dict) -> bool:
    """At least one module placed in every one of the 8 plan semesters."""
    return len(d["nonempty_semesters"]) == 8


def _check_near_graduation(d: dict) -> bool:
    """≥80% of total_required MCs placed (any state, including ungraded)."""
    if d["required_mcs"] <= 0:
        return False
    return d["total_placed_mcs"] / d["required_mcs"] >= 0.8


def _check_first_grade(d: dict) -> bool:
    return d["graded_count"] >= 1


def _check_engaged_grader(d: dict) -> bool:
    return d["graded_count"] >= 5


def _check_su_aware(d: dict) -> bool:
    return d["su_count"] >= 1


def _check_collaborator(d: dict) -> bool:
    return d["shares_sent"] >= 1


def _check_networker(d: dict) -> bool:
    return d["optin_count"] >= 1


def _check_popular_signup(d: dict) -> bool:
    """At least one of the user's opt-ins has 3+ others interested."""
    return d["max_optin_others"] >= 3


# ---------- the catalog ----------

CATALOG: list[BadgeDef] = [
    # Building tier — plan structure
    BadgeDef(
        key="first-module",
        title="First Module",
        description="Place your first module anywhere in the planner.",
        tier="Building",
        check=_check_first_module,
    ),
    BadgeDef(
        key="first-year",
        title="First Year Mapped",
        description="Place at least 20 MCs across Year 1 (Y1S1 + Y1S2).",
        tier="Building",
        check=_check_first_year,
    ),
    BadgeDef(
        key="full-map",
        title="Full Map",
        description="Place at least one module in every one of the 8 semesters.",
        tier="Building",
        check=_check_full_map,
    ),
    BadgeDef(
        key="near-graduation",
        title="Near Graduation",
        description="Place 80% or more of your major's required MCs.",
        tier="Building",
        check=_check_near_graduation,
    ),

    # Tracking tier — grades + S/U
    BadgeDef(
        key="first-grade",
        title="Grade Recorded",
        description="Record a grade for any module.",
        tier="Tracking",
        check=_check_first_grade,
    ),
    BadgeDef(
        key="engaged-grader",
        title="Engaged Grader",
        description="Record grades for 5 or more modules.",
        tier="Tracking",
        check=_check_engaged_grader,
    ),
    BadgeDef(
        key="su-aware",
        title="S/U Aware",
        description="Apply S/U to at least one module — strategic thinking ahead.",
        tier="Tracking",
        check=_check_su_aware,
    ),

    # Community tier — sharing + study groups
    BadgeDef(
        key="collaborator",
        title="Collaborator",
        description="Share your plan with at least one other person.",
        tier="Community",
        check=_check_collaborator,
    ),
    BadgeDef(
        key="networker",
        title="Networker",
        description="Opt into a study group for at least one module.",
        tier="Community",
        check=_check_networker,
    ),
    BadgeDef(
        key="popular-signup",
        title="Popular Signup",
        description="At least one of your study group opt-ins has 3+ other interested students.",
        tier="Community",
        check=_check_popular_signup,
    ),
]


# ---------- the public API of this module ----------

def evaluate(user_data: dict) -> dict[str, bool]:
    """Run every check against `user_data`. Returns {badge_key: earned_bool}."""
    return {b.key: bool(b.check(user_data)) for b in CATALOG}


def catalog_as_list() -> list[dict]:
    """Return the catalog in display-ready dict form, with no `check` callable.

    Used by the route to send the catalog to the frontend without exposing
    internal references.
    """
    return [
        {"key": b.key, "title": b.title, "description": b.description, "tier": b.tier}
        for b in CATALOG
    ]
