"""Deterministic templated-inflation signals: recycled bullets across unrelated
roles, repeated round metrics, junior positions claiming enterprise ownership.
"""

from __future__ import annotations

import re

from app.screening.types import PrescanHit

_BULLET_RE = re.compile(r"^\s*[-*•▪]\s+(.*\S)", re.MULTILINE)
_METRIC_RE = re.compile(r"\b\d{1,3}%|\b\d+(?:\.\d+)?x\b", re.IGNORECASE)
_JUNIOR_RE = re.compile(
    r"\b(intern|internship|junior|trainee|apprentice|student|summer)\b", re.IGNORECASE
)
_SOLE_RE = re.compile(
    r"\b(sole(?:ly)?|single[- ]handed|from scratch|end[- ]to[- ]end|personally (?:owned|architected|built)|architected and delivered)\b",
    re.IGNORECASE,
)
_ENTERPRISE_RE = re.compile(
    r"(\$\s?\d[\d,.]*\s?(?:m|mm|million|bn|billion)|\bmulti-?million\b|\benterprise\b|"
    r"\bcompany-?wide\b|\borgani[sz]ation-?wide\b|\bmulti-?year (?:technical )?roadmap\b)",
    re.IGNORECASE,
)


def _blocks(text: str) -> list[tuple[str, list[str]]]:
    """Split into (header, bullets) blocks. A header is a non-bullet, non-blank
    line; bullets attach to the most recent header."""
    blocks: list[tuple[str, list[str]]] = []
    header = "TOP"
    bullets: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        bm = _BULLET_RE.match(line)
        if bm:
            bullets.append(bm.group(1).strip())
        elif line.strip():
            if bullets:
                blocks.append((header, bullets))
            header = line.strip()
            bullets = []
    if bullets:
        blocks.append((header, bullets))
    return blocks


def _shingles(bullet: str) -> set[str]:
    norm = re.sub(r"\d+", "#", bullet.lower())
    words = re.findall(r"[a-z#]+", norm)
    return {" ".join(words[i : i + 3]) for i in range(max(1, len(words) - 2))}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def scan(text: str) -> tuple[list[PrescanHit], list[dict]]:
    hits: list[PrescanHit] = []
    clusters: list[dict] = []
    blocks = _blocks(text)

    # Flatten bullets with their block index.
    flat: list[tuple[int, str, set[str]]] = []
    for bi, (_, bullets) in enumerate(blocks):
        for b in bullets:
            flat.append((bi, b, _shingles(b)))

    used: set[int] = set()
    for i in range(len(flat)):
        if i in used:
            continue
        bi, bullet, sh = flat[i]
        members = [(bi, bullet)]
        for j in range(i + 1, len(flat)):
            if j in used:
                continue
            bj, bullet_j, sh_j = flat[j]
            if _jaccard(sh, sh_j) >= 0.6:
                members.append((bj, bullet_j))
                used.add(j)
        distinct_blocks = {m[0] for m in members}
        if len(members) >= 2 and len(distinct_blocks) >= 2:
            used.add(i)
            headers = [blocks[b][0] for b in sorted(distinct_blocks)]
            clusters.append(
                {"bullet": bullet, "count": len(members), "blocks": headers}
            )
            hits.append(
                PrescanHit(
                    "inflation_auditor",
                    "RECYCLED_METRIC",
                    f"{bullet}  (repeated across: {', '.join(headers)})",
                    f"A near-identical achievement bullet appears under "
                    f"{len(distinct_blocks)} unrelated roles.",
                    "RECYCLED_METRIC:cross_role_duplicate",
                )
            )
            if _METRIC_RE.search(bullet):
                hits.append(
                    PrescanHit(
                        "inflation_auditor",
                        "UNSUBSTANTIATED_INFLATION",
                        bullet,
                        "A quantified impact claim reused verbatim across "
                        "employers with no system, baseline or method named.",
                        "UNSUBSTANTIATED_INFLATION:recycled_metric_no_detail",
                    )
                )

    # Junior / intern claiming enterprise-scale sole ownership.
    for header, bullets in blocks:
        if not _JUNIOR_RE.search(header):
            continue
        for b in bullets:
            if _SOLE_RE.search(b) and _ENTERPRISE_RE.search(b):
                hits.append(
                    PrescanHit(
                        "inflation_auditor",
                        "UNSUBSTANTIATED_INFLATION",
                        f"{header}  ||  {b}",
                        "An intern / junior position claiming sole architecture "
                        "and delivery of an enterprise-scale system — the scope "
                        "of the claim is not consistent with the role.",
                        "UNSUBSTANTIATED_INFLATION:junior_enterprise_claim",
                    )
                )

    return hits, clusters
