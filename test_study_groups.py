"""Integration tests for the study group endpoints.

Covers:
  - POST opt-in: success + duplicate handling
  - PUT opt-in: update message, owner-only
  - DELETE opt-in: owner-only, 404 on missing
  - GET matches: ranking, profile metadata, excludes self
  - GET my-optins: lists current user's opt-ins with others_count
  - Bad input errors

Run: python tests/test_study_groups.py
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


def _auth(user_id):
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def _setup_user(client, user_id, major="CS", matric_year=2024, telegram=None):
    """Set profile fields. Auth lazy-inserts the user; PUT /api/me fills in profile."""
    body = {"major_code": major, "matric_year": matric_year}
    if telegram is not None:
        body["contact_telegram"] = telegram
    client.put("/api/me", headers=_auth(user_id), json=body)


def _make_plan_with(client, user_id, codes_by_sem):
    """Create a plan and add entries. codes_by_sem = {Y1S1: [codes], ...}."""
    p = client.post("/api/plans", headers=_auth(user_id), json={"name": "Test"})
    plan_id = p.get_json()["id"]
    for sem, codes in codes_by_sem.items():
        for code in codes:
            client.post(f"/api/plans/{plan_id}/entries", headers=_auth(user_id),
                        json={"module_code": code, "semester_id": sem})
    return plan_id


# ---------------- opt-in CRUD ----------------

def test_optin_and_duplicate():
    print("\n[POST optin: create + duplicate detection]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _setup_user(client, "alice")
        resp = client.post("/api/study-groups/optin", headers=_auth("alice"),
                           json={"module_code": "CS2030S", "semester_id": "Y1S2", "message": "hey"})
        assert_eq(resp.status_code, 201, "first opt-in created")
        body = resp.get_json()
        assert_eq(body["module_code"], "CS2030S", "code uppercased + stored")
        assert_eq(body["message"], "hey", "message stored")

        # Duplicate
        dup = client.post("/api/study-groups/optin", headers=_auth("alice"),
                          json={"module_code": "CS2030S", "semester_id": "Y1S2"})
        assert_eq(dup.status_code, 409, "duplicate → 409")
        assert_eq(dup.get_json()["code"], "DUPLICATE", "DUPLICATE error code")
    finally:
        _teardown(path, orig)


def test_optin_bad_input():
    print("\n[POST optin: bad input]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _setup_user(client, "alice")
        r = client.post("/api/study-groups/optin", headers=_auth("alice"), json={})
        assert_eq(r.status_code, 400, "empty body → 400")
        r = client.post("/api/study-groups/optin", headers=_auth("alice"),
                        json={"module_code": "CS2030S"})
        assert_eq(r.status_code, 400, "missing sem → 400")
    finally:
        _teardown(path, orig)


def test_optin_update_message():
    print("\n[PUT optin: update message]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _setup_user(client, "alice")
        opt = client.post("/api/study-groups/optin", headers=_auth("alice"),
                          json={"module_code": "CS2030S", "semester_id": "Y1S2",
                                "message": "original"}).get_json()
        resp = client.put(f"/api/study-groups/optin/{opt['id']}", headers=_auth("alice"),
                          json={"message": "updated"})
        assert_eq(resp.status_code, 200, "update returns 200")
        assert_eq(resp.get_json()["message"], "updated", "message updated")

        # Empty string → NULL
        resp = client.put(f"/api/study-groups/optin/{opt['id']}", headers=_auth("alice"),
                          json={"message": "   "})
        assert_eq(resp.get_json()["message"], None, "empty → null")
    finally:
        _teardown(path, orig)


def test_optin_update_owner_only():
    print("\n[PUT optin: owner only]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _setup_user(client, "alice")
        _setup_user(client, "bob")
        opt = client.post("/api/study-groups/optin", headers=_auth("alice"),
                          json={"module_code": "CS2030S", "semester_id": "Y1S2"}).get_json()
        # Bob tries to update Alice's opt-in
        resp = client.put(f"/api/study-groups/optin/{opt['id']}", headers=_auth("bob"),
                          json={"message": "haxx"})
        assert_eq(resp.status_code, 404, "bob can't update alice's opt-in")
    finally:
        _teardown(path, orig)


def test_optout():
    print("\n[DELETE optin]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _setup_user(client, "alice")
        opt = client.post("/api/study-groups/optin", headers=_auth("alice"),
                          json={"module_code": "CS2030S", "semester_id": "Y1S2"}).get_json()
        resp = client.delete(f"/api/study-groups/optin/{opt['id']}", headers=_auth("alice"))
        assert_eq(resp.status_code, 204, "delete returns 204")
        # second delete is 404
        resp = client.delete(f"/api/study-groups/optin/{opt['id']}", headers=_auth("alice"))
        assert_eq(resp.status_code, 404, "second delete → 404")
    finally:
        _teardown(path, orig)


# ---------------- matches ----------------

def test_matches_ranking_by_compatibility():
    print("\n[GET matches: ranked by compatibility]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        # Me: CS 2024 with a substantial plan
        _setup_user(client, "alice", major="CS", matric_year=2024)
        _make_plan_with(client, "alice", {
            "Y1S1": ["CS1101S", "CS1231S"],
            "Y1S2": ["CS2030S", "CS2040S"],
        })
        # Bob: CS 2024 with similar plan — best match
        _setup_user(client, "bob", major="CS", matric_year=2024)
        _make_plan_with(client, "bob", {
            "Y1S1": ["CS1101S", "CS1231S"],
            "Y1S2": ["CS2030S", "CS2040S"],
        })
        # Carol: BZA 2024 with disjoint plan — middling
        _setup_user(client, "carol", major="BZA", matric_year=2024)
        _make_plan_with(client, "carol", {
            "Y1S1": ["BT2102"],
        })
        # Dave: CS 2022 with no overlap — middling
        _setup_user(client, "dave", major="CS", matric_year=2022)
        _make_plan_with(client, "dave", {
            "Y4S1": ["CS4248"],
        })

        for u in ("bob", "carol", "dave"):
            client.post("/api/study-groups/optin", headers=_auth(u),
                        json={"module_code": "CS2030S", "semester_id": "Y1S2"})

        resp = client.get("/api/study-groups/matches?module_code=CS2030S&semester_id=Y1S2",
                          headers=_auth("alice"))
        assert_eq(resp.status_code, 200, "status 200")
        matches = resp.get_json()["matches"]
        assert_eq(len(matches), 3, "three matches found")
        # Bob should be #1: same major + same year + plan overlap
        assert_eq(matches[0]["user_id"], "dev-user-bob", "bob ranks first")
        assert matches[0]["score"] > matches[1]["score"], "bob > others"
        # Bob's reasons should mention both major and year
        bob_reasons_text = " ".join(matches[0]["reasons"]).lower()
        assert "major" in bob_reasons_text, "bob: major in reasons"
        assert "year" in bob_reasons_text, "bob: year in reasons"
    finally:
        _teardown(path, orig)


def test_matches_excludes_self():
    print("\n[GET matches: excludes the requester]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _setup_user(client, "alice")
        client.post("/api/study-groups/optin", headers=_auth("alice"),
                    json={"module_code": "CS2030S", "semester_id": "Y1S2"})
        resp = client.get("/api/study-groups/matches?module_code=CS2030S&semester_id=Y1S2",
                          headers=_auth("alice"))
        assert_eq(resp.get_json()["matches"], [], "alice doesn't see herself")
    finally:
        _teardown(path, orig)


def test_matches_includes_telegram_when_set():
    print("\n[GET matches: surfaces contact_telegram]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _setup_user(client, "alice")
        _setup_user(client, "bob", telegram="bob_nus")
        client.post("/api/study-groups/optin", headers=_auth("bob"),
                    json={"module_code": "CS2030S", "semester_id": "Y1S2"})

        resp = client.get("/api/study-groups/matches?module_code=CS2030S&semester_id=Y1S2",
                          headers=_auth("alice"))
        matches = resp.get_json()["matches"]
        assert_eq(matches[0]["contact_telegram"], "bob_nus", "telegram surfaced")
    finally:
        _teardown(path, orig)


def test_matches_excludes_target_module_from_overlap():
    print("\n[GET matches: target module doesn't count toward overlap]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        # Both have ONLY the target module in common — that shouldn't generate overlap signal.
        _setup_user(client, "alice", major="BZA", matric_year=2024)
        _make_plan_with(client, "alice", {"Y1S2": ["CS2030S"]})
        _setup_user(client, "bob", major="CS", matric_year=2022)
        _make_plan_with(client, "bob", {"Y1S2": ["CS2030S"]})

        client.post("/api/study-groups/optin", headers=_auth("bob"),
                    json={"module_code": "CS2030S", "semester_id": "Y1S2"})
        resp = client.get("/api/study-groups/matches?module_code=CS2030S&semester_id=Y1S2",
                          headers=_auth("alice"))
        match = resp.get_json()["matches"][0]
        assert_eq(match["plan_overlap_count"], 0, "no overlap (target module excluded)")
    finally:
        _teardown(path, orig)


# ---------------- my-optins ----------------

def test_my_optins():
    print("\n[GET my-optins]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _setup_user(client, "alice")
        _setup_user(client, "bob")
        # Alice opts in for two modules
        client.post("/api/study-groups/optin", headers=_auth("alice"),
                    json={"module_code": "CS2030S", "semester_id": "Y1S2", "message": "hi"})
        client.post("/api/study-groups/optin", headers=_auth("alice"),
                    json={"module_code": "CS2040S", "semester_id": "Y1S2"})
        # Bob opts in for one of them — bumps Alice's others_count for CS2030S to 1.
        client.post("/api/study-groups/optin", headers=_auth("bob"),
                    json={"module_code": "CS2030S", "semester_id": "Y1S2"})

        resp = client.get("/api/study-groups/my-optins", headers=_auth("alice"))
        assert_eq(resp.status_code, 200, "status 200")
        optins = resp.get_json()["optins"]
        assert_eq(len(optins), 2, "alice has 2 opt-ins")
        cs2030 = next(o for o in optins if o["module_code"] == "CS2030S")
        cs2040 = next(o for o in optins if o["module_code"] == "CS2040S")
        assert_eq(cs2030["others_count"], 1, "CS2030S: 1 other interested")
        assert_eq(cs2040["others_count"], 0, "CS2040S: no others")
        assert_eq(cs2030["message"], "hi", "message persisted")
        # Module title joined in
        assert cs2030["module_title"], "module_title populated"
    finally:
        _teardown(path, orig)


# ---------------- profile (telegram) ----------------

def test_users_can_set_telegram():
    print("\n[PUT /api/me accepts contact_telegram]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _setup_user(client, "alice")
        # With @ prefix → stripped on store
        resp = client.put("/api/me", headers=_auth("alice"),
                          json={"contact_telegram": "@alice_nus"})
        assert_eq(resp.get_json()["contact_telegram"], "alice_nus", "@ prefix stripped")

        # Empty string → null
        resp = client.put("/api/me", headers=_auth("alice"),
                          json={"contact_telegram": ""})
        assert_eq(resp.get_json()["contact_telegram"], None, "empty → null")
    finally:
        _teardown(path, orig)


if __name__ == "__main__":
    print("Running study-groups route tests…")
    test_optin_and_duplicate()
    test_optin_bad_input()
    test_optin_update_message()
    test_optin_update_owner_only()
    test_optout()
    test_matches_ranking_by_compatibility()
    test_matches_excludes_self()
    test_matches_includes_telegram_when_set()
    test_matches_excludes_target_module_from_overlap()
    test_my_optins()
    test_users_can_set_telegram()
    print("\nAll tests passed ✓")
