# NUS Study Planner

A four-year academic planner for NUS undergrads. Flask + SQLite backend, React + Vite frontend.

## Project layout

```
backend/
  app.py                  Flask app factory, blueprint registration, /api/health, boot-time migrations
  migrations/             Numbered SQL migration files (001_initial.sql, 002_...)
  migrate.py              CLI: `python migrate.py apply | status`
  seed.py                 Applies migrations + populates sample data
  routes/                 Thin HTTP adapters — auth + parse + delegate
  services/               Pure-function business logic (testable without DB)
  tests/                  18 test files, each runnable directly via python
  Dockerfile              Production image (gunicorn, non-root user, /data mount)
  fly.toml                Fly.io app config (Singapore region, volume mount, release_command)
frontend/
  src/App.jsx             Router + nav (top bar desktop, bottom tabs mobile) + ErrorBoundary + ToastProvider
  src/pages/              One file per top-level route
  src/components/         Shared UI (ModuleDetailPanel, ShareDialog)
  src/components/ui/      Feature 14 primitives: LoadingState, ErrorState, EmptyState, ErrorBoundary
  src/api/client.js       Single fetch wrapper, all endpoints in one object
  src/hooks/              useAppAuth, useMediaQuery, useIsMobile, useAsync
features/                 One folder per feature with a README explaining what + why
features/FLAGS.md         Running log of known limitations
API.md                    HTTP contract
.github/workflows/ci.yml  CI: backend tests + frontend build on every push/PR
```

## How to run

```bash
# Backend (port 5000)
cd backend
pip install -r requirements.txt
rm -f planner.db && python seed.py
flask --app app run --debug

# Frontend (port 5173)
cd frontend
npm install
npm run dev

# Full test sweep — runs every file, ~20s
cd backend && rm -f planner.db
for f in tests/test_*.py; do python "$f" || break; done
rm -f planner.db
```

Dev auth shortcut: any `Authorization: Bearer dev-user-<id>` header works without Clerk. Used by all tests and useful for curl experiments.

## Architecture conventions

**Backend separation.** Routes are thin: auth, parse request, call a service, jsonify the result. All real logic lives in `services/` as pure functions that don't touch Flask. This is why tests targeting services don't need a test client. When adding a feature, default to writing a service first and a route that wraps it.

**Schema changes go in a migration file.** Since Feature 15, `backend/migrations/` holds numbered SQL files (`001_initial.sql`, `002_XXX.sql`, …). Each schema-touching feature adds a new file. `db.apply_migrations()` runs any un-applied files in filename order, tracked in a `schema_migrations` table. Runs automatically on app startup (dev) and via `fly.toml`'s `release_command` (prod). Fresh dev DBs come up via `python seed.py`, which applies migrations then inserts seed data. F1-2 is resolved. See `backend/migrations/README.md` for the convention.

**Frontend uses inline styles with CSS variables.** The design system is in `src/styles.css` as CSS custom properties (`--paper`, `--ink`, `--accent`, `--warn`, etc.) plus two utility classes (`font-display` for Fraunces serif, `font-mono` for JetBrains Mono). Everything else is inline style objects. Don't introduce a CSS-in-JS library or Tailwind — the inline pattern is consistent throughout.

**Shared UX primitives** (added in Feature 14, in `src/components/ui/` and `src/hooks/`):
- `<LoadingState size="small|medium|large" label="…" />` — the only way to render a spinner. Don't inline `<Loader2 />` for page/section loads.
- `<ErrorState error={e} onRetry={fn} size="inline|page" />` — the only way to render an error box.
- `<EmptyState icon={Icon} title="…" hint="…" action={{label, onClick}} />` — for "nothing here yet".
- `<ErrorBoundary>` wraps `<Routes>` in App.jsx — catches component crashes.
- `useToast()` returns `{ showToast, showError, showSuccess, showInfo }`. Prefer over `alert()` (which shouldn't exist anywhere) and prefer over local toast state.
- `useAsync(asyncFn, deps)` returns `{ data, loading, error, refetch }` for one-shot fetches on mount/deps-change. Not for button-click mutations.

**Mobile responsiveness via `useIsMobile()` hook.** Single breakpoint at 768px. Pages conditionally swap layouts (e.g. `gridTemplateColumns: isMobile ? '1fr' : '300px 1fr'`). Bottom tab bar on mobile, top nav on desktop. Backend is identical for both.

## Test pattern

Every test file is a standalone Python script — no pytest, no test runner. Pattern:

```python
def _setup_temp_db():
    fd, path = tempfile.mkstemp(suffix=".db"); os.close(fd)
    original = config.DATABASE_PATH
    config.DATABASE_PATH = path
    from db import init_db
    init_db(schema_path="schema.sql")
    import importlib, seed; importlib.reload(seed); seed.seed()
    from app import create_app
    return create_app(), path, original
```

Each test function calls `_setup_temp_db()`, exercises the API, and `_teardown()` in a `finally`. The `assert_eq(actual, expected, label)` helper prints a `✓`/`✗` line so test output is readable when run standalone. At the bottom: `if __name__ == "__main__": run every test function, print "All tests passed ✓"`.

When adding a feature: write a unit test file for any pure service (e.g. `test_badges.py`) and an integration test for the route (`test_badges_route.py`). 13 features have followed this and it works well.

## The "flags" pattern

When you hit a non-ideal trade-off (missing migration framework, scoring weights pulled from feel, comparison view that only works for two plans, etc.), record it in `features/FLAGS.md` rather than papering over it. Each entry has Raised-in / Issue / Action — Action is what we'd do to fix it, and is often "won't fix" or "defer until usage data exists". 34 flags are currently open; they're the running list of known limitations, deliberately surfaced rather than hidden.

When considering whether something needs a flag: would a future engineer reading this code think "wait, why?" or "is this a bug?" If yes, it deserves a flag entry explaining the trade-off was conscious.

## Per-feature documentation

Every feature ships with `features/NN-feature-name/README.md`. The shape:
- **Goal** — one paragraph
- **What changed** — files modified, grouped Backend / Frontend / Schema
- **How to test** — curl examples + UI walkthrough
- **Design notes** — bullet list of decisions and why
- **Flags raised** — links to FLAGS.md entries
- **What's not done (deferred)** — things considered and skipped, with rationale

When adding the next feature (14: loading/error UX layer; 15: deployment), follow this shape. The READMEs are how the project explains itself to future-you.

## Remaining work

All 15 planned features are complete. Iteration from here — bug fixes, tuning based on real usage, resolving flags as they turn from theoretical to actual, or building new features on top of the platform.

Consider these next steps if you want directions:

- **Sync real NUSMods data** (F1-1). The catalogue sync code has never been run against the real API. `flask sync-modules` from a shell inside the deployed VM (`fly ssh console`) is the path.
- **Automate deploy on merge** (F15-2). Add a deploy job to `.github/workflows/ci.yml` when confidence in the tests is high.
- **Enable rate limiting** before opening to public users. Flask-Limiter is a small add.
- **Error tracking** via Sentry or similar — the ErrorBoundary logs to console, which nobody reads in prod.
- **Backup the SQLite volume** on a schedule once real user data exists.

## Deployment

Backend deploys to Fly.io, frontend to Vercel. Full runbook in `features/15-deployment/README.md`. Quick reference:

```bash
# Backend
cd backend && fly deploy   # runs migrations via release_command, then rolls new instances

# Frontend
cd frontend && vercel --prod
```

Env vars are set via `fly secrets set` and `vercel env add`. Never commit real secrets — `.env.example` files document the required keys.

## What lives in API.md

Full endpoint contract: request shapes, response shapes, error codes. Update it any time you add or change a route. Mobile (Feature 13) made no API changes; backend test files don't enforce the doc, but the convention is "if you'd be annoyed by an undocumented endpoint as a consumer, document it."

## Code style notes

- Backend: standard PEP 8, type hints on new code, docstrings on services explaining the "why" (not just the "what").
- Frontend: functional components, hooks, no class components. Destructure props at the top. Keep components in the same file unless they're reused.
- Comments earn their keep by explaining decisions, not narrating the code. "Excludes target module from overlap because having THIS module in common is what brought us here" is useful; "loop over candidates" is not.
- Error messages aimed at the user, not the developer. The frontend displays `error.message` directly in many places.
