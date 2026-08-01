"""Majors / degree programs.

Used by onboarding (lets users pick a degree program) and by anywhere else that
needs to show a friendly degree name. The set of majors lives in the `majors`
table; their requirement buckets live in `degree_requirements`.
"""
from flask import Blueprint, jsonify
from db import get_db
from auth import require_auth

bp = Blueprint("majors", __name__)


def _major_row_to_dict(row, requirements_count: int = 0) -> dict:
    return {
        "code": row["code"],
        "name": row["name"],
        "faculty": row["faculty"],
        "total_mcs": row["total_mcs"],
        "acad_year": row["acad_year"],
        "requirements_count": requirements_count,
    }


@bp.get("/api/majors")
@require_auth
def list_majors():
    """List all degree programs. Used by onboarding's major picker.

    Returns each major plus a count of its requirement buckets, so the UI can
    show e.g. "6 categories" alongside total MCs.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT m.code, m.name, m.faculty, m.total_mcs, m.acad_year,
               COUNT(dr.id) AS requirements_count
        FROM majors m
        LEFT JOIN degree_requirements dr ON dr.major_code = m.code
        GROUP BY m.code
        ORDER BY m.display_order, m.code
        """
    ).fetchall()
    return jsonify([_major_row_to_dict(r, r["requirements_count"]) for r in rows])


@bp.get("/api/majors/<code>")
@require_auth
def major_detail(code):
    """Full major detail including its requirement buckets.

    Useful preview during onboarding ("here's what you'll need to plan around")
    and as a building block for the Progress page later.
    """
    db = get_db()
    row = db.execute("SELECT * FROM majors WHERE code = ?", (code.upper(),)).fetchone()
    if not row:
        return jsonify(error=f"Major {code} not found", code="NOT_FOUND"), 404

    reqs = db.execute(
        """
        SELECT category, label, required_mcs, display_order
        FROM degree_requirements
        WHERE major_code = ?
        ORDER BY display_order, category
        """,
        (code.upper(),),
    ).fetchall()

    return jsonify({
        **_major_row_to_dict(row, len(reqs)),
        "requirements": [
            {
                "category": r["category"],
                "label": r["label"],
                "required_mcs": r["required_mcs"],
            }
            for r in reqs
        ],
    })
