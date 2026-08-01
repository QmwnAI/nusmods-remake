"""Tests for the prereq tree evaluator.

Run from the backend directory: python -m pytest tests/

Or without pytest installed:
    python -m tests.test_prereqs
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.prereqs import prereqs_met, explain_unmet, collect_required_codes


def assert_eq(a, b, label):
    status = "✓" if a == b else "✗"
    print(f"  {status} {label}: got {a!r}")
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


def test_empty():
    print("\n[empty/None trees]")
    assert_eq(prereqs_met(None, []), True, "None is always met")
    assert_eq(prereqs_met("", []), True, "empty string is always met")


def test_single():
    print("\n[single module]")
    assert_eq(prereqs_met("CS1101S", []), False, "missing")
    assert_eq(prereqs_met("CS1101S", ["CS1101S"]), True, "present")
    assert_eq(prereqs_met("CS1101S", ["cs1101s"]), True, "case-insensitive")


def test_and():
    print("\n[AND]")
    tree = {"and": ["CS1101S", "MA1521"]}
    assert_eq(prereqs_met(tree, ["CS1101S"]), False, "partial AND")
    assert_eq(prereqs_met(tree, ["CS1101S", "MA1521"]), True, "full AND")


def test_or():
    print("\n[OR]")
    tree = {"or": ["CS1101S", "CS1010S"]}
    assert_eq(prereqs_met(tree, []), False, "no options met")
    assert_eq(prereqs_met(tree, ["CS1010S"]), True, "second option met")


def test_nested():
    print("\n[nested AND of ORs]")
    # CS2040S: requires CS1101S (or CS1010S) AND CS1231S
    tree = {"and": [
        {"or": ["CS1101S", "CS1010S"]},
        "CS1231S",
    ]}
    assert_eq(prereqs_met(tree, ["CS1101S"]), False, "missing CS1231S")
    assert_eq(prereqs_met(tree, ["CS1010S", "CS1231S"]), True, "OR via fallback")
    assert_eq(prereqs_met(tree, ["CS1101S", "CS1231S"]), True, "OR via primary")


def test_explain():
    print("\n[explain_unmet]")
    tree = {"and": ["CS1101S", {"or": ["MA1521", "MA1102R"]}]}
    msg = explain_unmet(tree, [])
    assert_eq(msg, "CS1101S and (MA1521 or MA1102R)", "both clauses missing")

    msg2 = explain_unmet(tree, ["CS1101S"])
    assert_eq(msg2, "MA1521 or MA1102R", "only OR clause missing")

    msg3 = explain_unmet(tree, ["CS1101S", "MA1521"])
    assert_eq(msg3, None, "everything met")


def test_collect():
    print("\n[collect_required_codes]")
    tree = {"and": ["CS1101S", {"or": ["MA1521", "MA1102R"]}]}
    assert_eq(collect_required_codes(tree), {"CS1101S", "MA1521", "MA1102R"}, "all codes")


def test_nof():
    print("\n[nOf]")
    # NUSMods occasionally uses "any N of these"
    tree = {"nOf": [2, ["CS1101S", "CS1231S", "MA1521"]]}
    assert_eq(prereqs_met(tree, ["CS1101S"]), False, "only 1 of 2")
    assert_eq(prereqs_met(tree, ["CS1101S", "MA1521"]), True, "exactly 2")


if __name__ == "__main__":
    print("Running prereq tests…")
    test_empty()
    test_single()
    test_and()
    test_or()
    test_nested()
    test_explain()
    test_collect()
    test_nof()
    print("\nAll tests passed ✓")
