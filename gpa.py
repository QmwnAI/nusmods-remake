"""GPA / CAP calculation and what-if simulation.

NUS uses a 5-point grade-point average (called CAP — Cumulative Average Point).
S/U-graded modules contribute MCs toward graduation but don't count toward CAP.

This module exposes three layers:

1. Pure CAP math — `compute_cap`, the existing function used by /api/plans/:id/gpa.

2. Target planning — `required_avg_for_target(current_pts, current_mcs, remaining_mcs, target)`
   answers "what GP-average do I need across my remaining modules to reach this CAP?"

3. S/U what-ifs — `su_impact(entries, code)` answers "if I S/U this one graded module,
   how does my CAP change?" and `recommend_sus(entries, budget_mcs)` greedily picks the
   set of S/Us within a budget that maximises CAP gain.

The S/U logic models NUS's policy at a high level: each student gets a fixed budget of
S/U-able MCs across their degree (typically ~32 for incoming students). The recommend
function takes the budget as input — it's the caller's job to know what the user has
left to spend. We don't enforce module-level S/U eligibility here (some modules don't
allow S/U at all); the caller is expected to filter ineligible modules out before
asking for advice. F6-1 in features/FLAGS.md tracks adding eligibility metadata.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

GRADE_POINTS = {
    "A+": 5.0, "A": 5.0, "A-": 4.5,
    "B+": 4.0, "B": 3.5, "B-": 3.0,
    "C+": 2.5, "C": 2.0,
    "D+": 1.5, "D": 1.0,
    "F": 0.0,
}

# Highest grade in the scale. Used to detect impossible CAP targets.
MAX_GP = 5.0


def grade_points(grade: str | None) -> float | None:
    if grade is None:
        return None
    return GRADE_POINTS.get(grade)


# ---------------- existing: compute_cap ----------------

def compute_cap(entries: list[dict]) -> dict:
    """Given a list of plan-entry dicts (with `grade`, `is_su`, and joined `mcs`),
    return both pre-S/U and post-S/U CAP.

    Each entry must include: grade (str|None), is_su (0/1), mcs (int|float).
    Entries with no grade contribute nothing to CAP but their MCs still count
    toward graduation elsewhere — see progress.py.
    """
    pre_pts, pre_mcs = 0.0, 0.0
    post_pts, post_mcs = 0.0, 0.0
    su_mcs = 0.0

    for e in entries:
        grade = e.get("grade")
        if not grade:
            continue
        pts = GRADE_POINTS.get(grade)
        if pts is None:
            continue
        mcs = float(e.get("mcs") or 0)
        if mcs == 0:
            continue

        pre_pts += pts * mcs
        pre_mcs += mcs

        if e.get("is_su"):
            su_mcs += mcs
        else:
            post_pts += pts * mcs
            post_mcs += mcs

    return {
        "pre_su":  {"cap": round(pre_pts  / pre_mcs,  3) if pre_mcs  else 0.0, "mcs": pre_mcs},
        "post_su": {"cap": round(post_pts / post_mcs, 3) if post_mcs else 0.0, "mcs": post_mcs},
        "su_used_mcs": su_mcs,
    }


# ---------------- new: target CAP planning ----------------

@dataclass
class TargetResult:
    """Outcome of a target-CAP query."""
    target_cap: float                 # the goal the user asked about
    current_cap: float                # CAP based on entries graded so far (non-S/U)
    current_mcs: float                # graded non-S/U MCs counted so far
    remaining_mcs: float              # MCs still to come (ungraded or planned)
    required_avg_gp: float | None     # required average GP across remaining MCs; None if remaining is 0
    achievable: bool                  # False if required_avg_gp > MAX_GP
    note: str                         # human-readable summary

    def as_dict(self):
        return {
            "target_cap": self.target_cap,
            "current_cap": self.current_cap,
            "current_mcs": self.current_mcs,
            "remaining_mcs": self.remaining_mcs,
            "required_avg_gp": self.required_avg_gp,
            "achievable": self.achievable,
            "note": self.note,
        }


def required_avg_for_target(
    current_pts: float,
    current_mcs: float,
    remaining_mcs: float,
    target_cap: float,
) -> TargetResult:
    """Given:
      - current_pts = sum of (grade_points × MCs) for graded non-S/U modules
      - current_mcs = sum of MCs of graded non-S/U modules
      - remaining_mcs = MCs still to be graded (ungraded entries or planned-future modules)
      - target_cap   = the CAP the user wants

    Solve for the required average grade-points across the remaining MCs.

    Math:  (current_pts + remaining_mcs * x) / (current_mcs + remaining_mcs) = target
       =>  x = (target * (current_mcs + remaining_mcs) - current_pts) / remaining_mcs

    Edge cases:
      - remaining_mcs == 0: no slack to adjust — return achievability based on current CAP.
      - x > MAX_GP: target is unreachable (would need above-A grades on remaining).
      - x < 0: target is already exceeded — any grade on remaining keeps you above target.
    """
    current_cap = round(current_pts / current_mcs, 3) if current_mcs else 0.0

    if remaining_mcs <= 0:
        # Nothing left to take. Achievable iff current CAP meets the target.
        achievable = current_cap >= target_cap - 1e-9
        return TargetResult(
            target_cap=target_cap,
            current_cap=current_cap,
            current_mcs=current_mcs,
            remaining_mcs=0.0,
            required_avg_gp=None,
            achievable=achievable,
            note=(
                f"You've already hit {current_cap:.3f} and have no graded MCs left to take."
                if achievable
                else f"With no graded MCs remaining, your CAP is locked at {current_cap:.3f}."
            ),
        )

    total_mcs = current_mcs + remaining_mcs
    required_pts_total = target_cap * total_mcs
    required_pts_remaining = required_pts_total - current_pts
    x = required_pts_remaining / remaining_mcs

    if x > MAX_GP + 1e-9:
        return TargetResult(
            target_cap=target_cap,
            current_cap=current_cap,
            current_mcs=current_mcs,
            remaining_mcs=remaining_mcs,
            required_avg_gp=round(x, 3),
            achievable=False,
            note=(
                f"Reaching {target_cap:.2f} would require an average of "
                f"{x:.2f} GP across your remaining {remaining_mcs:g} MCs, "
                f"but the maximum possible is {MAX_GP:.1f}."
            ),
        )

    if x <= 0:
        # Even an F average would keep them above target.
        return TargetResult(
            target_cap=target_cap,
            current_cap=current_cap,
            current_mcs=current_mcs,
            remaining_mcs=remaining_mcs,
            required_avg_gp=0.0,
            achievable=True,
            note=(
                f"You're already past {target_cap:.2f}. Even straight Fs from here "
                f"would keep you above target."
            ),
        )

    return TargetResult(
        target_cap=target_cap,
        current_cap=current_cap,
        current_mcs=current_mcs,
        remaining_mcs=remaining_mcs,
        required_avg_gp=round(x, 3),
        achievable=True,
        note=(
            f"You need an average of {x:.2f} GP across your remaining "
            f"{remaining_mcs:g} MCs to reach {target_cap:.2f}."
        ),
    )


def required_avg_from_entries(entries: list[dict], target_cap: float, remaining_mcs: float | None = None) -> TargetResult:
    """Convenience wrapper for `required_avg_for_target` that accepts plan entries directly.

    Treats graded non-S/U entries as `current_pts`/`current_mcs`. If `remaining_mcs` is
    None, treats every entry without a grade as remaining and sums their MCs.
    """
    current_pts = 0.0
    current_mcs = 0.0
    auto_remaining = 0.0

    for e in entries:
        mcs = float(e.get("mcs") or 0)
        grade = e.get("grade")
        if grade and not e.get("is_su"):
            pts = GRADE_POINTS.get(grade)
            if pts is not None:
                current_pts += pts * mcs
                current_mcs += mcs
        elif not grade and not e.get("is_su"):
            # Ungraded and not planned-as-S/U — counted as remaining.
            auto_remaining += mcs

    if remaining_mcs is None:
        remaining_mcs = auto_remaining
    return required_avg_for_target(current_pts, current_mcs, float(remaining_mcs), float(target_cap))


# ---------------- new: S/U what-ifs ----------------

@dataclass
class SUImpact:
    """How toggling S/U on one entry affects post-S/U CAP."""
    module_code: str
    mcs: float
    grade: str
    grade_points: float
    current_post_su_cap: float
    cap_if_sud: float
    delta: float           # positive = S/U helps
    helps: bool

    def as_dict(self):
        return {
            "module_code": self.module_code,
            "mcs": self.mcs,
            "grade": self.grade,
            "grade_points": self.grade_points,
            "current_post_su_cap": self.current_post_su_cap,
            "cap_if_sud": self.cap_if_sud,
            "delta": self.delta,
            "helps": self.helps,
        }


def _post_su_cap(entries: Iterable[dict]) -> tuple[float, float]:
    """Sum (pts, mcs) over graded non-S/U entries. Returns (post_pts, post_mcs)."""
    pts_total = 0.0
    mcs_total = 0.0
    for e in entries:
        if not e.get("grade") or e.get("is_su"):
            continue
        pts = GRADE_POINTS.get(e["grade"])
        if pts is None:
            continue
        mcs = float(e.get("mcs") or 0)
        pts_total += pts * mcs
        mcs_total += mcs
    return pts_total, mcs_total


def su_impact(entries: list[dict], target_code: str) -> SUImpact | None:
    """Return the CAP impact of S/U-ing exactly one currently-graded module.

    Returns None if the module isn't found, has no grade, or is already S/U'd.

    "Helps" semantics: positive delta means post-S/U CAP goes UP after the toggle.
    A module's S/U helps iff its grade-points are below the current post-S/U CAP
    (mathematically: removing a below-average entry raises the average).
    """
    target_code = target_code.upper()
    target = None
    for e in entries:
        if (e.get("module_code") or "").upper() == target_code:
            target = e
            break
    if target is None or not target.get("grade") or target.get("is_su"):
        return None

    pts = GRADE_POINTS.get(target["grade"])
    if pts is None:
        return None
    mcs = float(target.get("mcs") or 0)
    if mcs <= 0:
        return None

    post_pts, post_mcs = _post_su_cap(entries)
    current_cap = post_pts / post_mcs if post_mcs else 0.0

    new_pts = post_pts - pts * mcs
    new_mcs = post_mcs - mcs
    new_cap = new_pts / new_mcs if new_mcs else 0.0

    delta = new_cap - current_cap
    return SUImpact(
        module_code=target_code,
        mcs=mcs,
        grade=target["grade"],
        grade_points=pts,
        current_post_su_cap=round(current_cap, 3),
        cap_if_sud=round(new_cap, 3),
        delta=round(delta, 3),
        helps=delta > 0,
    )


def recommend_sus(entries: list[dict], budget_mcs: float) -> dict:
    """Recommend which graded modules to S/U to maximise CAP, within an MC budget.

    Greedy by grade-points-ascending: S/U-ing your lowest-graded module always
    helps most (it's furthest below the average). This is provably optimal for
    the CAP-maximisation problem subject to a total-MCs constraint, because the
    objective is separable: each S/U either removes a below-average entry
    (helping) or above-average (hurting), and the marginal benefit per MC is
    monotonic in the grade.

    Excludes modules already S/U'd and modules with no grade.

    Returns:
      {
        "current_cap":    float
        "recommended":    [SUImpact-as-dict, ...]  # ordered: highest CAP gain first
        "projected_cap":  float                    # CAP after applying all recommendations
        "mcs_used":       float
        "budget_mcs":     float
      }

    Notes:
      - S/U-ing an above-average grade REDUCES your CAP. We never recommend
        those, regardless of remaining budget.
      - We recompute the post-S/U CAP between iterations so each step picks
        the truly best remaining S/U. This matters because the "average" shifts
        after each removal.
    """
    # Build a working list of S/U-able candidates: graded, not S/U'd, has known grade-points.
    candidates = []
    for e in entries:
        if not e.get("grade") or e.get("is_su"):
            continue
        pts = GRADE_POINTS.get(e["grade"])
        if pts is None:
            continue
        mcs = float(e.get("mcs") or 0)
        if mcs <= 0:
            continue
        candidates.append({
            "module_code": (e.get("module_code") or "").upper(),
            "grade": e["grade"],
            "grade_points": pts,
            "mcs": mcs,
        })

    current_pts, current_mcs = _post_su_cap(entries)
    starting_cap = current_pts / current_mcs if current_mcs else 0.0
    starting_cap_rounded = round(starting_cap, 3)

    recommended: list[dict] = []
    used_mcs = 0.0

    # Iterate, picking the entry whose removal maximises CAP, while it still
    # helps and fits the budget.
    remaining = list(candidates)
    while remaining and used_mcs < budget_mcs - 1e-9:
        post_pts = current_pts
        post_mcs = current_mcs
        cap_now = post_pts / post_mcs if post_mcs else 0.0

        best = None
        best_delta = 0.0
        for c in remaining:
            if used_mcs + c["mcs"] > budget_mcs + 1e-9:
                continue  # doesn't fit budget
            new_pts = post_pts - c["grade_points"] * c["mcs"]
            new_mcs = post_mcs - c["mcs"]
            new_cap = new_pts / new_mcs if new_mcs else 0.0
            delta = new_cap - cap_now
            if delta > best_delta + 1e-9:
                best_delta = delta
                best = (c, new_cap, new_pts, new_mcs)

        if best is None:
            break  # nothing left that helps within budget

        c, new_cap, new_pts, new_mcs = best
        recommended.append({
            "module_code": c["module_code"],
            "mcs": c["mcs"],
            "grade": c["grade"],
            "grade_points": c["grade_points"],
            "cap_before": round(cap_now, 3),
            "cap_after": round(new_cap, 3),
            "delta": round(new_cap - cap_now, 3),
        })
        current_pts = new_pts
        current_mcs = new_mcs
        used_mcs += c["mcs"]
        remaining.remove(c)

    projected_cap = current_pts / current_mcs if current_mcs else 0.0
    return {
        "current_cap": starting_cap_rounded,
        "recommended": recommended,
        "projected_cap": round(projected_cap, 3),
        "mcs_used": used_mcs,
        "budget_mcs": budget_mcs,
    }


# ---------------- new: full scenario simulation ----------------

def simulate(entries: list[dict], overrides: dict) -> dict:
    """Apply per-entry overrides and recompute CAP.

    `overrides` is a dict keyed by entry id (as int or string) with values like:
        {
          "grade": "A-",      # set or change grade
          "is_su": True       # toggle S/U
        }
    Any field can be omitted; only the keys provided are overridden. Pass
    `"grade": null` to clear a grade.

    Returns the same shape as `compute_cap` plus a `changes_applied` count.
    """
    # Normalize keys to strings so callers can pass ints or strings interchangeably.
    norm_overrides = {str(k): v for k, v in (overrides or {}).items()}

    merged = []
    applied = 0
    for e in entries:
        eid_key = str(e.get("id")) if e.get("id") is not None else None
        if eid_key and eid_key in norm_overrides:
            ovr = norm_overrides[eid_key]
            new_entry = dict(e)
            if "grade" in ovr:
                new_entry["grade"] = ovr["grade"]  # may be None to clear
            if "is_su" in ovr:
                new_entry["is_su"] = bool(ovr["is_su"])
            merged.append(new_entry)
            applied += 1
        else:
            merged.append(e)

    result = compute_cap(merged)
    result["changes_applied"] = applied
    return result
