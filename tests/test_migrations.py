import re
import sys
import types
from pathlib import Path

from core.migrations import MIGRATIONS_DIR


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_run_pending_migrations_skips_without_db_url(monkeypatch, capsys):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    from core.migrations import run_pending_migrations

    run_pending_migrations()

    assert "SUPABASE_DB_URL" in capsys.readouterr().out


def test_run_pending_migrations_applies_sorted_unseen_files(tmp_path, monkeypatch):
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / "002_second.sql").write_text("create table if not exists second_table(id int);", encoding="utf-8")
    (migrations_dir / "001_init.sql").write_text("create table if not exists first_table(id int);", encoding="utf-8")
    (migrations_dir / "ignore.txt").write_text("not sql", encoding="utf-8")

    calls = []

    class FakeCursor:
        def execute(self, sql, params=None):
            calls.append((sql.strip(), params))
            if sql.strip().startswith("select filename"):
                return self
            return self

        def fetchall(self):
            return [("001_init.sql",)]

    class FakeTransaction:
        def __enter__(self):
            calls.append(("BEGIN", None))

        def __exit__(self, exc_type, exc, tb):
            calls.append(("END", None))

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            pass

        def execute(self, sql, params=None):
            return FakeCursor().execute(sql, params)

        def transaction(self):
            return FakeTransaction()

    fake_psycopg = types.SimpleNamespace(connect=lambda url: FakeConnection())
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://example")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")

    import core.migrations as migrations

    monkeypatch.setattr(migrations, "MIGRATIONS_DIR", migrations_dir)

    migrations.run_pending_migrations()

    executed_sql = [sql for sql, _ in calls]
    assert "create table if not exists first_table" not in "\n".join(executed_sql)
    assert "create table if not exists second_table(id int);" in executed_sql
    assert ("insert into schema_migrations (filename) values (%s)", ("002_second.sql",)) in calls


def test_security_migration_enables_rls_on_all_public_tables():
    sql = (MIGRATIONS_DIR / "002_enable_rls.sql").read_text(encoding="utf-8").lower()

    for table in ("profile", "saved_foods", "personalization_cache", "schema_migrations"):
        assert f"alter table public.{table} enable row level security;" in sql


def test_data_api_tables_have_explicit_least_privilege_grants():
    sql = (MIGRATIONS_DIR / "003_data_api_grants.sql").read_text(encoding="utf-8").lower()
    db_source = (PROJECT_ROOT / "core" / "db.py").read_text(encoding="utf-8")
    data_api_tables = set(re.findall(r'\.table\("([a-z_]+)"\)', db_source))
    expected_privileges = {
        "profile": "select, insert, update",
        "saved_foods": "select, insert, update, delete",
        "personalization_cache": "select, insert, update",
    }

    assert data_api_tables == set(expected_privileges)
    for table, privileges in expected_privileges.items():
        assert f"revoke all on table public.{table} from anon, authenticated, service_role;" in sql
        assert f"grant {privileges} on table public.{table} to service_role;" in sql

    assert " to anon" not in sql
    assert " to authenticated" not in sql


def test_migration_metadata_is_not_exposed_through_data_api():
    sql = (MIGRATIONS_DIR / "003_data_api_grants.sql").read_text(encoding="utf-8").lower()

    assert "revoke all on table public.schema_migrations from anon, authenticated, service_role;" in sql
    assert not re.search(r"grant .* public\.schema_migrations .* service_role", sql)


def test_keep_alive_function_is_the_only_anon_grant():
    sql = (MIGRATIONS_DIR / "004_keep_alive.sql").read_text(encoding="utf-8").lower()
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "keepalive.yml").read_text(encoding="utf-8")

    assert "security definer" in sql
    assert "set search_path = ''" in sql
    assert "revoke all on function public.keep_alive() from public, anon, authenticated, service_role;" in sql
    assert re.findall(r"grant .*;", sql) == ["grant execute on function public.keep_alive() to anon;"]
    assert "/rest/v1/rpc/keep_alive" in workflow
