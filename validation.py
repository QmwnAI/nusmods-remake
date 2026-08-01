"""Plan validation — combines all four checks into one typed result list.

Four kinds of violations are detected:

  PREREQ_UNMET     — module placed before its prereqs are satisfied
  COREQ_UNMET      — module placed without its corequisite in the same or earlier semester
  PRECLUSION       — two modules in the plan that preclude each other
  NOT_OFFERED      — module placed in a semester it isn't offered in

Each violation is a dict with these common fields:

  kind             (str)   one of the constants above
  entry_id         (int)   the offending plan_entries.id (for prereq/coreq/not_offered)
  module_code      (str)   the module the user placed
  semester_id      (str)   where it sits in the plan
  message          (str)   human-readable description

Prereq/coreq violations additionally include:
  unmet            (str)   description of what's missing — e.g. "CS1101S or CS1010S"

Preclusion violations are a pair, so they include:
  module_code_a / module_code_b
  entry_id_a / entry_id_b
  semester_id_a / semester_id_b
  (no `entry_id` / `module_code` / `semester_id` top-level, since there are two)

Not-offered violations include:
  offered_in       (list[int])  the semester numbers (1, 2, 3, 4) this module IS offered in

Note: this service does not know about academic-year-specific exceptions or
special-term offerings — it relies entirely on what's in `modules.semester_data`.
For modules NUSMods hasn't populated, semester_data may be missing and we skip
the not-offered check rather than producing false positives.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from services.prereqs import (
    corequisites_met,
    explain_unmet,
    extract_preclusion_codes,
    parse_corequisite_string,
    prereqs_met,
)
from services.timetable import (
    ExamEntry,
    extract_exam,
    find_exam_clashes,
)


# Y1S1 → 0, Y1S2 → 1, ..., Y4S2 → 7.
SEMESTER_ORDER = {f"Y{y}S{s}": (y - 1) * 2 + (s - 1) for y in range(1, 5) for s in range(1, 3)}
# Which NUS semester number each plan slot represents.
# Y_S1 maps to NUS Semester 1; Y_S2 to NUS Semester 2. Special terms (3, 4) aren't
# in the 8-slot grid — modules only offered in special terms get a NOT_OFFERED for any slot.
PLAN_SEM_TO_NUS = {f"Y{y}S{s}": s for y in range(1, 5) for s in range(1, 3)}


# Violation kinds, exported as constants so callers don't sprinkle string literals.
PREREQ_UNMET = "PREREQ_UNMET"
COREQ_UNMET = "COREQ_UNMET"
PRECLUSION = "PRECLUSION"
NOT_OFFERED = "NOT_OFFERED"
EXAM_CLASH = "EXAM_CLASH"


@dataclass
class PlanEntry:
    """A subset of plan_entries row + joined modules columns, for validation input."""
    id: int
    module_code: str
    semester_id: str
    prereq_tree: dict | str | None      # parsed (not the raw JSON string)
    corequisite: str | None
    preclusion: str | None
    semesters_offered: list[int] | None  # e.g. [1, 2] or [1] or None if unknown
    # Exam info derived from semester_data for the NUS semester this entry sits in.
    # When the underlying NUSMods data lacks examDate/examDuration (common for special
    # terms, or modules without final exams), these remain None and the exam-clash
    # check skips this entry entirely. See services/timetable.py for the extraction.
    exam_start: object | None = None        # datetime.datetime | None
    exam_duration_min: int | None = None


def validate(entries: Iterable[PlanEntry]) -> list[dict]:
    """Run all checks and return a flat list of violations.

    Order is stable: prereq first, then coreq, then preclusion (one per pair),
    then not-offered, then exam-clash. Within each kind, ordered by semester
    then by code.
    """
    entries = list(entries)
    by_sem_idx = sorted(entries, key=lambda e: (SEMESTER_ORDER[e.semester_id], e.module_code))

    out: list[dict] = []
    out.extend(_check_prereqs(by_sem_idx))
    out.extend(_check_corequisites(by_sem_idx))
    out.extend(_check_preclusions(by_sem_idx))
    out.extend(_check_offerings(by_sem_idx))
    out.extend(_check_exam_clashes(by_sem_idx))
    return out


# ---------- prereqs ----------

def _check_prereqs(entries: list[PlanEntry]) -> list[dict]:
    out = []
    for e in entries:
        target_idx = SEMESTER_ORDER[e.semester_id]
        # "Completed" = anything placed in an earlier semester.
        completed_before = {r.module_code for r in entries if SEMESTER_ORDER[r.semester_id] < target_idx}
        if e.prereq_tree is None:
            continue
        if not prereqs_met(e.prereq_tree, completed_before):
            unmet = explain_unmet(e.prereq_tree, completed_before)
            out.append({
                "kind": PREREQ_UNMET,
                "entry_id": e.id,
                "module_code": e.module_code,
                "semester_id": e.semester_id,
                "unmet": unmet,
                "message": f"needs {unmet} earlier" if unmet else "prerequisites not met",
            })
    return out


# ---------- corequisites ----------

def _check_corequisites(entries: list[PlanEntry]) -> list[dict]:
    out = []
    for e in entries:
        if not e.corequisite:
            continue
        coreq_tree = parse_corequisite_string(e.corequisite)
        if coreq_tree is None:
            continue
        target_idx = SEMESTER_ORDER[e.semester_id]
        # For coreqs, same-semester OR earlier counts as satisfied.
        completed_same_or_earlier = {r.module_code for r in entries if SEMESTER_ORDER[r.semester_id] <= target_idx and r.id != e.id}
        if not corequisites_met(coreq_tree, completed_same_or_earlier):
            unmet = explain_unmet(coreq_tree, completed_same_or_earlier) or e.corequisite
            out.append({
                "kind": COREQ_UNMET,
                "entry_id": e.id,
                "module_code": e.module_code,
                "semester_id": e.semester_id,
                "unmet": unmet,
                "message": f"needs {unmet} this semester or earlier",
            })
    return out


# ---------- preclusions ----------

def _check_preclusions(entries: list[PlanEntry]) -> list[dict]:
    """One violation per UNORDERED preclusion pair, regardless of which side declares it.

    NUSMods sometimes declares precludes one-sidedly (A precludes B but B doesn't
    list A). We treat the relation as symmetric for the user's purposes: if A
    declares B as a preclusion and both are in the plan, that's a conflict
    regardless of placement order.
    """
    out = []
    seen_pairs: set[tuple[str, str]] = set()
    code_to_entry = {e.module_code: e for e in entries}

    for e in entries:
        precluded_codes = extract_preclusion_codes(e.preclusion)
        for other_code in precluded_codes:
            if other_code == e.module_code:
                continue  # NUSMods sometimes self-references; ignore
            if other_code not in code_to_entry:
                continue
            # Canonical pair ordering: alphabetical, so each conflict reports once.
            pair = tuple(sorted([e.module_code, other_code]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            ea = code_to_entry[pair[0]]
            eb = code_to_entry[pair[1]]
            out.append({
                "kind": PRECLUSION,
                "module_code_a": ea.module_code,
                "entry_id_a": ea.id,
                "semester_id_a": ea.semester_id,
                "module_code_b": eb.module_code,
                "entry_id_b": eb.id,
                "semester_id_b": eb.semester_id,
                "message": f"{ea.module_code} and {eb.module_code} can't both be in your plan",
            })
    # Sort by the first module code in each pair for stable output.
    out.sort(key=lambda v: v["module_code_a"])
    return out


# ---------- offerings ----------

def _check_offerings(entries: list[PlanEntry]) -> list[dict]:
    out = []
    for e in entries:
        if not e.semesters_offered:
            # If we don't know offerings, don't guess.
            continue
        nus_sem = PLAN_SEM_TO_NUS.get(e.semester_id)
        if nus_sem is None:
            continue
        if nus_sem not in e.semesters_offered:
            out.append({
                "kind": NOT_OFFERED,
                "entry_id": e.id,
                "module_code": e.module_code,
                "semester_id": e.semester_id,
                "offered_in": list(e.semesters_offered),
                "message": f"not offered in Semester {nus_sem}; only in Semester {', '.join(str(s) for s in e.semesters_offered)}",
            })
    return out


# ---------- exam clashes ----------

def _check_exam_clashes(entries: list[PlanEntry]) -> list[dict]:
    """Delegate to services.timetable.find_exam_clashes for the actual pair math.

    We construct ExamEntry instances from PlanEntry's exam fields and let the
    timetable service do the within-semester pairing. Returning the clash
    dicts as-is — `find_exam_clashes` already produces the canonical shape
    with kind=EXAM_CLASH.
    """
    exam_entries = [
        ExamEntry(
            id=e.id,
            module_code=e.module_code,
            semester_id=e.semester_id,
            exam_start=e.exam_start,
            exam_duration_min=e.exam_duration_min,
        )
        for e in entries
    ]
    return find_exam_clashes(exam_entries)


# ---------- "ready" modules: what could the user take next? ----------

def find_ready_modules(
    semester_id: str,
    placed_entries: Iterable[PlanEntry],
    candidate_modules: Iterable[dict],
) -> list[dict]:
    """Return a subset of `candidate_modules` whose prereqs are satisfied
    by the placed entries strictly earlier than `semester_id`.

    Used by the "what can I take next?" suggestion feature. Each candidate is
    a dict from the modules table that includes at least `code` and `prereq_tree`
    (already parsed from JSON). Returns the same dicts unchanged, just filtered.

    Modules already placed in the plan (at ANY semester) are excluded — you can't
    "take next" something you've already scheduled.
    """
    target_idx = SEMESTER_ORDER.get(semester_id)
    if target_idx is None:
        raise ValueError(f"Invalid semester_id: {semester_id!r}")

    placed_list = list(placed_entries)
    placed_codes = {e.module_code for e in placed_list}
    completed_before = {e.module_code for e in placed_list if SEMESTER_ORDER[e.semester_id] < target_idx}

    out = []
    for m in candidate_modules:
        if m["code"] in placed_codes:
            continue
        tree = m.get("prereq_tree")
        if not prereqs_met(tree, completed_before):
            continue
        # Also check semester offering if known — no point suggesting a Sem-1
        # module for a Y2S2 slot.
        sems_offered = m.get("semesters_offered")
        if sems_offered:
            nus_sem = PLAN_SEM_TO_NUS.get(semester_id)
            if nus_sem and nus_sem not in sems_offered:
                continue
        out.append(m)
    return out


# ---------- helper to build PlanEntry from a DB row ----------

def entry_from_row(row, modules_row) -> PlanEntry:
    """Construct a PlanEntry from a sqlite3.Row of plan_entries joined with modules.

    Expects the row to have these columns:
      pe.id, pe.module_code, pe.semester_id
      m.prereq_tree (JSON string or NULL)
      m.corequisite (free text or NULL)
      m.preclusion  (free text or NULL)
      m.semester_data (JSON string or NULL)
    """
    sem_data = None
    raw_semester_data = None  # preserved for exam extraction below
    if modules_row["semester_data"]:
        try:
            raw = json.loads(modules_row["semester_data"])
            raw_semester_data = raw if isinstance(raw, list) else None
            if isinstance(raw, list) and raw and isinstance(raw[0], dict):
                sem_data = sorted({s["semester"] for s in raw if "semester" in s})
            elif isinstance(raw, list):
                sem_data = raw
        except (json.JSONDecodeError, TypeError):
            sem_data = None

    tree = None
    if modules_row["prereq_tree"]:
        try:
            tree = json.loads(modules_row["prereq_tree"])
        except json.JSONDecodeError:
            tree = None

    # Pull exam datetime + duration for THIS entry's NUS semester. If sem_data is
    # the short [int, int, ...] form (no exam metadata) extract_exam returns
    # (None, None) and exam clash detection skips the entry.
    exam_start, exam_duration_min = (None, None)
    nus_sem = PLAN_SEM_TO_NUS.get(row["semester_id"])
    if nus_sem is not None and raw_semester_data is not None:
        exam_start, exam_duration_min = extract_exam(raw_semester_data, nus_sem)

    return PlanEntry(
        id=row["id"],
        module_code=row["module_code"],
        semester_id=row["semester_id"],
        prereq_tree=tree,
        corequisite=_safe_col(modules_row, "corequisite"),
        preclusion=_safe_col(modules_row, "preclusion"),
        semesters_offered=sem_data,
        exam_start=exam_start,
        exam_duration_min=exam_duration_min,
    )


def _safe_col(row, key, default=None):
    try:
        return row[key]
    except (IndexError, KeyError):
        return default
