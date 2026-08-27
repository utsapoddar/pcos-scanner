import sys
from types import SimpleNamespace

import pytest

from core.personalize import MODEL, personalize
from core.profile import Profile


PROFILE = Profile(pcos_type="insulin_resistant", insulin_resistance=True)


def _fake_openai(capture_clients, capture_calls, content=None, error=None):
    class FakeCompletions:
        def create(self, **kwargs):
            capture_calls.append(kwargs)
            if error is not None:
                raise error
            message = SimpleNamespace(content=content)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            capture_clients.append(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions())

    return FakeOpenAI


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    """Keep Supabase out of these tests."""
    monkeypatch.setattr("core.personalize.db.get_cached_personalization", lambda *a, **k: None)
    monkeypatch.setattr("core.personalize.db.save_cached_personalization", lambda *a, **k: None)


def test_missing_api_key_falls_back_and_says_so(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setattr("core.personalize.load_dotenv", lambda *a, **k: None)

    result = personalize(4.2, {}, {"name": "Granola Bar"}, PROFILE)

    assert result["adjusted_score"] == 4.2
    assert "NVIDIA API key" in result["reason"]


def test_api_failure_does_not_blame_the_api_key(monkeypatch):
    """A dead model or timeout must not claim the key is missing.

    Regression: an EOL'd model raised, the bare except returned the
    no-key fallback, and the UI told the user to add a key they had.
    """
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=_fake_openai([], [], error=RuntimeError("410 Gone: model end of life"))),
    )

    result = personalize(4.2, {}, {"name": "Granola Bar"}, PROFILE)

    assert result["adjusted_score"] == 4.2
    assert "NVIDIA API key" not in result["reason"]
    assert "unavailable" in result["reason"].lower()


def test_uses_current_model_with_timeout_and_headroom(monkeypatch):
    clients, calls = [], []
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(
            OpenAI=_fake_openai(
                clients,
                calls,
                content='{"adjusted_score": 3.5, "verdict": "Limit", "reason": "High added sugar.",'
                ' "serving": "Half a bar.", "better_swap": "Nuts."}',
            )
        ),
    )

    result = personalize(4.2, {}, {"name": "Granola Bar"}, PROFILE)

    assert result["adjusted_score"] == 3.5
    assert result["verdict"] == "Limit"
    assert calls[0]["model"] == MODEL
    # The retired llama-3.3-70b must not come back.
    assert "llama-3.3-70b" not in MODEL
    # Measured completions run 415-600 chars; 500 tokens truncated them.
    assert calls[0]["max_tokens"] >= 800
    # Without low effort this model reasons until the budget is gone and
    # returns no JSON at all.
    assert calls[0]["reasoning_effort"] == "low"
    # Without these the client inherits the 600s OpenAI default.
    assert clients[0]["timeout"] <= 30
    assert clients[0]["max_retries"] <= 1


def test_cache_read_failure_still_returns_guidance(monkeypatch):
    """A paused Supabase must not take down scoring."""
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    def boom(*a, **k):
        raise RuntimeError("supabase paused")

    monkeypatch.setattr("core.personalize.db.get_cached_personalization", boom)
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(
            OpenAI=_fake_openai(
                [],
                [],
                content='{"adjusted_score": 3.5, "verdict": "Limit", "reason": "High added sugar.",'
                ' "serving": "Half a bar.", "better_swap": "Nuts."}',
            )
        ),
    )

    result = personalize(4.2, {}, {"barcode": "123", "name": "Granola Bar"}, PROFILE)

    assert result["adjusted_score"] == 3.5


def test_cache_write_failure_does_not_discard_a_good_answer(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")

    def boom(*a, **k):
        raise RuntimeError("supabase paused")

    monkeypatch.setattr("core.personalize.db.save_cached_personalization", boom)
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(
            OpenAI=_fake_openai(
                [],
                [],
                content='{"adjusted_score": 3.5, "verdict": "Limit", "reason": "High added sugar.",'
                ' "serving": "Half a bar.", "better_swap": "Nuts."}',
            )
        ),
    )

    result = personalize(4.2, {}, {"barcode": "123", "name": "Granola Bar"}, PROFILE)

    assert result["adjusted_score"] == 3.5
    assert "unavailable" not in result["reason"].lower()
