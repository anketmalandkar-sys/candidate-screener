# CONTEXT — domain vocabulary

The words this codebase uses, and what they mean. Use these terms verbatim in
issues, tests, and comments; don't drift to synonyms.

## Actors

- **Recruiter** — the only kind of user. Registers with email + password, owns
  everything they create. Also called the **tenant**: every row is scoped by
  `user_id` and one recruiter can never see another's data (a cross-tenant fetch
  returns **404**, not 403, so ids can't be probed).

## Hiring setup

- **Role** — an open position the recruiter is hiring for. Has a title, a job
  description, an `is_active` flag, and an ordered list of requirements.
- **Requirement** — one scored criterion on a role. Carries a **weight**
  (`must` = 3, `important` = 2, `nice` = 1) and an optional list of recruiter
  **aliases** (synonyms the matcher should also accept). Editing a role's
  requirement list **replaces it wholesale**, in one transaction.
- **Candidate** — a pool entry owned directly by the recruiter: one résumé, not
  attached to any role. Résumés arrive by paste (primary) or file upload (PDF /
  DOCX / TXT); only the **extracted text** is stored, never the uploaded file.

## Screening

Screening runs **integrity checks on a résumé before it is scored** and reports
what it finds in language a recruiter can act on. See
[`docs/screening.md`](docs/screening.md).

- **Screening run** — one role + a chosen set of candidates, screened together.
  Statuses: `queued` -> `running` -> `complete` | `partial` | `failed`.
- **Screening result** — the outcome for one candidate in one run. **Exactly one
  per selected candidate**, always (even on error). Statuses: `pending`,
  `screened`, `error` (`skipped` is a reserved enum value the coordinator never
  assigns).
- **Finding** — one concern found in a résumé: a category, the exact **quoted
  evidence**, a plain-language **reason**, and (from Agent 4) a **severity**
  (`info` / `low` / `medium` / `high`), a **benign_explanation** (the most
  plausible innocent reading), and a **recommended_action** (`verify` /
  `ask_candidate` / `human_read` / `no_action`).
- **Disposition** — the result's headline: `clear`, `review`, or `high_concern`,
  derived from the highest finding severity
  (`app/screening/assembly.py::disposition_for` is the single source of truth).
- **is_compromised** — true when the screening turned up **any** integrity
  finding, whatever the category (`app/screening/assembly.py`: any sub-agent
  flagged, or any merged finding exists). Manipulation of the screening process
  itself — prompt injection, spoofing, hidden payload — is the strongest
  trigger, but a timeline or inflation finding sets it too. A flag, **not** a
  rejection — the candidate is still fully screened and reported.
- **The five agents**
  - **1 · manipulation_guard** — text aimed at an automated reader:
    `PROMPT_INJECTION`, `SYSTEM_SPOOFING`, `HIDDEN_PAYLOAD`.
  - **2 · timeline_auditor** — contradictions inside the one document:
    `TIMELINE_OVERLAP`, `CHRONOLOGICAL_ERROR`, `SENIORITY_ANOMALY`.
  - **3 · inflation_auditor** — recycled, detail-free achievement claims:
    `RECYCLED_METRIC`, `UNSUBSTANTIATED_INFLATION`.
  - **4 · synthesizer** — re-reads the résumé + the three results, dedupes,
    enriches, writes the unified audit.
  - **5 · comparative_reasoner** — a separate endpoint: given two candidates,
    explains why one ranks above the other.
- **Pre-scan** — the deterministic, dependency-free, no-network detectors that
  run first (`app/screening/prescan/`). Feeds the agents evidence and acts as
  the coverage/canary backstop when a model misses something.
- **Provider** — the object that owns the model calls. **Tiers**: *detection*
  (Agents 1–3) and *synthesis* (Agents 4–5). **Backends**: `stub` (no network,
  the test default), `openai_agentic` (default detection), `hf_inference`,
  `hf_local`, `openai` (synthesis). A backend that can't be built degrades to
  `stub`; the candidate is still screened.
- **Calibration** *(designed, not yet built — see `.scratch/screening/spec.md`
  §7 and issue `06-feedback-and-calibration.md`)* — recruiter feedback
  (`accurate` / `false_positive` / `severity_too_high` / `severity_too_low` /
  `missed`) aggregated per `(recruiter, role, agent)` into a visible, reversible
  adjustment the next run reads. Intended to only **lower** severity,
  **suppress** a pattern, or **add examples** — never disable a category, and
  never touch manipulation findings. No feedback endpoint, table, or UI exists
  today.
- **Degraded** — a model call was attempted and failed, so that agent's
  contribution was assembled deterministically from the pre-scan. Distinct from
  **pre-scan mode**, where no model call was attempted at all.
- **Canary** — a token every system prompt is told never to emit; if it appears
  in a model's output, that output followed an instruction from the résumé and
  is quarantined.

## Architecture terms

`routers -> services -> repositories -> models`; `schemas/` are the DTOs. See
[`docs/architecture.md`](docs/architecture.md).
