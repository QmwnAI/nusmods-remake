"""Tests for the study group match scoring service.

Covers:
  - score_match: each signal contributes independently
  - Same-major + same-year stack
  - Plan overlap scales with Jaccard
  - Recency window: today scores, last year doesn't
  - rank_matches: ordering by score desc, deterministic tiebreak
  - Empty plan modules → no overlap signal but other signals still work
  - Missing major/matric_year on either side → no false matches

Run: python tests/test_study_group_match.py
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.study_group_match import (
    MatchCandidate,
    rank_matches,
    score_match,
    WEIGHT_SAME_MAJOR,
    WEIGHT_SAME_YEAR,
    WEIGHT_PLAN_OVERLAP,
    WEIGHT_RECENCY,
    RECENCY_WINDOW_DAYS,
)


def assert_eq(a, b, label):
    status = "✓" if a == b else "✗"
    print(f"  {status} {label}: got {a!r}")
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


def assert_true(v, label):
    status = "✓" if v else "✗"
    print(f"  {status} {label}: got {v!r}")
    assert v, label


def _cand(**kwargs):
    """Build a MatchCandidate with sensible defaults so each test only
    expresses what's different."""
    return MatchCandidate(
        user_id=kwargs.get("user_id", "u1"),
        display_name=kwargs.get("display_name", "Test User"),
        email=kwargs.get("email", "test@example.com"),
        major_code=kwargs.get("major_code"),
        matric_year=kwargs.get("matric_year"),
        contact_telegram=kwargs.get("contact_telegram"),
        optin_id=kwargs.get("optin_id", 1),
        message=kwargs.get("message"),
        optin_created_at=kwargs.get("optin_created_at"),
        other_plan_modules=kwargs.get("other_plan_modules", set()),
    )


# ---------- individual signals ----------

def test_same_major_alone():
    print("\n[same major alone]")
    c = _cand(major_code="CS")
    s = score_match(me_major="CS", me_matric_year=None, me_plan_modules=set(), candidate=c)
    assert_true(s.same_major, "same_major flag set")
    assert_eq(s.score, int(round(WEIGHT_SAME_MAJOR)), "score = same-major weight")
    assert any("major" in r.lower() for r in s.reasons), "reason mentions major"


def test_same_year_alone():
    print("\n[same matric year alone]")
    c = _cand(matric_year=2024)
    s = score_match(me_major=None, me_matric_year=2024, me_plan_modules=set(), candidate=c)
    assert_true(s.same_year, "same_year flag set")
    assert_eq(s.score, int(round(WEIGHT_SAME_YEAR)), "score = same-year weight")


def test_plan_overlap_perfect():
    print("\n[plan overlap perfect = full weight]")
    c = _cand(other_plan_modules={"CS2030S", "CS2040S"})
    s = score_match(
        me_major=None, me_matric_year=None,
        me_plan_modules={"CS2030S", "CS2040S"},
        candidate=c,
    )
    assert_eq(s.plan_overlap_count, 2, "overlap count")
    assert_eq(s.score, int(round(WEIGHT_PLAN_OVERLAP)), "score = full overlap weight (jaccard=1)")


def test_plan_overlap_partial():
    print("\n[plan overlap partial scales with Jaccard]")
    # Me: {A, B, C}, Other: {B, C, D, E}. Intersection 2, union 5, jaccard 0.4.
    c = _cand(other_plan_modules={"B", "C", "D", "E"})
    s = score_match(
        me_major=None, me_matric_year=None,
        me_plan_modules={"A", "B", "C"},
        candidate=c,
    )
    assert_eq(s.plan_overlap_count, 2, "overlap count")
    expected = int(round(WEIGHT_PLAN_OVERLAP * 0.4))
    assert_eq(s.score, expected, "score = overlap weight × jaccard 0.4")


def test_no_overlap():
    print("\n[disjoint plans → no overlap signal]")
    c = _cand(other_plan_modules={"X", "Y"})
    s = score_match(
        me_major=None, me_matric_year=None,
        me_plan_modules={"A", "B"},
        candidate=c,
    )
    assert_eq(s.plan_overlap_count, 0, "no overlap")
    assert_eq(s.score, 0, "no overlap → 0 (no other signal)")


def test_recency_bonus():
    print("\n[recency window]")
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    # Within window
    fresh = _cand(optin_created_at=(now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"))
    s = score_match(me_major=None, me_matric_year=None, me_plan_modules=set(),
                    candidate=fresh, now=now)
    assert_true(s.recent, "recent flag set within window")
    assert s.score >= WEIGHT_RECENCY, "recency contributes"

    # Outside window
    old = _cand(optin_created_at=(now - timedelta(days=RECENCY_WINDOW_DAYS + 5))
                .strftime("%Y-%m-%d %H:%M:%S"))
    s_old = score_match(me_major=None, me_matric_year=None, me_plan_modules=set(),
                        candidate=old, now=now)
    assert not s_old.recent, "outside window — not recent"


def test_recency_only_shown_when_no_other_reason():
    print("\n[recency reason is hidden when major/year/overlap fired]")
    # Recent + same major: reason should be "Same major", NOT "Joined recently".
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    c = _cand(major_code="CS",
              optin_created_at=(now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"))
    s = score_match(me_major="CS", me_matric_year=None, me_plan_modules=set(),
                    candidate=c, now=now)
    assert_true(s.recent, "is recent")
    assert all("recently" not in r.lower() for r in s.reasons), "recency suppressed when other signal present"


# ---------- composite + edge cases ----------

def test_stacking_signals():
    print("\n[same major + same year + 50% overlap]")
    c = _cand(major_code="CS", matric_year=2024, other_plan_modules={"A", "B"})
    s = score_match(
        me_major="CS", me_matric_year=2024,
        me_plan_modules={"A", "B", "C", "D"},   # jaccard = 2/4 = 0.5
        candidate=c,
    )
    expected = int(round(WEIGHT_SAME_MAJOR + WEIGHT_SAME_YEAR + WEIGHT_PLAN_OVERLAP * 0.5))
    assert_eq(s.score, expected, "stacked signals add up")
    assert len(s.reasons) >= 3, "three reasons surfaced"


def test_missing_profile_no_match():
    print("\n[missing major/year on either side → no false bonus]")
    # Both None → no signal even though "None == None"
    c = _cand(major_code=None, matric_year=None)
    s = score_match(me_major=None, me_matric_year=None,
                    me_plan_modules=set(), candidate=c)
    assert not s.same_major, "no same_major when both null"
    assert not s.same_year, "no same_year when both null"

    # Me set, candidate None
    c2 = _cand(major_code=None, matric_year=None)
    s2 = score_match(me_major="CS", me_matric_year=2024,
                     me_plan_modules=set(), candidate=c2)
    assert not s2.same_major, "no match when candidate has no major"
    assert_eq(s2.score, 0, "no signal → 0")


def test_score_clamped_to_100():
    print("\n[score is clamped to 100]")
    # Engineering an impossibly high score: all signals at max
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    c = _cand(
        major_code="CS", matric_year=2024,
        other_plan_modules={"A", "B", "C"},
        optin_created_at=now.strftime("%Y-%m-%d %H:%M:%S"),
    )
    s = score_match(me_major="CS", me_matric_year=2024,
                    me_plan_modules={"A", "B", "C"},
                    candidate=c, now=now)
    assert s.score <= 100, "score capped at 100"


def test_rank_matches_ordering():
    print("\n[rank_matches: score desc, alphabetical tiebreak]")
    candidates = [
        _cand(user_id="u-a", major_code="CS", matric_year=2024),     # both major+year
        _cand(user_id="u-b", major_code="CS"),                        # major only
        _cand(user_id="u-c", major_code="CS", matric_year=2024),     # both, tied with u-a
        _cand(user_id="u-d"),                                          # nothing
    ]
    out = rank_matches(
        me_major="CS", me_matric_year=2024, me_plan_modules=set(),
        candidates=candidates,
    )
    ids = [m.candidate.user_id for m in out]
    # u-a and u-c tied (both major+year); alphabetical → u-a then u-c.
    # u-b next (major only). u-d last (no signal).
    assert_eq(ids, ["u-a", "u-c", "u-b", "u-d"], "deterministic order")


def test_empty_candidates():
    print("\n[empty candidate list]")
    assert_eq(rank_matches(me_major="CS", me_matric_year=2024,
                           me_plan_modules=set(), candidates=[]),
              [], "empty in, empty out")


def test_generic_reason_when_no_signals():
    print("\n[fallback reason when no signals fire]")
    c = _cand(user_id="u-x")
    s = score_match(me_major=None, me_matric_year=None,
                    me_plan_modules=set(), candidate=c)
    assert s.reasons, "reasons never empty"
    assert "Taking this module" in s.reasons, "generic acknowledgement present"


if __name__ == "__main__":
    print("Running study group match scoring tests…")
    test_same_major_alone()
    test_same_year_alone()
    test_plan_overlap_perfect()
    test_plan_overlap_partial()
    test_no_overlap()
    test_recency_bonus()
    test_recency_only_shown_when_no_other_reason()
    test_stacking_signals()
    test_missing_profile_no_match()
    test_score_clamped_to_100()
    test_rank_matches_ordering()
    test_empty_candidates()
    test_generic_reason_when_no_signals()
    print("\nAll tests passed ✓")
