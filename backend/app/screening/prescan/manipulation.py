"""Deterministic manipulation signals: prompt injection, delimiter escapes,
fake system markers, hidden payloads.

High precision by design — these feed the ``manipulation_guard`` sub-agent as
evidence, and the verifier's coverage check treats an un-explained hit here as
proof the LLM missed an injection.
"""

from __future__ import annotations

import re

from app.screening.prescan.normalize import Normalized
from app.screening.types import PrescanHit

_FLAGS = re.IGNORECASE | re.MULTILINE

_INJECTION_PATTERNS: list[tuple[str, str]] = [
    (
        r"\b(ignore|disregard|forget)\b[^\n]{0,40}\b(previous|prior|above|earlier|all)\b[^\n]{0,25}\b(instruction|instructions|prompt|prompts|context)\b",
        "PROMPT_INJECTION:imperative_to_ai",
    ),
    (
        r"\bas (an?|the) (ai|assistant|language model|hiring ai|automated (reader|screener|system))\b",
        "PROMPT_INJECTION:roleplay_framing",
    ),
    (
        r"\b(assign|give|award|set)\b[^\n]{0,30}\b(maximum|highest|top|perfect|full|100)\b[^\n]{0,15}\b(score|rating|rank|marks?)\b",
        "PROMPT_INJECTION:score_tamper",
    ),
    (
        r"\b(do not|don'?t|never)\b[^\n]{0,20}\b(mention|report|disclose|reveal|flag|note)\b[^\n]{0,20}\b(this|the)\b[^\n]{0,15}\b(message|note|instruction|text)\b",
        "PROMPT_INJECTION:suppress_notice",
    ),
    (
        r"\b(note|message|instruction)s?\b[^\n]{0,25}\b(to|for)\b[^\n]{0,15}\b(any )?(automated|ai|ats|screening|bot)\b",
        "PROMPT_INJECTION:out_of_band_appeal",
    ),
    (
        r"\b(priorit(is|iz)e|expedite|fast[- ]track|ensure)\b[^\n]{0,30}\b(this )?(application|candidate|profile|resume|cv)\b",
        "PROMPT_INJECTION:out_of_band_appeal",
    ),
]

_SYSTEM_MARKER_PATTERNS: list[tuple[str, str]] = [
    (r"^[ \t]*(SYSTEM|ASSISTANT|USER)[ \t]*:", "SYSTEM_SPOOFING:role_prefix"),
    (r"<\|im_(start|end)\|>", "SYSTEM_SPOOFING:chat_template"),
    (
        r"^[ \t]*#{2,3}[ \t]*(Instruction|System|Assistant)\b",
        "SYSTEM_SPOOFING:markdown_role",
    ),
    (r"\bas the (system|hiring ai|evaluator)\b", "SYSTEM_SPOOFING:role_claim"),
]

# The data fence the sub-agents wrap candidate text in. A literal occurrence in
# the body is an attempt to break out of it.
_FENCE_TOKENS = ("</candidate_text>", "<candidate_text>", "</resume>", "<resume>")

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BASE64_LINE_RE = re.compile(r"^[A-Za-z0-9+/]{40,}={0,2}\s*$", re.MULTILINE)

# Words that signal a phrase like "ignore previous instructions" is the SUBJECT
# of the candidate's security work, not an instruction to the reader. Two or
# more within the surrounding window suppress the softer injection patterns
# (never the hard ones: score_tamper, suppress_notice, delimiter_escape,
# system-role markers).
_LEGIT_CONTEXT_RE = re.compile(
    r"\b(attack|payload|jailbreak|red[- ]?team|adversarial|threat model|"
    r"prompt[- ]?injection|injection detection|detection classifier|classifier|"
    r"defen[cs]|mitigat|guardrail|benchmark|evaluat|vulnerabilit|CVE|taxonomy|"
    r"security research|penetration test|exploit|hardening)\b",
    re.IGNORECASE,
)
_SOFT_INJECTION_KEYS = {
    "PROMPT_INJECTION:imperative_to_ai",
    "PROMPT_INJECTION:roleplay_framing",
    "PROMPT_INJECTION:out_of_band_appeal",
}


def _looks_like_security_terminology(text: str, idx: int) -> bool:
    window = text[max(0, idx - 220) : idx + 220]
    return len(set(_LEGIT_CONTEXT_RE.findall(window))) >= 2


def _line_containing(text: str, idx: int) -> str:
    start = text.rfind("\n", 0, idx) + 1
    end = text.find("\n", idx)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


def scan(text: str, norm: Normalized) -> list[PrescanHit]:
    hits: list[PrescanHit] = []
    seen: set[tuple[str, str]] = set()

    def add(category: str, evidence: str, reason: str, pattern_key: str) -> None:
        key = (pattern_key, evidence[:120])
        if key in seen or not evidence.strip():
            return
        seen.add(key)
        hits.append(
            PrescanHit(
                agent="manipulation_guard",
                category=category,
                evidence=evidence.strip(),
                reason=reason,
                pattern_key=pattern_key,
            )
        )

    # One PROMPT_INJECTION flag per offending line — several patterns often hit
    # the same sentence and the recruiter only needs to see it once.
    injection_lines: set[str] = set()
    for pattern, key in _INJECTION_PATTERNS:
        for m in re.finditer(pattern, text, _FLAGS):
            if key in _SOFT_INJECTION_KEYS and _looks_like_security_terminology(
                text, m.start()
            ):
                # e.g. an AI-safety researcher quoting an attack string — the
                # LLM tier is the second net; do not raise a deterministic flag.
                continue
            line = _line_containing(text, m.start())
            if line in injection_lines:
                continue
            injection_lines.add(line)
            add(
                "PROMPT_INJECTION",
                line,
                "Matches a known prompt-injection shape aimed at an automated "
                "reader rather than the recruiter.",
                key,
            )

    for pattern, key in _SYSTEM_MARKER_PATTERNS:
        for m in re.finditer(pattern, text, _FLAGS):
            add(
                "SYSTEM_SPOOFING",
                _line_containing(text, m.start()),
                "A line formatted to impersonate a system / assistant turn to "
                "the model reading the resume.",
                key,
            )

    for token in _FENCE_TOKENS:
        pos = text.find(token)
        if pos != -1:
            add(
                "PROMPT_INJECTION",
                _line_containing(text, pos),
                f"Contains a literal {token!r} delimiter — an attempt to escape "
                "the data fence the resume is wrapped in.",
                "PROMPT_INJECTION:delimiter_escape",
            )

    for m in _HTML_COMMENT_RE.finditer(text):
        add(
            "HIDDEN_PAYLOAD",
            m.group(0)[:200],
            "An HTML comment — content hidden from a human reader of the "
            "rendered document.",
            "HIDDEN_PAYLOAD:html_comment",
        )

    for m in _BASE64_LINE_RE.finditer(text):
        add(
            "HIDDEN_PAYLOAD",
            m.group(0)[:120],
            "A long base64-looking block on its own line — an unusual payload "
            "for a resume.",
            "HIDDEN_PAYLOAD:base64_block",
        )

    for run in norm.hidden_runs:
        add(
            "HIDDEN_PAYLOAD",
            f"[{run['kind']} run, {run['sample']}]",
            "A run of zero-width or bidirectional-control characters — "
            "invisible to a human reader, placed to carry text to an automated "
            "one.",
            f"HIDDEN_PAYLOAD:{run['kind']}",
        )

    return hits
