"""Integration tests for /api/plans/:id/validate and /ready-modules.

Exercises the actual HTTP routes against a seeded DB, so it covers JSON
serialization, the schema joins, and the seed's MODULE_EXTENSIONS too.

Run: python tests/test_plan_validate_routes.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config


def assert_eq(a, b, label):
    status = "✓" if a == b else "✗"
    print(f"  {status} {label}: got {a!r}")
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


def _setup_temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    original = config.DATABASE_PATH
    config.DATABASE_PATH = path

    from db import init_db
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    init_db(schema_path=schema_path)

    import importlib, seed
    importlib.reload(seed)
    seed.seed()

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["DATABASE_PATH"] = path
    return app, path, original


def _teardown(path, original):
    config.DATABASE_PATH = original
    try: os.unlink(path)
    except OSError: pass


AUTH = {"Authorization": "Bearer dev-user-validate"}


def _make_plan_with_entries(client, entries):
    """Create a plan and add entries; return plan_id."""
    plan_resp = client.post("/api/plans", headers=AUTH, json={"name": "Validation Test"})
    plan_id = plan_resp.get_json()["id"]
    for code, sem in entries:
        client.post(f"/api/plans/{plan_id}/entries", headers=AUTH,
                    json={"module_code": code, "semester_id": sem})
    return plan_id


def test_validate_back_compat():
    print("\n[/validate: legacy violations + new issues]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()
        # CS1101S in Y1S2, CS2030S in Y1S1 (impossible — prereq is later)
        plan_id = _make_plan_with_entries(client, [
            ("CS1101S", "Y1S2"),
            ("CS2030S", "Y1S1"),
        ])
        resp = client.get(f"/api/plans/{plan_id}/validate", headers=AUTH)
        assert_eq(resp.status_code, 200, "status 200")
        data = resp.get_json()
        assert "violations" in data, "legacy 'violations' key present"
        assert "issues" in data, "new 'issues' key present"
        # The legacy field should contain only prereq-shaped entries
        for v in data["violations"]:
            assert set(v.keys()) >= {"entry_id", "module_code", "semester_id", "unmet"}, "legacy shape"
        assert any(i["kind"] == "PREREQ_UNMET" for i in data["issues"]), "issue list has prereq"
    finally:
        _teardown(path, original)


def test_validate_coreq():
    print("\n[/validate: coreq via seed's CS2103T → CS2101]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()
        # Place CS2103T (Y3S1) but put its coreq CS2101 LATER (Y4S1) — should violate
        # We also need to place CS2103T's actual prereqs (CS2030S+CS2040S) earlier
        # to isolate the coreq error.
        plan_id = _make_plan_with_entries(client, [
            ("CS1101S", "Y1S1"),
            ("CS1231S", "Y1S1"),
            ("CS2030S", "Y1S2"),
            ("CS2040S", "Y1S2"),
            ("CS2103T", "Y2S1"),
            ("CS2101",  "Y3S1"),
        ])
        resp = client.get(f"/api/plans/{plan_id}/validate", headers=AUTH)
        issues = resp.get_json()["issues"]
        coreq = [i for i in issues if i["kind"] == "COREQ_UNMET"]
        assert_eq(len(coreq), 1, "one coreq violation")
        assert_eq(coreq[0]["module_code"], "CS2103T", "violation on CS2103T")
    finally:
        _teardown(path, original)


def test_validate_not_offered():
    print("\n[/validate: not-offered via seed's CS3216 Sem-1-only]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _make_plan_with_entries(client, [
            ("CS1101S", "Y1S1"),
            ("CS2030S", "Y1S2"),
            ("CS2040S", "Y1S2"),
            ("CS2103T", "Y2S1"),
            ("CS3216",  "Y2S2"),  # Sem 1-only in seed, but placed in S2
        ])
        resp = client.get(f"/api/plans/{plan_id}/validate", headers=AUTH)
        issues = resp.get_json()["issues"]
        not_offered = [i for i in issues if i["kind"] == "NOT_OFFERED"]
        assert_eq(len(not_offered), 1, "one not-offered violation")
        assert_eq(not_offered[0]["module_code"], "CS3216", "violation on CS3216")
        assert_eq(not_offered[0]["offered_in"], [1], "offered_in [1]")
    finally:
        _teardown(path, original)


def test_ready_modules():
    print("\n[/ready-modules]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()
        # Empty plan — Y1S1 ready should include any module with no prereqs
        plan_id = _make_plan_with_entries(client, [])
        resp = client.get(f"/api/plans/{plan_id}/ready-modules?semester_id=Y1S1", headers=AUTH)
        assert_eq(resp.status_code, 200, "status 200")
        ready_codes = {m["code"] for m in resp.get_json()["modules"]}
        # CS1101S, CS1231S, IS1108, etc. have no prereqs
        assert "CS1101S" in ready_codes, "CS1101S ready (no prereqs)"
        assert "CS1231S" in ready_codes, "CS1231S ready (no prereqs)"
        # CS2030S NOT ready (needs CS1101S earlier)
        assert "CS2030S" not in ready_codes, "CS2030S not ready in Y1S1 (no prior)"

        # Place CS1101S in Y1S1, ask for Y1S2
        plan_id2 = _make_plan_with_entries(client, [("CS1101S", "Y1S1")])
        resp = client.get(f"/api/plans/{plan_id2}/ready-modules?semester_id=Y1S2", headers=AUTH)
        ready = resp.get_json()["modules"]
        codes = {m["code"] for m in ready}
        assert "CS2030S" in codes, "CS2030S ready in Y1S2 after CS1101S in Y1S1"
        assert "CS1101S" not in codes, "already-placed CS1101S excluded"
    finally:
        _teardown(path, original)


def test_ready_modules_bad_input():
    print("\n[/ready-modules: bad input]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _make_plan_with_entries(client, [])

        # Missing semester_id
        resp = client.get(f"/api/plans/{plan_id}/ready-modules", headers=AUTH)
        assert_eq(resp.status_code, 400, "missing semester_id → 400")

        # Invalid semester_id
        resp = client.get(f"/api/plans/{plan_id}/ready-modules?semester_id=BAD", headers=AUTH)
        assert_eq(resp.status_code, 400, "invalid semester_id → 400")
    finally:
        _teardown(path, original)


def test_validate_exam_clash():
    """End-to-end: the seed's CS2030S and CS2040S have overlapping Sem 2 exam
    windows. Placing both in Y1S2 should surface an EXAM_CLASH issue."""
    print("\n[/validate: exam clash via seed's CS2030S + CS2040S]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()
        # Place CS1101S in Y1S1 first so CS2030S's prereq is satisfied — we want
        # the EXAM_CLASH cleanly, not entangled with PREREQ_UNMET.
        plan_id = _make_plan_with_entries(client, [
            ("CS1101S", "Y1S1"),
            ("CS1231S", "Y1S1"),
            ("CS2030S", "Y1S2"),
            ("CS2040S", "Y1S2"),
        ])
        resp = client.get(f"/api/plans/{plan_id}/validate", headers=AUTH)
        issues = resp.get_json()["issues"]
        clashes = [i for i in issues if i["kind"] == "EXAM_CLASH"]
        assert_eq(len(clashes), 1, "one EXAM_CLASH detected")
        c = clashes[0]
        assert_eq(c["module_code_a"], "CS2030S", "canonical-order code_a")
        assert_eq(c["module_code_b"], "CS2040S", "canonical-order code_b")
        assert_eq(c["semester_id"], "Y1S2", "in Y1S2")
        assert "CS2030S" in c["message"] and "CS2040S" in c["message"], "message mentions both"
    finally:
        _teardown(path, original)


def test_validate_no_exam_clash_when_only_one_placed():
    """A clashing pair only triggers when BOTH modules are in the plan."""
    print("\n[/validate: no clash when only one module placed]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _make_plan_with_entries(client, [
            ("CS1101S", "Y1S1"),
            ("CS2030S", "Y1S2"),
        ])
        resp = client.get(f"/api/plans/{plan_id}/validate", headers=AUTH)
        issues = resp.get_json()["issues"]
        clashes = [i for i in issues if i["kind"] == "EXAM_CLASH"]
        assert_eq(clashes, [], "no clash with only CS2030S placed")
    finally:
        _teardown(path, original)


if __name__ == "__main__":
    print("Running plan validate-route tests…")
    test_validate_back_compat()
    test_validate_coreq()
    test_validate_not_offered()
    test_ready_modules()
    test_ready_modules_bad_input()
    test_validate_exam_clash()
    test_validate_no_exam_clash_when_only_one_placed()
    print("\nAll tests passed ✓")
