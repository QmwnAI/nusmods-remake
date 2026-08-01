"""GPA scenario planning endpoints.

These hang off /api/plans/:id and answer hypothetical questions:

  GET  /api/plans/:id/gpa/target?cap=4.5&remaining_mcs=40
       What average grade-points do I need across `remaining_mcs` more MCs
       to hit a CAP of `cap`? If `remaining_mcs` is omitted, count ungraded
       entries in the plan as remaining.

  GET  /api/plans/:id/gpa/su-advice?budget_mcs=32
       Given an S/U budget, which graded modules should I S/U for the
       biggest CAP gain? Returns the greedy recommendation.

  POST /api/plans/:id/gpa/scenario
       Body: { "overrides": { "12": {"grade": "A", "is_su": false}, ... } }
       Returns the resulting CAP if these per-entry overrides were applied,
       without persisting anything to the DB.

All three are read-only and idempotent (despite scenario being POST — POST is
chosen because the override map can be larger than a query string).

Authentication is handled by @require_auth; the helper `_own_plan_or_404` from
plans.py is reused via a tiny local copy here to avoid coupling the two route
modules. (Could be factored into a shared `_plan_ownership.py` if a third caller
appears; not yet worth it.)
"""
from __future__ import annotations
from flask import Blueprint, request, jsonify, g

from db import get_db
from auth import require_auth
from services import gpa

bp = Blueprint("scenarios", __name__)


def _own_plan_or_404(plan_id: int):
    db = get_db()
    row = db.execute(
        "SELECT id FROM study_plans WHERE id = ? AND user_id = ?",
        (plan_id, g.user_id),
    ).fetchone()
    if not row:
        return None, (jsonify(error="Plan not found", code="NOT_FOUND"), 404)
    return row, None


def _load_plan_entries(plan_id: int) -> list[dict]:
    """Pull entries joined with module credits, as plain dicts.

    Each dict has: id, module_code, semester_id, grade, is_su, mcs.
    This is the shape the gpa service functions expect.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT pe.id, pe.module_code, pe.semester_id, pe.grade, pe.is_su, m.mcs
        FROM plan_entries pe
        JOIN modules m ON m.code = pe.module_code
        WHERE pe.plan_id = ?
        """,
        (plan_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "module_code": r["module_code"],
            "semester_id": r["semester_id"],
            "grade": r["grade"],
            "is_su": bool(r["is_su"]),
            "mcs": float(r["mcs"] or 0),
        }
        for r in rows
    ]


# ---------------- GET /gpa/target ----------------

@bp.get("/api/plans/<int:plan_id>/gpa/target")
@require_auth
def gpa_target(plan_id):
    _, err = _own_plan_or_404(plan_id)
    if err:
        return err

    try:
        target_cap = float(request.args.get("cap", "4.5"))
    except ValueError:
        return jsonify(error="`cap` must be a number", code="BAD_INPUT"), 400

    remaining_mcs_arg = request.args.get("remaining_mcs")
    remaining_mcs: float | None = None
    if remaining_mcs_arg is not None and remaining_mcs_arg != "":
        try:
            remaining_mcs = float(remaining_mcs_arg)
            if remaining_mcs < 0:
                raise ValueError("negative")
        except ValueError:
            return jsonify(error="`remaining_mcs` must be a non-negative number", code="BAD_INPUT"), 400

    entries = _load_plan_entries(plan_id)
    result = gpa.required_avg_from_entries(entries, target_cap, remaining_mcs=remaining_mcs)
    return jsonify(result.as_dict())


# ---------------- GET /gpa/su-advice ----------------

@bp.get("/api/plans/<int:plan_id>/gpa/su-advice")
@require_auth
def gpa_su_advice(plan_id):
    _, err = _own_plan_or_404(plan_id)
    if err:
        return err

    try:
        budget = float(request.args.get("budget_mcs", "32"))
        if budget < 0:
            raise ValueError("negative")
    except ValueError:
        return jsonify(error="`budget_mcs` must be a non-negative number", code="BAD_INPUT"), 400

    entries = _load_plan_entries(plan_id)
    return jsonify(gpa.recommend_sus(entries, budget_mcs=budget))


# ---------------- POST /gpa/scenario ----------------

@bp.post("/api/plans/<int:plan_id>/gpa/scenario")
@require_auth
def gpa_scenario(plan_id):
    _, err = _own_plan_or_404(plan_id)
    if err:
        return err

    payload = request.get_json(silent=True) or {}
    overrides = payload.get("overrides")
    if overrides is not None and not isinstance(overrides, dict):
        return jsonify(error="`overrides` must be an object (entry_id → {grade,is_su})", code="BAD_INPUT"), 400

    entries = _load_plan_entries(plan_id)
    return jsonify(gpa.simulate(entries, overrides or {}))
