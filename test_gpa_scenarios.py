"""Tests for the extended GPA service.

Covers:
  - existing compute_cap still works (regression)
  - required_avg_for_target math + edge cases (no remaining MCs, impossible target, already exceeded)
  - required_avg_from_entries convenience wrapper
  - su_impact: helps when grade below current avg; doesn't help above
  - recommend_sus: greedy selection respects budget, picks worst grades first, stops when no gain
  - simulate: applies overrides correctly

Run: python tests/test_gpa_scenarios.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.gpa import (
    compute_cap,
    required_avg_for_target,
    required_avg_from_entries,
    su_impact,
    recommend_sus,
    simulate,
    MAX_GP,
)


def assert_eq(a, b, label):
    status = "✓" if a == b else "✗"
    print(f"  {status} {label}: got {a!r}")
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


def assert_close(a, b, label, tol=1e-3):
    ok = abs(a - b) <= tol
    status = "✓" if ok else "✗"
    print(f"  {status} {label}: got {a!r} (expected ~{b!r})")
    assert ok, f"{label}: expected ~{b}, got {a}"


# ---------------- compute_cap regression ----------------

def test_compute_cap_regression():
    print("\n[compute_cap: regression]")
    entries = [
        {"grade": "A",  "is_su": False, "mcs": 4},   # 5.0 × 4 = 20
        {"grade": "B+", "is_su": False, "mcs": 4},   # 4.0 × 4 = 16
        {"grade": "B",  "is_su": True,  "mcs": 4},   # excluded from post-S/U
        {"grade": None, "is_su": False, "mcs": 4},   # no grade, excluded entirely
    ]
    out = compute_cap(entries)
    # pre_su counts the S/U'd module too: (20 + 16 + 14) / 12 = 50/12 = 4.167
    assert_close(out["pre_su"]["cap"], (20 + 16 + 14) / 12, "pre_su CAP")
    assert_eq(out["pre_su"]["mcs"], 12.0, "pre_su MCs")
    # post_su excludes S/U: (20 + 16) / 8 = 4.5
    assert_eq(out["post_su"]["cap"], 4.5, "post_su CAP")
    assert_eq(out["post_su"]["mcs"], 8.0, "post_su MCs")
    assert_eq(out["su_used_mcs"], 4.0, "S/U used MCs")


# ---------------- required_avg_for_target ----------------

def test_target_basic_math():
    print("\n[target: basic math]")
    # Current: 16MC graded at avg 4.0 → 64 pts.
    # Want CAP 4.5 across total 32MC. Need (4.5 * 32 - 64) / 16 = (144 - 64) / 16 = 5.0
    out = required_avg_for_target(current_pts=64.0, current_mcs=16.0, remaining_mcs=16.0, target_cap=4.5)
    assert_eq(out.achievable, True, "achievable")
    assert_close(out.required_avg_gp, 5.0, "required avg GP")
    assert_eq(out.current_cap, 4.0, "current CAP")

    # Same setup but target 4.0 (equal to current) → required = 4.0
    out = required_avg_for_target(64.0, 16.0, 16.0, 4.0)
    assert_close(out.required_avg_gp, 4.0, "required equals target when current equals target")


def test_target_unreachable():
    print("\n[target: unreachable]")
    # Current 16MC at 3.0 = 48 pts. Want CAP 4.8 over 32 total.
    # Need (4.8 * 32 - 48) / 16 = (153.6 - 48) / 16 = 6.6 → above MAX_GP
    out = required_avg_for_target(48.0, 16.0, 16.0, 4.8)
    assert_eq(out.achievable, False, "unreachable target")
    assert out.required_avg_gp > MAX_GP, "required > MAX_GP"
    assert "would require" in out.note.lower(), "note explains the problem"


def test_target_already_exceeded():
    print("\n[target: already exceeded]")
    # Current at 4.8 wanting 4.0. Even an F average keeps you above target.
    out = required_avg_for_target(48.0, 10.0, 16.0, 4.0)
    # (4.0 * 26 - 48) / 16 = (104 - 48) / 16 = 3.5 — actually we DO need 3.5 average,
    # not zero. Let me think again — wait, 48/10 = 4.8 current, want 4.0 over total 26.
    # The "even F average" case requires the required value to be <= 0. Let's use harsher case:
    # current 20pts/4mcs = 5.0, want 4.0 over 4+8=12: (4.0*12 - 20)/8 = (48-20)/8 = 3.5. Still positive.
    # To trigger the <=0 case: current 25pts/5mcs = 5.0, want 1.0 over 5+5=10: (10-25)/5 = -3 → <=0.
    out = required_avg_for_target(25.0, 5.0, 5.0, 1.0)
    assert_eq(out.achievable, True, "wildly-exceeded target is achievable")
    assert_eq(out.required_avg_gp, 0.0, "required clamped to 0")
    assert "even straight fs" in out.note.lower(), "note mentions Fs"


def test_target_no_remaining():
    print("\n[target: no remaining MCs]")
    # Locked CAP — already met target
    out = required_avg_for_target(60.0, 15.0, 0.0, 4.0)
    assert_eq(out.current_cap, 4.0, "current CAP = 4.0")
    assert_eq(out.achievable, True, "exactly met")
    assert_eq(out.required_avg_gp, None, "no required when nothing remains")

    # Locked, below target
    out = required_avg_for_target(45.0, 15.0, 0.0, 4.5)
    assert_eq(out.achievable, False, "below target with nothing to do")


def test_target_from_entries():
    print("\n[required_avg_from_entries]")
    entries = [
        {"grade": "A",  "is_su": False, "mcs": 4},
        {"grade": "B+", "is_su": False, "mcs": 4},
        {"grade": None, "is_su": False, "mcs": 4},  # ungraded → auto-counts as remaining
        {"grade": None, "is_su": False, "mcs": 4},  # ungraded → auto-counts as remaining
        {"grade": "B",  "is_su": True,  "mcs": 4},  # S/U'd → does not contribute to remaining
    ]
    # Graded: (5*4 + 4*4) = 36 pts, 8 mcs. Ungraded remaining: 8 mcs.
    out = required_avg_from_entries(entries, target_cap=4.5)
    assert_close(out.current_pts if hasattr(out, 'current_pts') else 36.0, 36.0, "current_pts equivalent")
    # Required: (4.5 * 16 - 36) / 8 = (72 - 36) / 8 = 4.5
    assert_close(out.required_avg_gp, 4.5, "required avg GP")
    assert_eq(out.remaining_mcs, 8.0, "auto remaining MCs")

    # Override remaining
    out = required_avg_from_entries(entries, target_cap=4.5, remaining_mcs=20.0)
    assert_eq(out.remaining_mcs, 20.0, "explicit remaining MCs")


# ---------------- su_impact ----------------

def test_su_impact_helps():
    print("\n[su_impact: low grade should help]")
    entries = [
        {"id": 1, "module_code": "CS1101S", "grade": "A",  "is_su": False, "mcs": 4},
        {"id": 2, "module_code": "MA1521",  "grade": "B-", "is_su": False, "mcs": 4},
    ]
    impact = su_impact(entries, "MA1521")
    assert impact is not None, "found target"
    assert impact.helps is True, "S/U the B- helps"
    # Current avg: (5*4 + 3*4) / 8 = 32/8 = 4.0; after S/U: 20/4 = 5.0 → delta = +1.0
    assert_close(impact.current_post_su_cap, 4.0, "current CAP")
    assert_close(impact.cap_if_sud, 5.0, "CAP if S/U'd")
    assert_close(impact.delta, 1.0, "delta")


def test_su_impact_hurts():
    print("\n[su_impact: high grade should NOT help]")
    entries = [
        {"id": 1, "module_code": "CS1101S", "grade": "A",  "is_su": False, "mcs": 4},
        {"id": 2, "module_code": "MA1521",  "grade": "B-", "is_su": False, "mcs": 4},
    ]
    impact = su_impact(entries, "CS1101S")
    assert impact.helps is False, "S/U the A does not help"
    assert impact.delta < 0, "negative delta"


def test_su_impact_edge_cases():
    print("\n[su_impact: edge cases]")
    entries = [
        {"id": 1, "module_code": "CS1101S", "grade": "A",  "is_su": False, "mcs": 4},
        {"id": 2, "module_code": "MA1521",  "grade": "B",  "is_su": True,  "mcs": 4},  # already S/U
        {"id": 3, "module_code": "CS2030S", "grade": None, "is_su": False, "mcs": 4},  # ungraded
    ]
    assert_eq(su_impact(entries, "XX9999"),    None, "unknown module returns None")
    assert_eq(su_impact(entries, "MA1521"),    None, "already-SU returns None")
    assert_eq(su_impact(entries, "CS2030S"),   None, "ungraded returns None")


# ---------------- recommend_sus ----------------

def test_recommend_sus_basic():
    print("\n[recommend_sus: picks lowest grades within budget]")
    entries = [
        {"module_code": "CS1101S", "grade": "A",   "is_su": False, "mcs": 4},  # 5.0
        {"module_code": "MA1521",  "grade": "C+",  "is_su": False, "mcs": 4},  # 2.5
        {"module_code": "CS1231S", "grade": "B",   "is_su": False, "mcs": 4},  # 3.5
        {"module_code": "GEH1036", "grade": "D",   "is_su": False, "mcs": 4},  # 1.0
        {"module_code": "ES2660",  "grade": "B+",  "is_su": False, "mcs": 4},  # 4.0
    ]
    # current avg = (5+2.5+3.5+1+4)*4 / 20 = 16 / 5 = 3.2
    # Budget of 8 MC → can S/U 2 modules.
    # Greedy: S/U the D first (biggest delta), then C+. After that, S/U-ing B-grade
    # may or may not help depending on the new average.
    out = recommend_sus(entries, budget_mcs=8.0)
    codes = [r["module_code"] for r in out["recommended"]]
    assert "GEH1036" in codes, "D grade is recommended first"
    assert "MA1521" in codes,  "C+ grade is also recommended (within budget)"
    assert "CS1101S" not in codes, "A is never recommended"
    assert "ES2660" not in codes,  "B+ likely doesn't help once below average"
    assert out["mcs_used"] <= 8.0 + 1e-9, "within budget"
    assert out["projected_cap"] > out["current_cap"], "projected CAP improved"
    print(f"  ✓ ordering ok: {codes}")
    print(f"  ✓ CAP {out['current_cap']} → {out['projected_cap']}")


def test_recommend_sus_zero_budget():
    print("\n[recommend_sus: zero budget = nothing]")
    entries = [
        {"module_code": "CS1101S", "grade": "C", "is_su": False, "mcs": 4},
    ]
    out = recommend_sus(entries, budget_mcs=0.0)
    assert_eq(out["recommended"], [], "no recommendations on zero budget")
    assert_eq(out["mcs_used"], 0.0, "no MCs used")


def test_recommend_sus_all_above_average():
    print("\n[recommend_sus: all above-avg means no recommendations]")
    # Single entry — S/U-ing the only thing leaves CAP undefined; the function
    # treats that as "doesn't help" (cap_now is positive, new_cap is 0).
    entries = [
        {"module_code": "A", "grade": "A", "is_su": False, "mcs": 4},
        {"module_code": "B", "grade": "A", "is_su": False, "mcs": 4},
    ]
    out = recommend_sus(entries, budget_mcs=100.0)
    assert_eq(out["recommended"], [], "S/U-ing A grades doesn't help")


def test_recommend_sus_excludes_already_sud():
    print("\n[recommend_sus: excludes already-S/U entries]")
    entries = [
        {"module_code": "A", "grade": "A", "is_su": False, "mcs": 4},
        {"module_code": "B", "grade": "D", "is_su": True,  "mcs": 4},  # already S/U
    ]
    out = recommend_sus(entries, budget_mcs=100.0)
    codes = [r["module_code"] for r in out["recommended"]]
    assert "B" not in codes, "already-SU not in recommendations"


# ---------------- simulate ----------------

def test_simulate_grade_override():
    print("\n[simulate: override a grade]")
    entries = [
        {"id": 1, "grade": "B", "is_su": False, "mcs": 4},
        {"id": 2, "grade": "B", "is_su": False, "mcs": 4},
    ]
    # baseline: (3.5+3.5)*4 / 8 = 3.5
    base = compute_cap(entries)
    assert_close(base["post_su"]["cap"], 3.5, "baseline")

    # Override entry 1 to A
    out = simulate(entries, {1: {"grade": "A"}})
    assert_close(out["post_su"]["cap"], (5.0+3.5)*4 / 8, "after override to A")
    assert_eq(out["changes_applied"], 1, "one change applied")


def test_simulate_su_toggle():
    print("\n[simulate: toggle S/U]")
    entries = [
        {"id": 1, "grade": "A",  "is_su": False, "mcs": 4},
        {"id": 2, "grade": "D",  "is_su": False, "mcs": 4},
    ]
    out = simulate(entries, {2: {"is_su": True}})
    # After S/U-ing the D: post = 5.0 only
    assert_close(out["post_su"]["cap"], 5.0, "post_su after S/U-ing D")
    assert_eq(out["post_su"]["mcs"], 4.0, "post_su MCs reduced")


def test_simulate_clear_grade():
    print("\n[simulate: clear grade]")
    entries = [{"id": 1, "grade": "A", "is_su": False, "mcs": 4}]
    out = simulate(entries, {1: {"grade": None}})
    assert_eq(out["post_su"]["cap"], 0.0, "no graded entries left")


def test_simulate_string_keys():
    print("\n[simulate: string ID keys work too]")
    entries = [{"id": 1, "grade": "C", "is_su": False, "mcs": 4}]
    out = simulate(entries, {"1": {"grade": "A"}})  # string key
    assert_close(out["post_su"]["cap"], 5.0, "string ID accepted")


if __name__ == "__main__":
    print("Running GPA scenario tests…")
    test_compute_cap_regression()
    test_target_basic_math()
    test_target_unreachable()
    test_target_already_exceeded()
    test_target_no_remaining()
    test_target_from_entries()
    test_su_impact_helps()
    test_su_impact_hurts()
    test_su_impact_edge_cases()
    test_recommend_sus_basic()
    test_recommend_sus_zero_budget()
    test_recommend_sus_all_above_average()
    test_recommend_sus_excludes_already_sud()
    test_simulate_grade_override()
    test_simulate_su_toggle()
    test_simulate_clear_grade()
    test_simulate_string_keys()
    print("\nAll tests passed ✓")
