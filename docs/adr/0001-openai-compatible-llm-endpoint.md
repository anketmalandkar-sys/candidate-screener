# ADR-0001: The screening LLM tiers target any OpenAI-compatible endpoint

**Status:** Accepted (2026-09-10)

## Context

The screening subsystem's original design (`.scratch/screening/spec.md`,
lines 7–8) fixed the model backend as:

> Model backend: **Hugging Face Inference** for the detection tier
> (Agents 1/2/3) + **OpenAI** for the synthesis tier (Agents 4/5).
> **Anthropic/Claude is not used.**

In practice the detection sub-agents already run on OpenAI by default
(`SCREENING_DETECTION_BACKEND=openai_agentic`), and both OpenAI-backed providers
already accept `OPENAI_BASE_URL`. The remaining friction to running the screener
against a different model — a self-hosted or third-party OpenAI-compatible
server — was: one shared key/URL for both tiers, a hard-coded provider record,
and string literals for backend/model names.

## Decision

Both chat tiers target **any OpenAI-compatible `/chat/completions` endpoint**,
selected purely from environment variables. No UI, no database column, no
runtime switch.

- `OPENAI_API_KEY` / `OPENAI_BASE_URL` are the shared default for both tiers;
  `OPENAI_SUBAGENT_MODEL` / `OPENAI_SYNTHESIS_MODEL` are the per-tier model ids
  (unchanged).
- New optional per-tier overrides — `SCREENING_DETECTION_BASE_URL` /
  `SCREENING_DETECTION_API_KEY` and `SCREENING_SYNTHESIS_BASE_URL` /
  `SCREENING_SYNTHESIS_API_KEY` — each fall back to the shared `OPENAI_*` value.
- An **empty** env value is treated as unset, resolved in one place:
  `backend/app/screening/providers/_endpoint.py` (`resolve_endpoint`).
- Backend dispatch is a name→builder registry in `CompositeProvider`
  (`_DETECTION_BUILDERS` / `_SYNTHESIS_BUILDERS`); an unknown name degrades that
  tier to the deterministic stub rather than raising.
- The Hugging Face `text_classification` prompt-injection classifier
  (`HF_INJECTION_MODEL`) is **unchanged** — it is a genuine task model, not a
  chat model. With no `HF_TOKEN` its agent-run row is `degraded` and the
  deterministic pre-scan is the injection backstop; the candidate is still
  fully screened.
- **Anthropic/Claude is still not added** as a distinct provider. It is not
  OpenAI-compatible on the wire and would need a bespoke message/tool/structured
  -output translation layer.

## Consequences

- The backend names `openai` / `openai_agentic` and the `tier="openai"` label on
  `screening_agent_runs` rows are **vendor-neutral** — they mean "the
  OpenAI-compatible chat tier", whatever the actual vendor.
- Changing the model is an `.env` edit + `docker compose up -d backend`.
  Ready-to-paste configs (OpenAI, Ollama, vLLM, Azure, Groq, split-tier) live in
  `docs/llm-backends.md`.
- `docker-compose.yml` now passes `OPENAI_BASE_URL` and the four `SCREENING_*`
  override vars through; blank values are safe because `resolve_endpoint`
  coalesces them.

## Supersedes

`.scratch/screening/spec.md` lines 7–8. The synthesis tier is no longer "OpenAI"
specifically but "any OpenAI-compatible endpoint"; the detection tier's default
is likewise. The HF prompt-injection classifier requirement stands.
