"""Study group opt-in and matching — Feature 11 rewrite.

Endpoints:
  POST   /api/study-groups/optin               opt into a (module, semester) for matching
  PUT    /api/study-groups/optin/:id           update message
  DELETE /api/study-groups/optin/:id           opt out
  GET    /api/study-groups/matches?...         find others opted into the same (module, semester),
                                               ranked by compatibility (see services.study_group_match)
  GET    /api/study-groups/my-optins           list MY opt-ins with match counts per row

Matches are ranked using a small additive scoring function (same major,
same matric year, plan overlap, recency). The route hydrates each
candidate with their plan's modules (best-active-plan heuristic, see below)
so the scorer can compute Jaccard overlap on the side.
"""
from __future__ import annotations
from flask import Blueprint, request, jsonify, g

from db import get_db
from auth import require_auth
from services.study_group_match import MatchCandidate, rank_matches

bp = Blueprint("study_groups", __name__)


def _user_active_plan_modules(db, user_id: str) -> set[str]:
    """Return the set of module codes in `user_id`'s first plan.

    "First" = lowest id = most likely the primary plan. Most users have one
    plan; the rare user with multiple gets their oldest one counted for
    matching purposes. Good enough for v1; if usage shifts to multi-plan as
    a norm, we'd surface a plan picker in the opt-in flow.
    """
    rows = db.execute(
        """
        SELECT pe.module_code
        FROM plan_entries pe
        JOIN study_plans p ON p.id = pe.plan_id
        WHERE p.user_id = ?
          AND p.id = (SELECT MIN(id) FROM study_plans WHERE user_id = ?)
        """,
        (user_id, user_id),
    ).fetchall()
    return {r["module_code"] for r in rows}


# ---------- POST opt-in ----------

@bp.post("/api/study-groups/optin")
@require_auth
def optin():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("module_code") or "").upper().strip()
    sem = payload.get("semester_id")
    msg = (payload.get("message") or "").strip() or None
    if not code or not sem:
        return jsonify(error="module_code and semester_id required", code="BAD_INPUT"), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO study_group_optins (user_id, module_code, semester_id, message) VALUES (?, ?, ?, ?)",
            (g.user_id, code, sem, msg),
        )
        db.commit()
    except Exception:
        # The likely cause is the UNIQUE constraint; return a friendly DUPLICATE
        # rather than a generic 500.
        return jsonify(error="Already opted in for this module/semester", code="DUPLICATE"), 409
    return jsonify(
        id=cur.lastrowid,
        module_code=code,
        semester_id=sem,
        message=msg,
    ), 201


# ---------- PUT opt-in (edit message) ----------

@bp.put("/api/study-groups/optin/<int:optin_id>")
@require_auth
def update_optin(optin_id):
    """Update the opt-in's message. Other fields are immutable — to change
    module/semester, opt out and back in (rare action, not worth the complexity)."""
    payload = request.get_json(silent=True) or {}
    if "message" not in payload:
        return jsonify(error="No editable field provided. Send {message: \"...\"}.",
                       code="BAD_INPUT"), 400
    msg = payload.get("message")
    msg = msg.strip() if isinstance(msg, str) else None
    msg = msg or None  # empty string → NULL

    db = get_db()
    cur = db.execute(
        "UPDATE study_group_optins SET message = ? WHERE id = ? AND user_id = ?",
        (msg, optin_id, g.user_id),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Opt-in not found", code="NOT_FOUND"), 404
    row = db.execute("SELECT * FROM study_group_optins WHERE id = ?", (optin_id,)).fetchone()
    return jsonify(dict(row))


# ---------- DELETE opt-in ----------

@bp.delete("/api/study-groups/optin/<int:optin_id>")
@require_auth
def optout(optin_id):
    db = get_db()
    cur = db.execute(
        "DELETE FROM study_group_optins WHERE id = ? AND user_id = ?",
        (optin_id, g.user_id),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Opt-in not found", code="NOT_FOUND"), 404
    return ("", 204)


# ---------- GET ranked matches ----------

@bp.get("/api/study-groups/matches")
@require_auth
def matches():
    """Return other students opted into (module_code, semester_id), ranked by
    compatibility. The requesting user is NOT auto-opted-in — they see the
    match list whether or not they themselves have opted in (so they can
    decide based on who's there).

    Each match includes per-pair signals: same_major, same_year, plan_overlap_count,
    recent, plus a numeric `score` (0-100) and a `reasons[]` array suitable for
    direct display.
    """
    code = (request.args.get("module_code") or "").upper().strip()
    sem = request.args.get("semester_id")
    if not code or not sem:
        return jsonify(error="module_code and semester_id required", code="BAD_INPUT"), 400

    db = get_db()
    # Pull the requester's profile + plan modules once.
    me_row = db.execute(
        "SELECT major_code, matric_year FROM users WHERE id = ?",
        (g.user_id,),
    ).fetchone()
    me_major = me_row["major_code"] if me_row else None
    me_year = me_row["matric_year"] if me_row else None
    me_plan_modules = _user_active_plan_modules(db, g.user_id)
    # Exclude the current target module from the overlap signal — having THIS
    # module in common is what brought us here, so it shouldn't contribute.
    me_plan_modules.discard(code)

    # Find everyone else who's opted in for this (module, semester).
    rows = db.execute(
        """
        SELECT sgo.id AS optin_id, sgo.user_id, sgo.message, sgo.created_at,
               u.display_name, u.email, u.major_code, u.matric_year, u.contact_telegram
        FROM study_group_optins sgo
        JOIN users u ON u.id = sgo.user_id
        WHERE sgo.module_code = ? AND sgo.semester_id = ? AND sgo.user_id != ?
        """,
        (code, sem, g.user_id),
    ).fetchall()

    if not rows:
        return jsonify(matches=[])

    # Hydrate each candidate with their plan modules. One small query per
    # candidate keeps the code simple; if this becomes a hot path we'd batch
    # with a single IN-clause join. With opt-ins typically <30 per module
    # this is fine.
    candidates: list[MatchCandidate] = []
    for r in rows:
        other_modules = _user_active_plan_modules(db, r["user_id"])
        other_modules.discard(code)  # same exclusion as above
        candidates.append(MatchCandidate(
            user_id=r["user_id"],
            display_name=r["display_name"],
            email=r["email"],
            major_code=r["major_code"],
            matric_year=r["matric_year"],
            contact_telegram=r["contact_telegram"],
            optin_id=r["optin_id"],
            message=r["message"],
            optin_created_at=r["created_at"],
            other_plan_modules=other_modules,
        ))

    ranked = rank_matches(
        me_major=me_major,
        me_matric_year=me_year,
        me_plan_modules=me_plan_modules,
        candidates=candidates,
    )
    return jsonify(matches=[m.as_dict() for m in ranked])


# ---------- GET my opt-ins ----------

@bp.get("/api/study-groups/my-optins")
@require_auth
def my_optins():
    """List the requesting user's opt-ins, each annotated with how many
    OTHERS have opted into the same (module, semester). Useful for the
    "My signups" panel where the user manages what they've opted into."""
    db = get_db()
    rows = db.execute(
        """
        SELECT sgo.id, sgo.module_code, sgo.semester_id, sgo.message, sgo.created_at,
               m.title AS module_title,
               (
                 SELECT COUNT(*) FROM study_group_optins o2
                 WHERE o2.module_code = sgo.module_code
                   AND o2.semester_id = sgo.semester_id
                   AND o2.user_id != sgo.user_id
               ) AS others_count
        FROM study_group_optins sgo
        LEFT JOIN modules m ON m.code = sgo.module_code
        WHERE sgo.user_id = ?
        ORDER BY sgo.created_at DESC
        """,
        (g.user_id,),
    ).fetchall()
    return jsonify(optins=[
        {
            "id": r["id"],
            "module_code": r["module_code"],
            "module_title": r["module_title"],
            "semester_id": r["semester_id"],
            "message": r["message"],
            "created_at": r["created_at"],
            "others_count": r["others_count"],
        }
        for r in rows
    ])
