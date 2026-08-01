"""Plan sharing endpoints.

  POST   /api/plans/:id/share          — grant a share to another user
  GET    /api/plans/:id/shares         — list current shares of this plan (owner only)
  DELETE /api/plans/:id/shares/:shareId — revoke a share (owner only)
  GET    /api/shared-with-me           — list plans shared with the current user

All endpoints require auth. Ownership is checked locally rather than via
the helper in plans.py to keep the two route modules independent — sharing
shouldn't import from plans.py and risk circular imports if plans.py grows.

The share recipient can be specified by either `user_id` or `email`. If `email`
is given we look up the user; if no user with that email exists we return a
USER_NOT_FOUND error (not a silent succeed-with-no-effect) so the sharer
knows the recipient hasn't signed up yet. Pre-signup invites would need a
separate mechanism (pending_invites table); see API.md "What's not done".
"""
from __future__ import annotations
from flask import Blueprint, request, jsonify, g

from db import get_db
from auth import require_auth

bp = Blueprint("shares", __name__)


def _own_plan_row(plan_id: int):
    """Return the study_plans row if the current user owns it, else None."""
    db = get_db()
    return db.execute(
        "SELECT id, user_id, name FROM study_plans WHERE id = ? AND user_id = ?",
        (plan_id, g.user_id),
    ).fetchone()


def _resolve_recipient(payload: dict):
    """Resolve a share recipient from a payload {user_id?, email?}.

    Returns (user_row_or_None, error_response_or_None). Caller should bail out
    if the second element is non-None.
    """
    db = get_db()
    user_id = (payload.get("user_id") or "").strip() or None
    email = (payload.get("email") or "").strip().lower() or None

    if not user_id and not email:
        return None, (jsonify(error="Either user_id or email required", code="BAD_INPUT"), 400)

    if user_id:
        row = db.execute(
            "SELECT id, email, display_name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    else:
        # Email lookup is case-insensitive; users table stores whatever the
        # auth provider gave us, so we lower() on both sides.
        row = db.execute(
            "SELECT id, email, display_name FROM users WHERE LOWER(email) = ?",
            (email,),
        ).fetchone()

    if not row:
        ref = user_id or email
        return None, (jsonify(
            error=f"No user found for {ref!r}. They may need to sign in once before you can share with them.",
            code="USER_NOT_FOUND",
        ), 404)
    return row, None


# ---------- POST /api/plans/:id/share ----------

@bp.post("/api/plans/<int:plan_id>/share")
@require_auth
def share_plan(plan_id):
    plan = _own_plan_row(plan_id)
    if not plan:
        return jsonify(error="Plan not found", code="NOT_FOUND"), 404

    payload = request.get_json(silent=True) or {}
    recipient, err = _resolve_recipient(payload)
    if err:
        return err

    if recipient["id"] == g.user_id:
        return jsonify(error="You can't share a plan with yourself", code="BAD_INPUT"), 400

    include_grades = 1 if bool(payload.get("include_grades", False)) else 0

    db = get_db()
    # UPSERT on (plan_id, shared_with_user_id) so re-sharing updates the
    # include_grades flag rather than failing.
    db.execute(
        """
        INSERT INTO plan_shares (plan_id, shared_with_user_id, include_grades)
        VALUES (?, ?, ?)
        ON CONFLICT(plan_id, shared_with_user_id) DO UPDATE SET
          include_grades = excluded.include_grades
        """,
        (plan_id, recipient["id"], include_grades),
    )
    db.commit()

    row = db.execute(
        """
        SELECT id, plan_id, shared_with_user_id, include_grades, created_at
        FROM plan_shares
        WHERE plan_id = ? AND shared_with_user_id = ?
        """,
        (plan_id, recipient["id"]),
    ).fetchone()

    return jsonify({
        "id": row["id"],
        "plan_id": row["plan_id"],
        "shared_with": {
            "user_id": recipient["id"],
            "email": recipient["email"],
            "display_name": recipient["display_name"],
        },
        "include_grades": bool(row["include_grades"]),
        "created_at": row["created_at"],
    }), 201


# ---------- GET /api/plans/:id/shares ----------

@bp.get("/api/plans/<int:plan_id>/shares")
@require_auth
def list_shares(plan_id):
    """List all current shares of a plan. Owner only."""
    plan = _own_plan_row(plan_id)
    if not plan:
        return jsonify(error="Plan not found", code="NOT_FOUND"), 404

    db = get_db()
    rows = db.execute(
        """
        SELECT ps.id, ps.plan_id, ps.include_grades, ps.created_at,
               u.id AS recipient_id, u.email AS recipient_email,
               u.display_name AS recipient_name
        FROM plan_shares ps
        JOIN users u ON u.id = ps.shared_with_user_id
        WHERE ps.plan_id = ?
        ORDER BY ps.created_at DESC
        """,
        (plan_id,),
    ).fetchall()

    return jsonify(shares=[
        {
            "id": r["id"],
            "plan_id": r["plan_id"],
            "include_grades": bool(r["include_grades"]),
            "created_at": r["created_at"],
            "shared_with": {
                "user_id": r["recipient_id"],
                "email": r["recipient_email"],
                "display_name": r["recipient_name"],
            },
        }
        for r in rows
    ])


# ---------- DELETE /api/plans/:id/shares/:shareId ----------

@bp.delete("/api/plans/<int:plan_id>/shares/<int:share_id>")
@require_auth
def revoke_share(plan_id, share_id):
    plan = _own_plan_row(plan_id)
    if not plan:
        return jsonify(error="Plan not found", code="NOT_FOUND"), 404

    db = get_db()
    cur = db.execute(
        "DELETE FROM plan_shares WHERE id = ? AND plan_id = ?",
        (share_id, plan_id),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Share not found", code="NOT_FOUND"), 404
    return jsonify(deleted=True), 200


# ---------- GET /api/shared-with-me ----------

@bp.get("/api/shared-with-me")
@require_auth
def shared_with_me():
    """List plans shared with the current user.

    Includes the sharer's identity so the recipient can label "Alice's plan"
    in the UI without a second lookup.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT ps.id AS share_id, ps.include_grades, ps.created_at AS shared_at,
               p.id AS plan_id, p.name AS plan_name,
               u.id AS owner_id, u.email AS owner_email, u.display_name AS owner_name,
               u.major_code AS owner_major
        FROM plan_shares ps
        JOIN study_plans p ON p.id = ps.plan_id
        JOIN users u ON u.id = p.user_id
        WHERE ps.shared_with_user_id = ?
        ORDER BY ps.created_at DESC
        """,
        (g.user_id,),
    ).fetchall()
    return jsonify(plans=[
        {
            "share_id": r["share_id"],
            "plan_id": r["plan_id"],
            "plan_name": r["plan_name"],
            "include_grades": bool(r["include_grades"]),
            "shared_at": r["shared_at"],
            "owner": {
                "user_id": r["owner_id"],
                "email": r["owner_email"],
                "display_name": r["owner_name"],
                "major_code": r["owner_major"],
            },
        }
        for r in rows
    ])
