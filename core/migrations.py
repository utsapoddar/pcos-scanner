"""Tiny SQL migration runner for Supabase Postgres."""

from __future__ import annotations

import os
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"

_SCHEMA_MIGRATIONS_SQL = """
create table if not exists schema_migrations (
    filename text primary key,
    applied_at timestamptz not null default now()
)
"""


def run_pending_migrations() -> None:
    """Run unapplied SQL files from migrations/ in lexicographic order."""
    db_url = os.getenv("SUPABASE_DB_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not db_url:
        print("Warning: SUPABASE_DB_URL is not set; skipping Supabase migrations.")
        return
    if not service_role_key:
        print("Warning: SUPABASE_SERVICE_ROLE_KEY is not set; skipping Supabase migrations.")
        return

    import psycopg

    sql_files = sorted(path for path in MIGRATIONS_DIR.glob("*.sql") if path.is_file())

    with psycopg.connect(db_url) as conn:
        conn.execute(_SCHEMA_MIGRATIONS_SQL)
        rows = conn.execute("select filename from schema_migrations").fetchall()
        applied = {row[0] for row in rows}

        for path in sql_files:
            if path.name in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            with conn.transaction():
                conn.execute(sql)
                conn.execute("insert into schema_migrations (filename) values (%s)", (path.name,))
