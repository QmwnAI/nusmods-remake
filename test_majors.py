"""Tests for /api/majors and the major/matric profile update flow.

This is the first test in the suite that exercises actual Flask HTTP endpoints
via the test client. The pattern:

  1. Point config.DATABASE_PATH at a temp file.
  2. Run schema + seed against it.
  3. Build the Flask app and use test_client to hit endpoints with a
     dev-mode bearer token.
  4. Clean up the temp DB.

This is heavier than the pure-function tests (test_prereqs, test_nusmods, test_auth),
but it's the right tool for catching routing/blueprint/auth integration issues.

Run: python tests/test_majors.py
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
    """Create a fresh seeded DB in a temp file; point config at it; build the app."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Override config BEFORE importing app/db helpers that read it.
    original_path = config.DATABASE_PATH
    config.DATABASE_PATH = path

    # Run schema + seed
    from db import init_db, connect
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    init_db(schema_path=schema_path)

    # Re-import seed in isolation so it picks up the new DATABASE_PATH
    import importlib
    import seed
    importlib.reload(seed)
    seed.seed()

    # Build the app with the patched DB path
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    app.config["DATABASE_PATH"] = path

    return app, path, original_path


def _teardown(path: str, original_path: str):
    config.DATABASE_PATH = original_path
    try:
        os.unlink(path)
    except OSError:
        pass


AUTH = {"Authorization": "Bearer dev-user-testharness"}


def test_list_majors():
    print("\n[GET /api/majors]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/api/majors", headers=AUTH)
        assert_eq(resp.status_code, 200, "status 200")
        data = resp.get_json()
        assert isinstance(data, list), "response is a list"
        codes = [m["code"] for m in data]
        assert "CS" in codes, "CS in majors"
        assert "BZA" in codes, "BZA in majors"
        assert "IS" in codes, "IS in majors"
        print(f"  ✓ found {len(data)} majors: {codes}")

        # Spot-check that requirements_count is populated.
        cs = next(m for m in data if m["code"] == "CS")
        assert_eq(cs["requirements_count"], 6, "CS has 6 requirement buckets")
        assert_eq(cs["total_mcs"], 128, "CS total MCs")
        assert "Computer Science" in cs["name"], "CS name contains 'Computer Science'"
        print(f"  ✓ CS name: {cs['name']!r}")
    finally:
        _teardown(path, original)


def test_major_detail():
    print("\n[GET /api/majors/<code>]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()

        # Existing major
        resp = client.get("/api/majors/CS", headers=AUTH)
        assert_eq(resp.status_code, 200, "CS status 200")
        cs = resp.get_json()
        assert_eq(len(cs["requirements"]), 6, "CS has 6 requirement entries")
        # Check structure of one
        first = cs["requirements"][0]
        assert "category" in first, "requirement has category"
        assert "required_mcs" in first, "requirement has required_mcs"

        # Lowercase also works (route normalizes via .upper())
        resp = client.get("/api/majors/cs", headers=AUTH)
        assert_eq(resp.status_code, 200, "lowercase code accepted")

        # Unknown major
        resp = client.get("/api/majors/XX", headers=AUTH)
        assert_eq(resp.status_code, 404, "unknown major returns 404")
    finally:
        _teardown(path, original)


def test_update_profile_with_major():
    print("\n[PUT /api/me — set major + matric year]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()

        # First touch creates the user (via require_auth)
        resp = client.get("/api/me", headers=AUTH)
        assert_eq(resp.status_code, 200, "GET /api/me creates user")
        me = resp.get_json()
        assert_eq(me["major_code"], None, "major starts null")
        assert_eq(me["matric_year"], None, "matric_year starts null")

        # Set major and matric year
        resp = client.put(
            "/api/me",
            headers=AUTH,
            json={"major_code": "BZA", "matric_year": 2024},
        )
        assert_eq(resp.status_code, 200, "PUT /api/me status 200")
        updated = resp.get_json()
        assert_eq(updated["major_code"], "BZA", "major saved")
        assert_eq(updated["matric_year"], 2024, "matric_year saved")

        # Re-GET reflects the changes
        resp = client.get("/api/me", headers=AUTH)
        me2 = resp.get_json()
        assert_eq(me2["major_code"], "BZA", "major persists on next GET")
        assert_eq(me2["matric_year"], 2024, "matric_year persists on next GET")

        # Updating just one field doesn't wipe the other
        resp = client.put("/api/me", headers=AUTH, json={"matric_year": 2025})
        assert_eq(resp.status_code, 200, "partial update status 200")
        me3 = resp.get_json()
        assert_eq(me3["major_code"], "BZA", "major preserved on partial update")
        assert_eq(me3["matric_year"], 2025, "matric_year updated")
    finally:
        _teardown(path, original)


def test_auth_required():
    print("\n[auth required]")
    app, path, original = _setup_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/api/majors")  # no auth header
        assert_eq(resp.status_code, 401, "no auth header → 401")

        resp = client.get("/api/majors", headers={"Authorization": "Bearer garbage"})
        assert_eq(resp.status_code, 401, "garbage token → 401")
    finally:
        _teardown(path, original)


if __name__ == "__main__":
    print("Running majors / onboarding tests…")
    test_list_majors()
    test_major_detail()
    test_update_profile_with_major()
    test_auth_required()
    print("\nAll tests passed ✓")
