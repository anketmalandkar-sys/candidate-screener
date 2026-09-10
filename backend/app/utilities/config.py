"""Application configuration.

Every value comes from an environment variable whose name is the upper-cased
field name (``DATABASE_URL`` -> ``database_url``); ``pydantic-settings`` does the
reading and the type coercion. There are no credential literals here or anywhere
else in the tree — ``_validate_secret_key`` below makes booting with a missing
or placeholder secret impossible.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The value shipped in .env.example. If it survives into a running process it
# means somebody copied the template and never generated a real key.
PLACEHOLDER_SECRET = "CHANGE_ME_GENERATE_WITH_OPENSSL_RAND_HEX_32"

MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    # env_file=None: the app never reads a .env file itself — docker-compose and
    # Vite load .env and pass the values in as real environment variables.
    model_config = SettingsConfigDict(
        env_file=None, extra="ignore", case_sensitive=False
    )

    database_url: str = (
        "postgresql+psycopg://screener:screener@localhost:5432/candidate_screener"
    )

    app_secret_key: str = ""
    access_token_expire_hours: int = 8
    cookie_secure: bool = False

    extra_origins: str = ""
    trusted_proxy_count: int = 0

    # When true, a new registration is given its own private copy of the demo
    # dataset (~6 roles, ~120 candidates) so every recruiter sees seed data.
    seed_demo_data: bool = False

    # Login throttling: this many failures inside the window locks further
    # attempts for that IP / email pair until the window slides past them.
    login_max_attempts: int = 8
    login_window_seconds: int = 300

    # --- Screening -------------------------------------------------------------
    # `live` (default; use the configured detection + synthesis backends — falls
    # back to the deterministic pipeline if a backend cannot be built) or `stub`
    # (deterministic pre-scan only, no network). The test suite forces `stub`
    # via conftest regardless of this value.
    screening_provider: str = "live"
    # Detection tier (Agents 1/2/3):
    #   `openai_agentic` (default) — 1/2/3 are tool-using agents on
    #     `openai_subagent_model`; the HF injection classifier stays a task model
    #   `hf_inference` — 1/2/3 on an opt-in HF-routed chat model, or pre-scan
    #   `hf_local` | `stub`
    screening_detection_backend: str = "openai_agentic"
    # Synthesis tier (Agents 4/5): `openai` | `stub`.
    screening_synthesis_backend: str = "openai"
    # Fan-out bound and the per-run candidate cap.
    screening_concurrency: int = 4
    screening_max_batch: int = 200
    # When true (the default), every model request + response is logged at INFO
    # (verbose, and includes résumé text). Set SCREENING_LOG_PROMPTS=false to
    # quiet it. The request/response pair is always persisted to
    # `screening_agent_runs` regardless.
    screening_log_prompts: bool = True

    # Hugging Face Inference (detection tier). Task models are always pinned to
    # provider="hf-inference" so raw resume text never leaves HF infra.
    # `HF_API_TOKEN` is accepted as a fallback for `HF_TOKEN` (see the validator
    # below).
    hf_token: str = ""
    hf_bill_to: str = ""
    hf_injection_model: str = "protectai/deberta-v3-base-prompt-injection-v2"
    hf_nli_model: str = "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli"
    hf_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # Opt-in: a chat model for the 3 detection sub-agents. `hf-inference` serves
    # no chat model, so this only does anything paired with a
    # `hf_subagent_chat_provider` (a third-party provider reached through HF
    # routing) — and then résumé text leaves HF infra for that one call.
    hf_subagent_chat_model: str = ""
    hf_subagent_chat_provider: str = ""
    # When a sub-agent chat model is set, 1–3 run as tool-using agents: this
    # bounds how many tool-call rounds each may take before it must answer.
    hf_subagent_max_tool_steps: int = 4

    # OpenAI — or any OpenAI-compatible chat endpoint (Ollama, vLLM, LM Studio,
    # Groq, OpenRouter, together.ai, Azure OpenAI, llama.cpp, …).
    # `openai_synthesis_model` = Agents 4/5; `openai_subagent_model` = detection
    # Agents 1/2/3 when `screening_detection_backend=openai_agentic`.
    # `openai_api_key` / `openai_base_url` are the shared default for both chat
    # tiers; override per tier below. An empty value == unset everywhere.
    openai_api_key: str = ""
    openai_synthesis_model: str = "gpt-4.1"
    openai_subagent_model: str = "gpt-4.1-mini"
    openai_base_url: str = ""
    # Per-tier endpoint overrides — each falls back to the `openai_*` values
    # above, so a split like "cheap local detection + hosted synthesis" is just
    # env. Resolved by `app.screening.providers._endpoint.resolve_endpoint`.
    screening_detection_base_url: str = ""
    screening_detection_api_key: str = ""
    screening_synthesis_base_url: str = ""
    screening_synthesis_api_key: str = ""

    @model_validator(mode="after")
    def _accept_hf_api_token_alias(self) -> "Settings":
        """Older setups export the token as ``HF_API_TOKEN``; use it when
        ``HF_TOKEN`` is unset or empty."""
        if not self.hf_token:
            self.hf_token = os.getenv("HF_API_TOKEN", "")
        return self

    @property
    def screening_is_live(self) -> bool:
        return self.screening_provider.strip().lower() == "live"

    @property
    def cors_origins(self) -> list[str]:
        origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
        extra = [o.strip() for o in self.extra_origins.split(",") if o.strip()]
        return origins + extra


def _validate_secret_key(secret: str) -> None:
    """Refuse to start rather than sign sessions with a guessable key.

    A weak signing key is not a degraded mode — anyone can mint a token for any
    account. Failing loudly at import time is the only safe behaviour.
    """
    if not secret or not secret.strip():
        raise RuntimeError(
            "APP_SECRET_KEY is not set. Generate one with `openssl rand -hex 32` "
            "and put it in your .env file."
        )
    if secret == PLACEHOLDER_SECRET:
        raise RuntimeError(
            "APP_SECRET_KEY is still the .env.example placeholder. Generate a real "
            "one with `openssl rand -hex 32`."
        )
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"APP_SECRET_KEY must be at least {MIN_SECRET_LENGTH} characters "
            f"(got {len(secret)}). Generate one with `openssl rand -hex 32`."
        )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    _validate_secret_key(settings.app_secret_key)
    return settings
