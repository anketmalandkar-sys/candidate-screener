"""LLM system prompts and output normalisers for every screening agent.

* ``prompts``     — shared prompt fragments (``GUARD``, ``BENIGN_RULE``) and the
  builders that wrap untrusted candidate text in the data fence.
* ``detectors``   — the three isolated detection sub-agents (1/2/3): a system
  prompt plus ``normalise`` (model JSON -> ``IntegrityAuditResult``) and
  ``fallback`` (pre-scan -> ``IntegrityAuditResult`` when the JSON ladder fails).
* ``synthesizer`` — Agent 4 (aggregation) and Agent 5 (comparison): system
  prompts plus the normalisers for their outputs.
"""
