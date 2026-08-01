"""Progress tracker — Feature 7 enhanced.

Returns a richer view than the original Feature 3 version:

  - Per-category breakdown of WHICH modules count toward each bucket
    (split into 'completed' vs 'placed but not completed')
  - Eligible-but-not-placed modules per category, capped to a small preview
  - Unallocated placed modules (don't fit any requirement bucket)
  - Projected completion semester (the latest semester containing any placed entry)
  - 'completed' MCs distinct from 'placed' MCs: an F-graded module is placed
    but not completed.

API shape (see API.md):
  {
    total: {
      placed_mcs:    int,    # sum of MCs for all placed entries (excluding F)
      completed_mcs: int,    # sum of MCs for entries with passing grade
      required_mcs:  int,
      percent_placed: float,
      percent_completed: float,
    },
    projected_completion: { semester_id | null, year, sem },
    by_category: [
      {
        category, label, required,
        placed_mcs, completed_mcs,
        complete (bool, based on placed),
        placed_modules: [{ code, mcs, completed }],
        eligible_not_placed: [{ code, title, mcs }],   # capped
        eligible_not_placed_total: int,                # full count
      }
    ],
    unallocated_modules: [{ code, mcs, semester_id }],
    major_code: str,
  }
"""
from flask import Blueprint, request, jsonify, g
from db import get_db
from auth import require_auth
from services.gpa import GRADE_POINTS

bp = Blueprint("progress", __name__)


# Max eligible-not-placed modules to return per category. Avoids over-large payloads
# on UE buckets that could legitimately have thousands of candidates.
ELIGIBLE_PREVIEW_LIMIT = 8

# Semester ordering for projected completion math
SEMESTER_ORDER = {f"Y{y}S{s}": (y - 1) * 2 + (s - 1) for y in range(1, 5) for s in range(1, 3)}


def _is_passing(grade: str | None) -> bool:
    """A grade is passing iff it's known and not F.

    No grade (None) means "not yet completed" — placed but unfinished.
    F means failed; still placed but not completed.
    """
    if grade is None:
        return False
    if grade == "F":
        return False
    return grade in GRADE_POINTS  # known grade


@bp.get("/api/plans/<int:plan_id>/progress")
@require_auth
def plan_progress(plan_id):
    db = get_db()
    plan = db.execute(
        "SELECT * FROM study_plans WHERE id = ? AND user_id = ?",
        (plan_id, g.user_id),
    ).fetchone()
    if not plan:
        return jsonify(error="Plan not found", code="NOT_FOUND"), 404

    user = db.execute("SELECT major_code FROM users WHERE id = ?", (g.user_id,)).fetchone()
    major = user["major_code"] or "CS"

    # ---- 1. Load requirement buckets and module memberships ----
    reqs = db.execute(
        """
        SELECT id, category, label, required_mcs, display_order
        FROM degree_requirements
        WHERE major_code = ?
        ORDER BY display_order, category
        """,
        (major,),
    ).fetchall()

    # category -> set of module codes in that requirement
    req_modules: dict[int, set[str]] = {}
    req_id_to_row: dict[int, dict] = {}
    all_required_codes: set[str] = set()  # union across categories (for "unallocated" calc)
    for r in reqs:
        rows = db.execute(
            "SELECT module_code FROM requirement_modules WHERE requirement_id = ?",
            (r["id"],),
        ).fetchall()
        codes = {x["module_code"] for x in rows}
        req_modules[r["id"]] = codes
        req_id_to_row[r["id"]] = dict(r)
        all_required_codes |= codes

    # ---- 2. Load plan entries with grades and MCs ----
    entry_rows = db.execute(
        """
        SELECT pe.module_code, pe.semester_id, pe.grade, pe.is_completed,
               m.mcs, m.title
        FROM plan_entries pe
        JOIN modules m ON m.code = pe.module_code
        WHERE pe.plan_id = ?
        """,
        (plan_id,),
    ).fetchall()

    placed_modules = []
    for e in entry_rows:
        passing = _is_passing(e["grade"])
        placed_modules.append({
            "code": e["module_code"],
            "title": e["title"],
            "semester_id": e["semester_id"],
            "mcs": float(e["mcs"]),
            "grade": e["grade"],
            "completed": passing,
        })
    code_to_placed = {p["code"]: p for p in placed_modules}

    # ---- 3. Per-category accounting ----
    # Walk categories in their display order. For each:
    #   - placed modules: subset of plan that satisfies this category
    #   - completed MCs: same, but only those with passing grades
    #   - eligible not placed: requirement_modules - placed (subject to a cap)
    #
    # UE-style buckets with no listed requirement_modules absorb whatever's left
    # over (placed modules that fit no specific bucket). We allocate to those
    # in a second pass after specific buckets have claimed their share.

    # First pass: specific buckets
    by_category = []
    claimed_codes: set[str] = set()  # codes already attributed to a specific bucket

    for r in reqs:
        codes = req_modules[r["id"]]
        if not codes:
            # UE / open buckets — handled in second pass
            by_category.append({
                "_pending_unallocated": True,
                "req_row": dict(r),
            })
            continue

        # Placed modules matching this bucket
        matching = [p for p in placed_modules if p["code"] in codes]
        # We don't double-claim codes here — let them count toward every category
        # that lists them. Real life this isn't a concern because requirement_modules
        # rarely overlaps; the few overlaps are typically intentional cross-counting.
        for p in matching:
            claimed_codes.add(p["code"])

        placed_mcs = sum(p["mcs"] for p in matching)
        completed_mcs = sum(p["mcs"] for p in matching if p["completed"])

        # Eligible-not-placed preview
        placed_codes_set = {p["code"] for p in matching}
        not_placed_codes = sorted(c for c in codes if c not in placed_codes_set)
        eligible_not_placed_total = len(not_placed_codes)
        eligible_preview = []
        if not_placed_codes:
            preview_codes = not_placed_codes[:ELIGIBLE_PREVIEW_LIMIT]
            placeholders = ",".join("?" for _ in preview_codes)
            rows = db.execute(
                f"SELECT code, title, mcs FROM modules WHERE code IN ({placeholders}) ORDER BY code",
                preview_codes,
            ).fetchall()
            eligible_preview = [
                {"code": m["code"], "title": m["title"], "mcs": float(m["mcs"])}
                for m in rows
            ]

        # Cap displayed earned at requirement so a bucket can't show 120%.
        capped_placed = min(placed_mcs, r["required_mcs"])
        capped_completed = min(completed_mcs, r["required_mcs"])

        by_category.append({
            "category": r["category"],
            "label": r["label"],
            "required": r["required_mcs"],
            "placed_mcs": round(capped_placed, 1),
            "completed_mcs": round(capped_completed, 1),
            "complete": capped_placed >= r["required_mcs"],
            "placed_modules": [
                {"code": p["code"], "mcs": p["mcs"], "completed": p["completed"], "grade": p["grade"]}
                for p in matching
            ],
            "eligible_not_placed": eligible_preview,
            "eligible_not_placed_total": eligible_not_placed_total,
        })

    # Second pass: open buckets absorb un-claimed placed modules, filling earlier
    # display-order buckets first up to their required_mcs cap, then spilling over.
    # This keeps a sensible default for majors like BZA where no module-to-bucket
    # mapping has been seeded yet (see F3-1) — earlier buckets fill first instead
    # of one arbitrary bucket eating everything.
    leftover_remaining = [p for p in placed_modules if p["code"] not in claimed_codes]

    for entry in by_category:
        if not entry.get("_pending_unallocated"):
            continue
        r = entry.pop("req_row")
        entry.pop("_pending_unallocated", None)

        # Pull modules off the leftover list until this bucket is full or we run out.
        bucket_mods = []
        bucket_mcs = 0.0
        bucket_completed = 0.0
        still_remaining = []
        for p in leftover_remaining:
            if bucket_mcs < r["required_mcs"]:
                bucket_mods.append(p)
                bucket_mcs += p["mcs"]
                if p["completed"]:
                    bucket_completed += p["mcs"]
            else:
                still_remaining.append(p)
        leftover_remaining = still_remaining

        capped_placed = min(bucket_mcs, r["required_mcs"])
        capped_completed = min(bucket_completed, r["required_mcs"])

        entry.update({
            "category": r["category"],
            "label": r["label"],
            "required": r["required_mcs"],
            "placed_mcs": round(capped_placed, 1),
            "completed_mcs": round(capped_completed, 1),
            "complete": capped_placed >= r["required_mcs"],
            "placed_modules": [
                {"code": p["code"], "mcs": p["mcs"], "completed": p["completed"], "grade": p["grade"]}
                for p in bucket_mods
            ],
            # For open buckets we don't have a fixed candidate list — leave empty.
            "eligible_not_placed": [],
            "eligible_not_placed_total": 0,
        })

    # Anything still un-consumed after all open buckets are full is genuinely unallocated.
    leftover = leftover_remaining

    # ---- 4. Totals + projected completion ----
    placed_total = sum(p["mcs"] for p in placed_modules)
    completed_total = sum(p["mcs"] for p in placed_modules if p["completed"])
    required_total = sum(r["required_mcs"] for r in reqs)

    # Projected completion: the latest semester containing any placed entry.
    latest_idx = max(
        (SEMESTER_ORDER[p["semester_id"]] for p in placed_modules if p["semester_id"] in SEMESTER_ORDER),
        default=-1,
    )
    projected = None
    if latest_idx >= 0:
        for sem_id, idx in SEMESTER_ORDER.items():
            if idx == latest_idx:
                year = (idx // 2) + 1
                sem = (idx % 2) + 1
                projected = {"semester_id": sem_id, "year": year, "sem": sem}
                break

    # ---- 5. Unallocated: leftover after open buckets ----
    # If there are no open buckets in this major, leftover here represents modules
    # placed in the plan but not counting toward any requirement — surface them
    # so the user can decide whether to remove them.
    unallocated = [
        {"code": p["code"], "title": p["title"], "mcs": p["mcs"], "semester_id": p["semester_id"], "grade": p["grade"]}
        for p in leftover
    ]

    return jsonify(
        major_code=major,
        total={
            "placed_mcs": round(placed_total, 1),
            "completed_mcs": round(completed_total, 1),
            "required_mcs": required_total,
            "percent_placed": round(placed_total / required_total * 100, 1) if required_total else 0.0,
            "percent_completed": round(completed_total / required_total * 100, 1) if required_total else 0.0,
        },
        projected_completion=projected,
        by_category=by_category,
        unallocated_modules=unallocated,
    )
