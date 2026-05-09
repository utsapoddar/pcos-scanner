import sys
import types


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
