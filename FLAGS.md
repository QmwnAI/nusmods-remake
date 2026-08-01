# Flags & open questions

A running list of things flagged during feature builds that aren't blocking but deserve attention later. Each entry has a state: **open**, **resolved**, or **wontfix**.

When something here gets addressed in a future feature, mark it resolved and link the feature folder.

---

## Open

### F1-1 — NUSMods sync untested end-to-end against real API
**Raised in:** Feature 1 (NUSMods catalogue sync)
**Issue:** The sandbox where the sync was built has no internet access, so the HTTP layer (`fetch_with_retry`, `fetch_module_list`, `fetch_module_detail`) is structurally verified but never hit NUSMods for real.
**Action:** First time you run a real sync, watch for: (a) lots of 404s → `NUSMODS_ACAD_YEAR` mismatch; (b) timeouts → bump `--workers` down; (c) unexpected JSON shapes → log the failing payload and adjust `upsert_module` accordingly.

### F1-2 — No DB migration framework ✅ RESOLVED
**Raised in:** Feature 1
**Resolved in:** Feature 15
**Issue:** Feature 1's schema change (`mcs INTEGER` → `REAL`, added `preclusion`/`workload`/`corequisite`) required deleting `planner.db` because `CREATE TABLE IF NOT EXISTS` doesn't update existing tables. Reinforced across many features that added columns.
**Resolution:** Migration framework added in Feature 15. `backend/migrations/` holds numbered SQL files; `db.apply_migrations()` applies un-applied files in order and tracks them in `schema_migrations`. Runs automatically on app startup (dev) and via `release_command` in fly.toml (prod). See `features/15-deployment/README.md` and `backend/migrations/README.md`.

### F3-1 — BZA and IS majors seeded without module-to-bucket mappings
**Raised in:** Feature 3 (major selection & onboarding)
**Issue:** The seed data adds requirement *buckets* for BZA (6 buckets, 140 MCs) and IS (6 buckets, 128 MCs), but no `requirement_modules` rows linking specific modules to those buckets. A BZA user's progress page will show all-zero progress until either: (a) a real NUSMods sync runs and we add a proper mapping, or (b) the heuristic in `routes/progress.py` for unallocated modules kicks in.
**Action:** When implementing Feature 4 (module detail) or 7 (progress enhancements), add real module-to-bucket mappings for BZA and IS. The current CS mapping in `seed.py` is the template — extend it. Source of truth is the official curriculum pages on the NUS Computing site.

### F3-2 — flask-cors now an optional dep, but it's still in requirements.txt
**Raised in:** Feature 3
**Issue:** `app.py` was made tolerant of missing `flask-cors` so tests could run in barebones environments. Production envs will install it via `requirements.txt` so the warning won't fire, but the dual code path means a misconfigured prod env would silently drop CORS headers and fail in confusing ways.
**Action:** If we ever see "CORS error" reports from users, first check the backend startup logs for the `flask-cors not installed` warning. Consider promoting the warning to a hard error when `FLASK_ENV=production`.

### F4-1 — Unlocks query is a LIKE scan, not an index
**Raised in:** Feature 4 (module detail panel)
**Issue:** The "unlocks" list in `GET /api/modules/:code` runs `WHERE prereq_tree LIKE '%"CODE"%'` across the modules table. With the 31-module seed it's instant; with the real ~6000 modules it should still be fast (one query, no joins), but it scales linearly. False positives are theoretically possible if a code is a substring of another inside the JSON, but since codes are quoted in the JSON and follow consistent NUS naming, this is essentially impossible.
**Action:** If `GET /api/modules/:code` ever shows up in slow-query logs after Feature 1 (NUSMods sync) lands real data, build an inverse-prereq index: a `prereq_unlocks(prereq_code, unlocks_code)` table populated by walking each module's tree using `services.prereqs.collect_required_codes`. Repopulate as part of the sync job.

### F4-2 — Panel's "Add to plan" hardcodes Y1S1 as the target
**Raised in:** Feature 4
**Issue:** When the user opens a module's detail panel and clicks "Add to plan", the module is added to Y1S1 by default. They can drag it elsewhere afterwards, but it's a clunky UX for modules with a clear later-year placement (e.g. CS4248 which has a long prereq chain).
**Action:** Two reasonable improvements: (a) let the panel surface a semester picker before adding; (b) auto-pick the earliest semester where prereqs would be satisfied. The second is genuinely useful — the prereq evaluator already has the logic; it'd just need to scan Y1S1..Y4S2 and return the first valid slot. **Note:** Feature 5 added `find_ready_modules` in `services/validation.py` which is close to what we'd need — extending it to "find first ready semester" is a one-line change.

### F5-1 — Coreq parser handles flat strings well, but not parenthesised
**Raised in:** Feature 5 (validation polish)
**Issue:** `parse_corequisite_string` recognises `"X and Y"`, `"X or Y"`, and combined `"X and Y or Z"` (parsed as `X and (Y or Z)`), but doesn't parse parenthesised expressions like `"X and (Y or Z)"`. NUSMods coreq strings are almost always flat, so this is rare in practice. When the parser fails it returns `{"raw": text}` and the validator skips the check — the user sees the raw text but no automatic check.
**Action:** Fix only if real-world examples appear after the NUSMods sync runs. The raw-string fallback prevents user-visible breakage; this is just lost automatic validation.

### F5-2 — Preclusion check is symmetric but doesn't catch transitivity
**Raised in:** Feature 5
**Issue:** If A precludes B, and B precludes C, we don't conclude A precludes C. In practice NUSMods declares preclusions explicitly on each side, so transitive closure isn't needed — but if we ever see real users where this matters, we'd need to build a preclusion graph and do connected-components.
**Action:** Probably won't fix. Note the assumption in case future data violates it.

### F5-3 — `MODULE_EXTENSIONS` in seed.py is hardcoded; real coreq/preclusion data should come from NUSMods sync
**Raised in:** Feature 5
**Issue:** To exercise the new validation kinds, we hardcoded preclusion/coreq/semester data on a handful of modules in `seed.py`'s `MODULE_EXTENSIONS` dict. This is fine while we're using the seed for dev — gives demos something to show — but once Feature 1's NUSMods sync runs on a real DB, these manual extensions would be overwritten by the next `upsert_module` call (which is correct behaviour — we want real data winning).
**Action:** When running the real sync for the first time, expect the seed's demo coreqs/preclusions to disappear and be replaced with NUSMods reality. If demos still want hardcoded examples, move them to a separate `seed_demo_data.py` script that runs AFTER sync.

### F6-1 — S/U eligibility is not modeled
**Raised in:** Feature 6 (GPA scenario planner)
**Issue:** NUS forbids S/U on some module categories (compulsory CS Foundation modules for declared CS majors, capstone projects, internships, etc.). Our `recommend_sus` doesn't know about this — it'll happily recommend S/U-ing CS1101S even though that's not allowed for a CS major. We also don't track how many S/U-able MCs the user has actually used historically.
**Action:** Add a per-module `is_su_eligible` boolean (default true), populated from the NUSMods sync where possible plus a hardcoded blocklist for compulsory modules per major. Also consider tracking S/U budget consumption — currently the user types it in the budget field. A future "profile" extension could remember it.

### F6-2 — Scenario endpoint is POST despite being read-only
**Raised in:** Feature 6
**Issue:** `POST /api/plans/:id/gpa/scenario` is idempotent and doesn't persist anything, but it's POST because the override map can exceed query-string limits. A purist would say this should be GET. Browser caching of POST is non-existent, but for a what-if calculator that's actually fine — we never want it cached.
**Action:** Probably won't fix. Document it in the API.md so the choice is intentional. Future cleanup if we ever consolidate the API conventions.

### F6-3 — Target planner treats all remaining MCs as one bucket
**Raised in:** Feature 6
**Issue:** The "required avg GP" calculation assumes every remaining MC contributes the same way. In reality, students often have a clear sense that some modules will be S/U'd (so they don't contribute to CAP), and the target should account for that. Right now the user has to manually pre-compute their adjusted `remaining_mcs` if they want this granularity.
**Action:** Once the per-entry editor lets users mark planned-S/U on ungraded entries, the auto-counted remaining MCs should already exclude them — the existing logic does this. The remaining gap is just clearer UX explaining the assumption. Low priority.

### F7-1 — Progress endpoint response is unbounded
**Raised in:** Feature 7 (progress tracker enhancements)
**Issue:** The progress response includes every `placed_module` in every category. With ~40 modules in a typical 4-year plan that's a hundred-ish nested objects — fine. But once a user has multiple plans with lots of entries and we add a "compare plans" view (Feature 10), naive aggregation could balloon. We do cap `eligible_not_placed` at 8 items but `placed_modules` is uncapped.
**Action:** Add `placed_modules_total` and cap `placed_modules` to ~10 if we ever see slow loads. Probably never needed — placement count is bounded by degree size.

### F7-2 — Projected completion is naively "latest placed semester"
**Raised in:** Feature 7
**Issue:** We report "projected completion = latest semester containing a placed entry". This is true if the user finishes everything they've placed, but doesn't account for missing requirements (a plan with only Y1 placed shows projected = Y1S1, which is wrong if they need 4 years to graduate). A smarter projection would walk requirements and estimate how many more semesters are needed at a typical 20 MC/sem load.
**Action:** Improve when we have a clearer "ideal load per semester" notion. For now the displayed text is "based on your latest placed module" which is honest about the limitation.

### F7-3 — Bucket allocation for codes listed in multiple requirements is permissive
**Raised in:** Feature 7
**Issue:** If a module appears in `requirement_modules` under both CS_BREADTH and UE (unusual but legal), my code counts its MCs toward both. The cap-at-required ceiling per bucket prevents this from inflating the *category* progress beyond 100%, but the total across categories can exceed required_mcs. In the seed this never happens; once real cross-counting modules exist in NUSMods data it might.
**Action:** When fixing F3-1 (real BZA/IS module-to-bucket mapping), audit any cross-counting and either disallow it in the schema (PRIMARY KEY already lets it) or add greedy single-allocation logic. Defer until concrete examples appear.

### F8-1 — Recommendation cold-start when there are no other users
**Raised in:** Feature 8 (collaborative-filtering recommendations)
**Issue:** A real first deployment has zero "other users" — every recommendation is pure popularity (zero), and the seed's ghost users carry the demo. In dev that's fine; in prod, the first real user will get bare recommendations until others sign up. Same problem hits anyone with a totally unique plan profile (no Jaccard overlap with anyone).
**Action:** As a graceful improvement, add a "what most CS Y3 students take" fallback that uses major + matric year as a coarser bucket. Defer until usage data exists; for now the log1p(popularity) component does provide *some* signal even with zero overlap.

### F8-2 — Ghost users are visible to the recommendations endpoint in production
**Raised in:** Feature 8
**Issue:** The seed inserts `ghost-user-*` rows with `INSERT INTO users` so they're queryable as full users. If a production deployment runs `python seed.py` (it shouldn't, but might), the ghosts would be visible in any cross-user query. The naming prefix makes them easy to filter, but no code currently does.
**Action:** Either (a) move ghost insertion to a separate `seed_demo_data.py` that production never runs, or (b) tag ghost users with an `is_ghost` boolean and filter on read. Option (b) is more robust. Defer until production deployment is on the table — F1-2 (migrations) needs to land first.

### F8-3 — Recommendation scoring weights are unprincipled
**Raised in:** Feature 8
**Issue:** `WEIGHT_OVERLAP = 1.0`, `WEIGHT_SAME_MAJOR = 0.5`, `DIVERSITY_PENALTY_PER_DUP = 0.15` — pulled from feel, not data. With real usage we could tune these against click-through or "added to plan" rates.
**Action:** When we have ≥ a few hundred users actively recommending and adding, instrument click-through, then grid-search weights to optimize. Until then, these defaults are fine.

### F9-1 — Class-time clashes not detected, only exam clashes
**Raised in:** Feature 9 (timetable conflict detection)
**Issue:** Exam clashes are deterministic (each module has one exam per semester) so they're cheap to detect. Class-time clashes (lecture/tutorial/lab slots) require the user to have picked specific class numbers — `01` vs `02` for the lecture, etc. — and then evaluating whether at least one combination of all required lesson types across all placed modules can be scheduled without conflicts. We don't model class selection in the planner today, so this check is out of scope.
**Action:** When/if we add a per-semester class-picker view ("here are your timetables for this semester, choose slots"), build the conflict graph then. Until then, the recommendation is: pick exam-clean and use NUSMods.com for live timetable resolution. The exam clash check at least prevents the worst-case scheduling impossibility (you literally cannot sit two exams at once).

### F9-2 — Exam clash detection assumes one exam per module per semester
**Raised in:** Feature 9
**Issue:** NUSMods very occasionally lists modules with multiple exam dates (mid-terms, alternate sittings). `extract_exam` picks the first matching semester record and ignores the rest. For the AY2024-25 dataset this hasn't come up; if NUSMods evolves toward multiple exams per module, we'd silently miss clashes against the second.
**Action:** Audit after the next real NUSMods sync. If we find modules with multiple exam entries in one semester, generalize `extract_exam` to return a list and have `find_exam_clashes` enumerate all sub-pairs.

### F9-3 — Exam dates ignore venue and walking time
**Raised in:** Feature 9
**Issue:** NUS sometimes schedules back-to-back exams at venues on opposite ends of the Kent Ridge campus. Our half-open interval check (`a_end == b_start` is fine) doesn't account for travel time. In reality, NUS Exam Office tries to avoid this, so it's rarely an issue — but a 3-hour exam ending at noon in MPSH followed by a 12:00 PM exam in COM3 is technically valid here.
**Action:** Add a configurable buffer (e.g. 30 min minimum gap) once we see real cases. Until then, the strict interval overlap is honest and matches user expectation ("I literally cannot sit both at once").

### F10-1 — No pre-signup invites
**Raised in:** Feature 10 (plan sharing)
**Issue:** The share endpoint requires the recipient to already exist in the users table — typically by having signed in once. A user who wants to share with a friend who hasn't signed up yet sees a `USER_NOT_FOUND` error. The error message tells them to ask the friend to sign in first, but it's clunky.
**Action:** Add a `pending_invites` table keyed by email. On signup, check for matching pending invites and convert them to shares. Defer until we have actual real signups; this is the kind of bookkeeping that only matters with a user base.

### F10-2 — Share recipient sees plan owner's display_name only after they've set one
**Raised in:** Feature 10
**Issue:** The recipient's "shared with me" list shows `owner.display_name || owner.email`. In dev (where display_name auto-populates from the user ID like "dev-user-alice"), this looks OK. In prod with Clerk, display_name may be empty if the user hasn't completed their profile, so the recipient sees a raw email instead. Functionally fine, just less friendly.
**Action:** Add a setup prompt encouraging users to set a display name. Or fall back to "Anonymous CS Y3" or similar from the major/matric_year. Defer until a real user complains.

### F10-3 — Comparison view scales poorly past two plans
**Raised in:** Feature 10
**Issue:** The compare view is fixed at "yours vs theirs" — two columns, side-by-side. Asking "how do my plan, my mentor's plan, and my friend's plan compare?" would need a 3-column layout, which fits a desktop but cramps on mobile. The diff math also balloons combinatorially.
**Action:** Probably won't fix. Two-way comparison is the natural use case ("did I miss anything?"). If users actually request N-way, consider a different visualization — heatmap or matrix — rather than scaling the column count.

### F11-1 — Match scoring uses "first plan" for the candidate user
**Raised in:** Feature 11 (study group matching)
**Issue:** When computing plan overlap, the route picks `MIN(id) FROM study_plans WHERE user_id = ?` — i.e. the candidate's oldest plan. Most users have one plan, so this is correct in practice. A user with multiple plans (a "what-if" experiment alongside their real plan) would have their oldest plan counted for matching, which might not reflect what they're actually taking.
**Action:** Add an `is_active` or `is_primary` flag on `study_plans` (the column exists but is unused), and prefer the active plan. Or have the user explicitly designate which plan represents reality. Low priority — most users have one plan.

### F11-2 — Recency window is "since opt-in created", not "since opt-in last active"
**Raised in:** Feature 11
**Issue:** A user who opted in 6 months ago and never came back is still listed; the +5 recency bonus expires for them, but they're not filtered out. The recipient might email them and get silence.
**Action:** Add a "last active" tick (updated on any /me hit) and stop showing matches whose owner hasn't been active in 30+ days. Or, less invasively, surface "last active X weeks ago" on the card so the user can self-judge.

### F11-3 — Score weights are arbitrary
**Raised in:** Feature 11
**Issue:** `WEIGHT_SAME_MAJOR=25`, `SAME_YEAR=20`, `PLAN_OVERLAP=30`, `RECENCY=5` — pulled from feel, not data. Are these the right relative weights? Hard to say without instrumenting "did the user actually email this match?" and learning from outcomes.
**Action:** Same as F8-3 — log click-through, tune from data once usage exists. Until then, the displayed score is a soft ranking aid, not a number to over-index on.

### F11-4 — Telegram handle isn't verified
**Raised in:** Feature 11
**Issue:** The user can type any string into the Telegram field. If they typo'd or filled in someone else's handle, matches will get the wrong contact. We don't (and shouldn't) verify against Telegram's API.
**Action:** Probably won't fix — Telegram itself doesn't expose verification for non-bot users. Could add a "send yourself a test message via @TestBot" workflow, but that's heavy. Better path: add a "report incorrect contact" affordance on match cards if this turns out to matter.

### F12-1 — Badges cannot be un-earned
**Raised in:** Feature 12 (badges)
**Issue:** Once a user earns a badge, the earned_at row is locked. If they later opt out of a study group after earning `networker`, the badge stays earned. This is intentional — milestones are about reaching the moment, not maintaining the state — but it means the `earned` flag on subsequent responses might not match the user's current state. Anyone treating badges as a current-state indicator (analytics, perks) would be misled.
**Action:** Document the semantic clearly (done in API.md). Not a fix; an honest limitation. If un-earnable badges become useful, add a new "active" flag separate from "earned ever".

### F12-2 — Badge evaluation runs on the user's first plan only
**Raised in:** Feature 12
**Issue:** Same as F11-1. We use `MIN(id) FROM study_plans` as the user's primary plan. A second plan might have more modules placed, but it doesn't contribute to badge evaluation. Bug-shaped for power users; non-issue for the typical one-plan user.
**Action:** Resolve together with F11-1 when we make `is_active` actually mean something.

### F12-3 — No expiry / one-time celebrations
**Raised in:** Feature 12
**Issue:** The `newly_earned` flag is set on the response where we INSERT the row. If the frontend never sees that response (request fails, user closes tab), they never get the celebration toast. The next request will return `newly_earned: false` and they've silently missed the moment.
**Action:** Acceptable for v1 — the badge IS earned, just not celebrated. A robust fix would persist a `celebrated_at` column separate from `earned_at` and only set `newly_earned: true` until the client confirms it saw it. Overkill for the current product.

### F12-4 — Catalog is hard-coded
**Raised in:** Feature 12
**Issue:** The badge catalog lives in `services/badges.py`. Adding/removing/editing badges requires a code change. Fine for now; if we ever want "seasonal badges" or admin-configurable ones, we'd need a table-driven catalog with the check functions registered by key.
**Action:** Won't fix until use case exists.

### F13-1 — Drag-and-drop on touch is awkward for catalog → semester
**Raised in:** Feature 13 (mobile responsive layout)
**Issue:** dnd-kit's PointerSensor handles touch dragging in principle, but moving a card from the bottom-sheet catalog onto a semester cell requires dragging past the sheet boundary while the sheet stays interactive. In practice this either fights the sheet's scroll or doesn't trigger reliably across all browsers. The mobile flow we support: tap a catalogue card → detail panel opens → "Add to plan" button places it at the default semester; user can then drag-reorder within the grid (which works fine). The cross-region drag isn't blocked, just discouraged.
**Action:** Acceptable for v1 — tap-to-add is faster on mobile anyway. If we wanted "drag" parity, we'd need a long-press handle on each card that suspends the sheet's scroll while active. Defer.

### F13-2 — Mobile bottom tab bar takes vertical space on short viewports
**Raised in:** Feature 13
**Issue:** The bottom tab bar is ~60px (plus safe-area inset on home-indicator iPhones). On a 568px iPhone SE landscape mode, that's >10% of viewport height permanently reserved. We don't hide-on-scroll because the resulting "where did the nav go" confusion isn't worth the few extra pixels.
**Action:** Won't fix. Hide-on-scroll feels janky; the trade-off is honest.

### F13-3 — Single 768px breakpoint is coarse
**Raised in:** Feature 13
**Issue:** Every page uses the same `(max-width: 768px)` boundary. There's no separate treatment for small phones (320–375px) vs large phones (414+) vs portrait tablets (600–768px). Practically the layouts work across all those, but a portrait iPad would benefit from the desktop sidebar treatment with slightly narrower columns — it currently gets the full mobile bottom-tab treatment, which feels under-utilized at 768px.
**Action:** Add a tablet breakpoint (`min-width: 600px and max-width: 1024px`) if real users complain. The simplicity of one breakpoint is worth keeping until then.

### F14-1 — No automated tests for the UX primitives
**Raised in:** Feature 14 (loading/error UX layer)
**Issue:** LoadingState, ErrorState, EmptyState, ErrorBoundary, and the toast system have no unit tests. Manual verification only. Adding React Testing Library would be the right move but introduces a whole test infrastructure (test runner, jsdom, config) that the project doesn't currently have — every other test file is a plain-Python integration test against the backend.
**Action:** When we add any frontend testing (Playwright for e2e, or RTL for component tests), the UX primitives are natural first targets — they're small, pure-render, and side-effect-free. Defer until frontend testing is on the roadmap.

### F14-2 — useAsync doesn't dedupe or cache
**Raised in:** Feature 14
**Issue:** If two components mount at the same time and both call `useAsync(() => api.getPlan(planId))`, they each fire their own fetch. There's no in-flight deduplication and no result caching. Fine for the current app since each page owns its own data, but if we ever have shared data across components (e.g. a header that shows the plan name while the planner also loads it), we'd want SWR/React Query semantics.
**Action:** Introduce SWR or TanStack Query if data-sharing patterns emerge. Until then, useAsync is deliberately minimal — one useCallback+useEffect wrapped, nothing more.

### F14-3 — ErrorBoundary can't recover in-place
**Raised in:** Feature 14
**Issue:** When a component crashes, the ErrorBoundary shows a reload button, not a "try again" button that clears the error state. The class has no `resetErrorBoundary` mechanism. Reasoning: hook state after a crash is usually inconsistent; a re-render often reproduces the crash immediately. A hard reload is the honest recovery.
**Action:** Won't fix unless we see actual cases where in-place recovery is meaningful. `react-error-boundary`'s reset pattern is the reference if we change our mind.

### F14-4 — Toast queue silently drops on overflow
**Raised in:** Feature 14
**Issue:** MAX_VISIBLE = 3. If 5 toasts fire in rapid succession, the oldest 2 get dropped from the visible stack (their timeouts still run harmlessly). No indication to the user that toasts were dropped. In practice we've never seen 3 concurrent toasts in normal usage, but a burst of errors (say, a bad plan that fails validation N times) could hit this.
**Action:** Accept for now. If we start seeing it, either bump the cap or add a "+2 more" indicator on the stack.

### F15-1 — SQLite is single-region
**Raised in:** Feature 15 (deployment)
**Issue:** The Fly.io deployment uses SQLite on a mounted volume in a single region (sin). If we ever need multi-region for latency or availability, SQLite alone can't handle it. Options: LiteFS (SQLite replication) or migrate to Postgres.
**Action:** Not urgent — a study planner for NUS students in Singapore doesn't need geo-distribution. Revisit if the app expands beyond that.

### F15-2 — No automated deploy on merge to main
**Raised in:** Feature 15
**Issue:** CI runs tests but doesn't deploy. Every deploy is a manual `fly deploy` / `vercel deploy` from a dev machine. Manual is safer while the app is young (no failed-deploy panic at 2am from a bad merge), but it does mean deploy velocity is capped by human attention.
**Action:** Add a deploy job to `.github/workflows/ci.yml` gated on main + test success, once we have enough test coverage to trust it. Auth: use `FLY_API_TOKEN` and `VERCEL_TOKEN` secrets in the GH repo.

### F15-3 — Seed data must be applied manually on first deploy
**Raised in:** Feature 15
**Issue:** After `fly deploy` you have to `fly ssh console` and run `python seed.py` once, otherwise the modules and majors tables are empty. This isn't in the `release_command` because running it on every deploy would risk re-seeding / overwriting user data, and detecting "first run" reliably is more complex than the manual step.
**Action:** Leave manual. Document in the runbook (done, in `features/15-deployment/README.md`).

---

## Resolved

### F1-2 — No DB migration framework
**Resolved in:** Feature 15
**How:** `backend/migrations/` directory + `db.apply_migrations()` function. Numbered files, tracked in `schema_migrations` table, applied on app startup (dev) and via `release_command` in fly.toml (prod).

## Won't fix

### F10-3 — Comparison view scales poorly past two plans
**Raised in:** Feature 10
**Why won't fix:** Two-way comparison IS the natural use case. If N-way ever gets requested, a different visualization (heatmap/matrix) would work better than scaling column count.

### F11-4 — Telegram handle isn't verified
**Raised in:** Feature 11
**Why won't fix:** Telegram doesn't offer verification for non-bot handles. A "report incorrect contact" affordance would be the pragmatic mitigation if this ever becomes a real problem.

### F12-4 — Badge catalog is hard-coded
**Raised in:** Feature 12
**Why won't fix:** Admin-configurable catalogs would need a database-driven catalog with the check functions registered by key. Not worth the complexity until we actually want seasonal or dynamic badges.

### F13-2 — Bottom tab bar takes vertical space
**Raised in:** Feature 13
**Why won't fix:** Hide-on-scroll feels janky. The permanent ~60px is an honest trade-off.

### F14-3 — ErrorBoundary can't recover in-place
**Raised in:** Feature 14
**Why won't fix:** React hook state after a crash is usually inconsistent; re-rendering often re-crashes immediately. A hard reload is the honest recovery.
