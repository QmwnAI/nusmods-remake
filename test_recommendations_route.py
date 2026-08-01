"""Integration tests for /api/recommendations/ues.

Uses the seeded ghost users so we have real collaborative-filtering signal.

Run: python tests/test_recommendations_route.py
"""
from __future__ import annotations
import os, sys, tempfile

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


AUTH = {"Authorization": "Bearer dev-user-recotest"}


def test_recommendations_use_cf_signal():
    """A CS user with a plan similar to the ghost CS users should see
    CS-ghost-popular UEs near the top."""
    print("\n[/api/recommendations/ues — CS user gets CS-popular UEs]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        # Set up: declare as CS major, create a plan with core CS modules
        client.put("/api/me", headers=AUTH, json={"major_code": "CS", "matric_year": 2024})
        plan_resp = client.post("/api/plans", headers=AUTH, json={"name": "Test"})
        plan_id = plan_resp.get_json()["id"]
        # Place core CS modules — overlap with ghost CS users.
        # Include CS2103T so CS3216 (a CS-ghost-popular UE) passes the eligibility filter.
        for code in ["CS1101S", "CS1231S", "CS2030S", "CS2040S", "CS2100", "CS2103T", "MA1521"]:
            client.post(f"/api/plans/{plan_id}/entries", headers=AUTH,
                        json={"module_code": code, "semester_id": "Y1S1"})

        resp = client.get(f"/api/recommendations/ues?plan_id={plan_id}&limit=10", headers=AUTH)
        assert_eq(resp.status_code, 200, "status 200")
        data = resp.get_json()
        mods = data["modules"]
        assert len(mods) > 0, "got at least one recommendation"

        # All ghost CS users took CS3216 — it should rank highly
        top_codes = [m["code"] for m in mods[:3]]
        print(f"  ✓ top 3 picks: {top_codes}")
        assert "CS3216" in top_codes, "CS3216 (taken by all CS ghosts) is in top 3"

        # Each recommendation includes reasons
        for m in mods:
            assert "reasons" in m and len(m["reasons"]) > 0, f"{m['code']} has reasons"

        # CS user should see "similar plans" attribution somewhere
        any_similar = any(
            any("similar plans" in r for r in m["reasons"])
            for m in mods
        )
        assert any_similar, "at least one rec uses similar-plans reason"
    finally:
        _teardown(path, orig)


def test_recommendations_eligibility_filter():
    """Modules whose prereqs aren't met shouldn't appear."""
    print("\n[/api/recommendations/ues — eligibility filter]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        client.put("/api/me", headers=AUTH, json={"major_code": "CS", "matric_year": 2024})
        plan_resp = client.post("/api/plans", headers=AUTH, json={"name": "Empty"})
        plan_id = plan_resp.get_json()["id"]
        # EMPTY plan — only modules with NO prereqs should appear.
        resp = client.get(f"/api/recommendations/ues?plan_id={plan_id}&limit=20", headers=AUTH)
        codes = {m["code"] for m in resp.get_json()["modules"]}
        # CS3217 requires CS3216; without CS3216 placed, it shouldn't appear.
        assert "CS3217" not in codes, "CS3217 (requires CS3216) excluded from empty-plan recs"
        # MA2104 requires MA1521; without MA1521, it shouldn't appear.
        assert "MA2104" not in codes, "MA2104 (requires MA1521) excluded from empty-plan recs"
        # BT2102, EC1101E, PL1101E have no prereqs — eligible.
        eligible_no_prereq = {"BT2102", "EC1101E", "PL1101E"} & codes
        assert len(eligible_no_prereq) > 0, "no-prereq UEs are eligible"
        print(f"  ✓ eligible UEs surfaced: {eligible_no_prereq}")
    finally:
        _teardown(path, orig)


def test_recommendations_exclude_placed():
    """Modules already in the user's plan shouldn't be recommended back."""
    print("\n[/api/recommendations/ues — excludes already-placed]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        client.put("/api/me", headers=AUTH, json={"major_code": "CS", "matric_year": 2024})
        plan_resp = client.post("/api/plans", headers=AUTH, json={"name": "Has UE"})
        plan_id = plan_resp.get_json()["id"]
        client.post(f"/api/plans/{plan_id}/entries", headers=AUTH,
                    json={"module_code": "BT2102", "semester_id": "Y2S1"})
        resp = client.get(f"/api/recommendations/ues?plan_id={plan_id}", headers=AUTH)
        codes = {m["code"] for m in resp.get_json()["modules"]}
        assert "BT2102" not in codes, "placed module excluded from recs"
    finally:
        _teardown(path, orig)


def test_recommendations_auth():
    print("\n[/api/recommendations/ues — auth required]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/api/recommendations/ues")
        assert_eq(resp.status_code, 401, "no auth → 401")
    finally:
        _teardown(path, orig)


if __name__ == "__main__":
    print("Running recommendations route integration tests…")
    test_recommendations_use_cf_signal()
    test_recommendations_eligibility_filter()
    test_recommendations_exclude_placed()
    test_recommendations_auth()
    print("\nAll tests passed ✓")
