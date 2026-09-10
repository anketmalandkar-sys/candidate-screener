"""Multi-agent resume integrity screening. See ``docs/screening.md`` for the
full walkthrough.

Layout:

* ``prescan/``   — pure-Python deterministic detectors + a feature bundle
* ``agents/``    — the LLM system prompts and output normalisers
* ``providers/`` — the model backends: ``stub`` (no network, the test default),
  ``openai_agentic`` / ``hf_inference`` / ``hf_local`` for detection, and
  ``openai`` for synthesis
* ``verifier``   — canary / coverage / evidence-quote checks over agent output
* ``coordinator``— per-run orchestration; owns the "one row per candidate" and
  "never silently drop / execute an injection" invariants

The module constants below are the canary token every LLM system prompt is told
never to emit, and the fence that wraps untrusted candidate text.
"""

CANARY = "⟬CANARY-7Q2⟭"
CANDIDATE_FENCE_OPEN = "<candidate_text>"
CANDIDATE_FENCE_CLOSE = "</candidate_text>"
