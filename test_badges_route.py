"""Integration tests for the badges endpoint.

End-to-end scenarios that exercise the data gathering query + persistence
behavior. Each test sets up the user state, hits /api/badges, and asserts on
the returned earned states + newly_earned flags.

Run: python tests/test_badges_route.py
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


def _auth(uid):
    return {"Authorization": f"Bearer dev-user-{uid}"}


def _make_plan(client, uid, entries=None, grades=None, su=None):
    """Create a plan + optionally seed entries/grades/SU flags.
    `entries` = [(code, sem)], `grades` = {code: grade}, `su` = {code: bool}"""
    p = client.post("/api/plans", headers=_auth(uid), json={"name": "T"})
    plan_id = p.get_json()["id"]
    for code, sem in (entries or []):
        add = client.post(f"/api/plans/{plan_id}/entries", headers=_auth(uid),
                          json={"module_code": code, "semester_id": sem})
        eid = add.get_json()["id"]
        patch = {}
        if grades and code in grades: patch["grade"] = grades[code]
        if su and su.get(code): patch["is_su"] = True
        if patch:
            client.put(f"/api/plans/{plan_id}/entries/{eid}", headers=_auth(uid), json=patch)
    return plan_id


def _earned_set(badges):
    return {b["key"] for b in badges if b["earned"]}


# ---------------- tests ----------------

def test_empty_user_no_badges():
    print("\n[empty user → 0 badges]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        client.put("/api/me", headers=_auth("alice"),
                   json={"major_code": "CS", "matric_year": 2024})
        resp = client.get("/api/badges", headers=_auth("alice"))
        assert_eq(resp.status_code, 200, "status 200")
        data = resp.get_json()
        assert_eq(data["earned_count"], 0, "no earned badges")
        assert_eq(data["total_count"], 10, "10 total")
        # Catalog comes through fully even though nothing is earned
        for b in data["badges"]:
            for f in ("key", "title", "description", "tier"):
                assert b[f], f"badge {b.get('key')} missing {f}"
    finally:
        _teardown(path, orig)


def test_first_module_persists_and_newly_earned():
    print("\n[first-module: earned + newly_earned, then earned but not newly]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        client.put("/api/me", headers=_auth("alice"),
                   json={"major_code": "CS", "matric_year": 2024})
        _make_plan(client, "alice", [("CS1101S", "Y1S1")])

        # First call — first-module is newly_earned
        resp = client.get("/api/badges", headers=_auth("alice"))
        data = resp.get_json()
        fm = next(b for b in data["badges"] if b["key"] == "first-module")
        assert_eq(fm["earned"], True, "earned")
        assert_eq(fm["newly_earned"], True, "newly_earned on first eval")
        assert fm["earned_at"], "earned_at populated"

        # Second call — still earned, but no longer newly
        resp = client.get("/api/badges", headers=_auth("alice"))
        fm = next(b for b in resp.get_json()["badges"] if b["key"] == "first-module")
        assert_eq(fm["earned"], True, "still earned")
        assert_eq(fm["newly_earned"], False, "no longer newly_earned")
    finally:
        _teardown(path, orig)


def test_building_tier_badges_earn_together():
    print("\n[building tier: place enough to earn first-module + first-year]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        client.put("/api/me", headers=_auth("alice"),
                   json={"major_code": "CS", "matric_year": 2024})
        # 24 MC in Y1 — earns first-module + first-year
        _make_plan(client, "alice", [
            ("CS1101S", "Y1S1"), ("CS1231S", "Y1S1"), ("CS2030S", "Y1S2"),
            ("CS2040S", "Y1S2"), ("MA1521", "Y1S1"), ("MA1101R", "Y1S2"),
        ])
        resp = client.get("/api/badges", headers=_auth("alice"))
        earned = _earned_set(resp.get_json()["badges"])
        assert "first-module" in earned, "first-module earned"
        assert "first-year" in earned, "first-year earned (24 MC in Y1)"
        assert "full-map" not in earned, "full-map not yet (only 2 semesters)"
    finally:
        _teardown(path, orig)


def test_full_map_badge():
    print("\n[full-map: one module in each of 8 semesters]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        client.put("/api/me", headers=_auth("alice"),
                   json={"major_code": "CS", "matric_year": 2024})
        # Place one module in each of the 8 semesters
        sems = [f"Y{y}S{s}" for y in range(1, 5) for s in range(1, 3)]
        codes = ["CS1101S", "CS1231S", "CS2030S", "CS2040S",
                 "CS2100", "CS2103T", "CS3216", "CS4248"]
        _make_plan(client, "alice", list(zip(codes, sems)))

        resp = client.get("/api/badges", headers=_auth("alice"))
        earned = _earned_set(resp.get_json()["badges"])
        assert "full-map" in earned, "full-map earned"
    finally:
        _teardown(path, orig)


def test_tracking_tier_badges():
    print("\n[tracking tier: grades + S/U]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        client.put("/api/me", headers=_auth("alice"),
                   json={"major_code": "CS", "matric_year": 2024})
        _make_plan(
            client, "alice",
            entries=[("CS1101S", "Y1S1"), ("CS1231S", "Y1S1"), ("CS2030S", "Y1S2"),
                     ("CS2040S", "Y1S2"), ("MA1521", "Y1S1")],
            grades={"CS1101S": "A", "CS1231S": "B+", "CS2030S": "A-", "CS2040S": "B",
                    "MA1521": "A"},
            su={"MA1521": True},
        )
        resp = client.get("/api/badges", headers=_auth("alice"))
        earned = _earned_set(resp.get_json()["badges"])
        assert "first-grade" in earned, "first-grade"
        assert "engaged-grader" in earned, "engaged-grader (5 grades)"
        assert "su-aware" in earned, "su-aware (1 S/U)"
    finally:
        _teardown(path, orig)


def test_community_tier_badges():
    print("\n[community tier: share + opt-in]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        # Alice + Bob exist
        client.put("/api/me", headers=_auth("alice"),
                   json={"major_code": "CS", "matric_year": 2024})
        client.post("/api/auth/sync", headers=_auth("alice"),
                    json={"email": "alice@example.com"})
        client.put("/api/me", headers=_auth("bob"),
                   json={"major_code": "CS", "matric_year": 2024})
        client.post("/api/auth/sync", headers=_auth("bob"),
                    json={"email": "bob@example.com"})

        plan_id = _make_plan(client, "alice", [("CS1101S", "Y1S1")])
        # Alice shares her plan with Bob → earns "collaborator"
        client.post(f"/api/plans/{plan_id}/share", headers=_auth("alice"),
                    json={"email": "bob@example.com"})
        # Alice opts into a study group → earns "networker"
        client.post("/api/study-groups/optin", headers=_auth("alice"),
                    json={"module_code": "CS1101S", "semester_id": "Y1S1"})

        resp = client.get("/api/badges", headers=_auth("alice"))
        earned = _earned_set(resp.get_json()["badges"])
        assert "collaborator" in earned, "collaborator"
        assert "networker" in earned, "networker"
        # popular-signup requires 3+ others, which we don't have here
        assert "popular-signup" not in earned, "popular-signup not yet"
    finally:
        _teardown(path, orig)


def test_popular_signup_badge():
    print("\n[popular-signup: opt-in with 3+ others interested]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        client.put("/api/me", headers=_auth("alice"),
                   json={"major_code": "CS", "matric_year": 2024})
        # Alice opts in
        client.post("/api/study-groups/optin", headers=_auth("alice"),
                    json={"module_code": "CS2030S", "semester_id": "Y1S2"})
        # 3 other users also opt in for the same one
        for uid in ("bob", "carol", "dave"):
            client.put("/api/me", headers=_auth(uid),
                       json={"major_code": "CS", "matric_year": 2024})
            client.post("/api/study-groups/optin", headers=_auth(uid),
                        json={"module_code": "CS2030S", "semester_id": "Y1S2"})

        resp = client.get("/api/badges", headers=_auth("alice"))
        earned = _earned_set(resp.get_json()["badges"])
        assert "popular-signup" in earned, "popular-signup earned (3 others)"
    finally:
        _teardown(path, orig)


def test_near_graduation_badge():
    print("\n[near-graduation: ≥80% of required MCs placed]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        client.put("/api/me", headers=_auth("alice"),
                   json={"major_code": "CS", "matric_year": 2024})

        # CS major requires 128 MCs; 80% = 102.4. Place enough seed modules to
        # clear that — use every module the seed knows about (31 modules × ~4 MC
        # = 130 MC total) round-robin across the 8 semester slots. We don't
        # care about prereq validity here; we just need the placements to count
        # toward total_placed_mcs.
        from db import connect
        with connect() as c:
            all_codes = [r["code"] for r in c.execute("SELECT code FROM modules").fetchall()]
        sems = [f"Y{y}S{s}" for y in range(1, 5) for s in range(1, 3)]
        entries = [(code, sems[i % 8]) for i, code in enumerate(all_codes)]
        _make_plan(client, "alice", entries)

        resp = client.get("/api/badges", headers=_auth("alice"))
        earned = _earned_set(resp.get_json()["badges"])
        assert "near-graduation" in earned, "near-graduation earned"
    finally:
        _teardown(path, orig)


def test_earned_at_persists_across_requests():
    print("\n[earned_at is locked once earned]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        client.put("/api/me", headers=_auth("alice"),
                   json={"major_code": "CS", "matric_year": 2024})
        _make_plan(client, "alice", [("CS1101S", "Y1S1")])

        # First call
        first = client.get("/api/badges", headers=_auth("alice")).get_json()
        first_fm = next(b for b in first["badges"] if b["key"] == "first-module")
        first_ts = first_fm["earned_at"]
        assert first_ts, "earned_at populated"

        # Place more modules — first-module is still earned, earned_at shouldn't change
        client.post("/api/plans/1/entries", headers=_auth("alice"),
                    json={"module_code": "CS1231S", "semester_id": "Y1S1"})
        second = client.get("/api/badges", headers=_auth("alice")).get_json()
        second_fm = next(b for b in second["badges"] if b["key"] == "first-module")
        assert_eq(second_fm["earned_at"], first_ts, "earned_at unchanged")
        assert_eq(second_fm["newly_earned"], False, "not newly earned on re-fetch")
    finally:
        _teardown(path, orig)


def test_auth_required():
    print("\n[auth required]")
    app, path, orig = _setup_temp_db()
    try:
        client = app.test_client()
        resp = client.get("/api/badges")
        assert_eq(resp.status_code, 401, "no auth → 401")
    finally:
        _teardown(path, orig)


if __name__ == "__main__":
    print("Running badges route tests…")
    test_empty_user_no_badges()
    test_first_module_persists_and_newly_earned()
    test_building_tier_badges_earn_together()
    test_full_map_badge()
    test_tracking_tier_badges()
    test_community_tier_badges()
    test_popular_signup_badge()
    test_near_graduation_badge()
    test_earned_at_persists_across_requests()
    test_auth_required()
    print("\nAll tests passed ✓")
