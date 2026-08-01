"""UE recommendation engine.

Replaces the naive global-popularity ranking with a more useful score based on:

  - Plan overlap: users whose plans look like yours are stronger signals
    than random users. Quantified by Jaccard similarity on the non-UE
    portion of their plans (the "fingerprint" of what they're studying).

  - Major cohort: same-major users get a fixed bonus on top of overlap.
    A CS student's UE picks are more relevant to another CS student than
    a BZA student's are.

  - Eligibility: modules whose prereqs can't be met given what's currently
    placed (across any future semester) are filtered out. Recommending
    things the user literally can't take is worse than useless.

  - Diversity: a soft per-department penalty so a single department doesn't
    dominate the top 5 with five similar electives.

The output is a list of (module, score, reasons) tuples ordered by score.

Trade-offs / non-goals:
  - We don't do collaborative filtering in the matrix-factorization sense.
    For a few hundred users with sparse plans, Jaccard overlap is plenty
    and far easier to debug. Replacing this with a learned model would be
    overkill until we have ~10k+ users.
  - We don't weight by grade. A user can recommend a module they got an A
    in just as much as one they got a B in. Both are signal that they
    chose it; the grade is downstream.
  - We don't suppress recently-recommended modules (no "shown last time"
    state). The ranking should be stable enough that the same modules
    appear consistently; that's a feature, not a bug, for academic planning.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable

from services.prereqs import prereqs_met


# Score weights. Tuned by feel; instrumenting with real usage data could refine
# these later. Keep them here so they're easy to find and adjust.
WEIGHT_OVERLAP = 1.0          # base coefficient on Jaccard similarity
WEIGHT_SAME_MAJOR = 0.5       # added to per-user score when major matches
MIN_OVERLAP_THRESHOLD = 0.0   # ignore users whose overlap is below this (0 = include everyone)
DIVERSITY_PENALTY_PER_DUP = 0.15  # subtract this for each prior pick from the same department


@dataclass
class CandidateModule:
    """One module as input to the recommender."""
    code: str
    title: str
    mcs: float
    department: str | None = None
    prereq_tree: dict | str | None = None


@dataclass
class UserPlan:
    """One other user's plan, as input to the recommender."""
    user_id: str
    major_code: str | None
    module_codes: set[str]


@dataclass
class Recommendation:
    """One ranked output."""
    module: CandidateModule
    score: float
    placement_count: int     # raw popularity (across the OTHER-plans pool)
    similar_user_count: int  # number of other plans this module appeared in among those with positive overlap
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "code": self.module.code,
            "title": self.module.title,
            "mcs": _fmt_mcs(self.module.mcs),
            "department": self.module.department,
            "score": round(self.score, 4),
            "placement_count": self.placement_count,
            "similar_user_count": self.similar_user_count,
            "reasons": self.reasons,
        }


# ---------------- core scoring ----------------

def jaccard(a: set[str], b: set[str]) -> float:
    """Standard Jaccard similarity. Returns 0 on empty union."""
    if not a and not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def score_candidates(
    me: UserPlan,
    other_plans: Iterable[UserPlan],
    ue_candidates: Iterable[CandidateModule],
    ue_codes: set[str],
    limit: int = 5,
) -> list[Recommendation]:
    """Score and rank UE candidates for `me`.

    Parameters
    ----------
    me:
        The current user's plan + major.
    other_plans:
        Plans from other users — the signal pool. Each must include the user's
        major_code and the set of all module codes in their plan (UE-eligible
        or not).
    ue_candidates:
        Pool of modules eligible for recommendation. These should already be
        filtered to "could fulfill a UE bucket" and to "not already in me's plan".
    ue_codes:
        The set of all UE-eligible module codes (used to derive each candidate's
        score from each other user's plan).
    limit:
        Max number of recommendations to return.

    Scoring (per candidate module m):

        score(m) = popularity(m) + sum over similar users u:
                     overlap_weight(u) * (1 if m in u.plan else 0)

        overlap_weight(u) = WEIGHT_OVERLAP * jaccard_on_non_UE(u, me)
                          + (WEIGHT_SAME_MAJOR if u.major == me.major else 0)

        popularity(m) = log1p(global placement count) — keeps base ranking
        sensible when there are no similar users (cold start).

    After scoring, candidates are sorted descending and a diversity penalty
    is applied greedily: while building the top-N, each candidate's score is
    reduced by DIVERSITY_PENALTY_PER_DUP times the number of already-picked
    items from the same department.
    """
    me_signature = me.module_codes - ue_codes  # non-UE modules are the "fingerprint"

    # Pre-compute weight per other user.
    user_weights: dict[str, float] = {}
    for u in other_plans:
        if u.user_id == me.user_id:
            continue  # don't recommend yourself to yourself
        u_signature = u.module_codes - ue_codes
        overlap = jaccard(me_signature, u_signature)
        if overlap < MIN_OVERLAP_THRESHOLD:
            continue
        w = WEIGHT_OVERLAP * overlap
        if me.major_code and u.major_code == me.major_code:
            w += WEIGHT_SAME_MAJOR
        if w > 0:
            user_weights[u.user_id] = w

    # Index module → users who placed it (for cheap lookup and reason text)
    module_to_users: dict[str, set[str]] = {}
    for u in other_plans:
        for code in u.module_codes:
            module_to_users.setdefault(code, set()).add(u.user_id)

    # Score each candidate.
    import math
    candidate_list = list(ue_candidates)
    scored: list[Recommendation] = []
    for c in candidate_list:
        users_with_module = module_to_users.get(c.code, set())
        placement_count = len(users_with_module)
        popularity = math.log1p(placement_count)

        sim_score = 0.0
        similar_user_count = 0
        for uid in users_with_module:
            w = user_weights.get(uid)
            if w is None:
                continue
            sim_score += w
            similar_user_count += 1

        score = popularity + sim_score

        reasons = []
        if similar_user_count > 0:
            reasons.append(
                f"taken by {similar_user_count} user{'s' if similar_user_count != 1 else ''} with similar plans"
            )
        elif placement_count > 0:
            reasons.append(
                f"popular overall ({placement_count} planner{'s' if placement_count != 1 else ''})"
            )
        else:
            reasons.append("untaken so far — new option for you")

        scored.append(Recommendation(
            module=c,
            score=score,
            placement_count=placement_count,
            similar_user_count=similar_user_count,
            reasons=reasons,
        ))

    # Sort by score desc; tiebreak by code so output is deterministic.
    scored.sort(key=lambda r: (-r.score, r.module.code))

    # Greedy diversity pass — apply per-department penalty while picking top N.
    picked: list[Recommendation] = []
    dept_count: dict[str, int] = {}
    # We need to compare adjusted scores; if a penalised candidate drops below
    # the next one, we want the next to win. Simplest: iterate, compute adjusted
    # score, pick max, repeat.
    remaining = scored[:]
    while remaining and len(picked) < limit:
        best = None
        best_adjusted = float("-inf")
        for r in remaining:
            dept = r.module.department or "?"
            penalty = DIVERSITY_PENALTY_PER_DUP * dept_count.get(dept, 0)
            adjusted = r.score - penalty
            if adjusted > best_adjusted:
                best_adjusted = adjusted
                best = r
        if best is None:
            break
        # If a diversity penalty actually changed the picked module's score,
        # surface that in reasons.
        dept = best.module.department or "?"
        if dept_count.get(dept, 0) > 0:
            # Not a "reason for", more like a footnote — but useful for debugging.
            best.reasons.append(f"diversifying — already picked {dept_count[dept]} from {dept}")
        dept_count[dept] = dept_count.get(dept, 0) + 1
        picked.append(best)
        remaining.remove(best)

    return picked


# ---------------- eligibility filtering ----------------

def filter_eligible(
    candidates: Iterable[CandidateModule],
    placed_codes: set[str],
) -> list[CandidateModule]:
    """Drop candidates whose prereqs aren't satisfied by `placed_codes`.

    Permissive: a candidate with no prereq tree (None) is always eligible.
    We don't check semester ordering — just whether the user has placed
    the prerequisite modules anywhere in their plan. This matches the
    intent of a recommendation: "you could take this somewhere in your
    plan", not "you can take this in the next semester".
    """
    out = []
    for c in candidates:
        if prereqs_met(c.prereq_tree, placed_codes):
            out.append(c)
    return out


def _fmt_mcs(mcs):
    """Format MCs to drop trailing .0 for whole numbers."""
    if mcs is None:
        return 0
    mcs = float(mcs)
    return int(mcs) if mcs == int(mcs) else mcs
