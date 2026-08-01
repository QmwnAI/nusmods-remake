"""Migration CLI.

Usage:
    python migrate.py apply       # apply un-applied migrations
    python migrate.py status      # show which migrations are applied

For local dev: `python seed.py` already applies migrations before inserting
seed data, so you rarely need to run this by hand.

For production: run `python migrate.py apply` as part of the release
process, before starting the app. On Fly.io this can go in a `release_command`
in fly.toml so migrations run automatically on every deploy.
"""
from __future__ import annotations
import sys

from db import apply_migrations, connect


def cmd_apply() -> int:
    applied = apply_migrations()
    if applied:
        print(f"Applied {len(applied)} migration(s):")
        for name in applied:
            print(f"  ✓ {name}")
    else:
        print("Already up to date.")
    return 0


def cmd_status() -> int:
    with connect() as conn:
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(filename TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
        )
        rows = conn.execute(
            "SELECT filename, applied_at FROM schema_migrations ORDER BY filename"
        ).fetchall()
    if not rows:
        print("No migrations applied yet.")
        return 0
    print(f"{len(rows)} migration(s) applied:")
    for r in rows:
        print(f"  {r['filename']}  ({r['applied_at']})")
    return 0


COMMANDS = {"apply": cmd_apply, "status": cmd_status}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: python migrate.py [{'|'.join(COMMANDS)}]", file=sys.stderr)
        return 1
    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
