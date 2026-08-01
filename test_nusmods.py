"""Tests for services.nusmods parsing and DB helpers.

Run: python tests/test_nusmods.py
"""
import os
import sys
import sqlite3
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.nusmods import parse_credit, extract_semesters_offered, upsert_module
from db import _connect  # using the private helper directly is fine in tests


def assert_eq(a, b, label):
    status = "✓" if a == b else "✗"
    print(f"  {status} {label}: got {a!r}")
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


def test_parse_credit():
    print("\n[parse_credit]")
    assert_eq(parse_credit("4"),    4.0,  "int string")
    assert_eq(parse_credit("2.5"),  2.5,  "fractional string")
    assert_eq(parse_credit(4),      4.0,  "int")
    assert_eq(parse_credit(2.5),    2.5,  "float")
    assert_eq(parse_credit(None),   0.0,  "None")
    assert_eq(parse_credit(""),     0.0,  "empty string")
    assert_eq(parse_credit("abc"),  0.0,  "garbage")


def test_extract_semesters_offered():
    print("\n[extract_semesters_offered]")
    assert_eq(extract_semesters_offered(None), [], "None")
    assert_eq(extract_semesters_offered([]),   [], "empty")
    assert_eq(
        extract_semesters_offered([{"semester": 1, "examDate": "..."}, {"semester": 2}]),
        [1, 2],
        "two sems",
    )
    # NUSMods uses 3,4 for special term 1/2
    assert_eq(
        extract_semesters_offered([{"semester": 2}, {"semester": 1}, {"semester": 1}]),
        [1, 2],
        "deduplicated and sorted",
    )
    assert_eq(
        extract_semesters_offered([{"semester": 4}, {"semester": 1}]),
        [1, 4],
        "special term included",
    )


def _setup_temp_db():
    """Create a temp SQLite DB with the modules table for upsert testing.

    Reads the initial-schema migration file directly (this test doesn't need
    the full migration framework since it's not testing app boot — it just
    needs tables to insert into).
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    schema_path = os.path.join(os.path.dirname(__file__), "..", "migrations", "001_initial.sql")
    with open(schema_path) as f:
        conn.executescript(f.read())
    return path, conn


def test_upsert_module():
    print("\n[upsert_module]")
    path, conn = _setup_temp_db()
    try:
        # First insert
        upsert_module(
            {
                "moduleCode": "CS2030S",
                "title": "Programming Methodology II",
                "description": "OOP, FP, parallelism.",
                "moduleCredit": "4",
                "department": "Computer Science",
                "faculty": "Computing",
                "prereqTree": {"and": ["CS1101S", "CS1231S"]},
                "prerequisite": "CS1101S and CS1231S",
                "preclusion": "CS2030, CS2030DE",
                "workload": [2, 1, 0, 2, 5],
                "semesterData": [{"semester": 1}, {"semester": 2}],
                "acadYear": "2024-2025",
            },
            conn,
        )
        conn.commit()

        row = conn.execute("SELECT * FROM modules WHERE code = 'CS2030S'").fetchone()
        assert_eq(row[0], "CS2030S", "inserted code")
        # Verify the new columns are populated
        cursor = conn.execute("SELECT mcs, preclusion, workload FROM modules WHERE code = 'CS2030S'")
        mcs, preclusion, workload_json = cursor.fetchone()
        assert_eq(mcs, 4.0, "mcs stored as REAL")
        assert_eq(preclusion, "CS2030, CS2030DE", "preclusion stored")
        assert "[2, 1, 0, 2, 5]" in workload_json, "workload JSON contains array"
        print(f"  ✓ workload JSON contains array: got {workload_json!r}")

        # Upsert: change title and verify
        upsert_module(
            {
                "moduleCode": "CS2030S",
                "title": "PM II — updated",
                "moduleCredit": "4",
                "semesterData": [{"semester": 1}],
            },
            conn,
        )
        conn.commit()
        row = conn.execute("SELECT title FROM modules WHERE code = 'CS2030S'").fetchone()
        assert_eq(row[0], "PM II — updated", "upsert overwrote title")

        # Fractional MCs
        upsert_module(
            {"moduleCode": "PROJ", "title": "Half-credit project", "moduleCredit": "2.5"},
            conn,
        )
        conn.commit()
        row = conn.execute("SELECT mcs FROM modules WHERE code = 'PROJ'").fetchone()
        assert_eq(row[0], 2.5, "fractional credit preserved")
    finally:
        conn.close()
        os.unlink(path)


if __name__ == "__main__":
    print("Running NUSMods sync tests…")
    test_parse_credit()
    test_extract_semesters_offered()
    test_upsert_module()
    print("\nAll tests passed ✓")
