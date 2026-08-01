"""Unit tests for services/badges.py — each check function exercised
against the data dict.

Run: python tests/test_badges.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.badges import CATALOG, catalog_as_list, evaluate


def assert_eq(a, b, label):
    status = "✓" if a == b else "✗"
    print(f"  {status} {label}: got {a!r}")
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


def _data(**overrides):
    """Empty/zero baseline. Tests override only what they care about so each
    case stays focused on one signal."""
    base = {
        "total_entries": 0,
        "mcs_by_year": {},
        "nonempty_semesters": set(),
        "total_placed_mcs": 0.0,
        "required_mcs": 128,
        "graded_count": 0,
        "su_count": 0,
        "shares_sent": 0,
        "optin_count": 0,
        "max_optin_others": 0,
    }
    base.update(overrides)
    return base


def test_empty_user_earns_nothing():
    print("\n[empty user → no badges]")
    out = evaluate(_data())
    earned = [k for k, v in out.items() if v]
    assert_eq(earned, [], "no badges on empty user")


def test_first_module():
    print("\n[first-module]")
    assert_eq(evaluate(_data(total_entries=0))["first-module"], False, "0 entries")
    assert_eq(evaluate(_data(total_entries=1))["first-module"], True, "1 entry earns it")


def test_first_year():
    print("\n[first-year: 20+ MC in Y1]")
    assert_eq(evaluate(_data(mcs_by_year={1: 16}))["first-year"], False, "under 20")
    assert_eq(evaluate(_data(mcs_by_year={1: 20}))["first-year"], True, "exactly 20")
    assert_eq(evaluate(_data(mcs_by_year={1: 24}))["first-year"], True, "over 20")
    # MC in Y2 doesn't count for first-year
    assert_eq(evaluate(_data(mcs_by_year={2: 24}))["first-year"], False, "Y2 doesn't count")


def test_full_map():
    print("\n[full-map: all 8 semesters]")
    seven = {f"Y{y}S{s}" for y in range(1, 5) for s in range(1, 3)} - {"Y4S2"}
    eight = {f"Y{y}S{s}" for y in range(1, 5) for s in range(1, 3)}
    assert_eq(evaluate(_data(nonempty_semesters=seven))["full-map"], False, "7/8 semesters")
    assert_eq(evaluate(_data(nonempty_semesters=eight))["full-map"], True, "8/8 earns it")


def test_near_graduation():
    print("\n[near-graduation: 80%+ of required MCs]")
    assert_eq(evaluate(_data(required_mcs=128, total_placed_mcs=100))["near-graduation"], False,
              "100/128 = 78%")
    assert_eq(evaluate(_data(required_mcs=128, total_placed_mcs=102.4))["near-graduation"], True,
              "exactly 80%")
    assert_eq(evaluate(_data(required_mcs=128, total_placed_mcs=130))["near-graduation"], True,
              "over 100%")
    # Edge: required_mcs == 0 → never earned (no graduation requirement)
    assert_eq(evaluate(_data(required_mcs=0, total_placed_mcs=100))["near-graduation"], False,
              "no required MCs → not earned")


def test_first_grade():
    print("\n[first-grade]")
    assert_eq(evaluate(_data(graded_count=0))["first-grade"], False, "no grades")
    assert_eq(evaluate(_data(graded_count=1))["first-grade"], True, "1 grade earns it")


def test_engaged_grader():
    print("\n[engaged-grader: 5+ grades]")
    assert_eq(evaluate(_data(graded_count=4))["engaged-grader"], False, "4 grades")
    assert_eq(evaluate(_data(graded_count=5))["engaged-grader"], True, "5 grades")


def test_su_aware():
    print("\n[su-aware]")
    assert_eq(evaluate(_data(su_count=0))["su-aware"], False, "no S/U")
    assert_eq(evaluate(_data(su_count=1))["su-aware"], True, "1 S/U earns it")


def test_collaborator():
    print("\n[collaborator: shared a plan]")
    assert_eq(evaluate(_data(shares_sent=0))["collaborator"], False, "no shares")
    assert_eq(evaluate(_data(shares_sent=1))["collaborator"], True, "1 share earns it")


def test_networker():
    print("\n[networker: opted into a study group]")
    assert_eq(evaluate(_data(optin_count=0))["networker"], False, "no optins")
    assert_eq(evaluate(_data(optin_count=1))["networker"], True, "1 optin earns it")


def test_popular_signup():
    print("\n[popular-signup: opt-in with 3+ others]")
    assert_eq(evaluate(_data(max_optin_others=2))["popular-signup"], False, "2 others")
    assert_eq(evaluate(_data(max_optin_others=3))["popular-signup"], True, "3 others earns it")


def test_catalog_shape():
    print("\n[catalog: 10 badges, 3 tiers]")
    catalog = catalog_as_list()
    assert_eq(len(catalog), 10, "10 badges in catalog")
    tiers = {b["tier"] for b in catalog}
    assert_eq(tiers, {"Building", "Tracking", "Community"}, "three tiers")
    keys = [b["key"] for b in catalog]
    assert_eq(len(set(keys)), len(keys), "all keys unique")
    # Each badge has required display fields
    for b in catalog:
        for field in ("key", "title", "description", "tier"):
            assert b[field], f"{b.get('key', '?')} missing {field}"


def test_evaluate_returns_all_keys():
    print("\n[evaluate covers every catalog entry]")
    out = evaluate(_data())
    assert_eq(set(out.keys()), {b.key for b in CATALOG}, "every catalog key in output")


if __name__ == "__main__":
    print("Running badges service tests…")
    test_empty_user_earns_nothing()
    test_first_module()
    test_first_year()
    test_full_map()
    test_near_graduation()
    test_first_grade()
    test_engaged_grader()
    test_su_aware()
    test_collaborator()
    test_networker()
    test_popular_signup()
    test_catalog_shape()
    test_evaluate_returns_all_keys()
    print("\nAll tests passed ✓")
