"""NUSMods API sync.

Pulls the full NUSMods catalogue (~6000 modules per acad year) into the local DB.

Two endpoints used:
    GET {base}/{year}/moduleList.json                 — list of {moduleCode, title, semesters}
    GET {base}/{year}/modules/{code}.json             — full detail per module

Architecture:
  - Worker threads do HTTP fetching only (CPU-light, network-bound).
  - The main thread reads completed futures and writes to a single SQLite
    connection. This avoids cross-thread SQLite write contention and lets us
    batch commits every N rows for speed.
  - Each HTTP call is wrapped in fetch_with_retry() with exponential backoff
    for 5xx and connection errors. 404s short-circuit (module deprecated).

Usage:
    # From CLI
    flask --app app sync-modules                       # full sync
    flask --app app sync-modules --limit 50            # first 50 only, useful for testing
    flask --app app sync-modules --workers 20          # tune concurrency

    # From Python
    from services.nusmods import sync_all
    success, failed = sync_all(workers=10, on_progress=print)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Iterable

import requests

from config import config
from db import open_conn


# ---------- HTTP layer ----------

def _module_list_url(acad_year: str) -> str:
    return f"{config.NUSMODS_BASE_URL}/{acad_year}/moduleList.json"


def _module_detail_url(acad_year: str, code: str) -> str:
    return f"{config.NUSMODS_BASE_URL}/{acad_year}/modules/{code}.json"


def fetch_module_list(acad_year: str | None = None) -> list[dict]:
    year = acad_year or config.NUSMODS_ACAD_YEAR
    r = requests.get(_module_list_url(year), timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_module_detail(code: str, acad_year: str | None = None) -> dict:
    year = acad_year or config.NUSMODS_ACAD_YEAR
    r = requests.get(_module_detail_url(year, code), timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_with_retry(code: str, acad_year: str | None = None,
                    max_attempts: int = 3, base_delay: float = 1.0) -> dict:
    """Fetch with exponential backoff. 404s short-circuit (no point retrying)."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fetch_module_detail(code, acad_year=acad_year)
        except requests.HTTPError as e:
            # 404 = module doesn't exist this year. Don't retry; let caller log+skip.
            if e.response is not None and e.response.status_code == 404:
                raise
            last_exc = e
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exc = e
        # Backoff before next attempt (skip after final attempt)
        if attempt < max_attempts - 1:
            time.sleep(base_delay * (2 ** attempt))
    # All attempts exhausted
    raise last_exc  # type: ignore[misc]


# ---------- Parsing helpers ----------

def parse_credit(value) -> float:
    """NUSMods returns moduleCredit as a string like "4" or "2.5". Parse safely.

    Returns 0.0 for unparseable values.
    """
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def extract_semesters_offered(semester_data: list[dict] | None) -> list[int]:
    """Pull just the semester numbers from a NUSMods semesterData array.

    semesterData looks like [{"semester": 1, "examDate": "...", ...}, ...]
    """
    if not semester_data:
        return []
    return sorted({s["semester"] for s in semester_data if "semester" in s})


# ---------- DB writes ----------

UPSERT_SQL = """
INSERT INTO modules (
    code, title, description, mcs, department, faculty,
    prereq_tree, prereq_string, preclusion, corequisite, workload,
    semester_data, acad_year, updated_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT(code) DO UPDATE SET
  title         = excluded.title,
  description   = excluded.description,
  mcs           = excluded.mcs,
  department    = excluded.department,
  faculty       = excluded.faculty,
  prereq_tree   = excluded.prereq_tree,
  prereq_string = excluded.prereq_string,
  preclusion    = excluded.preclusion,
  corequisite   = excluded.corequisite,
  workload      = excluded.workload,
  semester_data = excluded.semester_data,
  acad_year     = excluded.acad_year,
  updated_at    = CURRENT_TIMESTAMP
"""


def upsert_module(detail: dict, conn) -> None:
    """Insert or update one module row.

    Caller owns the connection — does NOT commit (so the sync loop can batch).
    """
    code = detail["moduleCode"]
    sem_data = detail.get("semesterData") or []
    prereq_tree = detail.get("prereqTree")

    conn.execute(
        UPSERT_SQL,
        (
            code,
            detail.get("title", ""),
            detail.get("description"),
            parse_credit(detail.get("moduleCredit")),
            detail.get("department"),
            detail.get("faculty"),
            json.dumps(prereq_tree) if prereq_tree else None,
            detail.get("prerequisite"),
            detail.get("preclusion"),
            detail.get("corequisite"),
            json.dumps(detail.get("workload")) if detail.get("workload") else None,
            json.dumps(sem_data) if sem_data else None,
            detail.get("acadYear") or config.NUSMODS_ACAD_YEAR,
        ),
    )


# ---------- Top-level sync ----------

ProgressCallback = Callable[[int, int, int, int], None]
# (processed_so_far, total, successes, failures) — see _default_progress for a printer


def _default_progress(done: int, total: int, ok: int, failed: int) -> None:
    if done == total or done % 50 == 0:
        pct = (done / total * 100) if total else 0
        print(f"  [{done}/{total}] {pct:5.1f}%  ✓{ok}  ✗{failed}", flush=True)


def sync_all(
    workers: int = 10,
    limit: int | None = None,
    acad_year: str | None = None,
    on_progress: ProgressCallback | None = None,
    commit_every: int = 200,
) -> tuple[int, list[tuple[str, str]]]:
    """Full sync. Returns (successes_count, failures_list).

    Args:
        workers: number of concurrent HTTP workers. 10-20 is fine; NUSMods is on Cloudflare.
        limit: process only the first N modules (useful for testing).
        acad_year: override config default.
        on_progress: called after each module with (done, total, ok, failed).
        commit_every: batch DB commits every N rows. Tuning lever — bigger = faster but
                      larger transactions; smaller = safer if you ctrl-C mid-sync.
    """
    progress = on_progress or _default_progress
    year = acad_year or config.NUSMODS_ACAD_YEAR

    print(f"→ Fetching module list for {year}…", flush=True)
    listing = fetch_module_list(year)
    if limit:
        listing = listing[:limit]
    total = len(listing)
    print(f"→ {total} modules to sync (workers={workers})", flush=True)

    success = 0
    failures: list[tuple[str, str]] = []

    conn = open_conn()
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(fetch_with_retry, entry["moduleCode"], year): entry["moduleCode"]
                for entry in listing
            }
            for i, fut in enumerate(as_completed(futures), 1):
                code = futures[fut]
                try:
                    detail = fut.result()
                    upsert_module(detail, conn)
                    success += 1
                except Exception as e:
                    failures.append((code, type(e).__name__ + ": " + str(e)))

                if i % commit_every == 0:
                    conn.commit()
                progress(i, total, success, len(failures))

        conn.commit()
    finally:
        conn.close()

    print(f"\n✓ Sync complete: {success} succeeded, {len(failures)} failed", flush=True)
    if failures:
        print("\nFailed modules (first 20):")
        for code, msg in failures[:20]:
            print(f"  {code}: {msg}")
        if len(failures) > 20:
            print(f"  …and {len(failures) - 20} more")

    return success, failures


def sync_module(code: str, acad_year: str | None = None) -> dict:
    """Sync a single module. Useful for debugging or manual updates.

    Returns the raw detail dict.
    """
    detail = fetch_module_detail(code, acad_year=acad_year)
    conn = open_conn()
    try:
        upsert_module(detail, conn)
        conn.commit()
    finally:
        conn.close()
    return detail


# ---------- CLI ----------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m services.nusmods",
        description="NUSMods catalogue sync",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Full catalogue sync")
    sync.add_argument("--workers", type=int, default=10, help="concurrent HTTP workers (default 10)")
    sync.add_argument("--limit", type=int, default=None, help="cap on modules synced (for testing)")
    sync.add_argument("--year", type=str, default=None, help="override acad year e.g. 2024-2025")

    one = sub.add_parser("sync-one", help="Sync a single module by code")
    one.add_argument("code", type=str, help="e.g. CS2030S")
    one.add_argument("--year", type=str, default=None)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    if args.command == "sync":
        success, failures = sync_all(
            workers=args.workers,
            limit=args.limit,
            acad_year=args.year,
        )
        return 0 if not failures else 1

    if args.command == "sync-one":
        try:
            detail = sync_module(args.code, acad_year=args.year)
            print(f"✓ Synced {detail['moduleCode']}: {detail.get('title')}")
            return 0
        except Exception as e:
            print(f"✗ Failed: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
