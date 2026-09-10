"""Internal value types passed between the pre-scan, the providers, the
verifier and the coordinator. Kept dependency-free (dataclasses + plain types)
so ``no_db`` tests can exercise the pipeline with nothing imported from the ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PrescanHit:
    """One deterministic detection. ``agent`` says which sub-agent's domain it
    belongs to; ``category`` is the public finding category."""

    agent: str  # manipulation_guard | timeline_auditor | inflation_auditor
    category: str
    evidence: str
    reason: str
    pattern_key: str


@dataclass
class FeatureBundle:
    """Structured signals handed to the sub-agents as evidence to weigh."""

    timeline_table: list[dict] = field(default_factory=list)
    dup_clusters: list[dict] = field(default_factory=list)
    injection_hits: list[str] = field(default_factory=list)
    delimiter_escapes: list[str] = field(default_factory=list)
    system_markers: list[str] = field(default_factory=list)
    hidden_text_inventory: list[dict] = field(default_factory=list)


@dataclass
class PrescanResult:
    clean_text: str
    hits: list[PrescanHit]
    features: FeatureBundle

    def hits_for(self, agent: str) -> list[PrescanHit]:
        return [h for h in self.hits if h.agent == agent]


@dataclass
class AgentCall:
    """A record of one model invocation, persisted to ``screening_agent_runs``.

    ``prompt_text`` is the full request sent to the model (system + user for a
    chat call), ``raw_response`` the verbatim reply — the pair kept as the
    audit-trail "info" for that call.
    """

    agent_name: str
    tier: str
    model: str = ""
    prompt_sha256: str = ""
    prompt_text: str = ""
    raw_response: str = ""
    parsed_result: dict | None = None
    parsed_ok: bool = False
    repair_attempts: int = 0
    degraded: bool = False
    notes: str | None = None
    # For an agentic sub-agent: one entry per tool the model called —
    # {name, arguments, result_summary, latency_ms}.
    tool_calls: list[dict] = field(default_factory=list)
    latency_ms: int = 0
    input_chars: int = 0
