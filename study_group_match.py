"""Study group match scoring.

When two students opt into the same module for the same semester, they're a
potential study partner pair. But not all pairs are equally good — a CS Y3
student and another CS Y3 student probably have more in common than a CS Y3
and a BZA Y1, even if both are taking the module.

This service ranks potential matches with a small set of additive signals:

  - Same major:         WEIGHT_SAME_MAJOR  (default 25)
  - Same matric year:   WEIGHT_SAME_YEAR   (default 20)
  - Plan overlap:       WEIGHT_PLAN_OVERLAP * jaccard(plans)  (max 30)
  - Recency:            WEIGHT_RECENCY     (default 5) if other opted in this week

Maximum theoretical score is the sum of weights (80 today). For display we
clamp to 0-100 and call it a "compatibility score". The exact number is
arbitrary — it's the ranking and the per-match `reasons` that matter.

Notes / non-goals:
  - We don't score on grades or CAP. People who study together don't need
    matching grades, and exposing CAPs would be a privacy headache.
  - We don't filter out anyone — a low-score match is still a match. The
    user decides whether to reach out.
  - No collaborative filtering ("students who matched with X also matched
    with Y"). That kind of meta-matching has weird incentives and would
    need a long usage history to mean anything.
  - We don't recommend tutorial-group buddies — that requires class slot
    selection (see F9-1). Until that lands, "same module + same plan
    semester" is the unit of matching.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

# Weights — tune by feel; instrumentation against real usage would refine.
WEIGHT_SAME_MAJOR = 25.0
WEIGHT_SAME_YEAR = 20.0
WEIGHT_PLAN_OVERLAP = 30.0   # multiplied by jaccard, so up to this value
WEIGHT_RECENCY = 5.0
RECENCY_WINDOW_DAYS = 7


@dataclass
class MatchCandidate:
    """Input shape for the scorer — one other opted-in student."""
    user_id: str
    display_name: str | None
    email: str
    major_code: str | None
    matric_year: int | None
    contact_telegram: str | None
    optin_id: int
    message: str | None
    optin_created_at: str | None   # ISO string from SQLite; parsed below
    other_plan_modules: set[str] = field(default_factory=set)


@dataclass
class ScoredMatch:
    candidate: MatchCandidate
    score: int                     # rounded 0-100
    reasons: list[str]             # human-readable explanations
    same_major: bool
    same_year: bool
    plan_overlap_count: int        # number of modules in common excluding the current one
    recent: bool

    def as_dict(self) -> dict:
        return {
            "user_id": self.candidate.user_id,
            "display_name": self.candidate.display_name,
            "email": self.candidate.email,
            "major_code": self.candidate.major_code,
            "matric_year": self.candidate.matric_year,
            "contact_telegram": self.candidate.contact_telegram,
            "optin_id": self.candidate.optin_id,
            "message": self.candidate.message,
            "optin_created_at": self.candidate.optin_created_at,
            "score": self.score,
            "reasons": self.reasons,
            "same_major": self.same_major,
            "same_year": self.same_year,
            "plan_overlap_count": self.plan_overlap_count,
            "recent": self.recent,
        }


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _parse_sqlite_ts(s: str | None) -> datetime | None:
    """SQLite CURRENT_TIMESTAMP gives 'YYYY-MM-DD HH:MM:SS' in UTC."""
    if not s:
        return None
    try:
        # SQLite default format is "YYYY-MM-DD HH:MM:SS", no T separator.
        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            # Fall back to a permissive parse — strip subseconds and try again.
            cleaned = s.split(".")[0]
            return datetime.fromisoformat(cleaned).replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def score_match(
    *,
    me_major: str | None,
    me_matric_year: int | None,
    me_plan_modules: set[str],
    candidate: MatchCandidate,
    now: datetime | None = None,
) -> ScoredMatch:
    """Score one candidate. Pure function — testable without DB."""
    if now is None:
        now = datetime.now(timezone.utc)

    reasons: list[str] = []
    raw_score = 0.0

    # Same major
    same_major = (
        bool(me_major)
        and bool(candidate.major_code)
        and me_major == candidate.major_code
    )
    if same_major:
        raw_score += WEIGHT_SAME_MAJOR
        reasons.append(f"Same major ({me_major})")

    # Same matric year
    same_year = (
        me_matric_year is not None
        and candidate.matric_year is not None
        and me_matric_year == candidate.matric_year
    )
    if same_year:
        raw_score += WEIGHT_SAME_YEAR
        reasons.append(f"Same matric year ({me_matric_year})")

    # Plan overlap (Jaccard on the other modules in both plans)
    overlap = _jaccard(me_plan_modules, candidate.other_plan_modules)
    overlap_count = len(me_plan_modules & candidate.other_plan_modules)
    if overlap > 0:
        raw_score += WEIGHT_PLAN_OVERLAP * overlap
        # Phrase the overlap as a count rather than a fraction — easier to read.
        if overlap_count == 1:
            reasons.append("1 other module in common")
        else:
            reasons.append(f"{overlap_count} other modules in common")

    # Recency
    recent = False
    optin_dt = _parse_sqlite_ts(candidate.optin_created_at)
    if optin_dt:
        days = (now - optin_dt).total_seconds() / 86400
        if 0 <= days <= RECENCY_WINDOW_DAYS:
            raw_score += WEIGHT_RECENCY
            recent = True
            # Don't always surface recency as a reason — it's a tiebreaker, not a
            # primary signal. Only include it if no stronger signal fired.
            if not reasons:
                reasons.append("Joined recently")

    # Cap & round to 0-100.
    score = int(round(min(100.0, max(0.0, raw_score))))

    # If we have no specific reasons, fall back to a generic acknowledgement so
    # the UI never shows an empty list.
    if not reasons:
        reasons.append("Taking this module")

    return ScoredMatch(
        candidate=candidate,
        score=score,
        reasons=reasons,
        same_major=same_major,
        same_year=same_year,
        plan_overlap_count=overlap_count,
        recent=recent,
    )


def rank_matches(
    *,
    me_major: str | None,
    me_matric_year: int | None,
    me_plan_modules: set[str],
    candidates: Iterable[MatchCandidate],
    now: datetime | None = None,
) -> list[ScoredMatch]:
    """Score and sort every candidate. Ties broken alphabetically by user_id
    so the output is deterministic (helpful for tests and for users who
    revisit the page expecting stable ordering)."""
    scored = [
        score_match(
            me_major=me_major,
            me_matric_year=me_matric_year,
            me_plan_modules=me_plan_modules,
            candidate=c,
            now=now,
        )
        for c in candidates
    ]
    scored.sort(key=lambda s: (-s.score, s.candidate.user_id))
    return scored
