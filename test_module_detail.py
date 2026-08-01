"""Tests for the enhanced /api/modules/<code> endpoint.

Covers:
  - basic detail still works
  - stats.placement_count is correct
  - stats.by_semester groups correctly
  - unlocks returns modules that have this one as a prereq
  - unlocks doesn't include the module itself
  - case-insensitive code lookup
  - 404 for unknown modules

Uses Flask's test client against a temp seeded DB, plus inserts plan entries
to exercise the stats query.

Run: python tests/test_module_detail.py
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
    """Create a fresh seeded DB and return (app, path, original_db_path)."""
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


AUTH = {"Authorization": "Bearer dev-user-modtest"}


def test_basic_detail():
    print("\n[basic detail]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/api/modules/CS2030S", headers=AUTH)
        assert_eq(resp.status_code, 200, "status 200")
        data = resp.get_json()
        assert_eq(data["code"], "CS2030S", "code")
        assert_eq(data["mcs"], 4, "mcs (integer formatted)")
        assert "prereq_tree" in data, "has prereq_tree"
        assert "stats" in data, "has stats block"
        assert "unlocks" in data, "has unlocks block"
    finally:
        _teardown(path, orig)


def test_case_insensitive():
    print("\n[case insensitive]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/api/modules/cs2030s", headers=AUTH)
        assert_eq(resp.status_code, 200, "lowercase accepted")
        assert_eq(resp.get_json()["code"], "CS2030S", "code normalized to upper")
    finally:
        _teardown(path, orig)


def test_not_found():
    print("\n[not found]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/api/modules/XX9999", headers=AUTH)
        assert_eq(resp.status_code, 404, "unknown module returns 404")
        assert_eq(resp.get_json()["code"], "NOT_FOUND", "error code")
    finally:
        _teardown(path, orig)


def test_placement_stats():
    print("\n[placement stats]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()

        # Use CS4248: it's in the seed but not in any ghost plan, so the baseline
        # placement count is 0 regardless of Feature 8's ghost users.
        # Empty stats first
        resp = client.get("/api/modules/CS4248", headers=AUTH)
        stats = resp.get_json()["stats"]
        assert_eq(stats["placement_count"], 0, "initial placement count is 0")
        assert_eq(stats["by_semester"], {}, "initial by_semester is empty")

        # Insert plan entries to exercise the count. We need to create a plan first.
        # The simplest path is using the API.
        plan_resp = client.post("/api/plans", headers=AUTH, json={"name": "Test"})
        plan_id = plan_resp.get_json()["id"]

        # Add CS4248 to Y3S2 — this should bump the global stats.
        client.post(f"/api/plans/{plan_id}/entries", headers=AUTH,
                    json={"module_code": "CS4248", "semester_id": "Y3S2"})

        # A second user places it in Y4S1
        other_auth = {"Authorization": "Bearer dev-user-other"}
        other_plan = client.post("/api/plans", headers=other_auth, json={"name": "Other"})
        other_plan_id = other_plan.get_json()["id"]
        client.post(f"/api/plans/{other_plan_id}/entries", headers=other_auth,
                    json={"module_code": "CS4248", "semester_id": "Y4S1"})

        # Re-check stats — should reflect across both users
        resp = client.get("/api/modules/CS4248", headers=AUTH)
        stats = resp.get_json()["stats"]
        assert_eq(stats["placement_count"], 2, "two placements across two users")
        assert "Y3S2" in stats["by_semester"], "Y3S2 in by_semester"
        assert "Y4S1" in stats["by_semester"], "Y4S1 in by_semester"
        assert_eq(stats["by_semester"]["Y3S2"], 1, "Y3S2 count")
        assert_eq(stats["by_semester"]["Y4S1"], 1, "Y4S1 count")
    finally:
        _teardown(path, orig)


def test_unlocks():
    print("\n[unlocks]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()

        # CS2030S unlocks CS2103T, CS2106, CS2109S, CS3243, CS4243 in the seed.
        # (Anything whose prereq tree includes "CS2030S" should be in unlocks.)
        resp = client.get("/api/modules/CS2030S", headers=AUTH)
        unlocks = resp.get_json()["unlocks"]
        unlock_codes = {u["code"] for u in unlocks}
        # We don't pin the exact set — that depends on seed data — but check known ones.
        assert "CS2103T" in unlock_codes, "CS2103T unlocked by CS2030S"
        assert "CS2106" in unlock_codes, "CS2106 unlocked by CS2030S"
        print(f"  ✓ CS2030S unlocks {len(unlock_codes)} modules: {sorted(unlock_codes)}")

        # CS2030S should NOT be in its own unlocks
        assert "CS2030S" not in unlock_codes, "module is not in its own unlocks"
        print("  ✓ module not in its own unlocks")

        # A leaf module with no dependents
        resp = client.get("/api/modules/CS4248", headers=AUTH)  # NLP — nothing depends on it in seed
        assert_eq(resp.get_json()["unlocks"], [], "CS4248 unlocks nothing in seed")
    finally:
        _teardown(path, orig)


if __name__ == "__main__":
    print("Running module detail tests…")
    test_basic_detail()
    test_case_insensitive()
    test_not_found()
    test_placement_stats()
    test_unlocks()
    print("\nAll tests passed ✓")
