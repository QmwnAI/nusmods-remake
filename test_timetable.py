"""Tests for the timetable conflict-detection service.

Covers:
  - parse_exam_datetime: ISO 8601 with ms + timezone, edge cases
  - extract_exam: pulls (start, duration) from semester_data list
  - exams_overlap: half-open intervals, missing-data permissiveness
  - find_exam_clashes: per-semester grouping, pair canonical-ordering, dedup

Run: python tests/test_timetable.py
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.timetable import (
    ExamEntry,
    PLAN_SEM_TO_NUS,
    exams_overlap,
    extract_exam,
    find_exam_clashes,
    parse_exam_datetime,
)


def assert_eq(a, b, label):
    status = "✓" if a == b else "✗"
    print(f"  {status} {label}: got {a!r}")
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


def assert_truthy(v, label):
    status = "✓" if v else "✗"
    print(f"  {status} {label}: got {v!r}")
    assert v, label


# ---------- parse_exam_datetime ----------

def test_parse_exam_datetime():
    print("\n[parse_exam_datetime]")
    # NUSMods format
    dt = parse_exam_datetime("2024-11-25T13:00:00.000+08:00")
    assert dt is not None, "parsed real format"
    assert_eq(dt.year, 2024, "year")
    assert_eq(dt.month, 11, "month")
    assert_eq(dt.day, 25, "day")
    assert_eq(dt.hour, 13, "hour")
    # Timezone preserved
    expected_offset = timedelta(hours=8)
    assert_eq(dt.utcoffset(), expected_offset, "tz +08:00 preserved")

    # No milliseconds — also parses
    dt2 = parse_exam_datetime("2024-11-25T13:00:00+08:00")
    assert dt2 is not None, "no-ms variant parses"

    # Empty / None / garbage
    assert_eq(parse_exam_datetime(None), None, "None → None")
    assert_eq(parse_exam_datetime(""), None, "empty → None")
    assert_eq(parse_exam_datetime("not a date"), None, "garbage → None")
    assert_eq(parse_exam_datetime(12345), None, "non-string → None")


# ---------- extract_exam ----------

def test_extract_exam():
    print("\n[extract_exam]")
    semester_data = [
        {"semester": 1, "examDate": "2024-11-25T13:00:00.000+08:00", "examDuration": 120},
        {"semester": 2, "examDate": "2025-04-29T09:00:00.000+08:00", "examDuration": 90},
    ]
    # Sem 1 lookup
    start, dur = extract_exam(semester_data, 1)
    assert start is not None, "got Sem 1 datetime"
    assert_eq(dur, 120, "Sem 1 duration")

    # Sem 2 lookup
    start, dur = extract_exam(semester_data, 2)
    assert start is not None, "got Sem 2 datetime"
    assert_eq(dur, 90, "Sem 2 duration")

    # Sem with no entry
    assert_eq(extract_exam(semester_data, 3), (None, None), "sem 3 not in data → None,None")

    # Empty / non-list / malformed
    assert_eq(extract_exam([], 1), (None, None), "empty list → None,None")
    assert_eq(extract_exam(None, 1), (None, None), "None data → None,None")
    assert_eq(extract_exam("garbage", 1), (None, None), "string data → None,None")

    # Sem entry with no exam info (just {semester: 1})
    sem_data_no_exam = [{"semester": 1}]
    assert_eq(extract_exam(sem_data_no_exam, 1), (None, None),
              "sem entry without examDate → None,None")

    # Duration as string number (NUSMods sometimes does this)
    sem_data_str_dur = [{"semester": 1, "examDate": "2024-11-25T13:00:00.000+08:00", "examDuration": "120"}]
    _, dur = extract_exam(sem_data_str_dur, 1)
    assert_eq(dur, 120, "string duration coerced to int")

    # Duration garbage
    sem_data_bad_dur = [{"semester": 1, "examDate": "2024-11-25T13:00:00.000+08:00", "examDuration": "two hours"}]
    _, dur = extract_exam(sem_data_bad_dur, 1)
    assert_eq(dur, None, "garbage duration → None")


# ---------- exams_overlap ----------

def _dt(h, m=0):
    """Build a local-naive datetime at the given hour:min on a fixed day."""
    return datetime(2025, 4, 29, h, m, 0)


def test_exams_overlap():
    print("\n[exams_overlap]")
    # Same time, same duration → overlap
    assert_eq(exams_overlap(_dt(9), 120, _dt(9), 120), True, "identical → overlap")
    # B starts mid-A → overlap
    assert_eq(exams_overlap(_dt(9), 120, _dt(10), 60), True, "B inside A → overlap")
    # A ends exactly when B starts → NOT overlap (half-open)
    assert_eq(exams_overlap(_dt(9), 120, _dt(11), 60), False, "back-to-back → no overlap")
    # Completely disjoint
    assert_eq(exams_overlap(_dt(9), 60, _dt(14), 60), False, "disjoint → no overlap")
    # A starts mid-B → overlap (symmetric)
    assert_eq(exams_overlap(_dt(10), 60, _dt(9), 120), True, "A inside B → overlap")
    # 1-minute overlap → still overlap
    assert_eq(exams_overlap(_dt(9), 121, _dt(11), 60), True, "1-min overlap → overlap")

    # Missing data → permissive (no overlap inferred)
    assert_eq(exams_overlap(None,    120, _dt(9), 120), False, "missing A start → no overlap")
    assert_eq(exams_overlap(_dt(9),  None, _dt(9), 120), False, "missing A duration → no overlap")
    assert_eq(exams_overlap(_dt(9),  120, None,    120), False, "missing B start → no overlap")
    assert_eq(exams_overlap(_dt(9),  120, _dt(9), None), False, "missing B duration → no overlap")


# ---------- find_exam_clashes ----------

def test_find_exam_clashes_basic():
    print("\n[find_exam_clashes: basic pair]")
    a = ExamEntry(id=1, module_code="CS2030S", semester_id="Y1S2",
                  exam_start=_dt(9), exam_duration_min=120)
    b = ExamEntry(id=2, module_code="CS2040S", semester_id="Y1S2",
                  exam_start=_dt(9), exam_duration_min=120)
    clashes = find_exam_clashes([a, b])
    assert_eq(len(clashes), 1, "one clash detected")
    c = clashes[0]
    assert_eq(c["kind"], "EXAM_CLASH", "kind = EXAM_CLASH")
    assert_eq(c["module_code_a"], "CS2030S", "canonical-order code_a")
    assert_eq(c["module_code_b"], "CS2040S", "canonical-order code_b")
    assert_eq(c["semester_id"], "Y1S2", "semester surfaced")
    assert_truthy(c["exam_start_a"], "exam_start_a serialized")


def test_find_exam_clashes_different_semesters():
    print("\n[find_exam_clashes: different semesters don't clash]")
    a = ExamEntry(id=1, module_code="CS3216", semester_id="Y2S1",
                  exam_start=_dt(13), exam_duration_min=120)
    b = ExamEntry(id=2, module_code="CS3243", semester_id="Y3S1",
                  exam_start=_dt(13), exam_duration_min=120)
    # Same wall clock time but different plan semesters → no clash
    assert_eq(find_exam_clashes([a, b]), [], "different semesters → no clash")


def test_find_exam_clashes_missing_data_skipped():
    print("\n[find_exam_clashes: missing data skips]")
    a = ExamEntry(id=1, module_code="A", semester_id="Y1S1",
                  exam_start=_dt(9), exam_duration_min=120)
    b = ExamEntry(id=2, module_code="B", semester_id="Y1S1",
                  exam_start=None, exam_duration_min=None)
    assert_eq(find_exam_clashes([a, b]), [], "module without exam doesn't trigger")


def test_find_exam_clashes_canonical_dedup():
    print("\n[find_exam_clashes: canonical ordering & no duplicate pairs]")
    # Three modules all clashing pairwise in the same window — expect 3 pairs
    # (A,B), (A,C), (B,C), each reported once with codes in alpha order.
    a = ExamEntry(id=1, module_code="CS-A", semester_id="Y1S1",
                  exam_start=_dt(9), exam_duration_min=120)
    b = ExamEntry(id=2, module_code="CS-B", semester_id="Y1S1",
                  exam_start=_dt(9), exam_duration_min=120)
    c = ExamEntry(id=3, module_code="CS-C", semester_id="Y1S1",
                  exam_start=_dt(9), exam_duration_min=120)
    clashes = find_exam_clashes([a, b, c])
    assert_eq(len(clashes), 3, "three pairwise clashes")
    pairs = {(cl["module_code_a"], cl["module_code_b"]) for cl in clashes}
    assert_eq(pairs, {("CS-A", "CS-B"), ("CS-A", "CS-C"), ("CS-B", "CS-C")},
              "canonical pairs, alphabetical")


def test_find_exam_clashes_stable_output():
    print("\n[find_exam_clashes: deterministic ordering]")
    # Build inputs in reversed code order, ensure output is sorted by semester then code.
    a = ExamEntry(id=1, module_code="CS-Z", semester_id="Y1S2",
                  exam_start=_dt(9), exam_duration_min=120)
    b = ExamEntry(id=2, module_code="CS-A", semester_id="Y1S1",
                  exam_start=_dt(9), exam_duration_min=120)
    c = ExamEntry(id=3, module_code="CS-Y", semester_id="Y1S2",
                  exam_start=_dt(9), exam_duration_min=120)
    d = ExamEntry(id=4, module_code="CS-B", semester_id="Y1S1",
                  exam_start=_dt(9), exam_duration_min=120)
    clashes = find_exam_clashes([a, b, c, d])
    # Two pairs total: (Y1S1: A,B) and (Y1S2: Y,Z). Should sort by semester first.
    assert_eq(len(clashes), 2, "two clash pairs")
    assert_eq(clashes[0]["semester_id"], "Y1S1", "Y1S1 first by sort")
    assert_eq(clashes[1]["semester_id"], "Y1S2", "Y1S2 second")


def test_plan_sem_to_nus_mapping():
    print("\n[PLAN_SEM_TO_NUS mapping]")
    assert_eq(PLAN_SEM_TO_NUS["Y1S1"], 1, "Y1S1 → Sem 1")
    assert_eq(PLAN_SEM_TO_NUS["Y1S2"], 2, "Y1S2 → Sem 2")
    assert_eq(PLAN_SEM_TO_NUS["Y4S2"], 2, "Y4S2 → Sem 2")
    assert_eq(len(PLAN_SEM_TO_NUS), 8, "8 plan slots total")


if __name__ == "__main__":
    print("Running timetable service tests…")
    test_parse_exam_datetime()
    test_extract_exam()
    test_exams_overlap()
    test_find_exam_clashes_basic()
    test_find_exam_clashes_different_semesters()
    test_find_exam_clashes_missing_data_skipped()
    test_find_exam_clashes_canonical_dedup()
    test_find_exam_clashes_stable_output()
    test_plan_sem_to_nus_mapping()
    print("\nAll tests passed ✓")
