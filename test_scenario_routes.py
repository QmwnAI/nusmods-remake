"""Integration tests for /api/plans/:id/gpa/* scenario endpoints.

Run: python tests/test_scenario_routes.py
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


def assert_close(a, b, label, tol=1e-3):
    ok = abs(a - b) <= tol
    status = "✓" if ok else "✗"
    print(f"  {status} {label}: got {a!r} (expected ~{b!r})")
    assert ok, f"{label}: expected ~{b}, got {a}"


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


AUTH = {"Authorization": "Bearer dev-user-scenarios"}


def _plan_with_graded_entries(client, graded: list[tuple[str, str, str, bool]]):
    """Create a plan and add entries. `graded` = [(code, sem, grade_or_none, is_su)]."""
    plan_resp = client.post("/api/plans", headers=AUTH, json={"name": "Test"})
    plan_id = plan_resp.get_json()["id"]
    for code, sem, grade, is_su in graded:
        # Add the entry
        add = client.post(f"/api/plans/{plan_id}/entries", headers=AUTH,
                          json={"module_code": code, "semester_id": sem})
        entry_id = add.get_json()["id"]
        # Patch grade + S/U if requested
        if grade is not None or is_su:
            patch = {}
            if grade is not None: patch["grade"] = grade
            if is_su: patch["is_su"] = True
            client.put(f"/api/plans/{plan_id}/entries/{entry_id}", headers=AUTH, json=patch)
    return plan_id


def test_target_endpoint():
    print("\n[/gpa/target]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _plan_with_graded_entries(client, [
            ("CS1101S", "Y1S1", "A",  False),
            ("CS1231S", "Y1S1", "B+", False),
            ("CS2030S", "Y1S2", None, False),  # ungraded → counts as remaining
            ("CS2040S", "Y1S2", None, False),
        ])
        resp = client.get(f"/api/plans/{plan_id}/gpa/target?cap=4.5", headers=AUTH)
        assert_eq(resp.status_code, 200, "status 200")
        data = resp.get_json()
        # Graded: (5*4 + 4*4) = 36, mcs 8. Remaining ungraded: 8. Target 4.5.
        # required = (4.5 * 16 - 36) / 8 = 4.5
        assert_close(data["required_avg_gp"], 4.5, "required avg GP")
        assert_eq(data["achievable"], True, "achievable")
        assert "remaining_mcs" in data, "remaining_mcs in response"

        # Override remaining
        resp = client.get(f"/api/plans/{plan_id}/gpa/target?cap=4.5&remaining_mcs=20", headers=AUTH)
        data = resp.get_json()
        assert_eq(data["remaining_mcs"], 20.0, "explicit remaining used")

        # Bad input
        resp = client.get(f"/api/plans/{plan_id}/gpa/target?cap=garbage", headers=AUTH)
        assert_eq(resp.status_code, 400, "bad cap → 400")

        resp = client.get(f"/api/plans/{plan_id}/gpa/target?cap=4.5&remaining_mcs=-5", headers=AUTH)
        assert_eq(resp.status_code, 400, "negative remaining → 400")
    finally:
        _teardown(path, orig)


def test_su_advice_endpoint():
    print("\n[/gpa/su-advice]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _plan_with_graded_entries(client, [
            ("CS1101S", "Y1S1", "A",   False),
            ("CS1231S", "Y1S1", "D",   False),  # should be top S/U recommendation
            ("MA1521",  "Y1S1", "C+",  False),
        ])
        resp = client.get(f"/api/plans/{plan_id}/gpa/su-advice?budget_mcs=8", headers=AUTH)
        assert_eq(resp.status_code, 200, "status 200")
        data = resp.get_json()
        recs = data["recommended"]
        codes = [r["module_code"] for r in recs]
        assert "CS1231S" in codes, "D grade is top recommendation"
        assert "CS1101S" not in codes, "A is never recommended"
        assert data["projected_cap"] > data["current_cap"], "CAP improves"

        # Plan ownership: another user can't peek
        other = client.get(f"/api/plans/{plan_id}/gpa/su-advice", headers={"Authorization": "Bearer dev-user-stranger"})
        assert_eq(other.status_code, 404, "other user can't access")

        # Bad budget
        resp = client.get(f"/api/plans/{plan_id}/gpa/su-advice?budget_mcs=-1", headers=AUTH)
        assert_eq(resp.status_code, 400, "negative budget → 400")
    finally:
        _teardown(path, orig)


def test_scenario_endpoint():
    print("\n[/gpa/scenario]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _plan_with_graded_entries(client, [
            ("CS1101S", "Y1S1", "B",  False),
            ("CS1231S", "Y1S1", "B",  False),
        ])

        # Find entry IDs
        plan = client.get(f"/api/plans/{plan_id}", headers=AUTH).get_json()
        first_id = plan["entries"][0]["id"]

        # Override one entry's grade to A
        resp = client.post(
            f"/api/plans/{plan_id}/gpa/scenario",
            headers=AUTH,
            json={"overrides": {str(first_id): {"grade": "A"}}},
        )
        assert_eq(resp.status_code, 200, "status 200")
        data = resp.get_json()
        # (5+3.5)*4 / 8 = 4.25
        assert_close(data["post_su"]["cap"], 4.25, "scenario CAP after override")
        assert_eq(data["changes_applied"], 1, "one override applied")

        # Without overrides, returns current CAP
        resp = client.post(f"/api/plans/{plan_id}/gpa/scenario", headers=AUTH, json={})
        data = resp.get_json()
        assert_close(data["post_su"]["cap"], 3.5, "baseline scenario CAP")

        # Bad input — overrides not a dict
        resp = client.post(f"/api/plans/{plan_id}/gpa/scenario", headers=AUTH, json={"overrides": "garbage"})
        assert_eq(resp.status_code, 400, "non-dict overrides → 400")
    finally:
        _teardown(path, orig)


def test_auth_required():
    print("\n[auth required on scenario routes]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        # No header at all
        assert_eq(client.get("/api/plans/1/gpa/target").status_code, 401, "target no auth")
        assert_eq(client.get("/api/plans/1/gpa/su-advice").status_code, 401, "su-advice no auth")
        assert_eq(client.post("/api/plans/1/gpa/scenario", json={}).status_code, 401, "scenario no auth")
    finally:
        _teardown(path, orig)


if __name__ == "__main__":
    print("Running scenario route tests…")
    test_target_endpoint()
    test_su_advice_endpoint()
    test_scenario_endpoint()
    test_auth_required()
    print("\nAll tests passed ✓")
