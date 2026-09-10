"""Settings load from the environment with the right defaults and coercions.

Locks the behaviour that used to live in a hand-rolled ``os.getenv`` block in
``app.utilities.config`` and is now delegated to ``pydantic-settings``.
"""

from __future__ import annotations

import pytest

from app.utilities.config import Settings, get_settings

pytestmark = pytest.mark.no_db


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _settings(monkeypatch, **env: str) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    return get_settings()


def test_defaults(monkeypatch):
    # NB: conftest forces SCREENING_PROVIDER=stub for the whole suite, so that
    # one field is not at its declared default here.
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HF_API_TOKEN", raising=False)
    monkeypatch.delenv("SCREENING_LOG_PROMPTS", raising=False)
    monkeypatch.delenv("SCREENING_CONCURRENCY", raising=False)
    s = _settings(monkeypatch)

    assert s.screening_log_prompts is True
    assert s.cookie_secure is False
    assert s.seed_demo_data is False
    assert s.screening_concurrency == 4
    assert s.screening_detection_backend == "openai_agentic"
    assert s.cors_origins[:1] == ["http://localhost:5173"]


def test_screening_is_live_reads_the_provider(monkeypatch):
    assert _settings(monkeypatch, SCREENING_PROVIDER="live").screening_is_live is True
    assert _settings(monkeypatch, SCREENING_PROVIDER="stub").screening_is_live is False


def test_int_and_bool_are_coerced(monkeypatch):
    s = _settings(
        monkeypatch,
        SCREENING_CONCURRENCY="9",
        SCREENING_LOG_PROMPTS="false",
        COOKIE_SECURE="true",
    )
    assert s.screening_concurrency == 9
    assert s.screening_log_prompts is False
    assert s.cookie_secure is True


def test_hf_api_token_is_accepted_as_a_fallback(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    assert (
        _settings(monkeypatch, HF_API_TOKEN="legacy-token").hf_token == "legacy-token"
    )


def test_hf_token_wins_over_the_fallback(monkeypatch):
    s = _settings(monkeypatch, HF_TOKEN="primary", HF_API_TOKEN="legacy")
    assert s.hf_token == "primary"


def test_empty_hf_token_falls_back(monkeypatch):
    # docker-compose always passes HF_TOKEN through, empty when unset.
    s = _settings(monkeypatch, HF_TOKEN="", HF_API_TOKEN="legacy")
    assert s.hf_token == "legacy"


@pytest.mark.parametrize(
    "bad", ["", "short", "CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32"]
)
def test_boot_refuses_a_weak_secret(monkeypatch, bad):
    monkeypatch.setenv("APP_SECRET_KEY", bad)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="APP_SECRET_KEY"):
        get_settings()
