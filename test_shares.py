"""Integration tests for plan sharing endpoints + shared-plan reads.

Covers:
  - POST /api/plans/:id/share: by user_id, by email, with/without grades, errors
  - Re-sharing updates include_grades (upsert)
  - GET /api/plans/:id/shares: owner-only listing
  - DELETE /api/plans/:id/shares/:share_id: revoke, errors
  - GET /api/shared-with-me
  - GET /api/plans/:id: serves shared plans, hides grades when include_grades=false
  - Non-owner, non-recipient sees 404 (no leaking which plan IDs exist)
  - Owner of plan A can't share plan B they don't own
  - You can't share with yourself

Run: python tests/test_shares.py
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


def _auth(user_id: str) -> dict:
    return {"Authorization": f"Bearer dev-user-{user_id}"}


def _ensure_user(client, user_id: str, email: str | None = None, major: str = "CS"):
    """Create a user (via lazy-insert in require_auth) and patch in profile fields.

    Uses /api/auth/sync to set email (PUT /api/me doesn't accept it — it's an
    auth-provider-managed field, populated from the JWT in prod) and PUT /api/me
    for major_code / matric_year.
    """
    auth = _auth(user_id)
    # Set email via auth/sync — this is the canonical "user just signed in" call
    if email:
        client.post("/api/auth/sync", headers=auth, json={"email": email})
    # Set major/matric_year via /api/me
    client.put("/api/me", headers=auth, json={"major_code": major, "matric_year": 2024})


def _make_plan(client, user_id: str, entries: list[tuple[str, str]] = None, grades: dict = None):
    """Create a plan owned by user_id, optionally with entries and grades.
    `entries` is [(module_code, semester_id), ...]; `grades` is {module_code: grade_str}."""
    plan_resp = client.post("/api/plans", headers=_auth(user_id), json={"name": "Test"})
    plan_id = plan_resp.get_json()["id"]
    for code, sem in (entries or []):
        add = client.post(f"/api/plans/{plan_id}/entries", headers=_auth(user_id),
                          json={"module_code": code, "semester_id": sem})
        eid = add.get_json()["id"]
        if grades and code in grades:
            client.put(f"/api/plans/{plan_id}/entries/{eid}", headers=_auth(user_id),
                       json={"grade": grades[code]})
    return plan_id


# ---------- POST /share ----------

def test_share_by_user_id():
    print("\n[share by user_id]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        plan_id = _make_plan(client, "alice", [("CS1101S", "Y1S1")])

        resp = client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                           json={"user_id": "dev-user-bob"})
        assert_eq(resp.status_code, 201, "share created")
        body = resp.get_json()
        assert_eq(body["shared_with"]["user_id"], "dev-user-bob", "shared_with user_id")
        assert_eq(body["include_grades"], False, "default include_grades is False")
    finally:
        _teardown(path, orig)


def test_share_by_email():
    print("\n[share by email]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        plan_id = _make_plan(client, "alice")

        # Lowercase email — should match regardless of case
        resp = client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                           json={"email": "BOB@NUS.EXAMPLE.COM", "include_grades": True})
        assert_eq(resp.status_code, 201, "share created via uppercase email")
        body = resp.get_json()
        assert_eq(body["shared_with"]["user_id"], "dev-user-bob", "resolved to bob")
        assert_eq(body["include_grades"], True, "include_grades True")
    finally:
        _teardown(path, orig)


def test_share_unknown_user():
    print("\n[share with unknown user → 404]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        plan_id = _make_plan(client, "alice")

        resp = client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                           json={"email": "nobody@nus.example.com"})
        assert_eq(resp.status_code, 404, "unknown email → 404")
        assert_eq(resp.get_json()["code"], "USER_NOT_FOUND", "USER_NOT_FOUND code")
    finally:
        _teardown(path, orig)


def test_share_with_self_blocked():
    print("\n[can't share with self]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        plan_id = _make_plan(client, "alice")

        resp = client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                           json={"user_id": "dev-user-alice"})
        assert_eq(resp.status_code, 400, "self-share → 400")
    finally:
        _teardown(path, orig)


def test_share_bad_input():
    print("\n[share with neither user_id nor email → 400]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        plan_id = _make_plan(client, "alice")
        resp = client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"), json={})
        assert_eq(resp.status_code, 400, "no recipient → 400")
    finally:
        _teardown(path, orig)


def test_share_non_owner_blocked():
    print("\n[non-owner can't share]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        _ensure_user(client, "eve",   "eve@nus.example.com")
        plan_id = _make_plan(client, "alice")

        # Eve tries to share Alice's plan with Bob
        resp = client.post(f"/api/plans/{plan_id}/share", headers=_auth("eve"),
                           json={"user_id": "dev-user-bob"})
        assert_eq(resp.status_code, 404, "non-owner → 404 (looks like plan doesn't exist)")
    finally:
        _teardown(path, orig)


def test_reshare_updates_include_grades():
    print("\n[re-share updates include_grades flag]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        plan_id = _make_plan(client, "alice")

        # First share: no grades
        client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                    json={"user_id": "dev-user-bob", "include_grades": False})
        # Re-share: include grades
        resp = client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                           json={"user_id": "dev-user-bob", "include_grades": True})
        assert_eq(resp.status_code, 201, "re-share returns 201")
        assert_eq(resp.get_json()["include_grades"], True, "now include_grades=True")

        # And there's still only ONE share row (upsert, not insert)
        list_resp = client.get(f"/api/plans/{plan_id}/shares", headers=_auth("alice"))
        assert_eq(len(list_resp.get_json()["shares"]), 1, "still one share row")
    finally:
        _teardown(path, orig)


# ---------- GET /shares ----------

def test_list_shares():
    print("\n[list shares of plan]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        _ensure_user(client, "carol", "carol@nus.example.com")
        plan_id = _make_plan(client, "alice")

        client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                    json={"user_id": "dev-user-bob"})
        client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                    json={"user_id": "dev-user-carol", "include_grades": True})

        resp = client.get(f"/api/plans/{plan_id}/shares", headers=_auth("alice"))
        assert_eq(resp.status_code, 200, "status 200")
        shares = resp.get_json()["shares"]
        assert_eq(len(shares), 2, "two shares")
        recipients = {s["shared_with"]["user_id"] for s in shares}
        assert recipients == {"dev-user-bob", "dev-user-carol"}, "right recipients"

        # Bob (recipient, not owner) can't list shares
        bob_resp = client.get(f"/api/plans/{plan_id}/shares", headers=_auth("bob"))
        assert_eq(bob_resp.status_code, 404, "non-owner can't list shares")
    finally:
        _teardown(path, orig)


# ---------- DELETE /shares/:id ----------

def test_revoke_share():
    print("\n[revoke share]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        plan_id = _make_plan(client, "alice")

        share = client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                            json={"user_id": "dev-user-bob"}).get_json()
        share_id = share["id"]

        # Bob can read while shared
        get_resp = client.get(f"/api/plans/{plan_id}", headers=_auth("bob"))
        assert_eq(get_resp.status_code, 200, "Bob can read shared plan")

        # Alice revokes
        del_resp = client.delete(f"/api/plans/{plan_id}/shares/{share_id}", headers=_auth("alice"))
        assert_eq(del_resp.status_code, 200, "revoke returns 200")

        # Bob can no longer read
        get_resp = client.get(f"/api/plans/{plan_id}", headers=_auth("bob"))
        assert_eq(get_resp.status_code, 404, "Bob locked out after revoke")

        # Revoking again returns 404
        re_del = client.delete(f"/api/plans/{plan_id}/shares/{share_id}", headers=_auth("alice"))
        assert_eq(re_del.status_code, 404, "second revoke → 404")
    finally:
        _teardown(path, orig)


# ---------- GET /shared-with-me ----------

def test_shared_with_me():
    print("\n[/shared-with-me]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        _ensure_user(client, "carol", "carol@nus.example.com")
        alice_plan = _make_plan(client, "alice", [("CS1101S", "Y1S1")])
        carol_plan = _make_plan(client, "carol", [("MA1521", "Y1S1")])

        # Alice and Carol both share with Bob
        client.post(f"/api/plans/{alice_plan}/share", headers=_auth("alice"),
                    json={"user_id": "dev-user-bob", "include_grades": True})
        client.post(f"/api/plans/{carol_plan}/share", headers=_auth("carol"),
                    json={"user_id": "dev-user-bob"})

        resp = client.get("/api/shared-with-me", headers=_auth("bob"))
        plans = resp.get_json()["plans"]
        assert_eq(len(plans), 2, "Bob sees 2 plans")
        owners = {p["owner"]["user_id"] for p in plans}
        assert owners == {"dev-user-alice", "dev-user-carol"}, "owners attributed"
        # Alice's share had include_grades=True
        alice_entry = next(p for p in plans if p["owner"]["user_id"] == "dev-user-alice")
        assert_eq(alice_entry["include_grades"], True, "Alice's share includes grades")
    finally:
        _teardown(path, orig)


# ---------- GET /plans/:id when shared ----------

def test_shared_read_hides_grades():
    print("\n[GET shared plan hides grades when include_grades=False]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        plan_id = _make_plan(client, "alice",
                             entries=[("CS1101S", "Y1S1"), ("CS1231S", "Y1S1")],
                             grades={"CS1101S": "A", "CS1231S": "B+"})

        # Share WITHOUT grades
        client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                    json={"user_id": "dev-user-bob"})

        # Alice (owner) sees grades
        resp = client.get(f"/api/plans/{plan_id}", headers=_auth("alice"))
        plan = resp.get_json()
        assert_eq(plan["access"], "owner", "alice: access=owner")
        assert any(e.get("grade") for e in plan["entries"]), "alice sees grades"

        # Bob (recipient, no-grade share) does NOT see grades
        resp = client.get(f"/api/plans/{plan_id}", headers=_auth("bob"))
        plan = resp.get_json()
        assert_eq(plan["access"], "shared", "bob: access=shared")
        assert_eq(plan["include_grades"], False, "bob: include_grades=False")
        for e in plan["entries"]:
            assert "grade" not in e, f"grade stripped from entry {e}"
    finally:
        _teardown(path, orig)


def test_shared_read_with_grades():
    print("\n[GET shared plan exposes grades when include_grades=True]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        plan_id = _make_plan(client, "alice",
                             entries=[("CS1101S", "Y1S1")],
                             grades={"CS1101S": "A"})

        client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                    json={"user_id": "dev-user-bob", "include_grades": True})

        resp = client.get(f"/api/plans/{plan_id}", headers=_auth("bob"))
        plan = resp.get_json()
        assert_eq(plan["include_grades"], True, "bob: include_grades=True")
        cs1101 = next(e for e in plan["entries"] if e["module_code"] == "CS1101S")
        assert_eq(cs1101["grade"], "A", "bob sees grade A")
    finally:
        _teardown(path, orig)


def test_non_recipient_404():
    print("\n[non-recipient sees 404 (no plan-id leak)]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        _ensure_user(client, "eve",   "eve@nus.example.com")
        plan_id = _make_plan(client, "alice")
        client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                    json={"user_id": "dev-user-bob"})

        # Eve has nothing — should see 404
        resp = client.get(f"/api/plans/{plan_id}", headers=_auth("eve"))
        assert_eq(resp.status_code, 404, "eve gets 404")
        # Same error code as a truly non-existent plan
        nonexistent = client.get("/api/plans/99999", headers=_auth("eve"))
        assert_eq(nonexistent.get_json()["code"], resp.get_json()["code"],
                  "same error code for both — no leak")
    finally:
        _teardown(path, orig)


def test_shared_plan_is_readonly():
    print("\n[recipient can read but not modify shared plan]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        _ensure_user(client, "alice", "alice@nus.example.com")
        _ensure_user(client, "bob",   "bob@nus.example.com")
        plan_id = _make_plan(client, "alice", [("CS1101S", "Y1S1")])
        client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                    json={"user_id": "dev-user-bob"})

        # Bob tries to add an entry — should fail because the entry routes
        # still use _own_plan_or_404 (the strict ownership check). We're
        # intentionally not granting write access via shares.
        resp = client.post(f"/api/plans/{plan_id}/entries", headers=_auth("bob"),
                           json={"module_code": "CS1231S", "semester_id": "Y1S1"})
        assert_eq(resp.status_code, 404, "Bob can't add entries — read-only")

        # Bob tries to delete the plan
        del_resp = client.delete(f"/api/plans/{plan_id}", headers=_auth("bob"))
        assert_eq(del_resp.status_code, 404, "Bob can't delete the plan")
    finally:
        _teardown(path, orig)


if __name__ == "__main__":
    print("Running share endpoint tests…")
    test_share_by_user_id()
    test_share_by_email()
    test_share_unknown_user()
    test_share_with_self_blocked()
    test_share_bad_input()
    test_share_non_owner_blocked()
    test_reshare_updates_include_grades()
    test_list_shares()
    test_revoke_share()
    test_shared_with_me()
    test_shared_read_hides_grades()
    test_shared_read_with_grades()
    test_non_recipient_404()
    test_shared_plan_is_readonly()
    print("\nAll tests passed ✓")
