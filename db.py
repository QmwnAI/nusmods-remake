"""SQLite helper. Thin wrapper around sqlite3 — no ORM.

Usage:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM modules WHERE code = ?", (code,)).fetchall()

`get_db()` returns a request-scoped connection inside Flask routes.

Migrations: production and tests both use `apply_migrations()`, which reads
`backend/migrations/*.sql` in filename order, tracks what's been applied in a
`schema_migrations` table, and applies un-applied files exactly once. See
`migrations/README.md` for the convention.
"""
import os
import sqlite3
from contextlib import contextmanager
from flask import g, current_app
from config import config


def _connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connect():
    """Standalone connection — use in scripts (seed.py, sync jobs)."""
    conn = _connect(config.DATABASE_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def open_conn() -> sqlite3.Connection:
    """Open a raw connection (caller owns commit/close).

    Use when you need fine-grained control over commit batching — e.g. a long
    sync job that wants to commit every N rows rather than once at the end.
    """
    return _connect(config.DATABASE_PATH)


def get_db() -> sqlite3.Connection:
    """Request-scoped connection — use in Flask routes."""
    if "db" not in g:
        g.db = _connect(current_app.config["DATABASE_PATH"])
    return g.db


def close_db(_=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---------- migrations ----------

_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename    TEXT PRIMARY KEY,
  applied_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _default_migrations_dir() -> str:
    """Locate the migrations directory relative to this file."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")


def apply_migrations(migrations_dir: str | None = None) -> list[str]:
    """Apply un-applied migration files in filename order.

    Migration files: `backend/migrations/NNN_description.sql` (e.g. `001_initial.sql`,
    `002_add_something.sql`). Filenames sort correctly with lexicographic order as
    long as we use zero-padded numeric prefixes.

    Each file runs as one transaction. If it fails midway, the transaction rolls
    back and the migration is NOT recorded in `schema_migrations`, so the same
    file will be re-tried on the next run. SQLite doesn't support transactional
    DDL in every case (some ALTER TABLE variants can't be rolled back), so the
    convention is: one logical change per migration, keep them small.

    Returns the list of migration filenames that were applied on THIS run
    (empty if the DB was already up to date).
    """
    directory = migrations_dir or _default_migrations_dir()
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Migrations directory not found: {directory}")

    files = sorted(f for f in os.listdir(directory) if f.endswith(".sql"))
    applied: list[str] = []

    with connect() as conn:
        conn.executescript(_MIGRATIONS_TABLE_SQL)
        already_applied = {
            row["filename"]
            for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
        }

        for filename in files:
            if filename in already_applied:
                continue
            path = os.path.join(directory, filename)
            with open(path, encoding="utf-8") as f:
                sql = f.read()
            # executescript commits any open transaction and starts a new one
            # per its own semantics. For our purposes each migration file is a
            # unit; failure aborts and the outer connect() context re-raises.
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (?)",
                (filename,),
            )
            applied.append(filename)
    return applied


def init_db(schema_path: str | None = None) -> None:
    """Legacy shim. Now equivalent to `apply_migrations()`.

    `schema_path` is accepted for backwards compatibility with older test
    setups that passed `schema.sql` explicitly — the argument is ignored and
    we always apply migrations from the standard directory.
    """
    apply_migrations()


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()} if row else None
