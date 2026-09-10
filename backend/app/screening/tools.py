"""Deterministic checks exposed as agent-callable tools.

When a sub-agent chat model is configured, detection sub-agents 1–3 call these
instead of being handed the pre-scan output as a static block. Every tool wraps
an existing ``prescan/`` result — no detection logic lives here.

Boundary rule: the four deterministic tools take **no free-text argument**. They
always operate on the candidate résumé the coordinator already passed into
``detect()`` (the model chooses *which* check to run, never *what text* to feed
it), so an injected instruction cannot ride in through a tool argument.
``classify_prompt_injection`` takes a ``segment`` string because it is a pure
classifier with no instruction-following surface.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.screening.types import PrescanResult

_NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}

_SPECS: dict[str, dict] = {
    "scan_manipulation_patterns": {
        "type": "function",
        "function": {
            "name": "scan_manipulation_patterns",
            "description": (
                "Run the deterministic manipulation scan over the candidate "
                "résumé currently under review. Returns prompt-injection "
                "imperatives, data-fence / delimiter escapes, fake system-role "
                "markers, and hidden or zero-width character runs — raw "
                "high-precision signals, not verdicts. Absence of a hit is not "
                "proof of safety. Takes no arguments."
            ),
            "parameters": _NO_ARGS,
        },
    },
    "parse_resume_timeline": {
        "type": "function",
        "function": {
            "name": "parse_resume_timeline",
            "description": (
                "Return the parsed employment date ranges from the résumé under "
                "review: each entry has the source line, start year, end year, "
                "whether it reads as full-time, and whether the line looks like "
                "a job entry (vs prose). Takes no arguments."
            ),
            "parameters": _NO_ARGS,
        },
    },
    "check_timeline_consistency": {
        "type": "function",
        "function": {
            "name": "check_timeline_consistency",
            "description": (
                "Return the deterministic internal-timeline contradictions found "
                "in the résumé under review: overlapping full-time roles, "
                "chronological errors (end before start, senior title before "
                "degree, header years vs listed tenure), and seniority/scope "
                "anomalies. Raw signals, not verdicts. Takes no arguments."
            ),
            "parameters": _NO_ARGS,
        },
    },
    "find_recycled_or_inflated_claims": {
        "type": "function",
        "function": {
            "name": "find_recycled_or_inflated_claims",
            "description": (
                "Return the deterministic templated-inflation signals for the "
                "résumé under review: near-identical achievement bullets reused "
                "across unrelated roles, recycled quantified metrics with no "
                "detail, and junior/intern positions claiming enterprise-scale "
                "sole ownership. Raw signals, not verdicts. Takes no arguments."
            ),
            "parameters": _NO_ARGS,
        },
    },
    "classify_prompt_injection": {
        "type": "function",
        "function": {
            "name": "classify_prompt_injection",
            "description": (
                "Score one span of text with the configured prompt-injection "
                "classifier. Use it on a specific suspicious sentence quoted "
                "from the résumé. Returns {segment, labels:[{label, score}]}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "segment": {
                        "type": "string",
                        "description": (
                            "The exact text span to classify — a sentence or "
                            "line copied verbatim from the résumé."
                        ),
                    }
                },
                "required": ["segment"],
                "additionalProperties": False,
            },
        },
    },
}

TOOLS_BY_AGENT: dict[str, tuple[str, ...]] = {
    "manipulation_guard": ("scan_manipulation_patterns", "classify_prompt_injection"),
    "timeline_auditor": ("parse_resume_timeline", "check_timeline_consistency"),
    "inflation_auditor": ("find_recycled_or_inflated_claims",),
}


def specs_for(
    agent_name: str, *, with_classifier: bool = True, injection_model: str = ""
) -> list[dict]:
    """The `tools=` list to offer this sub-agent. When ``injection_model`` is
    given, the classifier spec names it (kept out of the module constant so the
    model id has a single source — the settings)."""
    names = TOOLS_BY_AGENT.get(agent_name, ())
    out: list[dict] = []
    for n in names:
        if n not in _SPECS:
            continue
        if n == "classify_prompt_injection":
            if not with_classifier:
                continue
            out.append(_classifier_spec(injection_model))
        else:
            out.append(_SPECS[n])
    return out


def _classifier_spec(injection_model: str) -> dict:
    spec = _SPECS["classify_prompt_injection"]
    if not injection_model.strip():
        return spec
    fn = dict(spec["function"])
    fn["description"] = fn["description"].replace(
        "the configured prompt-injection classifier",
        f"the configured prompt-injection classifier ({injection_model.strip()})",
    )
    return {**spec, "function": fn}


def _by_category(prescan: PrescanResult, agent: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for h in prescan.hits_for(agent):
        out.setdefault(h.category, []).append(
            {"evidence": h.evidence, "reason": h.reason, "pattern_key": h.pattern_key}
        )
    return out


async def run_tool(
    name: str,
    arguments: dict,
    *,
    prescan: PrescanResult,
    classify: Callable[[str], Awaitable[list[dict]]] | None = None,
) -> dict:
    """Dispatch one tool call. Never raises — a failure comes back as
    ``{"error": ...}`` so the agent loop can carry on."""
    arguments = arguments or {}

    if name == "scan_manipulation_patterns":
        by = _by_category(prescan, "manipulation_guard")
        return {
            "prompt_injection": by.get("PROMPT_INJECTION", []),
            "system_spoofing": by.get("SYSTEM_SPOOFING", []),
            "hidden_payload": by.get("HIDDEN_PAYLOAD", []),
            "hidden_or_zerowidth_runs": prescan.features.hidden_text_inventory,
            "note": (
                "Deterministic high-precision matches only. Read the résumé "
                "yourself as well — absence here is not proof of safety."
            ),
        }

    if name == "parse_resume_timeline":
        return {
            "roles": prescan.features.timeline_table,
            "note": (
                "Parsed date ranges. is_role_line=false usually means the line "
                "is prose, not a job entry."
            ),
        }

    if name == "check_timeline_consistency":
        by = _by_category(prescan, "timeline_auditor")
        return {
            "timeline_overlap": by.get("TIMELINE_OVERLAP", []),
            "chronological_error": by.get("CHRONOLOGICAL_ERROR", []),
            "seniority_anomaly": by.get("SENIORITY_ANOMALY", []),
        }

    if name == "find_recycled_or_inflated_claims":
        by = _by_category(prescan, "inflation_auditor")
        return {
            "recycled_metric": by.get("RECYCLED_METRIC", []),
            "unsubstantiated_inflation": by.get("UNSUBSTANTIATED_INFLATION", []),
            "duplicate_bullet_clusters": prescan.features.dup_clusters,
        }

    if name == "classify_prompt_injection":
        seg = str(arguments.get("segment", "")).strip()
        if not seg:
            return {"error": "segment is required and must be a non-empty string"}
        if classify is None:
            return {"error": "the prompt-injection classifier is not available here"}
        try:
            labels = await classify(seg)
        except Exception as exc:
            return {"error": f"classifier call failed: {exc}"}
        return {"segment": seg[:200], "labels": labels}

    return {"error": f"unknown tool {name!r}"}


def summarize(name: str, result: dict) -> str:
    """A one-line human summary of a tool result for the audit transcript."""
    if not isinstance(result, dict):
        return "ok"
    if "error" in result:
        return str(result["error"])
    if name == "scan_manipulation_patterns":
        n = sum(
            len(result.get(k, []))
            for k in ("prompt_injection", "system_spoofing", "hidden_payload")
        )
        return f"{n} deterministic manipulation hit(s)"
    if name == "parse_resume_timeline":
        return f"{len(result.get('roles', []))} date range(s) parsed"
    if name == "check_timeline_consistency":
        n = sum(
            len(result.get(k, []))
            for k in ("timeline_overlap", "chronological_error", "seniority_anomaly")
        )
        return f"{n} timeline inconsistency hit(s)"
    if name == "find_recycled_or_inflated_claims":
        n = len(result.get("recycled_metric", [])) + len(
            result.get("unsubstantiated_inflation", [])
        )
        return f"{n} recycled / inflation hit(s)"
    if name == "classify_prompt_injection":
        labels = result.get("labels") or []
        if labels:
            top = labels[0]
            return f"{top.get('label')} {top.get('score')}"
        return "no label returned"
    return "ok"
