# Feature 7 — Progress tracker enhancements

**Goal:** Turn the progress page from a percentage indicator into an actionable view: show which modules count toward each bucket, what's eligible-but-not-placed, where MCs are unallocated, and when the user is projected to graduate.

## What changed

**Backend**
- `routes/progress.py` — full rewrite. Response now includes:
  - `total.placed_mcs` and `total.completed_mcs` (split based on whether the grade is passing — F counts as placed but not completed)
  - `projected_completion` — the semester containing the latest placed entry
  - Per-category `placed_modules` array with `{code, mcs, completed, grade}`
  - Per-category `eligible_not_placed` (capped at 8) and `eligible_not_placed_total`
  - `unallocated_modules` — modules in the plan that don't fit any requirement bucket
- Allocation logic — when a category has no `requirement_modules` mapping (an "open" bucket like UE), leftover placed modules are distributed across open buckets in display order, filling earlier buckets first up to their `required_mcs` cap. Prevents the "first open bucket eats everything" arbitrariness.
- `tests/test_progress.py` — new, 6 test functions, 25+ assertions. Covers F-grade exclusion, eligible-not-placed preview, unallocated handling, projected completion, and bucket completion markers.

**Frontend**
- `pages/Progress.jsx` — rewritten. New surfaces:
  - **Two-tone progress ring** in the header — lighter arc for placed, solid arc for completed. Caption explains.
  - **Projection card** and **Remaining card** side by side, showing projected graduation semester + MCs/categories left.
  - **Expandable category rows** — click any category to reveal the placed modules (chips, accent-coloured when completed) and the eligible-not-placed list with "showing N of M" indicators.
  - **Two-tone bars** per category — same accent-on-accent treatment as the ring.
  - **Unallocated section** — surfaces with a warning icon when present.
  - Module chips, eligible items, and UE recommendations all open the ModuleDetailPanel (lifted from Feature 4) for further inspection.

## How to test

```bash
rm -f planner.db && python seed.py
flask --app app run --debug
```

In the frontend (logged in as the CS dev user):
1. Place CS1101S in Y1S1, grade it A. The FOUNDATION bar shows 4/24 (solid).
2. Place CS1231S, grade it F. The FOUNDATION bar shows 8/24 *placed* but only 4/24 *completed* — the lighter arc grows; the solid arc doesn't.
3. Expand FOUNDATION — see CS1101S as a completed chip (accent background), CS1231S as a placed-but-not-completed chip (plain background).
4. The eligible-to-place section lists CS2030S, CS2040S, CS2100, CS2103T.
5. Click any eligible item to open the module detail panel.
6. Switch your major to BZA on /onboarding and re-visit — your placed CS modules end up in the first open bucket (BZA Foundation), with no unallocated section since BZA has 6 open buckets.

## Design notes

- **Two-tone bars/ring** carry semantic load. The lighter arc says "you've committed to this in your plan"; the solid arc says "you've actually earned this". Different planning vs review states. The caption under the ring spells this out.
- **F = placed, not completed.** A failed module still occupies its slot in the plan (and bucket), but its MCs don't count toward graduation. Same for ungraded.
- **Open bucket distribution** fills in display order. Without this rule, leftover modules dump into one arbitrary open bucket — which is what an earlier draft of this code did and the test caught (CS modules going into BZA's UE bucket instead of FOUNDATION).
- **Eligible-not-placed is a preview, not a full list.** Capped at 8 items per bucket. UE buckets in the real catalogue could have thousands of candidates — surfacing all of them is what the catalogue search is for. F7-1 flagged in case we ever need to surface more.
- **Module chips replace plain text.** Clicking opens the detail panel. The mental model: progress page tells you what state you're in; detail panel tells you about each piece. Keeping the link makes both pages more useful.

## API contract additions

See `API.md` → `GET /api/plans/:id/progress` (shape changed).

## Flags raised

- **F7-1:** placed_modules list per category is uncapped. Bounded by degree size anyway.
- **F7-2:** projected completion is naively "latest placed semester" — doesn't account for missing requirements forcing later semesters.
- **F7-3:** cross-counting modules (in multiple buckets) inflate the total. Not in current seed data.

## Tests

```bash
python tests/test_prereqs.py                  # 8  cases ✓
python tests/test_nusmods.py                  # 18 cases ✓
python tests/test_auth.py                     # 18 cases ✓
python tests/test_majors.py                   # 12 cases ✓
python tests/test_module_detail.py            # 14 cases ✓
python tests/test_validation.py               # 33 cases ✓
python tests/test_plan_validate_routes.py     #  8 cases ✓
python tests/test_gpa_scenarios.py            # 17 funcs, 40+ asserts ✓
python tests/test_scenario_routes.py          # 12 cases ✓
python tests/test_progress.py                 # 6 funcs, 25+ asserts ✓ (new)
```

Total: **10 test files, all green.**

## What's not done (deferred)

- **Manual semester planning** in eligible-not-placed — clicking an eligible module opens the panel; from there the user can "Add to plan" but it lands in Y1S1 (F4-2). Better UX would target the earliest valid semester. F4-2 is still open and a small change to that lands the polish.
- **Filters on eligible-not-placed list** — by semester offered, by department, etc.
- **"You can graduate one semester early if…" insight** — needs more sophisticated projection than the current naive one. Tracked as F7-2.
- **Showing requirement-mapping conflicts** — if a module is listed under multiple buckets, surface that visually rather than silently cross-counting. F7-3.
