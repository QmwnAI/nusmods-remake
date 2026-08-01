"""Modules and degree requirements endpoints."""
import json
from flask import Blueprint, request, jsonify
from db import get_db
from auth import require_auth

bp = Blueprint("modules", __name__)


def _fmt_mcs(mcs):
    """Render mcs as an int when it's whole (4.0 -> 4) and a float otherwise (2.5 -> 2.5).

    Avoids '4.0 MC' showing up in the UI for the 99% of modules that have integer credits.
    """
    if mcs is None:
        return 0
    mcs = float(mcs)
    return int(mcs) if mcs == int(mcs) else mcs


def _module_row_to_dict(row) -> dict:
    """Convert a modules row (sqlite3.Row) to the API representation."""
    semester_data = json.loads(row["semester_data"]) if row["semester_data"] else None
    # NUSMods semesterData is a list of {semester, examDate, timetable, ...}.
    # For the list view we expose just the semester numbers; full data is in the field too.
    if isinstance(semester_data, list) and semester_data and isinstance(semester_data[0], dict):
        semesters_offered = sorted({s["semester"] for s in semester_data if "semester" in s})
    elif isinstance(semester_data, list):
        # legacy seed format: a list of ints
        semesters_offered = semester_data
    else:
        semesters_offered = []

    return {
        "code": row["code"],
        "title": row["title"],
        "description": row["description"],
        "mcs": _fmt_mcs(row["mcs"]),
        "department": row["department"],
        "faculty": row["faculty"],
        "prereq_tree": json.loads(row["prereq_tree"]) if row["prereq_tree"] else None,
        "prereq_string": row["prereq_string"],
        "preclusion": _row_get(row, "preclusion"),
        "corequisite": _row_get(row, "corequisite"),
        "workload": json.loads(row["workload"]) if _row_get(row, "workload") else None,
        "semester_data": semester_data,
        "semesters_offered": semesters_offered,
        "acad_year": row["acad_year"],
    }


def _row_get(row, key, default=None):
    """Tolerate older DB schemas that may not have a column yet."""
    try:
        return row[key]
    except (KeyError, IndexError):
        return default


@bp.get("/api/modules")
@require_auth
def list_modules():
    q = (request.args.get("q") or "").strip().lower()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    db = get_db()

    where_clauses, params = [], []
    if q:
        where_clauses.append("(LOWER(code) LIKE ? OR LOWER(title) LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    rows = db.execute(
        f"SELECT * FROM modules {where_sql} ORDER BY code LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    total = db.execute(f"SELECT COUNT(*) AS c FROM modules {where_sql}", params).fetchone()["c"]

    return jsonify(
        modules=[_module_row_to_dict(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@bp.get("/api/modules/<code>")
@require_auth
def module_detail(code):
    """Module detail, enhanced with usage stats and reverse-prereq lookups.

    Stats are computed from the global `plan_entries` table — i.e. across ALL users.
    They're rough but useful: "how popular is this module?" and "which semester do
    most planners take it in?". For privacy we omit grade distributions until we
    have a real user base; with the seed's 31 modules and one dev user the numbers
    would identify individuals anyway.

    `unlocks` is the inverse-prereq lookup: "what modules require THIS one?" We use
    a `LIKE '%"CODE"%'` scan over the prereq_tree JSON. False positives would
    require a code that's a substring of another code (e.g. CS2030 vs CS2030SS),
    which essentially doesn't happen for NUS module codes — and they all live in
    quotes in the JSON, which tightens the match further.

    If performance becomes a concern at full catalogue scale (~6000 modules),
    precompute an inverse index in a `prereq_unlocks` table — see F4-1 in
    features/FLAGS.md.
    """
    code = code.upper()
    db = get_db()
    row = db.execute("SELECT * FROM modules WHERE code = ?", (code,)).fetchone()
    if not row:
        return jsonify(error=f"Module {code} not found", code="NOT_FOUND"), 404

    payload = _module_row_to_dict(row)

    # --- Placement stats ---
    total = db.execute(
        "SELECT COUNT(*) AS c FROM plan_entries WHERE module_code = ?",
        (code,),
    ).fetchone()["c"]

    by_sem_rows = db.execute(
        """
        SELECT semester_id, COUNT(*) AS n
        FROM plan_entries
        WHERE module_code = ?
        GROUP BY semester_id
        ORDER BY n DESC
        """,
        (code,),
    ).fetchall()

    payload["stats"] = {
        "placement_count": total,
        "by_semester": {r["semester_id"]: r["n"] for r in by_sem_rows},
    }

    # --- Unlocks: modules that list this one as a prereq ---
    # Match the code inside the JSON-encoded tree. We wrap in quotes to avoid
    # substring matches against other codes.
    unlock_rows = db.execute(
        """
        SELECT code, title, mcs
        FROM modules
        WHERE prereq_tree LIKE ? AND code != ?
        ORDER BY code
        LIMIT 50
        """,
        (f'%"{code}"%', code),
    ).fetchall()
    payload["unlocks"] = [
        {"code": r["code"], "title": r["title"], "mcs": _fmt_mcs(r["mcs"])}
        for r in unlock_rows
    ]

    return jsonify(payload)


@bp.get("/api/requirements")
@require_auth
def list_requirements():
    major = request.args.get("major", "CS")
    db = get_db()
    reqs = db.execute(
        """
        SELECT id, category, label, required_mcs, display_order
        FROM degree_requirements
        WHERE major_code = ?
        ORDER BY display_order, category
        """,
        (major,),
    ).fetchall()

    out = []
    for r in reqs:
        mods = db.execute(
            "SELECT module_code FROM requirement_modules WHERE requirement_id = ? ORDER BY module_code",
            (r["id"],),
        ).fetchall()
        out.append(
            {
                "category": r["category"],
                "label": r["label"],
                "required_mcs": r["required_mcs"],
                "modules": [m["module_code"] for m in mods],
            }
        )
    return jsonify(out)
