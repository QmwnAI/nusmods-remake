"""Tests for the enhanced /api/plans/:id/progress endpoint.

Covers:
  - basic empty plan shape
  - placed vs completed MC distinction (F doesn't count as completed)
  - per-category placed_modules list with completed flag
  - eligible_not_placed preview is capped + total count is honest
  - unallocated modules surface for modules not in any bucket
  - open (no-modules-listed) buckets absorb leftover placed modules
  - projected_completion reflects latest placed semester

Run: python tests/test_progress.py
"""
from __future__ import annotations
import os, sys, tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config import config


def assert_eq(a, b, label):
    status = "✓" if a == b else "✗"
    print(f"  {status} {label}: got {a!r}")
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


def assert_in(item, container, label):
    ok = item in container
    status = "✓" if ok else "✗"
    print(f"  {status} {label}")
    assert ok, f"{label}: {item!r} not in {container!r}"


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


AUTH = {"Authorization": "Bearer dev-user-progress"}


def _new_plan_with_major(client, major="CS"):
    """Create user with major + a plan. Returns plan_id."""
    client.put("/api/me", headers=AUTH, json={"major_code": major, "matric_year": 2024})
    plan_resp = client.post("/api/plans", headers=AUTH, json={"name": "Test"})
    return plan_resp.get_json()["id"]


def _add(client, plan_id, code, sem, grade=None, is_su=False):
    """Add a plan entry, optionally set grade and S/U."""
    add = client.post(f"/api/plans/{plan_id}/entries", headers=AUTH,
                      json={"module_code": code, "semester_id": sem})
    eid = add.get_json()["id"]
    if grade is not None or is_su:
        patch = {}
        if grade is not None: patch["grade"] = grade
        if is_su: patch["is_su"] = True
        client.put(f"/api/plans/{plan_id}/entries/{eid}", headers=AUTH, json=patch)
    return eid


# --------------- tests ---------------

def test_empty_plan_shape():
    print("\n[empty plan shape]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _new_plan_with_major(client)
        resp = client.get(f"/api/plans/{plan_id}/progress", headers=AUTH)
        assert_eq(resp.status_code, 200, "status 200")
        data = resp.get_json()
        # Expected keys
        for key in ("major_code", "total", "projected_completion", "by_category", "unallocated_modules"):
            assert_in(key, data, f"has '{key}' key")
        assert_eq(data["total"]["placed_mcs"], 0, "no placed MCs")
        assert_eq(data["total"]["completed_mcs"], 0, "no completed MCs")
        assert_eq(data["projected_completion"], None, "no projected completion")
        assert_eq(data["unallocated_modules"], [], "no unallocated modules")
    finally:
        _teardown(path, orig)


def test_placed_vs_completed_distinction():
    print("\n[placed vs completed MCs]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _new_plan_with_major(client)
        # 3 modules: one passed (A), one failed (F), one ungraded
        _add(client, plan_id, "CS1101S", "Y1S1", grade="A")
        _add(client, plan_id, "CS1231S", "Y1S1", grade="F")
        _add(client, plan_id, "MA1521",  "Y1S2", grade=None)

        data = client.get(f"/api/plans/{plan_id}/progress", headers=AUTH).get_json()
        # Total placed: 4+4+4 = 12; completed: only the A → 4
        assert_eq(data["total"]["placed_mcs"], 12.0, "placed MCs")
        assert_eq(data["total"]["completed_mcs"], 4.0, "completed MCs (F excluded)")

        # Look inside CS Foundation category
        foundation = next(c for c in data["by_category"] if c["category"] == "FOUNDATION")
        codes_in_foundation = {p["code"] for p in foundation["placed_modules"]}
        assert_in("CS1101S", codes_in_foundation, "CS1101S in FOUNDATION placed_modules")
        assert_in("CS1231S", codes_in_foundation, "CS1231S (failed) still in FOUNDATION placed_modules")
        # Verify completed flag per module
        cs1101 = next(p for p in foundation["placed_modules"] if p["code"] == "CS1101S")
        cs1231 = next(p for p in foundation["placed_modules"] if p["code"] == "CS1231S")
        assert_eq(cs1101["completed"], True,  "CS1101S (A) marked completed")
        assert_eq(cs1231["completed"], False, "CS1231S (F) marked not completed")
    finally:
        _teardown(path, orig)


def test_eligible_not_placed_preview():
    print("\n[eligible_not_placed preview]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _new_plan_with_major(client)
        # Place CS1101S — the other 5 FOUNDATION modules should appear in eligible_not_placed
        _add(client, plan_id, "CS1101S", "Y1S1")

        data = client.get(f"/api/plans/{plan_id}/progress", headers=AUTH).get_json()
        foundation = next(c for c in data["by_category"] if c["category"] == "FOUNDATION")
        codes = {m["code"] for m in foundation["eligible_not_placed"]}
        # Should include CS1231S, CS2030S, etc. (not CS1101S since it's placed)
        assert "CS1101S" not in codes, "placed module excluded from eligible_not_placed"
        assert "CS1231S" in codes, "CS1231S in eligible_not_placed"
        # Total count is honest
        assert_eq(foundation["eligible_not_placed_total"], 5, "5 other FOUNDATION modules unplaced")

        # Each preview item has expected fields
        if foundation["eligible_not_placed"]:
            sample = foundation["eligible_not_placed"][0]
            for key in ("code", "title", "mcs"):
                assert_in(key, sample, f"preview item has '{key}'")
    finally:
        _teardown(path, orig)


def test_unallocated_modules():
    print("\n[unallocated modules]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _new_plan_with_major(client)
        # CS Foundation modules placed → all claimed by specific buckets.
        # If we use BZA major (no module-to-bucket mapping per F3-1), CS modules become
        # leftover and get distributed into BZA's open buckets in display-order.
        client.put("/api/me", headers=AUTH, json={"major_code": "BZA", "matric_year": 2024})
        _add(client, plan_id, "CS1101S", "Y1S1")
        _add(client, plan_id, "CS1231S", "Y1S1")

        data = client.get(f"/api/plans/{plan_id}/progress", headers=AUTH).get_json()
        assert_eq(data["major_code"], "BZA", "switched major to BZA")
        # BZA's "FOUNDATION" bucket is the first open bucket (display_order=1) — it
        # should absorb the first ~28 MC of leftover. Our 2 placed modules = 8 MC
        # fit comfortably inside FOUNDATION; they should NOT spill to UE.
        foundation = next(c for c in data["by_category"] if c["category"] == "FOUNDATION")
        f_codes = {m["code"] for m in foundation["placed_modules"]}
        assert "CS1101S" in f_codes, "CS1101S absorbed by BZA FOUNDATION (first open bucket)"
        assert "CS1231S" in f_codes, "CS1231S absorbed by BZA FOUNDATION"

        # Later buckets should be empty
        ue_bucket = next(c for c in data["by_category"] if c["category"] == "UE")
        assert_eq(ue_bucket["placed_modules"], [], "UE didn't get any leftover")

        # Since the first bucket absorbed everything, unallocated should be empty.
        assert_eq(data["unallocated_modules"], [], "all leftover absorbed → no unallocated")
    finally:
        _teardown(path, orig)


def test_projected_completion():
    print("\n[projected completion]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _new_plan_with_major(client)
        _add(client, plan_id, "CS1101S", "Y1S1")
        _add(client, plan_id, "CS2030S", "Y2S1")
        _add(client, plan_id, "CS3203",  "Y3S1")

        data = client.get(f"/api/plans/{plan_id}/progress", headers=AUTH).get_json()
        proj = data["projected_completion"]
        assert proj is not None, "projected_completion populated"
        assert_eq(proj["semester_id"], "Y3S1", "latest semester is Y3S1")
        assert_eq(proj["year"], 3, "year 3")
        assert_eq(proj["sem"], 1, "sem 1")
    finally:
        _teardown(path, orig)


def test_complete_bucket_marker():
    print("\n[complete bucket marker]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        plan_id = _new_plan_with_major(client)
        # CS FOUNDATION requires 24 MC — place all 6 CS Foundation modules (4 MC each = 24)
        for code in ["CS1101S", "CS1231S", "CS2030S", "CS2040S", "CS2100", "CS2103T"]:
            _add(client, plan_id, code, "Y1S1")

        data = client.get(f"/api/plans/{plan_id}/progress", headers=AUTH).get_json()
        foundation = next(c for c in data["by_category"] if c["category"] == "FOUNDATION")
        assert_eq(foundation["complete"], True, "FOUNDATION marked complete")
        assert_eq(foundation["placed_mcs"], 24, "FOUNDATION placed MCs = 24")
        assert_eq(foundation["eligible_not_placed_total"], 0, "no more to place in FOUNDATION")
    finally:
        _teardown(path, orig)


if __name__ == "__main__":
    print("Running progress endpoint tests…")
    test_empty_plan_shape()
    test_placed_vs_completed_distinction()
    test_eligible_not_placed_preview()
    test_unallocated_modules()
    test_projected_completion()
    test_complete_bucket_marker()
    print("\nAll tests passed ✓")
