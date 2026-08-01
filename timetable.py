"""Timetable conflict detection.

Today this covers EXAM clashes only — pairs of modules in the same plan
semester whose final-exam windows overlap. Class-time clashes (lectures,
tutorials, labs) require the student to have picked specific class slots,
which the planner doesn't model yet. See F9-2 in features/FLAGS.md for
the deferred work.

NUSMods stores each module's exam info inside `semesterData`:

  "semesterData": [
    {
      "semester": 1,
      "examDate":     "2024-11-25T13:00:00.000+08:00",
      "examDuration": 120,    // minutes
      "timetable":    [...]
    },
    ...
  ]

`extract_exam` here pulls (exam_start_datetime, duration_minutes) out of
that structure for a given NUS semester number. `find_exam_clashes`
enumerates pairs within the same plan semester and returns the overlaps.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable


# Mapping from plan-semester id ("Y1S1" .. "Y4S2") to the NUS semester number
# that determines which entry of semesterData to read. Y_S1 -> Sem 1, Y_S2 -> Sem 2.
# Special terms (semester 3, 4) aren't in the 8-slot grid; modules only offered
# in special terms are handled by the NOT_OFFERED check, not this one.
PLAN_SEM_TO_NUS = {f"Y{y}S{s}": s for y in range(1, 5) for s in range(1, 3)}


# ---------------- parsing ----------------

def parse_exam_datetime(s: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp like ``2024-11-25T13:00:00.000+08:00``.

    Returns None on empty / unparseable input. We tolerate the milliseconds
    component (NUSMods always includes ``.000``) by stripping it before
    handing the string to ``fromisoformat``, which keeps us compatible with
    Python 3.10 (where fromisoformat doesn't accept fractional seconds).
    """
    if not s or not isinstance(s, str):
        return None
    cleaned = re.sub(r"\.\d+", "", s)
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def extract_exam(semester_data: list, nus_sem: int) -> tuple[datetime | None, int | None]:
    """From a module's semesterData JSON, return (exam_start, duration_min) for
    the given NUS semester number.

    Returns (None, None) if no semester data is present, the semester isn't
    listed, or the exam fields are missing.
    """
    if not isinstance(semester_data, list):
        return (None, None)
    for s in semester_data:
        if not isinstance(s, dict):
            continue
        if s.get("semester") != nus_sem:
            continue
        exam_date_str = s.get("examDate")
        exam_duration = s.get("examDuration")
        exam_start = parse_exam_datetime(exam_date_str) if exam_date_str else None
        try:
            duration = int(exam_duration) if exam_duration is not None else None
        except (TypeError, ValueError):
            duration = None
        return (exam_start, duration)
    return (None, None)


# ---------------- overlap math ----------------

def exams_overlap(
    a_start: datetime | None, a_duration_min: int | None,
    b_start: datetime | None, b_duration_min: int | None,
) -> bool:
    """True iff the two exam intervals overlap.

    Treats missing data permissively: if either side has no datetime or no
    duration, we return False (can't prove a conflict from missing data).

    Intervals are half-open [start, start+duration); back-to-back exams
    (one ending exactly when the next begins) don't clash by this rule.
    That matches the practical concern — you can walk between rooms in
    zero minutes only in a thought experiment.
    """
    if not a_start or not b_start:
        return False
    if a_duration_min is None or b_duration_min is None:
        return False
    a_end = a_start + timedelta(minutes=a_duration_min)
    b_end = b_start + timedelta(minutes=b_duration_min)
    return a_start < b_end and b_start < a_end


# ---------------- pair detection ----------------

@dataclass
class ExamEntry:
    """Minimal info needed to detect clashes between scheduled exams."""
    id: int                       # plan_entries.id
    module_code: str
    semester_id: str              # "Y1S1" .. "Y4S2"
    exam_start: datetime | None
    exam_duration_min: int | None


def find_exam_clashes(entries: Iterable[ExamEntry]) -> list[dict]:
    """Return a list of clash dicts. Pairs are reported once, in canonical
    (alphabetical) code order, so the output is stable and deduplicated.

    Each clash:
      {
        kind: "EXAM_CLASH",
        semester_id: "Y1S2",
        module_code_a / entry_id_a / exam_start_a,
        module_code_b / entry_id_b / exam_start_b,
        message: "...",
      }
    """
    # Group entries by plan-semester. Clashes only happen within the same
    # plan semester (you don't sit a Y1S1 exam during Y2S1).
    by_sem: dict[str, list[ExamEntry]] = {}
    for e in entries:
        if e.exam_start and e.exam_duration_min:
            by_sem.setdefault(e.semester_id, []).append(e)

    clashes: list[dict] = []
    for sem_id, group in by_sem.items():
        # All pairs within this semester.
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if not exams_overlap(a.exam_start, a.exam_duration_min, b.exam_start, b.exam_duration_min):
                    continue
                # Canonical ordering for stable output and easy deduplication.
                if a.module_code <= b.module_code:
                    first, second = a, b
                else:
                    first, second = b, a
                clashes.append({
                    "kind": "EXAM_CLASH",
                    "semester_id": sem_id,
                    "module_code_a": first.module_code,
                    "entry_id_a": first.id,
                    "exam_start_a": first.exam_start.isoformat() if first.exam_start else None,
                    "module_code_b": second.module_code,
                    "entry_id_b": second.id,
                    "exam_start_b": second.exam_start.isoformat() if second.exam_start else None,
                    "message": (
                        f"{first.module_code} and {second.module_code} have overlapping exams "
                        f"in {sem_id}"
                    ),
                })

    # Sort for stable output: by semester, then by first module code.
    clashes.sort(key=lambda c: (c["semester_id"], c["module_code_a"]))
    return clashes
