"""Study plan CRUD and entry manipulation."""
import json
from flask import Blueprint, request, jsonify, g
from db import get_db
from auth import require_auth
from services import validation
from services.gpa import compute_cap, GRADE_POINTS

bp = Blueprint("plans", __name__)

SEMESTER_ORDER = {f"Y{y}S{s}": (y - 1) * 2 + (s - 1) for y in range(1, 5) for s in range(1, 3)}
VALID_SEMS = set(SEMESTER_ORDER.keys())


def _own_plan_or_404(plan_id: int):
    """Fetch a plan owned by the current user. Returns (plan_row, None) on success
    or (None, response) on failure."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM study_plans WHERE id = ? AND user_id = ?",
        (plan_id, g.user_id),
    ).fetchone()
    if not row:
        return None, (jsonify(error="Plan not found", code="NOT_FOUND"), 404)
    return row, None


def _accessible_plan_or_404(plan_id: int):
    """Fetch a plan the current user can READ — owns OR has been shared with.

    Returns (plan_row, share_row_or_None, err) where share_row is None for
    owned plans and the plan_shares row when access came via a share. Use
    `share_row.include_grades` to decide whether to expose grade fields.

    The 404 message is intentionally identical to _own_plan_or_404's so we
    don't leak which plan IDs exist to non-recipients.
    """
    db = get_db()
    # Owned?
    own = db.execute(
        "SELECT * FROM study_plans WHERE id = ? AND user_id = ?",
        (plan_id, g.user_id),
    ).fetchone()
    if own:
        return own, None, None
    # Shared with me?
    shared = db.execute(
        """
        SELECT p.*, ps.id AS share_id, ps.include_grades AS share_include_grades
        FROM study_plans p
        JOIN plan_shares ps ON ps.plan_id = p.id
        WHERE p.id = ? AND ps.shared_with_user_id = ?
        """,
        (plan_id, g.user_id),
    ).fetchone()
    if shared:
        return shared, shared, None
    return None, None, (jsonify(error="Plan not found", code="NOT_FOUND"), 404)


def _plan_to_dict(plan_row, with_entries: bool = False, include_grades: bool = True) -> dict:
    """Serialize a plan. When include_grades is False, grade/is_su/is_completed
    are stripped from every entry — used when serving a shared plan to a
    recipient whose share didn't opt into grade visibility.

    `notes` is treated like grades for the same reason: it can contain private
    info the sharer didn't intend to broadcast.
    """
    out = {
        "id": plan_row["id"],
        "user_id": plan_row["user_id"],
        "name": plan_row["name"],
        "is_active": bool(plan_row["is_active"]),
        "created_at": plan_row["created_at"],
        "updated_at": plan_row["updated_at"],
    }
    if with_entries:
        db = get_db()
        entries = db.execute(
            """
            SELECT id, module_code, semester_id, position, grade, is_su, is_completed, notes
            FROM plan_entries
            WHERE plan_id = ?
            ORDER BY semester_id, position, module_code
            """,
            (plan_row["id"],),
        ).fetchall()
        if include_grades:
            out["entries"] = [
                {
                    "id": e["id"],
                    "module_code": e["module_code"],
                    "semester_id": e["semester_id"],
                    "position": e["position"],
                    "grade": e["grade"],
                    "is_su": bool(e["is_su"]),
                    "is_completed": bool(e["is_completed"]),
                    "notes": e["notes"],
                }
                for e in entries
            ]
        else:
            out["entries"] = [
                {
                    "id": e["id"],
                    "module_code": e["module_code"],
                    "semester_id": e["semester_id"],
                    "position": e["position"],
                    # grade/is_su/is_completed/notes intentionally omitted
                }
                for e in entries
            ]
    return out


# ====== Plans CRUD ======

@bp.get("/api/plans")
@require_auth
def list_plans():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM study_plans WHERE user_id = ? ORDER BY created_at",
        (g.user_id,),
    ).fetchall()
    return jsonify([_plan_to_dict(r) for r in rows])


@bp.post("/api/plans")
@require_auth
def create_plan():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "My Plan").strip()
    db = get_db()
    cur = db.execute(
        "INSERT INTO study_plans (user_id, name) VALUES (?, ?)",
        (g.user_id, name),
    )
    db.commit()
    row = db.execute("SELECT * FROM study_plans WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(_plan_to_dict(row)), 201


@bp.get("/api/plans/<int:plan_id>")
@require_auth
def get_plan(plan_id):
    """Return a plan if the current user owns it OR has been granted a share.

    Shared reads obey the share's `include_grades` flag: grade/is_su/is_completed/notes
    are stripped when the sharer didn't opt into grade visibility.

    The response includes a top-level `access` field — "owner" or "shared" — so the
    frontend can render read-only UI for shared plans.
    """
    row, share_row, err = _accessible_plan_or_404(plan_id)
    if err:
        return err
    include_grades = share_row is None or bool(share_row["share_include_grades"])
    payload = _plan_to_dict(row, with_entries=True, include_grades=include_grades)
    payload["access"] = "owner" if share_row is None else "shared"
    payload["include_grades"] = include_grades
    return jsonify(payload)


@bp.put("/api/plans/<int:plan_id>")
@require_auth
def update_plan(plan_id):
    row, err = _own_plan_or_404(plan_id)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", row["name"]).strip()
    db = get_db()
    db.execute(
        "UPDATE study_plans SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (name, plan_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM study_plans WHERE id = ?", (plan_id,)).fetchone()
    return jsonify(_plan_to_dict(row))


@bp.delete("/api/plans/<int:plan_id>")
@require_auth
def delete_plan(plan_id):
    _, err = _own_plan_or_404(plan_id)
    if err:
        return err
    db = get_db()
    db.execute("DELETE FROM study_plans WHERE id = ?", (plan_id,))
    db.commit()
    return ("", 204)


# ====== Plan entries ======

@bp.post("/api/plans/<int:plan_id>/entries")
@require_auth
def add_entry(plan_id):
    _, err = _own_plan_or_404(plan_id)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    code = (payload.get("module_code") or "").upper().strip()
    sem = payload.get("semester_id")

    if sem not in VALID_SEMS:
        return jsonify(error=f"Invalid semester_id (expected one of {sorted(VALID_SEMS)})", code="BAD_INPUT"), 400

    db = get_db()
    if not db.execute("SELECT 1 FROM modules WHERE code = ?", (code,)).fetchone():
        return jsonify(error=f"Unknown module {code}", code="UNKNOWN_MODULE"), 400

    try:
        cur = db.execute(
            "INSERT INTO plan_entries (plan_id, module_code, semester_id) VALUES (?, ?, ?)",
            (plan_id, code, sem),
        )
        db.commit()
    except Exception:
        return jsonify(error=f"{code} is already in this plan", code="DUPLICATE"), 409

    row = db.execute("SELECT * FROM plan_entries WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify({"id": row["id"], "module_code": row["module_code"], "semester_id": row["semester_id"]}), 201


@bp.put("/api/plans/<int:plan_id>/entries/<int:entry_id>")
@require_auth
def update_entry(plan_id, entry_id):
    _, err = _own_plan_or_404(plan_id)
    if err:
        return err
    payload = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute(
        "SELECT * FROM plan_entries WHERE id = ? AND plan_id = ?",
        (entry_id, plan_id),
    ).fetchone()
    if not row:
        return jsonify(error="Entry not found", code="NOT_FOUND"), 404

    # Build a partial update — only touch fields the caller actually sent.
    fields, params = [], []
    if "semester_id" in payload:
        if payload["semester_id"] not in VALID_SEMS:
            return jsonify(error="Invalid semester_id", code="BAD_INPUT"), 400
        fields.append("semester_id = ?"); params.append(payload["semester_id"])
    if "grade" in payload:
        grade = payload["grade"]
        if grade is not None and grade not in GRADE_POINTS:
            return jsonify(error="Invalid grade", code="BAD_INPUT"), 400
        fields.append("grade = ?"); params.append(grade)
    if "is_su" in payload:
        fields.append("is_su = ?"); params.append(1 if payload["is_su"] else 0)
    if "is_completed" in payload:
        fields.append("is_completed = ?"); params.append(1 if payload["is_completed"] else 0)
    if "position" in payload:
        fields.append("position = ?"); params.append(int(payload["position"]))
    if "notes" in payload:
        fields.append("notes = ?"); params.append(payload["notes"])

    if fields:
        params.append(entry_id)
        db.execute(f"UPDATE plan_entries SET {', '.join(fields)} WHERE id = ?", params)
        db.commit()

    row = db.execute("SELECT * FROM plan_entries WHERE id = ?", (entry_id,)).fetchone()
    return jsonify({
        "id": row["id"],
        "module_code": row["module_code"],
        "semester_id": row["semester_id"],
        "grade": row["grade"],
        "is_su": bool(row["is_su"]),
        "is_completed": bool(row["is_completed"]),
    })


@bp.delete("/api/plans/<int:plan_id>/entries/<int:entry_id>")
@require_auth
def delete_entry(plan_id, entry_id):
    _, err = _own_plan_or_404(plan_id)
    if err:
        return err
    db = get_db()
    cur = db.execute(
        "DELETE FROM plan_entries WHERE id = ? AND plan_id = ?",
        (entry_id, plan_id),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Entry not found", code="NOT_FOUND"), 404
    return ("", 204)


# ====== Computed views ======

@bp.get("/api/plans/<int:plan_id>/validate")
@require_auth
def validate_plan(plan_id):
    """Find all validation issues for a plan.

    Returns prereq violations, coreq violations, preclusion conflicts, and
    not-offered-this-semester violations. See `services/validation.py` for the
    full violation shape spec.

    The legacy `violations` key is preserved for back-compat: it contains only
    PREREQ_UNMET violations in the original shape. New clients should read the
    typed `issues` field instead.
    """
    _, err = _own_plan_or_404(plan_id)
    if err:
        return err
    db = get_db()
    rows = db.execute(
        """
        SELECT pe.id, pe.module_code, pe.semester_id,
               m.prereq_tree, m.corequisite, m.preclusion, m.semester_data
        FROM plan_entries pe
        JOIN modules m ON m.code = pe.module_code
        WHERE pe.plan_id = ?
        """,
        (plan_id,),
    ).fetchall()

    entries = [validation.entry_from_row(r, r) for r in rows]
    issues = validation.validate(entries)

    # Back-compat: extract just prereq violations in the original shape so existing
    # frontends (or anything else hitting this endpoint) doesn't break.
    legacy_violations = [
        {
            "entry_id": v["entry_id"],
            "module_code": v["module_code"],
            "semester_id": v["semester_id"],
            "unmet": v["unmet"],
        }
        for v in issues
        if v["kind"] == validation.PREREQ_UNMET
    ]

    return jsonify(issues=issues, violations=legacy_violations)


@bp.get("/api/plans/<int:plan_id>/ready-modules")
@require_auth
def ready_modules(plan_id):
    """Suggest modules the user can take next in a given semester.

    Query: ?semester_id=Y2S1 (required)

    Returns modules whose prereqs are satisfied by everything placed in strictly
    earlier semesters, that aren't already in the plan, and that are offered in
    the target semester (when offering info is available).

    Useful for: filling out a half-empty semester, finding electives that "unlock"
    early, and as the data source for a future "smart catalogue" view that
    highlights what's currently takeable.
    """
    _, err = _own_plan_or_404(plan_id)
    if err:
        return err

    semester_id = request.args.get("semester_id")
    if semester_id not in VALID_SEMS:
        return jsonify(error=f"Invalid or missing semester_id (expected one of {sorted(VALID_SEMS)})", code="BAD_INPUT"), 400

    limit = min(int(request.args.get("limit", 50)), 200)

    db = get_db()
    # All entries in this plan, joined with module info so we have semester order.
    rows = db.execute(
        """
        SELECT pe.id, pe.module_code, pe.semester_id,
               m.prereq_tree, m.corequisite, m.preclusion, m.semester_data
        FROM plan_entries pe
        JOIN modules m ON m.code = pe.module_code
        WHERE pe.plan_id = ?
        """,
        (plan_id,),
    ).fetchall()
    placed = [validation.entry_from_row(r, r) for r in rows]

    # All modules — converted to the shape find_ready_modules expects.
    module_rows = db.execute("SELECT * FROM modules").fetchall()
    candidates = []
    for r in module_rows:
        tree = None
        if r["prereq_tree"]:
            try:
                tree = json.loads(r["prereq_tree"])
            except json.JSONDecodeError:
                tree = None
        sems_offered = None
        if r["semester_data"]:
            try:
                raw = json.loads(r["semester_data"])
                if isinstance(raw, list) and raw and isinstance(raw[0], dict):
                    sems_offered = sorted({s["semester"] for s in raw if "semester" in s})
                elif isinstance(raw, list):
                    sems_offered = raw
            except (json.JSONDecodeError, TypeError):
                sems_offered = None
        candidates.append({
            "code": r["code"],
            "title": r["title"],
            "mcs": float(r["mcs"]) if r["mcs"] is not None else 0.0,
            "prereq_tree": tree,
            "semesters_offered": sems_offered,
        })

    ready = validation.find_ready_modules(semester_id, placed, candidates)

    # Sort by code, truncate to limit. The "best ordering" question is interesting
    # (popularity? prereq depth?) but premature optimisation — alphabetical is fine.
    ready.sort(key=lambda m: m["code"])
    payload_modules = [
        {
            "code": m["code"],
            "title": m["title"],
            "mcs": int(m["mcs"]) if m["mcs"] == int(m["mcs"]) else m["mcs"],
            "semesters_offered": m["semesters_offered"] or [],
        }
        for m in ready[:limit]
    ]
    return jsonify(modules=payload_modules, total=len(ready))


@bp.get("/api/plans/<int:plan_id>/gpa")
@require_auth
def plan_gpa(plan_id):
    _, err = _own_plan_or_404(plan_id)
    if err:
        return err
    db = get_db()
    rows = db.execute(
        """
        SELECT pe.grade, pe.is_su, m.mcs
        FROM plan_entries pe
        JOIN modules m ON m.code = pe.module_code
        WHERE pe.plan_id = ?
        """,
        (plan_id,),
    ).fetchall()
    return jsonify(compute_cap([dict(r) for r in rows]))
