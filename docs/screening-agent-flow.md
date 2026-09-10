# The screening agent flow, end to end

This document traces exactly what happens when a résumé is screened: which
agents run, in what order, what each one is handed, what it returns, and how the
result is verified and persisted. It is a code-level companion to
[`screening.md`](./screening.md) (the product view) and
[`architecture.md`](./architecture.md) (the backend layering).

All paths below are under `backend/app/`.

---

## 1. The cast

Five of the components are LLM agents; the rest are deterministic Python that
frames, checks and persists what the agents do.

| # | Name | Kind | Module | Runs where |
|---|---|---|---|---|
| — | **Coordinator** | plain Python | `screening/coordinator.py` | FastAPI `BackgroundTasks` |
| — | **Deterministic pre-scan** | pure Python | `screening/prescan/` | in-process, per candidate |
| — | **Injection classifier** | HF task model | `screening/providers/hf_inference.py::_injection_scores` | `hf-inference` (optional) |
| 1 | **`manipulation_guard`** | LLM (tool-using) | prompt in `screening/agents/detectors.py` | detection tier |
| 2 | **`timeline_auditor`** | LLM (tool-using) | prompt in `screening/agents/detectors.py` | detection tier |
| 3 | **`inflation_auditor`** | LLM (tool-using) | prompt in `screening/agents/detectors.py` | detection tier |
| — | **Verifier** | pure Python | `screening/verifier.py` | in-process, per candidate |
| 4 | **`synthesizer`** | LLM | prompt in `screening/agents/synthesizer.py` | synthesis tier |
| 5 | **`comparative_reasoner`** | LLM | prompt in `screening/agents/synthesizer.py` | synthesis tier, **separate endpoint** |

Agents 1–3 are **isolated from each other**: Agent 1's output is never placed in
Agent 2's or Agent 3's input, so an injection that lands on one cannot
contaminate a sibling. Agent 4 re-derives from the raw résumé, so it cannot be
steered by a compromised sub-agent either.

The internal value types passed between these steps
(`PrescanResult`, `FeatureBundle`, `AgentCall`, …) live in
`screening/types.py` and are plain dataclasses — no ORM import — so the whole
pipeline is exercisable in `no_db` tests.

---

## 2. Two entry points

### 2.1 A screening run (Agents 1–4)

```
POST /api/screening/runs
  └─ routers/screening.py::create_run
       ├─ role_repo.get_owned(...)                     # 404 if not the caller's
       ├─ services/screening.py::start_run             # creates rows, commits
       └─ background.add_task(run_screening, run.id)   # returns 201 immediately
```

`start_run` (`services/screening.py:31`):

1. De-dups `candidate_ids`, rejects the whole request with **422** if the count
   exceeds `screening_max_batch` **or** any id is not in the caller's pool
   (`missing` list) — it never quietly screens the subset it recognises.
2. Inserts one `ScreeningRun` (`status="queued"`) and **one
   `ScreeningResult` per candidate** (`status="pending"`, with
   `resume_sha256` snapshotted now).
3. Commits, then the router schedules `coordinator.run_screening(run.id)`.

From here the coordinator owns the run.

### 2.2 A comparison (Agent 5)

```
POST /api/screening/comparisons
  └─ routers/screening.py::create_comparison
       └─ services/screening.py::create_comparison
            ├─ repo.latest_screened_result(...) for A and B   # prior audits, if any
            ├─ provider.compare(...)                          # Agent 5, one call
            └─ INSERT comparisons row (verbatim request + response)
```

Agent 5 **never runs inside a screening run** and never gates one
(`screening.md`: "The coordinator never calls it"). It is a synchronous request
handled in-process via `asyncio.run`.

---

## 3. The screening run, step by step

`coordinator.run_screening` is the sync entry point FastAPI calls; it is just
`asyncio.run(_run(run_id))` (`coordinator.py:340`).

### 3.1 `_run(run_id)` — set-up (`coordinator.py:237`)

1. `get_settings()` → `get_provider(settings)` picks the provider object
   (§6).
2. Open a `Session`, load the `ScreeningRun`, set `status="running"`,
   `run.provider = provider.describe()` (the tiers that will actually run), commit.
3. Load the `Role` → `_role_context(role)` = `{title, description,
   requirements[]}` (context only; screening does **not** judge fit).
4. Load every `pending` `ScreeningResult` for the run and the matching
   `Candidate` rows.
5. **Snapshot to plain dicts** (`jobs`): `result_id`, `candidate_id`,
   `candidate_name`, `text` (= `candidate.resume_text`), `resume_sha256`,
   `missing` flag. After this the concurrent coroutines touch **no** DB session.

### 3.2 Fan-out (`coordinator.py:280`)

```python
sem = asyncio.Semaphore(max(1, settings.screening_concurrency))   # default 4

async def _process(job):
    async with sem:
        if job["missing"]:
            unified, calls, error = None, [], "candidate no longer exists"
        else:
            unified, calls, error = await _screen_one(provider, role_context, run_id, ...)
    await asyncio.to_thread(_persist_one_sync, job["result_id"], unified, calls, error)

await asyncio.gather(*(_process(j) for j in jobs))
```

- Candidates are screened **concurrently**, bounded by
  `SCREENING_CONCURRENCY`.
- Each candidate is **persisted the moment it finishes**, in its own
  short-lived session (`_persist_one_sync`), so the run page and activity feed
  fill in row by row during the scan rather than all at the end.

### 3.3 Reconcile and finalise (`coordinator.py:304`)

After the gather:

1. `db.expire_all()` (the worker threads committed; re-read).
2. Any row still `pending` → forced to `status="error"`
   ("screening did not complete for this candidate"). **The invariant: one
   finalised row per selected candidate.**
3. Recompute `run.screened`, `run.errored`, `run.compromised`.
4. `run.status = "partial" if run.errored else "complete"`; set
   `completed_at`; commit.
5. If `_run` itself threw (bad role, a whole tier's auth/quota failed at the
   start) → `run.status = "failed"`, `run.error` set, and **no results are
   written**.
6. `finally:` → `provider.aclose()` closes any network clients.

---

## 4. `_screen_one` — the per-candidate pipeline

`coordinator.py:78`. Pure with respect to the DB (safe to `gather`). Returns
`(UnifiedCandidateAudit | None, list[AgentCall], error | None)` and **never
raises for an expected failure** — a caught exception becomes
`(None, calls, "screening did not complete: …")`.

```
text ─┐
      ▼
1. prescan = run_prescan(text)                         # deterministic signals + feature bundle
      ▼
2. audits, detect_calls = await provider.detect(       # Agents 1/2/3  → 3 × IntegrityAuditResult
        candidate_id, text, prescan, role_context)
      ▼
3. for audit in audits:                                # verifier: evidence-quote check
       cleaned, notes = verify_audit(audit, text)      #   drop flags whose quote isn't in the text
      ▼
4. audits, coverage_notes = coverage_check(prescan, audits)   # re-synthesise a missed injection flag
      ▼
5. canary_notes  = scan_for_canary([c.raw_response for c in detect_calls])
      ▼
6. unified, synth_call = await provider.synthesize(    # Agent 4 → UnifiedCandidateAudit
        run_id, candidate_id, candidate_name,
        resume_sha256, text, audits, prescan)
      ▼
7. canary_notes += scan_for_canary([synth_call.raw_response])
      ▼
8. if canary_notes:  quarantine → append a high-severity PROMPT_INJECTION
                     finding, force is_compromised, re-derive disposition
   if coverage_notes: force unified.is_compromised = True
      ▼
   return unified, calls, None
```

### 4.1 Step 1 — the deterministic pre-scan (`prescan/__init__.py::run_prescan`)

Pure, dependency-free. Runs **unconditionally**, whatever backend is configured,
because it is the coverage + canary backstop.

1. `normalize.normalize(text)` — NFKC fold, then strip and **record** every run
   of ≥3 zero-width / bidi / control characters (`hidden_runs` with a
   `U+XXXX` sample). `normalize.py`.
2. `manipulation.scan(text, norm)` — regex families for injection imperatives,
   score-tampering, notice-suppression, out-of-band appeals, role-play framing;
   fake system markers (`SYSTEM:`, `<|im_start|>`, `### Instruction`); a literal
   `</candidate_text>` / `</resume>` fence token (delimiter escape); HTML
   comments; lone base64 blocks; the hidden runs from step 1. A
   `_LEGIT_CONTEXT_RE` window check **suppresses the soft injection patterns**
   when ≥2 security-terminology cues sit within ±220 chars (an AI-safety
   researcher quoting an attack string), but never the hard ones
   (score_tamper, suppress_notice, delimiter_escape, system markers).
   `manipulation.py`.
3. `timeline.scan(clean_text)` — parse every `start–end` range; flag
   end-before-start, concurrent full-time roles overlapping > ~1 yr,
   `N+ years` header vs the non-overlapping union of listed tenure, a senior
   "since <year>" dated before the qualifying degree, and "led a team of N≥8"
   with no management title nearby. Also returns the parsed `timeline_table`.
   `timeline.py`.
4. `inflation.scan(clean_text)` — split into `(header, bullets)` blocks;
   shingled-Jaccard (≥0.6) cluster bullets across **distinct** blocks →
   `RECYCLED_METRIC` (+ `UNSUBSTANTIATED_INFLATION` if the recycled bullet
   carries a `%`/`x` metric); junior/intern header + a "sole / from scratch"
   phrase + an "enterprise / $Nm / company-wide" phrase → junior-enterprise
   claim. Also returns `dup_clusters`. `inflation.py`.

Output — `PrescanResult(clean_text, hits[], features)`:

- `hits` — `PrescanHit(agent, category, evidence, reason, pattern_key)`,
  each tagged with the sub-agent whose domain it belongs to
  (`hits_for("manipulation_guard")` etc.).
- `features` — a `FeatureBundle` (`injection_hits`, `delimiter_escapes`,
  `system_markers`, `hidden_text_inventory`, `timeline_table`, `dup_clusters`)
  passed to the sub-agents **as evidence to weigh, never as verdicts**
  (`prompts.py::_features_block` labels it exactly that).

### 4.2 Step 2 — `provider.detect(...)` → Agents 1/2/3

See §5 for the internals. It returns:

- `audits: list[IntegrityAuditResult]` — one per sub-agent, each
  `{agent_name, candidate_id (str), is_compromised, flags: [{category,
  evidence, reason}]}`.
- `calls: list[AgentCall]` — one per model invocation (plus one
  `injection_classifier` row), later written verbatim to
  `screening_agent_runs`.

### 4.3 Steps 3–5 & 7–8 — the verifier (`verifier.py`)

Three deterministic guard rails run over agent output:

| Check | Function | Effect |
|---|---|---|
| **evidence-quote** | `verify_audit(audit, text)` | Every `evidence` string must be a whitespace-tolerant substring of the original text (spans joined with `\|\|` are checked part by part). A flag whose quote cannot be located is **dropped** and a note recorded on that agent's `AgentCall`. `HIDDEN_PAYLOAD` evidence is a synthetic `[zero_width run, …]` descriptor and is exempt. |
| **coverage** | `coverage_check(prescan, audits)` | For every deterministic `PROMPT_INJECTION` / `SYSTEM_SPOOFING` pre-scan hit **not** covered by a `manipulation_guard` flag, synthesise the flag back in, mark `is_compromised=True` on that audit, and record `LLM_MISSED_INJECTION: <pattern_key>`. An injection the model missed never vanishes. |
| **canary** | `scan_for_canary(raw_responses)` | If the token `⟬CANARY-7Q2⟭` (`screening/__init__.py::CANARY`) appears in **any** `raw_response` — detection *or* synthesis — return a note. In `_screen_one` step 8 this triggers **quarantine**: a `high`-severity `PROMPT_INJECTION` finding is appended, `is_compromised` is forced true, and `overall_disposition` is re-derived via `assembly.disposition_for`. |

### 4.4 Step 6 — `provider.synthesize(...)` → Agent 4

See §5.4. Returns `(UnifiedCandidateAudit, AgentCall)`.

---

## 5. Inside the detection tier (Agents 1–3)

The default backend is **`openai_agentic`**
(`providers/openai_detection.py`), a subclass of `HFDetectionProvider`
(`providers/hf_inference.py`) that overrides only the two provider seams
(`_chat`, `_classify_segment`) and client construction. So the flow below is the
same for `openai_agentic` and `hf_inference`; only *where the chat call lands*
differs.

### 5.1 `detect()` (`hf_inference.py:203`)

1. **Injection classifier, once per candidate** — `_injection_scores(text)`
   chunks the résumé into ≤6 × 1500-char segments and scores each with the HF
   `text_classification` task model `hf_injection_model`
   (`protectai/deberta-v3-base-prompt-injection-v2`). The result is recorded as
   its own `AgentCall(agent_name="injection_classifier", tier="hf")` for the
   activity feed; **its score is not merged into the feature bundle**. No
   `HF_TOKEN` → this one row is `degraded`, the candidate is still fully
   screened.

2. **For each of the three `detectors.SPECS`** (`agents/detectors.py:113` —
   `manipulation_guard`, `timeline_auditor`, `inflation_auditor`):

   - **Pre-scan mode** (`hf_inference` with no `HF_SUBAGENT_CHAT_MODEL`, or
     `hf_local`): skip the model entirely.
     `res = detectors.fallback(agent_name, prescan, candidate_id)` builds a
     valid `IntegrityAuditResult` straight from `prescan.hits_for(agent_name)`.
     The `AgentCall` is marked `notes="pre-scan mode"` (not `degraded` — no
     call was attempted).
   - **Agentic mode** (the default): build the user message and run the bounded
     tool-calling loop `_run_agent(spec, user, prescan)` (§5.2).

3. Assemble each sub-agent's `AgentCall` (model, `prompt_text` = system +
   user + tool transcript, `raw_response`, `tool_calls`, `repair_attempts`,
   `degraded`, `latency_ms`, …) and return `(results, calls)`.

### 5.2 The sub-agent loop `_run_agent` (`hf_inference.py:302`)

Each sub-agent is a **tool-using agent**:

- **System prompt** = its `DetectorSpec.system` (from `agents/detectors.py`,
  every one built with the shared `GUARD` + `BENIGN_RULE` fragments from
  `agents/prompts.py`) **+** an appended instruction that it may call tools for
  deterministic evidence but must still read the text itself and reply with only
  the `IntegrityAuditResult` JSON.
- **User message** = `detection_user_message(...)`
  (`agents/prompts.py:43`): `candidate_id`, `role_context`, the labelled
  `deterministic_pre_scan` feature block, then the résumé wrapped in
  `<candidate_text>…</candidate_text>`. **No résumé text is ever concatenated
  into the instruction portion.**
- **Tools offered** — `tools.specs_for(agent_name)` (`tools.py:107`):

  | agent | tools |
  |---|---|
  | `manipulation_guard` | `scan_manipulation_patterns`, `classify_prompt_injection` |
  | `timeline_auditor` | `parse_resume_timeline`, `check_timeline_consistency` |
  | `inflation_auditor` | `find_recycled_or_inflated_claims` |

  The four deterministic tools **take no free-text argument** — they always run
  against the résumé already under review, so an injected instruction cannot
  ride in through a tool call. Each wraps a slice of the existing
  `PrescanResult` (`tools.py::run_tool`). `classify_prompt_injection(segment)`
  is the one exception — a pure classifier with no instruction-following
  surface — and calls back into `_classify_segment` (the HF task model).

- **Loop**: up to `HF_SUBAGENT_MAX_TOOL_STEPS` (default 4) rounds. Each round
  the model may emit `tool_calls`; the loop runs them
  (`screening_tools.run_tool`), appends a `role:"tool"` message with the JSON
  result (capped at 6000 chars) and a one-line transcript entry, and loops. On
  the step budget or the first turn with no tool call, the model's content is
  taken as the final answer.
- **Provider-variance handling**: JSON mode (`{"type":"json_object"}`), not
  strict `json_schema` (routed HF providers and some OpenAI-compatible servers
  reject the schema form, especially alongside `tools=`). A 400-ish error
  *while offering tools* → drop `tools` and retry once
  (`note_suffix="tools unsupported by provider"`). An auth / quota / "model
  does not exist" error → stop, `hard_error` set, fall back to the pre-scan for
  that sub-agent.
- **JSON ladder**: the final content is run through
  `jsonio.run_ladder(_final_call, IntegrityAuditResult)` (§7) — parse →
  validate → one repair call → give up.

Returns `{parsed, raw, attempts, tool_calls, transcript, note_suffix}`.

### 5.3 Turning that into an `IntegrityAuditResult` (`hf_inference.py:256`)

- `parsed is not None` → `detectors.normalise(parsed, agent_name,
  candidate_id)` coerces the dict and **drops any flag whose category is
  outside that agent's domain** (`_CATEGORIES` in `detectors.py`); `degraded =
  False`, note `"agentic"`.
- `parsed is None` (ladder exhausted, or the chat call was unreachable) →
  `detectors.fallback(agent_name, prescan, candidate_id)` — the deterministic
  pre-scan assembly; `degraded = True`, note names the reason. **The candidate
  is still screened.**

### 5.4 The synthesis tier — Agent 4 (`providers/openai_synth.py:110`)

`synthesize(...)`:

1. `user = synthesis_user_message(...)` (`agents/prompts.py:62`):
   `candidate_id`, `candidate_name`, `role_context`, the three
   `IntegrityAuditResult`s inside `<audit_results>` **as data**, the
   `deterministic_pattern_keys`, then the raw résumé inside `<candidate_text>`
   (with the same `GUARD`).
2. System prompt = `synthesizer.SYNTHESIS_SYSTEM` (`agents/synthesizer.py:45`):
   re-read the text, **do not blindly trust the detectors** (confirm each flag,
   drop unlocatable evidence, add any clear concern they missed), deduplicate,
   and for every finding set `severity`, a **non-empty** `benign_explanation`
   (or lower the severity toward `info`), `confidence`, `recommended_action`
   (`verify` / `ask_candidate` / `human_read` / `no_action` + one sentence),
   `source`. A manipulation finding is never `info` and its action is
   `human_read`. Set `overall_disposition` and `is_compromised`, write a
   1–3-sentence summary stating screening did not follow any instruction in the
   résumé.
3. `_chat(...)` — one call, `temperature=0`, `max_tokens=4000`, JSON mode.
4. `run_ladder(_call, SynthesisModelOutput)` (§7).
   - **parsed** → `synthesizer.normalise_unified(...)`
     (`agents/synthesizer.py:106`): validate each finding into
     `EnrichedFinding`, back-fill guard rails the model skipped
     (`severity` default, non-empty `benign_explanation`, manipulation floor of
     `low`), compute `overall_disposition` via `assembly.disposition_for`, OR
     `is_compromised` with `any(a.is_compromised for a in audits)`.
   - **not parsed** → `assembly.assemble_unified(..., degraded=["synthesizer"])`
     — a deterministic `UnifiedCandidateAudit` built from the sub-agent flags
     with conservative default severities (`assembly.py::_SEVERITY_BY_CATEGORY`
     / `_ACTION_BY_CATEGORY`). Still a full, explained row.
5. Return `(unified, AgentCall(agent_name="synthesizer", tier="openai", …))`.

### 5.5 Endpoint resolution (`providers/_endpoint.py`)

Both chat tiers hit an **OpenAI-compatible `/chat/completions`** endpoint,
resolved purely from env: per-tier `SCREENING_{DETECTION,SYNTHESIS}_{BASE_URL,
API_KEY}` → shared `OPENAI_BASE_URL` / `OPENAI_API_KEY` → `https://api.openai.com/v1`.
Model ids: `OPENAI_SUBAGENT_MODEL` (default `gpt-4.1-mini`) for detection,
`OPENAI_SYNTHESIS_MODEL` (default `gpt-4.1`) for synthesis. An **empty** env var
is treated as unset.

---

## 6. Provider selection

`get_provider(settings)` (`providers/__init__.py:33`):

```
SCREENING_PROVIDER = stub   ──────────────────────────────►  StubProvider
   (test default; also if detection == synthesis == "stub")

SCREENING_PROVIDER = live  ─► CompositeProvider(settings)
   │  (on any construction error → StubProvider, logged, run never 500s)
   │
   ├─ detection backend  (SCREENING_DETECTION_BACKEND)
   │    openai_agentic ─► OpenAIAgenticDetectionProvider   (key present)
   │                   └► HFDetectionProvider              (no key → fallback)
   │    hf_inference   ─► HFDetectionProvider
   │    hf_local       ─► HFLocalDetectionProvider         (ImportError → stub tier)
   │    stub / unknown ─► StubProvider tier
   │
   └─ synthesis backend  (SCREENING_SYNTHESIS_BACKEND)
        openai         ─► OpenAISynthesisProvider
        stub / unknown ─► StubProvider tier
```

`CompositeProvider` (`providers/composite.py`) just delegates `detect` to the
detection object and `synthesize` / `compare` to the synthesis object, and
`describe()` reports the tiers that were actually built. It constructs the
network clients and closes them in `aclose()`.

- **`StubProvider`** (`providers/stub.py`) — `detect` turns pre-scan hits
  straight into three `IntegrityAuditResult`s; `synthesize` runs
  `assembly.assemble_unified`; `compare` ranks by fewer open findings. No
  network for either tier. This is the pipeline shape every other provider
  implements.
- **`HFLocalDetectionProvider`** (`providers/hf_local.py`) — runs the
  `protectai/…` classifier locally via `transformers`; the sub-agents
  themselves emit the deterministic pre-scan, so every result here is
  `degraded`.

---

## 7. The JSON ladder (`screening/jsonio.py::run_ladder`)

Every LLM → schema conversion in both tiers goes through it:

1. Call the model.
2. `parse_json` — tolerant extraction of the first balanced `{…}` (handles
   ```` ```json ```` fences).
3. `model_cls.model_validate(data)` → return `(obj, raw, attempts)`.
4. On parse/validation failure, **one** repair call that feeds the exact error
   back and demands "ONLY a single JSON object".
5. Second failure → return `(None, raw, attempts)`. The caller then assembles
   that agent's contribution deterministically from the pre-scan and marks it
   `degraded`.

It **never raises for a model failure** and it **never drops the candidate**.
Only a whole-tier auth/quota failure at the start of `_run` marks the run
`failed`.

---

## 8. The two structural invariants

### 8.1 Never comply with an injected instruction

| Mechanism | Where |
|---|---|
| Résumé text only ever appears inside `<candidate_text>` tags, framed as untrusted data by `GUARD` in **every** system prompt, both tiers | `agents/prompts.py::GUARD`, used by `agents/detectors.py` and `agents/synthesizer.py` |
| Agents can only return their fixed schema — no free-form channel | `IntegrityAuditResult` / `UnifiedCandidateAudit` / `ComparativeAnalysisResult` in `schemas/screening.py` |
| Deterministic tools take no free text | `screening/tools.py` (`_NO_ARGS`) |
| Canary token — never emit `⟬CANARY-7Q2⟭` — asserted absent from every `raw_response` | `verifier.py::scan_for_canary`; quarantine in `coordinator.py::_screen_one` step 8 |
| Coverage check — a pre-scan injection hit the LLM didn't report is synthesised back in, `LLM_MISSED_INJECTION` logged, `is_compromised` forced | `verifier.py::coverage_check` |
| The deterministic pre-scan runs **unconditionally**, whatever the backend | `coordinator.py::_screen_one` step 1 |

### 8.2 Never silently drop a candidate

| Mechanism | Where |
|---|---|
| One `ScreeningResult` per candidate, pre-created `pending` | `services/screening.py::start_run` |
| DB unique constraint | `UniqueConstraint("run_id", "candidate_id")` in `models/screening.py` |
| Coordinator only *updates* rows; any leftover `pending` → `error`; counts reconciled | `coordinator.py::_run` (§3.3) |
| A model failure degrades to pre-scan assembly, never 500s | `jsonio.run_ladder` → `assembly.assemble_unified`; `get_provider` stub fallback |
| Every model call → a `screening_agent_runs` row (request + response verbatim), success or failure | `coordinator.py::_persist_agent_runs`, fed by every provider's `AgentCall` list |
| `POST /runs` rejects the whole request (422) listing every unknown/unowned id | `services/screening.py::start_run` |

---

## 9. Persistence & the audit trail

`_persist_one_sync` → `_write_result` (`coordinator.py:174`), per candidate, in
its own session:

- Always writes the `AgentCall` list to **`screening_agent_runs`**
  (`agent_name`, `tier`, `model`, `prompt_sha256`, `prompt_text`,
  `raw_response`, `parsed_result`, `tool_calls`, `parsed_ok`,
  `repair_attempts`, `degraded`, `notes`, `latency_ms`, `input_chars`).
- `error` or no `unified` → `ScreeningResult.status = "error"`, `error` set,
  `overall_disposition = None`.
- Otherwise → `status = "screened"`, copy `is_compromised`,
  `overall_disposition`, `summary`, `agent_results` (the three raw
  `IntegrityAuditResult`s), `degraded`, `models`; one **`screening_findings`**
  row per enriched finding.

Read paths (`routers/screening.py`):

```
GET /api/screening/runs/{run_id}                                  # run + per-candidate result summaries
GET /api/screening/runs/{run_id}/agent-runs                       # live activity feed, metadata only
GET /api/screening/runs/{run_id}/results/{candidate_id}           # the UnifiedCandidateAudit
GET /api/screening/runs/{run_id}/results/{candidate_id}/agent-runs # Agents 1–4, full request + response
GET /api/screening/comparisons/{comparison_id}                    # Agent 5, full request + response
```

`SCREENING_LOG_PROMPTS` (on by default) also logs every full request + response
at `INFO`.

---

## 10. Data / trust boundaries

| Data | Reaches |
|---|---|
| Raw résumé text | the detection chat tier (OpenAI-compatible endpoint, or a routed HF provider); the HF `protectai/…` classifier; Agent 4; Agent 5 |
| The three `IntegrityAuditResult`s | Agent 4 (as fenced data) |
| Both full profiles + both audits | Agent 5 |
| Résumé text → the *instruction* half of any prompt | **never** — always inside `<candidate_text>` as data |
| Injection classifier score → the sub-agents' feature bundle | **never merged** — recorded only as its own agent-run row |

---

## 11. Agent 5 — comparative reasoner, in detail

`OpenAISynthesisProvider.compare` (`providers/openai_synth.py:205`):

1. `comparison_user_message(...)` (`agents/prompts.py:87`): `role_context`,
   both ids, both audits (as JSON data), both résumés in `<candidate_a>` /
   `<candidate_b>` fences.
2. System prompt `synthesizer.COMPARISON_SYSTEM`: cite verbatim evidence from
   **both** candidates in every dimension (`TECHNICAL_DEPTH`, `PROVEN_IMPACT`,
   `ROLE_RELEVANCE`, `RISK_PROFILE`); **never output a numeric score**;
   integrity violations and unsubstantiated inflation **penalise rank
   regardless of nominal years of experience**, and an open medium+ integrity
   finding on either side forces a `RISK_PROFILE` dimension stating that
   penalty.
3. Targeted retries: if a `score|rating|rank` number slips in → one retry
   demanding words only; if no dimensions list can be read → one retry
   demanding the exact keys and a JSON array.
4. `synthesizer.normalise_comparison` coerces the common wrong shapes
   (`comparison` object keyed by dimension, `candidate_a` vs
   `candidate_a_evidence`) and pins `higher_ranked_id` / `lower_ranked_id` to
   the two real ids.
5. Persisted to the **`comparisons`** table with the verbatim request +
   response and the medium+ findings it surfaced from either prior audit.

---

## 12. Sequence diagram

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant R as router
    participant S as services.start_run
    participant BG as coordinator._run (BackgroundTask)
    participant P as prescan
    participant D as detect() Agents 1/2/3
    participant V as verifier
    participant A4 as synthesize() Agent 4
    participant DB as Postgres

    C->>R: POST /api/screening/runs {role_id, candidate_ids}
    R->>S: start_run(...)
    S->>DB: INSERT run(queued) + 1 pending ScreeningResult per candidate
    S-->>R: run
    R-->>C: 201 RunDetail
    R->>BG: run_screening(run.id)

    BG->>DB: run.status = running, provider = describe()
    BG->>DB: load role + pending results + candidates, snapshot to plain dicts

    loop each candidate, bounded by SCREENING_CONCURRENCY
        BG->>P: run_prescan(text)
        P-->>BG: PrescanResult(hits, features)
        BG->>D: detect(candidate_id, text, prescan, role_context)
        Note over D: injection_classifier (1×) + Agents 1/2/3<br/>isolated, tool-using, JSON ladder<br/>fail → pre-scan fallback (degraded)
        D-->>BG: 3 × IntegrityAuditResult + AgentCalls
        BG->>V: verify_audit (evidence quotes) + coverage_check + scan_for_canary
        V-->>BG: cleaned audits + notes
        BG->>A4: synthesize(text, audits, prescan)
        Note over A4: re-read text, dedupe, enrich,<br/>set severity / disposition / summary<br/>fail → assemble_unified (degraded)
        A4-->>BG: UnifiedCandidateAudit + AgentCall
        BG->>V: scan_for_canary(synth response)
        Note over BG: canary → quarantine finding + force is_compromised<br/>coverage → force is_compromised
        BG->>DB: (own session) UPDATE result=screened + findings + agent_runs, COMMIT
    end

    BG->>DB: leftover pending → error; recompute counts;<br/>status = partial | complete | failed; completed_at
```

---

## 13. What is specified but not yet in the code

`.scratch/screening/spec.md` §7 describes a **feedback loop and calibration**
(recruiter marks findings accurate / false-positive / missed; adjustments feed
the next run's prompts). There are **no** `screening_feedback` /
`screening_calibration` models, routers, or services in the tree today — the
`pattern_key` on each finding is the seam it would key on, but the loop itself
is not built.
