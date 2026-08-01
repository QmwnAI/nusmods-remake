"""User-facing auth endpoints."""
from flask import Blueprint, request, jsonify, g
from db import get_db
from auth import require_auth

bp = Blueprint("users", __name__)


@bp.post("/api/auth/sync")
@require_auth
def sync_user():
    """Called by the frontend on login. The require_auth decorator already creates
    the user row if missing; we just patch in any extra profile fields the client sends."""
    payload = request.get_json(silent=True) or {}
    db = get_db()
    fields, params = [], []
    if "email" in payload:
        fields.append("email = ?"); params.append(payload["email"])
    if "display_name" in payload:
        fields.append("display_name = ?"); params.append(payload["display_name"])
    if fields:
        params.append(g.user_id)
        db.execute(f"UPDATE users SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
        db.commit()
    row = db.execute("SELECT * FROM users WHERE id = ?", (g.user_id,)).fetchone()
    return jsonify(dict(row))


@bp.get("/api/me")
@require_auth
def me():
    return jsonify(dict(g.user))


@bp.put("/api/me")
@require_auth
def update_me():
    payload = request.get_json(silent=True) or {}
    fields, params = [], []
    if "major_code" in payload:
        fields.append("major_code = ?"); params.append(payload["major_code"])
    if "matric_year" in payload:
        fields.append("matric_year = ?"); params.append(payload["matric_year"])
    if "display_name" in payload:
        fields.append("display_name = ?"); params.append(payload["display_name"])
    if "contact_telegram" in payload:
        # Strip leading @ and surrounding whitespace; empty string → NULL.
        # Storing without @ keeps the column canonical and means display logic
        # can prefix uniformly.
        raw = payload["contact_telegram"]
        if isinstance(raw, str):
            cleaned = raw.strip().lstrip("@").strip()
            params.append(cleaned or None)
        else:
            params.append(None)
        fields.append("contact_telegram = ?")
    if not fields:
        return jsonify(dict(g.user))
    params.append(g.user_id)
    db = get_db()
    db.execute(f"UPDATE users SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)
    db.commit()
    row = db.execute("SELECT * FROM users WHERE id = ?", (g.user_id,)).fetchone()
    return jsonify(dict(row))
