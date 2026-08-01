"""Seed the database with schema + sample data.

Run: python seed.py

Applies all migrations (creating tables as needed) and inserts ~30 sample
modules + the CS major requirements. Idempotent — re-running upserts.

When you wire up NUSMods sync (services/nusmods.py:sync_all), you can drop
the SAMPLE_MODULES section here entirely.
"""
import json
from db import apply_migrations, connect


# (code, title, mcs, dept, prereq_tree, category) — category is the requirement bucket for seeding.
SAMPLE_MODULES = [
    # CS Foundation
    ("CS1101S", "Programming Methodology",         4, "CS", None,                                   "FOUNDATION", True),
    ("CS1231S", "Discrete Structures",             4, "CS", None,                                   "FOUNDATION", True),
    ("CS2030S", "Programming Methodology II",      4, "CS", "CS1101S",                              "FOUNDATION", True),
    ("CS2040S", "Data Structures and Algorithms",  4, "CS", {"and": ["CS1101S", "CS1231S"]},        "FOUNDATION", True),
    ("CS2100",  "Computer Organisation",           4, "CS", "CS1101S",                              "FOUNDATION", True),
    ("CS2103T", "Software Engineering",            4, "CS", {"and": ["CS2030S", "CS2040S"]},        "FOUNDATION", True),

    # CS Breadth & Depth
    ("CS2106",  "Operating Systems",               4, "CS", {"and": ["CS2030S", "CS2100"]},         "CS_BREADTH", False),
    ("CS2109S", "Intro to AI and ML",              4, "CS", {"and": ["CS2030S", "CS2040S", "MA1521"]}, "CS_BREADTH", False),
    ("CS3230",  "Design and Analysis of Algorithms", 4, "CS", {"and": ["CS2040S", "CS1231S"]},      "CS_BREADTH", False),
    ("CS3243",  "Introduction to AI",              4, "CS", {"and": ["CS2030S", "CS2040S"]},        "CS_BREADTH", False),
    ("CS3245",  "Information Retrieval",           4, "CS", {"and": ["CS2040S", "ST2334"]},         "CS_BREADTH", False),
    ("CS3203",  "Software Engineering Project",    8, "CS", "CS2103T",                              "CS_BREADTH", False),
    ("CS4243",  "Computer Vision",                 4, "CS", {"and": ["CS2030S", "MA1101R"]},        "CS_BREADTH", False),
    ("CS4248",  "Natural Language Processing",     4, "CS", "CS2109S",                              "CS_BREADTH", False),

    # IT Professionalism
    ("IS1108",  "Digital Ethics and Data Privacy", 4, "IS", None,                                   "IT_PROF", True),
    ("CS2101",  "Effective Communication for Computing", 4, "CS", None,                             "IT_PROF", True),

    # Math & Sciences
    ("MA1521",  "Calculus for Computing",          4, "MA", None,                                   "MATH", True),
    ("MA1101R", "Linear Algebra I",                4, "MA", None,                                   "MATH", True),
    ("ST2334",  "Probability and Statistics",      4, "ST", "MA1521",                               "MATH", True),

    # General Education
    ("GEA1000",  "Quantitative Reasoning with Data",   4, "GE", None,                               "GE", False),
    ("GESS1025", "Public Health in Action",            4, "GE", None,                               "GE", False),
    ("GEC1015",  "The Worlds of Wine",                 4, "GE", None,                               "GE", False),
    ("GEN2061",  "Communicating Across Cultures",      4, "GE", None,                               "GE", False),
    ("GEH1036",  "Living with Mathematics",            4, "GE", None,                               "GE", False),
    ("ES2660",   "Communicating in the Information Age", 4, "GE", None,                             "GE", False),

    # Unrestricted Electives
    ("CS3216",  "Software Product Engineering",    5, "CS", "CS2103T",                              "UE", False),
    ("CS3217",  "Modern Application Engineering",  5, "CS", "CS3216",                               "UE", False),
    ("BT2102",  "Data Management and Visualisation", 4, "BT", None,                                 "UE", False),
    ("EC1101E", "Introduction to Economic Analysis", 4, "EC", None,                                 "UE", False),
    ("PL1101E", "Introduction to Psychology",      4, "PL", None,                                   "UE", False),
    ("MA2104",  "Multivariable Calculus",          4, "MA", "MA1521",                               "UE", False),
]


REQUIREMENTS = [
    # Computer Science
    ("CS", "FOUNDATION",  "CS Foundation",          24, 1),
    ("CS", "CS_BREADTH",  "CS Breadth & Depth",     32, 2),
    ("CS", "IT_PROF",     "IT Professionalism",      8, 3),
    ("CS", "MATH",        "Mathematics & Sciences", 12, 4),
    ("CS", "GE",          "General Education",      20, 5),
    ("CS", "UE",          "Unrestricted Electives", 32, 6),

    # Business Analytics — buckets only for now; modules-to-bucket mapping
    # will fill in once the NUSMods sync runs.
    ("BZA", "FOUNDATION", "BZA Foundation",         28, 1),
    ("BZA", "DOMAIN",     "Business Domain",        32, 2),
    ("BZA", "MATH",       "Mathematics & Statistics", 16, 3),
    ("BZA", "IT_PROF",    "IT Professionalism",      8, 4),
    ("BZA", "GE",         "General Education",      20, 5),
    ("BZA", "UE",         "Unrestricted Electives", 36, 6),

    # Information Systems
    ("IS", "FOUNDATION",  "IS Foundation",          28, 1),
    ("IS", "IS_BREADTH",  "IS Breadth & Depth",     32, 2),
    ("IS", "IT_PROF",     "IT Professionalism",      8, 3),
    ("IS", "MATH",        "Mathematics & Sciences", 12, 4),
    ("IS", "GE",          "General Education",      20, 5),
    ("IS", "UE",          "Unrestricted Electives", 28, 6),
]


# (code, name, faculty, total_mcs, display_order)
# total_mcs should match the sum of REQUIREMENTS entries for that major.
MAJORS = [
    ("CS",  "Bachelor of Computing (Computer Science)",   "School of Computing",     128, 1),
    ("BZA", "Bachelor of Science (Business Analytics)",   "School of Computing",     140, 2),
    ("IS",  "Bachelor of Computing (Information Systems)", "School of Computing",   128, 3),
]


# Extra fields layered onto SAMPLE_MODULES after the basic insert.
# Used by Feature 5 (validation polish) to exercise coreqs, preclusions,
# and semester-offering checks. Extended in Feature 9 to cover exam clashes.
# Keep small — these are mock examples chosen for illustration; real values
# come from the NUSMods sync.
#
# Each value is a dict that may have:
#   "preclusion":   str — comma-separated codes that conflict
#   "corequisite":  str — free-text, parsed by services.prereqs.parse_corequisite_string
#   "semester_data": list[int] — NUS semester numbers (shorthand; no exam metadata)
#   "exam_data":    list[dict] — full semester records with examDate/examDuration;
#                   takes precedence over semester_data when present
#
# Note on exam dates: NUSMods uses ISO 8601 with Singapore offset (+08:00). The
# dates below are realistic AY2024-2025 final-exam window dates; the times are
# deliberately *overlapping pairs* so the demo plan shows the EXAM_CLASH path:
#   - CS2030S and CS2040S: both Y1 modules, overlapping Sem 2 morning exams
#   - CS3216 and CS3243: overlapping Sem 1 afternoon exams
# These specific clashes do happen in real life when NUS reuses time slots
# across modules from different cohorts; the recommender is supposed to catch it.
MODULE_EXTENSIONS = {
    "CS2103T": {"corequisite": "CS2101"},
    "CS2030S": {
        "preclusion": "CS2030, CS2030DE",
        "exam_data": [
            {"semester": 2, "examDate": "2025-04-29T09:00:00.000+08:00", "examDuration": 120},
        ],
    },
    "CS2040S": {
        "exam_data": [
            # Overlaps with CS2030S above — same morning, same duration.
            {"semester": 2, "examDate": "2025-04-29T09:00:00.000+08:00", "examDuration": 120},
        ],
    },
    "CS3216": {
        "semester_data": [1],
        "exam_data": [
            {"semester": 1, "examDate": "2024-11-26T13:00:00.000+08:00", "examDuration": 120},
        ],
    },
    "CS3203": {"semester_data": [1]},
    "ST2334": {"semester_data": [1, 2]},
    "CS3243": {
        "preclusion": "CS3243R",
        "exam_data": [
            # Overlaps with CS3216 in Sem 1 (both 1pm-3pm same day).
            {"semester": 1, "examDate": "2024-11-26T13:00:00.000+08:00", "examDuration": 120},
        ],
    },
    "IS1108": {"semester_data": [1]},
    # CS2100: stand-alone exam, no clashes — sanity check that a module with an
    # exam date but no overlapping counterpart doesn't trigger spurious clashes.
    "CS2100": {
        "exam_data": [
            {"semester": 2, "examDate": "2025-05-02T13:00:00.000+08:00", "examDuration": 120},
        ],
    },
}


def seed():
    print("→ Applying migrations…")
    applied = apply_migrations()
    if applied:
        print(f"  applied {len(applied)}: {', '.join(applied)}")
    else:
        print("  schema already up to date")

    print("→ Seeding modules…")
    with connect() as conn:
        for code, title, mcs, dept, prereq, _cat, _comp in SAMPLE_MODULES:
            conn.execute(
                """
                INSERT INTO modules (code, title, mcs, department, prereq_tree, acad_year)
                VALUES (?, ?, ?, ?, ?, '2024-2025')
                ON CONFLICT(code) DO UPDATE SET
                  title = excluded.title,
                  mcs = excluded.mcs,
                  department = excluded.department,
                  prereq_tree = excluded.prereq_tree,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (code, title, mcs, dept, json.dumps(prereq) if prereq else None),
            )

        # Apply Feature 5 extensions: coreq / preclusion / offerings on select modules.
        # Feature 9 adds exam_data — a richer form that takes precedence over the
        # bare semester_data shorthand because it carries examDate/examDuration too.
        for code, ext in MODULE_EXTENSIONS.items():
            sets = []
            params = []
            if "preclusion" in ext:
                sets.append("preclusion = ?"); params.append(ext["preclusion"])
            if "corequisite" in ext:
                sets.append("corequisite = ?"); params.append(ext["corequisite"])
            if "exam_data" in ext:
                # Store as-is; extract_exam handles the dict shape and pulls semesters
                # from "semester" keys for the offerings check.
                sets.append("semester_data = ?"); params.append(json.dumps(ext["exam_data"]))
            elif "semester_data" in ext:
                sem_objs = [{"semester": s} for s in ext["semester_data"]]
                sets.append("semester_data = ?"); params.append(json.dumps(sem_objs))
            if sets:
                params.append(code)
                conn.execute(f"UPDATE modules SET {', '.join(sets)} WHERE code = ?", params)

        print("→ Seeding requirements…")
        for major, cat, label, mcs, order in REQUIREMENTS:
            conn.execute(
                """
                INSERT INTO degree_requirements (major_code, category, label, required_mcs, acad_year, display_order)
                VALUES (?, ?, ?, ?, '2024-2025', ?)
                ON CONFLICT(major_code, category, acad_year) DO UPDATE SET
                  label = excluded.label,
                  required_mcs = excluded.required_mcs,
                  display_order = excluded.display_order
                """,
                (major, cat, label, mcs, order),
            )

        print("→ Seeding majors…")
        for code, name, faculty, total_mcs, order in MAJORS:
            conn.execute(
                """
                INSERT INTO majors (code, name, faculty, total_mcs, acad_year, display_order)
                VALUES (?, ?, ?, ?, '2024-2025', ?)
                ON CONFLICT(code) DO UPDATE SET
                  name = excluded.name,
                  faculty = excluded.faculty,
                  total_mcs = excluded.total_mcs,
                  display_order = excluded.display_order
                """,
                (code, name, faculty, total_mcs, order),
            )

        print("→ Linking modules to requirements…")
        # Clear and re-link based on SAMPLE_MODULES categories.
        conn.execute("DELETE FROM requirement_modules")
        req_ids = {
            r["category"]: r["id"]
            for r in conn.execute(
                "SELECT id, category FROM degree_requirements WHERE major_code = 'CS'"
            ).fetchall()
        }
        for code, _title, _mcs, _dept, _prereq, cat, compulsory in SAMPLE_MODULES:
            rid = req_ids.get(cat)
            if rid:
                conn.execute(
                    "INSERT INTO requirement_modules (requirement_id, module_code, is_compulsory) VALUES (?, ?, ?)",
                    (rid, code, 1 if compulsory else 0),
                )

        # ----- Demo "ghost" users for Feature 8 (collaborative recommendations) -----
        # Three synthetic CS users with slightly different study profiles, plus one
        # BZA user. Without other plans in the system, the collaborative filter has
        # no signal and falls back to pure popularity — fine for prod (real users
        # will populate it) but lifeless in dev. These fixtures give the
        # recommender something to chew on for demos.
        #
        # SAFE_TO_DROP: nothing in production seeds users with the `ghost-user-*`
        # prefix, so we can clear and reinsert without disturbing real data.
        print("→ Seeding demo ghost users for recommendations…")
        conn.execute("DELETE FROM plan_entries WHERE plan_id IN (SELECT id FROM study_plans WHERE user_id LIKE 'ghost-user-%')")
        conn.execute("DELETE FROM study_plans WHERE user_id LIKE 'ghost-user-%'")
        conn.execute("DELETE FROM users WHERE id LIKE 'ghost-user-%'")

        ghosts = [
            # (user_id, major, [modules]). Modules include both core CS and UE picks.
            ("ghost-user-cs-1", "CS", [
                "CS1101S", "CS1231S", "CS2030S", "CS2040S", "CS2100", "CS2103T",
                "MA1521", "MA1101R", "ST2334",
                "CS3216", "BT2102", "EC1101E",   # UE picks
            ]),
            ("ghost-user-cs-2", "CS", [
                "CS1101S", "CS1231S", "CS2030S", "CS2040S", "CS2100", "CS2103T",
                "MA1521", "ST2334",
                "CS3216", "CS3217", "MA2104",    # UE picks (different mix)
            ]),
            ("ghost-user-cs-3", "CS", [
                "CS1101S", "CS1231S", "CS2030S", "CS2040S",
                "MA1521", "MA1101R",
                "BT2102", "PL1101E",             # UE picks (more applied)
            ]),
            ("ghost-user-bza-1", "BZA", [
                "BT2102", "EC1101E", "MA1521", "ST2334",
                "MA2104", "CS3216",              # UE picks (overlap with CS ghosts)
            ]),
        ]

        # Sem assignments are arbitrary for ghosts — recommendations only care about
        # which modules are placed, not where. Spread across Y1S1..Y3S2 for realism.
        sems = ["Y1S1", "Y1S2", "Y2S1", "Y2S2", "Y3S1", "Y3S2"]
        for user_id, major, modules in ghosts:
            conn.execute(
                "INSERT INTO users (id, email, display_name, major_code, matric_year) VALUES (?, ?, ?, ?, 2023)",
                (user_id, f"{user_id}@dev.local", user_id, major),
            )
            cur = conn.execute(
                "INSERT INTO study_plans (user_id, name) VALUES (?, 'Ghost Plan')",
                (user_id,),
            )
            plan_id = cur.lastrowid
            for i, mod in enumerate(modules):
                conn.execute(
                    "INSERT INTO plan_entries (plan_id, module_code, semester_id) VALUES (?, ?, ?)",
                    (plan_id, mod, sems[i % len(sems)]),
                )

    print("✓ Done.")
    print()
    print("Try it:")
    print('  curl -H "Authorization: Bearer dev-user-alice" http://localhost:5000/api/modules?limit=5')


if __name__ == "__main__":
    seed()
