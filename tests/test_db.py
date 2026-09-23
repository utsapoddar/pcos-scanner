import sys
import types


def test_client_uses_service_role_key(monkeypatch):
    captured = {}

    def create_client(url, key):
        captured.update(url=url, key=key)
        return object()

    monkeypatch.setitem(sys.modules, "supabase", types.SimpleNamespace(create_client=create_client))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")

    import core.db as db

    monkeypatch.setattr(db, "_SUPABASE_CLIENT", None)
    db._client()

    assert captured == {
        "url": "https://example.supabase.co",
        "key": "service-role-key",
    }
