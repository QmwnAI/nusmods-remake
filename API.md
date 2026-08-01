# API Contract

Base URL: `http://localhost:5000/api`

All endpoints except `/health` require an `Authorization: Bearer <token>` header.

In **dev mode** (default), any token of the form `dev-user-<id>` is accepted and resolves to that user. Example:

```bash
curl -H "Authorization: Bearer dev-user-alice" http://localhost:5000/api/me
```

In **production mode**, set `CLERK_SECRET_KEY` and the backend will verify Clerk JWTs.

---

## Conventions

- All requests and responses are JSON.
- Errors return `{ "error": "human readable", "code": "MACHINE_READABLE" }` with appropriate 4xx/5xx status.
- Timestamps are ISO 8601 UTC.
- Module codes are uppercase strings (`CS2030S`).
- Semester IDs are `Y{1-4}S{1-2}` (e.g. `Y2S1`).
- Grades are one of: `A+ A A- B+ B B- C+ C D+ D F`.

---

## Auth & user

### `GET /api/health`
No auth. Returns `{"status": "ok"}`.

### `POST /api/auth/sync`
Called by the frontend after Clerk login. Idempotent; creates the user row if missing.

**Body:** `{ "email": "...", "display_name": "..." }`
**Returns:** `User`

### `GET /api/me`
Returns the current user.

### `PUT /api/me`
Update profile (major, matric year).

**Body:** `{ "major_code": "CS", "matric_year": 2024 }`

---

## Modules

### `GET /api/modules?q=&category=&limit=50`
List modules with optional search and category filter.

**Returns:** `{ "modules": Module[], "total": number }`

### `GET /api/modules/:code`
Module detail including parsed prereq tree, usage statistics across all users, and reverse-prereq lookups (modules that require this one).

**Returns:**
```json
{
  "code": "CS2030S",
  "title": "Programming Methodology II",
  "description": "...",
  "mcs": 4,
  "prereq_tree": {"and": ["CS1101S", "CS1231S"]},
  "prereq_string": "CS1101S and CS1231S",
  "preclusion": "CS2030, CS2030DE",
  "corequisite": null,
  "workload": [2, 1, 0, 2, 5],
  "semester_data": [...],
  "semesters_offered": [1, 2],
  "stats": {
    "placement_count": 142,
    "by_semester": {"Y1S2": 90, "Y2S1": 30, "Y1S1": 12}
  },
  "unlocks": [
    {"code": "CS2103T", "title": "Software Engineering", "mcs": 4}
  ]
}
```

---

## Degree requirements

### `GET /api/requirements?major=CS`
Returns the requirement structure for a major. Used to render the progress tracker and validate completion.

**Returns:** `Requirement[]`

```json
[
  {
    "category": "FOUNDATION",
    "label": "CS Foundation",
    "required_mcs": 24,
    "modules": ["CS1101S", "CS1231S", "CS2030S", "CS2040S", "CS2100", "CS2103T"]
  }
]
```

---

## Majors

### `GET /api/majors`
List all degree programs. Used by onboarding's major picker.

**Returns:**
```json
[
  {
    "code": "CS",
    "name": "Bachelor of Computing (Computer Science)",
    "faculty": "School of Computing",
    "total_mcs": 128,
    "acad_year": "2024-2025",
    "requirements_count": 6
  }
]
```

### `GET /api/majors/:code`
Get one major with its requirement buckets expanded.

**Returns:**
```json
{
  "code": "CS",
  "name": "Bachelor of Computing (Computer Science)",
  "faculty": "School of Computing",
  "total_mcs": 128,
  "requirements": [
    { "category": "FOUNDATION", "label": "CS Foundation", "required_mcs": 24 }
  ]
}
```

---

## Study plans

### `GET /api/plans`
List the user's plans (most will only have one).

### `POST /api/plans`
Create a plan.

**Body:** `{ "name": "My Plan" }`

### `GET /api/plans/:id`
Get a plan with all its entries.

**Returns:**
```json
{
  "id": 1,
  "name": "My Plan",
  "user_id": "user_xyz",
  "entries": [
    {
      "id": 12,
      "module_code": "CS2030S",
      "semester_id": "Y1S2",
      "grade": "A-",
      "is_su": false,
      "is_completed": false
    }
  ]
}
```

### `PUT /api/plans/:id`
Update plan metadata (name).

### `DELETE /api/plans/:id`
Delete plan and all entries.

---

## Plan entries (the drag-and-drop target)

### `POST /api/plans/:id/entries`
Add a module to a semester. Returns 409 if the module is already in this plan.

**Body:** `{ "module_code": "CS2030S", "semester_id": "Y1S2" }`

### `PUT /api/plans/:id/entries/:entryId`
Update an entry — move semester, set grade, toggle S/U, mark completed.

**Body (all fields optional):**
```json
{
  "semester_id": "Y2S1",
  "grade": "A",
  "is_su": false,
  "is_completed": true
}
```

### `DELETE /api/plans/:id/entries/:entryId`
Remove a module from the plan.

---

## Computed views

### `GET /api/plans/:id/progress`
Returns rich progress detail including which modules count toward each bucket, what's eligible-but-not-placed, projected completion, and any modules that don't fit any requirement.

**Returns:**
```json
{
  "major_code": "CS",
  "total": {
    "placed_mcs": 84,
    "completed_mcs": 60,
    "required_mcs": 128,
    "percent_placed": 65.6,
    "percent_completed": 46.9
  },
  "projected_completion": { "semester_id": "Y3S2", "year": 3, "sem": 2 },
  "by_category": [
    {
      "category": "FOUNDATION",
      "label": "CS Foundation",
      "required": 24,
      "placed_mcs": 16,
      "completed_mcs": 12,
      "complete": false,
      "placed_modules": [
        { "code": "CS1101S", "mcs": 4, "completed": true,  "grade": "A" },
        { "code": "CS1231S", "mcs": 4, "completed": false, "grade": "F" }
      ],
      "eligible_not_placed": [
        { "code": "CS2030S", "title": "Programming Methodology II", "mcs": 4 }
      ],
      "eligible_not_placed_total": 4
    }
  ],
  "unallocated_modules": [
    { "code": "BT2102", "title": "...", "mcs": 4, "semester_id": "Y2S1", "grade": null }
  ]
}
```

Notes:
- `placed_mcs` counts every entry; `completed_mcs` excludes ungraded entries AND F-graded entries.
- `eligible_not_placed` is capped at 8 items; `eligible_not_placed_total` reports the full count.
- "Open" buckets (categories with no `requirement_modules` mapping — e.g. UE) absorb leftover placed modules in display order, filling earlier buckets first.
- `unallocated_modules` lists anything still uncategorised after open buckets fill up. Usually empty.

### `GET /api/plans/:id/gpa`
Computes pre-S/U and post-S/U CAP from graded entries.

**Returns:**
```json
{
  "pre_su": { "cap": 4.52, "mcs": 48 },
  "post_su": { "cap": 4.67, "mcs": 40 },
  "su_used_mcs": 8
}
```

### `GET /api/plans/:id/gpa/target?cap=4.5&remaining_mcs=40`
Compute the required average grade-points across remaining ungraded MCs to hit a target CAP.

Query params:
- `cap` (required): target CAP, e.g. `4.5`
- `remaining_mcs` (optional): override the auto-counted ungraded MCs

**Returns:**
```json
{
  "target_cap": 4.5,
  "current_cap": 4.0,
  "current_mcs": 16,
  "remaining_mcs": 40,
  "required_avg_gp": 4.7,
  "achievable": true,
  "note": "You need an average of 4.70 GP across your remaining 40 MCs to reach 4.50."
}
```

If unreachable (would require above-A grades), `achievable` is false and the note explains.

### `GET /api/plans/:id/gpa/su-advice?budget_mcs=32`
Greedy recommendation of which graded modules to S/U for biggest CAP gain.

Query params:
- `budget_mcs` (optional, default 32): MCs of S/U budget remaining

**Returns:**
```json
{
  "current_cap": 3.5,
  "projected_cap": 4.2,
  "mcs_used": 8,
  "budget_mcs": 32,
  "recommended": [
    { "module_code": "GEH1036", "mcs": 4, "grade": "D",  "grade_points": 1.0, "cap_before": 3.5, "cap_after": 3.9, "delta": 0.4 },
    { "module_code": "MA1521",  "mcs": 4, "grade": "C+", "grade_points": 2.5, "cap_before": 3.9, "cap_after": 4.2, "delta": 0.3 }
  ]
}
```

If no S/U would help (all graded modules are at or above the current average), `recommended` is empty.

### `POST /api/plans/:id/gpa/scenario`
Apply hypothetical grade/S-U overrides and recompute CAP, without persisting anything.

**Body:**
```json
{
  "overrides": {
    "12": {"grade": "A"},
    "15": {"is_su": true},
    "18": {"grade": null}
  }
}
```
Keys are plan entry IDs (as integers or strings). Any field in the value object can be omitted; `grade: null` clears.

**Returns:** same shape as `GET /gpa` plus a `changes_applied` count.

### `GET /api/plans/:id/validate`
Returns all validation issues for the plan, in typed form. Five kinds of issue:

- **PREREQ_UNMET** — module placed before its prerequisites
- **COREQ_UNMET** — module placed without its corequisite in the same or earlier semester
- **PRECLUSION** — two modules in the plan that preclude each other (pair-shaped)
- **NOT_OFFERED** — module placed in a semester it isn't offered in
- **EXAM_CLASH** — two modules in the same plan semester whose final-exam windows overlap (pair-shaped)

**Returns:**
```json
{
  "issues": [
    {
      "kind": "PREREQ_UNMET",
      "entry_id": 12,
      "module_code": "CS2030S",
      "semester_id": "Y1S1",
      "unmet": "CS1101S",
      "message": "needs CS1101S earlier"
    },
    {
      "kind": "COREQ_UNMET",
      "entry_id": 18,
      "module_code": "CS2103T",
      "semester_id": "Y2S1",
      "unmet": "CS2101",
      "message": "needs CS2101 this semester or earlier"
    },
    {
      "kind": "PRECLUSION",
      "module_code_a": "CS2030",
      "entry_id_a": 4,
      "semester_id_a": "Y1S2",
      "module_code_b": "CS2030S",
      "entry_id_b": 5,
      "semester_id_b": "Y2S1",
      "message": "CS2030 and CS2030S can't both be in your plan"
    },
    {
      "kind": "NOT_OFFERED",
      "entry_id": 22,
      "module_code": "CS3216",
      "semester_id": "Y2S2",
      "offered_in": [1],
      "message": "not offered in Semester 2; only in Semester 1"
    },
    {
      "kind": "EXAM_CLASH",
      "semester_id": "Y1S2",
      "module_code_a": "CS2030S",
      "entry_id_a": 11,
      "exam_start_a": "2025-04-29T09:00:00+08:00",
      "module_code_b": "CS2040S",
      "entry_id_b": 14,
      "exam_start_b": "2025-04-29T09:00:00+08:00",
      "message": "CS2030S and CS2040S have overlapping exams in Y1S2"
    }
  ],
  "violations": [
    // Back-compat: prereq violations only, in the original (pre-F5) shape.
    { "entry_id": 12, "module_code": "CS2030S", "semester_id": "Y1S1", "unmet": "CS1101S" }
  ]
}
```

### `GET /api/plans/:id/ready-modules?semester_id=Y2S1&limit=50`
Returns modules whose prerequisites are met by everything placed in strictly earlier semesters, that aren't already in the plan, and that are offered in the target semester.

Useful for filling out a half-empty semester or finding electives that "unlock" early.

**Returns:**
```json
{
  "modules": [
    { "code": "CS2106", "title": "Operating Systems", "mcs": 4, "semesters_offered": [1, 2] }
  ],
  "total": 23
}
```

---

## Recommendations

### `GET /api/recommendations/ues?plan_id=<id>&limit=<n>`
Returns ranked UE recommendations. Ranking combines:
- **Collaborative filtering** — users whose plans look like yours weight more.
- **Major cohort** — same-major users get a bonus on top of overlap.
- **Eligibility** — modules whose prereqs aren't met by your placed modules are filtered out.
- **Diversity** — soft penalty per duplicate department in the top-N to avoid clustering.

Query params:
- `plan_id` (optional): the plan to use as context. Defaults to no plan (pure popularity).
- `limit` (optional, default 5, max 20): number of recommendations.

**Returns:**
```json
{
  "modules": [
    {
      "code": "CS3216",
      "title": "Software Product Engineering",
      "mcs": 5,
      "department": "CS",
      "score": 2.193,
      "placement_count": 3,
      "similar_user_count": 3,
      "reasons": ["taken by 3 users with similar plans"]
    }
  ]
}
```

Notes:
- `score` is a relative ranking score, not a probability. Compare within a single response, not across.
- `placement_count` is the raw count across all *other* users' plans.
- `similar_user_count` is the subset of those whose Jaccard overlap with the current user exceeds the threshold.
- `reasons` is an array; the first is the primary explanation, subsequent entries may include diversity notes.

---

## Plan sharing

### `POST /api/plans/:id/share`
Share a plan you own with another user.

**Body:** one of:
```json
{ "user_id": "dev-user-bob", "include_grades": false }
{ "email":   "bob@nus.example.com", "include_grades": true }
```

`include_grades` defaults to `false`. Email lookup is case-insensitive. Re-sharing with the same recipient is allowed and updates the `include_grades` flag (UPSERT, not duplicate row).

Sharing with yourself returns 400. Sharing with an unknown user returns 404 with code `USER_NOT_FOUND`.

**Returns (201):**
```json
{
  "id": 12,
  "plan_id": 3,
  "shared_with": {
    "user_id": "dev-user-bob",
    "email": "bob@nus.example.com",
    "display_name": "Bob"
  },
  "include_grades": true,
  "created_at": "2026-01-15 09:00:00"
}
```

### `GET /api/plans/:id/shares`
List current shares of a plan. Owner only — non-owners get 404.

**Returns:**
```json
{
  "shares": [
    {
      "id": 12,
      "plan_id": 3,
      "include_grades": true,
      "created_at": "2026-01-15 09:00:00",
      "shared_with": { "user_id": "...", "email": "...", "display_name": "..." }
    }
  ]
}
```

### `DELETE /api/plans/:id/shares/:shareId`
Revoke a share. Owner only.

### `GET /api/shared-with-me`
Plans shared with the current user, ordered by `shared_at` desc.

**Returns:**
```json
{
  "plans": [
    {
      "share_id": 12,
      "plan_id":  3,
      "plan_name": "My Plan",
      "include_grades": true,
      "shared_at": "2026-01-15 09:00:00",
      "owner": {
        "user_id": "dev-user-alice",
        "email":   "alice@nus.example.com",
        "display_name": "Alice",
        "major_code": "CS"
      }
    }
  ]
}
```

### `GET /api/plans/:id` (extended)
Now accepts requests from non-owners IF a share row exists. The response includes:
- `access`: `"owner"` or `"shared"`
- `include_grades`: bool — true for owner, mirror of share row for shared reads
- `entries[]`: when `include_grades` is false, each entry omits `grade`, `is_su`, `is_completed`, `notes`

Non-recipients still get a 404 with the same `NOT_FOUND` code as a truly missing plan, so the endpoint doesn't leak which plan IDs exist.

Comparison itself is computed client-side: fetch your plan and the shared plan, then diff their entries by `module_code`. No `/compare` endpoint — simpler than another route and the data volumes are tiny.

---

## Study groups

Opt-in matching for finding study partners taking the same module in the same plan semester.

### `POST /api/study-groups/optin`
Opt into a (module, semester) so other users see you.

**Body:**
```json
{ "module_code": "CS2103T", "semester_id": "Y2S2", "message": "Looking for group of 3-4" }
```

`message` is optional. Returns `201` on success, `409 DUPLICATE` if already opted in for that (module, semester).

### `PUT /api/study-groups/optin/:id`
Update the message on one of your opt-ins. Only `message` is editable.

**Body:** `{ "message": "Updated note" }` (empty string clears).

### `DELETE /api/study-groups/optin/:id`
Withdraw your opt-in. Owner only.

### `GET /api/study-groups/matches?module_code=&semester_id=`
Returns other users opted into the same (module, semester), ranked by compatibility. Compatibility scoring combines: same major (+25), same matric year (+20), plan overlap on non-target modules (up to +30 × Jaccard), recency (+5 in last week). Score capped at 100.

**Returns:**
```json
{
  "matches": [
    {
      "user_id": "dev-user-bob",
      "display_name": "Bob",
      "email": "bob@nus.example.com",
      "major_code": "CS",
      "matric_year": 2024,
      "contact_telegram": "bob_nus",
      "optin_id": 14,
      "message": "Looking for someone serious",
      "optin_created_at": "2026-06-10 09:00:00",
      "score": 75,
      "reasons": ["Same major (CS)", "Same matric year (2024)", "3 other modules in common"],
      "same_major": true,
      "same_year": true,
      "plan_overlap_count": 3,
      "recent": false
    }
  ]
}
```

Excludes the requesting user from results. The target module is excluded from the overlap signal (having THIS module in common is what brought you here — it shouldn't count as a bonus).

### `GET /api/study-groups/my-optins`
List your own opt-ins, each annotated with `others_count` — how many other users are interested in the same (module, semester). Used by the "Your signups" panel for managing what you've opted into.

**Returns:**
```json
{
  "optins": [
    {
      "id": 12,
      "module_code": "CS2030S",
      "module_title": "Programming Methodology II",
      "semester_id": "Y1S2",
      "message": "DM if forming a group",
      "created_at": "2026-06-08 14:30:00",
      "others_count": 3
    }
  ]
}
```

### `PUT /api/me` (extended)
Now also accepts `contact_telegram` (optional). Stored without the `@` prefix; surfaced on match cards when the user has opted to share it.

---

## Badges

### `GET /api/badges`
Evaluate the user's current state against the badge catalog, persist any newly-earned badges to the `earned_badges` table, and return the full catalog with per-badge earned status.

The endpoint is read-most-of-the-time (idempotent on its observable effects after the first earn) — repeat calls after a badge is earned just return `newly_earned: false`. There's no separate "evaluate then read" split; one endpoint does both.

**Returns:**
```json
{
  "badges": [
    {
      "key": "first-module",
      "title": "First Module",
      "description": "Place your first module anywhere in the planner.",
      "tier": "Building",
      "earned": true,
      "earned_at": "2026-06-12 09:30:00",
      "newly_earned": true
    },
    {
      "key": "engaged-grader",
      "title": "Engaged Grader",
      "description": "Record grades for 5 or more modules.",
      "tier": "Tracking",
      "earned": false,
      "earned_at": null,
      "newly_earned": false
    }
  ],
  "earned_count": 4,
  "total_count": 10
}
```

The frontend should use `newly_earned` to trigger a celebration on this response — by the next request the flag will be false.

**Tiers and behaviour:**
- `Building` — plan structure (place modules, fill semesters, near graduation)
- `Tracking` — engagement with grades and S/U
- `Community` — sharing and study-group participation

**Earned timestamp:** locked at first earn. Re-evaluating the same badge later returns the same `earned_at`. Badges cannot be un-earned even if the underlying state changes (e.g. user opts out of a study group after earning `networker`).

---

## Type reference

```ts
type User = {
  id: string;
  email: string;
  display_name: string | null;
  major_code: string | null;
  matric_year: number | null;
};

type Module = {
  code: string;
  title: string;
  mcs: number;
  description: string | null;
  prereq_tree: PrereqNode | null;  // recursive {and: [...]} | {or: [...]} | string
  prereq_string: string | null;
};

type PrereqNode = string | { and: PrereqNode[] } | { or: PrereqNode[] };

type Requirement = {
  category: string;
  label: string;
  required_mcs: number;
  modules: string[];
};
```
