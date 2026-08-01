"""Tests for the validation service and the new parsing helpers in prereqs.

Covers:
  - parse_corequisite_string for the common shapes
  - extract_preclusion_codes for varied separators
  - corequisites_met semantics (same-semester counts)
  - The full validate() pipeline producing prereq / coreq / preclusion / not-offered violations
  - find_ready_modules suggesting only valid candidates

Run: python tests/test_validation.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.prereqs import (
    parse_corequisite_string,
    extract_preclusion_codes,
    corequisites_met,
)
from services import validation
from services.validation import (
    PlanEntry,
    validate,
    find_ready_modules,
    PREREQ_UNMET,
    COREQ_UNMET,
    PRECLUSION,
    NOT_OFFERED,
)


def assert_eq(a, b, label):
    status = "✓" if a == b else "✗"
    print(f"  {status} {label}: got {a!r}")
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


# ---------- Parsing ----------

def test_parse_corequisite_string():
    print("\n[parse_corequisite_string]")
    assert_eq(parse_corequisite_string(None), None, "None")
    assert_eq(parse_corequisite_string(""), None, "empty")
    assert_eq(parse_corequisite_string("CS2101"), "CS2101", "single code")
    assert_eq(parse_corequisite_string("  cs2101  "), "CS2101", "whitespace + lowercase normalized")
    assert_eq(
        parse_corequisite_string("CS2101 and CS3203"),
        {"and": ["CS2101", "CS3203"]},
        "and pair",
    )
    assert_eq(
        parse_corequisite_string("CS2101 or ES2660"),
        {"or": ["CS2101", "ES2660"]},
        "or pair",
    )
    # Combined and/or: AND of OR-groups
    result = parse_corequisite_string("CS2101 and CS3203 or CS3215")
    assert isinstance(result, dict), "combined produced dict"
    print(f"  ✓ combined produced dict: got {result!r}")
    # Garbage falls back to raw
    raw = parse_corequisite_string("must be discussed with prof")
    assert isinstance(raw, dict) and "raw" in raw, "garbage falls back to {raw: ...}"
    print(f"  ✓ garbage falls back to raw: got {raw!r}")


def test_extract_preclusion_codes():
    print("\n[extract_preclusion_codes]")
    assert_eq(extract_preclusion_codes(None), set(), "None")
    assert_eq(extract_preclusion_codes(""), set(), "empty")
    assert_eq(extract_preclusion_codes("CS2030"), {"CS2030"}, "single")
    assert_eq(
        extract_preclusion_codes("CS2030, CS2030DE"),
        {"CS2030", "CS2030DE"},
        "comma-separated",
    )
    assert_eq(
        extract_preclusion_codes("CS2030; CS2030DE / IT5001"),
        {"CS2030", "CS2030DE", "IT5001"},
        "mixed separators",
    )
    # Case-insensitive in, uppercase out
    assert_eq(extract_preclusion_codes("cs2030, cs2030de"), {"CS2030", "CS2030DE"}, "lowercase input")


def test_corequisites_met():
    print("\n[corequisites_met]")
    # Single-code coreq, same semester counts
    assert_eq(corequisites_met("CS2101", ["CS2101"]), True, "coreq present in same/earlier")
    assert_eq(corequisites_met("CS2101", []), False, "coreq missing")
    # AND coreq
    assert_eq(corequisites_met({"and": ["CS2101", "CS3203"]}, ["CS2101", "CS3203"]), True, "AND both met")
    assert_eq(corequisites_met({"and": ["CS2101", "CS3203"]}, ["CS2101"]), False, "AND partial")
    # Raw — unparseable, evaluates True
    assert_eq(corequisites_met({"raw": "tba"}, []), True, "raw evaluates True")


# ---------- validate() ----------

def _entry(eid, code, sem, **kwargs):
    """Helper to build a PlanEntry with sensible defaults."""
    return PlanEntry(
        id=eid,
        module_code=code,
        semester_id=sem,
        prereq_tree=kwargs.get("prereq_tree"),
        corequisite=kwargs.get("corequisite"),
        preclusion=kwargs.get("preclusion"),
        semesters_offered=kwargs.get("semesters_offered"),
    )


def test_prereq_violation():
    print("\n[validate: prereq violations]")
    entries = [
        # CS2030S in Y1S1 but its prereq CS1101S is also Y1S1 (not earlier) — violation.
        _entry(1, "CS1101S", "Y1S1"),
        _entry(2, "CS2030S", "Y1S1", prereq_tree="CS1101S"),
    ]
    issues = validate(entries)
    prereq_issues = [i for i in issues if i["kind"] == PREREQ_UNMET]
    assert_eq(len(prereq_issues), 1, "one prereq violation")
    assert_eq(prereq_issues[0]["module_code"], "CS2030S", "for CS2030S")

    # Move CS2030S to Y1S2 → no violation.
    entries[1] = _entry(2, "CS2030S", "Y1S2", prereq_tree="CS1101S")
    issues = validate(entries)
    assert_eq([i for i in issues if i["kind"] == PREREQ_UNMET], [], "no prereq violation when ordered")


def test_coreq_violation():
    print("\n[validate: coreq violations]")
    # CS2103T has CS2101 as coreq — same semester is fine
    entries = [
        _entry(1, "CS2103T", "Y2S2", corequisite="CS2101"),
        _entry(2, "CS2101",  "Y2S2"),
    ]
    issues = [i for i in validate(entries) if i["kind"] == COREQ_UNMET]
    assert_eq(issues, [], "same-semester coreq is satisfied")

    # CS2101 in LATER semester → coreq not met
    entries = [
        _entry(1, "CS2103T", "Y2S2", corequisite="CS2101"),
        _entry(2, "CS2101",  "Y3S1"),
    ]
    issues = [i for i in validate(entries) if i["kind"] == COREQ_UNMET]
    assert_eq(len(issues), 1, "coreq in later semester is violation")
    assert_eq(issues[0]["module_code"], "CS2103T", "violation on CS2103T")

    # Earlier semester also satisfies coreq
    entries = [
        _entry(1, "CS2103T", "Y3S1", corequisite="CS2101"),
        _entry(2, "CS2101",  "Y2S1"),
    ]
    issues = [i for i in validate(entries) if i["kind"] == COREQ_UNMET]
    assert_eq(issues, [], "earlier-semester coreq also counts")


def test_preclusion_violation():
    print("\n[validate: preclusion violations]")
    entries = [
        _entry(1, "CS2030",  "Y1S2"),
        _entry(2, "CS2030S", "Y1S2", preclusion="CS2030, CS2030DE"),
    ]
    issues = [i for i in validate(entries) if i["kind"] == PRECLUSION]
    assert_eq(len(issues), 1, "one preclusion violation")
    # Pair is reported once, with codes in canonical order
    v = issues[0]
    assert_eq(v["module_code_a"], "CS2030", "canonical-order code_a")
    assert_eq(v["module_code_b"], "CS2030S", "canonical-order code_b")

    # No preclusion when only one of the pair is present
    entries = [_entry(2, "CS2030S", "Y1S2", preclusion="CS2030")]
    issues = [i for i in validate(entries) if i["kind"] == PRECLUSION]
    assert_eq(issues, [], "no preclusion when other code absent")


def test_not_offered_violation():
    print("\n[validate: not-offered violations]")
    # CS3216 only in Sem 1 — placing in Y2S2 is wrong
    entries = [_entry(1, "CS3216", "Y2S2", semesters_offered=[1])]
    issues = [i for i in validate(entries) if i["kind"] == NOT_OFFERED]
    assert_eq(len(issues), 1, "Sem 1-only module in S2 slot → violation")
    assert_eq(issues[0]["offered_in"], [1], "offered_in is [1]")

    # Same module in Y2S1 — OK
    entries = [_entry(1, "CS3216", "Y2S1", semesters_offered=[1])]
    issues = [i for i in validate(entries) if i["kind"] == NOT_OFFERED]
    assert_eq(issues, [], "Sem 1-only module in S1 slot → OK")

    # Both-semester module — never violates
    entries = [
        _entry(1, "ST2334", "Y2S1", semesters_offered=[1, 2]),
        _entry(2, "ST2334", "Y2S2", semesters_offered=[1, 2]),
    ]
    issues = [i for i in validate(entries) if i["kind"] == NOT_OFFERED]
    assert_eq(issues, [], "any-semester module never violates")

    # Unknown offerings → no violation (we don't guess)
    entries = [_entry(1, "CS3216", "Y2S2", semesters_offered=None)]
    issues = [i for i in validate(entries) if i["kind"] == NOT_OFFERED]
    assert_eq(issues, [], "no offering info → no violation")


def test_validate_back_compat():
    print("\n[validate: order and back-compat]")
    entries = [
        _entry(1, "CS1101S", "Y1S1"),
        _entry(2, "CS2030S", "Y1S1", prereq_tree="CS1101S", preclusion="CS2030"),
        _entry(3, "CS2030",  "Y1S2"),
        _entry(4, "CS3216",  "Y2S2", semesters_offered=[1]),
        _entry(5, "CS2103T", "Y3S1", prereq_tree={"and": ["CS2030S"]}, corequisite="CS2101"),
    ]
    issues = validate(entries)
    kinds = [i["kind"] for i in issues]
    print(f"  ✓ produced {len(issues)} issues: {kinds}")
    # We expect each kind to appear at least once.
    assert PREREQ_UNMET in kinds, "prereq violation present"
    assert COREQ_UNMET in kinds, "coreq violation present"
    assert PRECLUSION in kinds, "preclusion present"
    assert NOT_OFFERED in kinds, "not-offered present"


# ---------- find_ready_modules ----------

def test_find_ready_modules():
    print("\n[find_ready_modules]")
    # User has placed CS1101S and CS1231S in Y1S1.
    placed = [
        _entry(1, "CS1101S", "Y1S1"),
        _entry(2, "CS1231S", "Y1S1"),
    ]
    catalogue = [
        {"code": "CS1101S", "prereq_tree": None, "title": "...", "mcs": 4, "semesters_offered": [1, 2]},
        {"code": "CS2030S", "prereq_tree": "CS1101S", "title": "...", "mcs": 4, "semesters_offered": [1, 2]},
        {"code": "CS2040S", "prereq_tree": {"and": ["CS1101S", "CS1231S"]}, "title": "...", "mcs": 4, "semesters_offered": [1, 2]},
        {"code": "CS3243",  "prereq_tree": {"and": ["CS2030S", "CS2040S"]}, "title": "...", "mcs": 4, "semesters_offered": [1, 2]},
        {"code": "CS3216",  "prereq_tree": None, "title": "...", "mcs": 4, "semesters_offered": [1]},  # S1-only
    ]
    ready_y1s2 = find_ready_modules("Y1S2", placed, catalogue)
    ready_codes = {m["code"] for m in ready_y1s2}
    assert "CS2030S" in ready_codes, "CS2030S ready (prereq CS1101S met)"
    assert "CS2040S" in ready_codes, "CS2040S ready (both prereqs met)"
    assert "CS3243" not in ready_codes, "CS3243 NOT ready (needs CS2030S + CS2040S)"
    assert "CS1101S" not in ready_codes, "already-placed modules excluded"
    print(f"  ✓ Y1S2 ready: {sorted(ready_codes)}")

    # In Y1S2, CS3216 (S1-only) should NOT appear
    assert "CS3216" not in ready_codes, "S1-only module not ready in Y1S2"

    # In Y2S1 (Sem 1 slot), CS3216 SHOULD appear
    ready_y2s1 = find_ready_modules("Y2S1", placed, catalogue)
    assert "CS3216" in {m["code"] for m in ready_y2s1}, "S1-only module ready in Y2S1"

    # Invalid semester id
    try:
        find_ready_modules("BAD", placed, catalogue)
        raise AssertionError("expected ValueError")
    except ValueError:
        print("  ✓ invalid semester_id raises ValueError")


if __name__ == "__main__":
    print("Running validation service tests…")
    test_parse_corequisite_string()
    test_extract_preclusion_codes()
    test_corequisites_met()
    test_prereq_violation()
    test_coreq_violation()
    test_preclusion_violation()
    test_not_offered_violation()
    test_validate_back_compat()
    test_find_ready_modules()
    print("\nAll tests passed ✓")
