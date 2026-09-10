"""Deterministic timeline signals: concurrent full-time roles, chronological
inversions, summed-tenure vs header claim, seniority-vs-scope.

Produces both ``PrescanHit``s and a ``timeline_table`` for the feature bundle.
"""

from __future__ import annotations

import re
from datetime import date

from app.screening.types import PrescanHit

_CURRENT_YEAR = date.today().year

_MONTHS = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|"
    "january|february|march|april|june|july|august|september|october|november|december"
)
_YEAR = r"(?:19|20)\d{2}"
_END = rf"(?:{_YEAR}|present|current|now|ongoing|date)"
_RANGE_RE = re.compile(
    rf"(?P<start>(?:{_MONTHS})?\s*{_YEAR})\s*(?:[-–—]|to)\s*(?P<end>(?:{_MONTHS})?\s*{_END})",
    re.IGNORECASE,
)
_YEARS_CLAIM_RE = re.compile(
    r"(\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience|building|in|working|as)",
    re.IGNORECASE,
)
_DEGREE_RE = re.compile(
    rf"\b(?:BSc|BS|BA|B\.?Tech|MSc|MS|MA|MBA|PhD|Ph\.?D|Bachelor|Master|Doctorate)\b[^\n]*?({_YEAR})",
    re.IGNORECASE,
)
_SENIOR_SINCE_RE = re.compile(
    rf"\b(Principal|Staff|Senior|Lead|Head|Director|VP|Chief)\b[^\n]*?\bsince\s+({_YEAR})",
    re.IGNORECASE,
)
_TEAM_SIZE_RE = re.compile(
    r"\b(?:led|managed|ran|headed)\b[^\n]{0,25}\bteam of\s+(\d{1,3})", re.IGNORECASE
)
_PARTTIME_RE = re.compile(
    r"\b(part[- ]time|contract|contractor|freelan|intern|internship|advisor|advisory|consult)\b",
    re.IGNORECASE,
)
# Deliberately does NOT include a bare "lead" — it is a common verb and produces
# false negatives on the seniority check. Real management signals only.
_MGMT_TITLE_RE = re.compile(
    r"\b(manager|management|\bhead of\b|director|\bvp\b|chief|people lead|"
    r"engineering lead|eng lead)\b",
    re.IGNORECASE,
)
# A line that reads like a job entry: starts with a capitalised word, is not
# prose (no leading pronoun), reasonably short, and carries a company/date cue.
_ROLE_LINE_RE = re.compile(r"^[A-Z][^\n]{0,90}?(?:,| at |\(| [–-] )", re.MULTILINE)
_PROSE_START_RE = re.compile(
    r"^(I|We|My|Our|Since|After|Before|During)\b", re.IGNORECASE
)


def _year(token: str) -> int | None:
    m = re.search(_YEAR, token)
    if m:
        return int(m.group(0))
    if re.search(r"present|current|now|ongoing|date", token, re.IGNORECASE):
        return _CURRENT_YEAR
    return None


def _line_of(text: str, idx: int) -> str:
    start = text.rfind("\n", 0, idx) + 1
    end = text.find("\n", idx)
    return text[start : end if end != -1 else len(text)].strip()


def scan(text: str) -> tuple[list[PrescanHit], list[dict]]:
    hits: list[PrescanHit] = []
    table: list[dict] = []

    roles: list[dict] = []
    for m in _RANGE_RE.finditer(text):
        line = _line_of(text, m.start())
        s, e = _year(m.group("start")), _year(m.group("end"))
        if s is None or e is None:
            continue
        is_role_line = (
            len(line) <= 110
            and not _PROSE_START_RE.match(line)
            and _ROLE_LINE_RE.match(line) is not None
        )
        entry = {
            "line": line,
            "start": s,
            "end": e,
            "full_time": not bool(_PARTTIME_RE.search(line)),
            "is_role_line": is_role_line,
        }
        roles.append(entry)
        table.append(entry)

    # 1. Chronological inversion: end precedes start.
    for r in roles:
        if r["end"] < r["start"]:
            hits.append(
                PrescanHit(
                    "timeline_auditor",
                    "CHRONOLOGICAL_ERROR",
                    r["line"],
                    f"The end year ({r['end']}) precedes the start year ({r['start']}).",
                    "CHRONOLOGICAL_ERROR:end_before_start",
                )
            )

    # 2. Concurrent full-time roles overlapping by > 12 months. Compare only
    # lines that read like job entries — never summary prose.
    ft = [
        r
        for r in roles
        if r["full_time"] and r["is_role_line"] and r["end"] >= r["start"]
    ]
    seen_pairs: set[tuple] = set()
    for i in range(len(ft)):
        for j in range(i + 1, len(ft)):
            a, b = ft[i], ft[j]
            overlap = min(a["end"], b["end"]) - max(a["start"], b["start"])
            key = tuple(sorted((a["line"], b["line"])))
            if overlap > 1 and a["line"] != b["line"] and key not in seen_pairs:
                seen_pairs.add(key)
                hits.append(
                    PrescanHit(
                        "timeline_auditor",
                        "TIMELINE_OVERLAP",
                        f"{a['line']}  ||  {b['line']}",
                        f"Two roles both presented as full-time overlap by about "
                        f"{overlap} years.",
                        "TIMELINE_OVERLAP:concurrent_fulltime",
                    )
                )

    # 3. "N+ years" header vs the non-overlapping union of listed tenure.
    claim_m = _YEARS_CLAIM_RE.search(text)
    if claim_m and roles:
        claimed = int(claim_m.group(1))
        intervals = sorted(
            (r["start"], r["end"]) for r in roles if r["end"] >= r["start"]
        )
        union = 0
        cur_s = cur_e = None
        for s, e in intervals:
            if cur_e is None or s > cur_e:
                if cur_e is not None:
                    union += cur_e - cur_s
                cur_s, cur_e = s, e
            else:
                cur_e = max(cur_e, e)
        if cur_e is not None:
            union += cur_e - cur_s
        span_start = intervals[0][0] if intervals else _CURRENT_YEAR
        actual = max(union, _CURRENT_YEAR - span_start)
        if claimed - actual >= 2:
            hits.append(
                PrescanHit(
                    "timeline_auditor",
                    "CHRONOLOGICAL_ERROR",
                    f"{_line_of(text, claim_m.start())}  ||  earliest listed role starts {span_start}",
                    f"Header claims {claimed}+ years; the listed roles account for "
                    f"about {actual} years.",
                    "CHRONOLOGICAL_ERROR:tenure_mismatch",
                )
            )

    # 4. Senior title dated before the degree that would qualify it.
    for sm in _SENIOR_SINCE_RE.finditer(text):
        since = int(sm.group(2))
        for dm in _DEGREE_RE.finditer(text):
            deg = int(dm.group(1))
            if deg > since + 1:
                hits.append(
                    PrescanHit(
                        "timeline_auditor",
                        "CHRONOLOGICAL_ERROR",
                        f"{_line_of(text, sm.start())}  ||  {_line_of(text, dm.start())}",
                        f"A {sm.group(1)} title dated from {since}, "
                        f"{deg - since} years before the listed degree in {deg}.",
                        "CHRONOLOGICAL_ERROR:title_before_degree",
                    )
                )
                break

    # 5. Team-of-N leadership under a non-management title.
    for tm in _TEAM_SIZE_RE.finditer(text):
        n = int(tm.group(1))
        line = _line_of(text, tm.start())
        # Just the current line plus the one before it — enough to see the role
        # header, not so much that a stray "manager" elsewhere suppresses it.
        block_start = text.rfind("\n", 0, text.rfind("\n", 0, tm.start()))
        window = text[max(0, block_start) : tm.start() + 80]
        if n >= 8 and not _MGMT_TITLE_RE.search(window):
            hits.append(
                PrescanHit(
                    "timeline_auditor",
                    "SENIORITY_ANOMALY",
                    line,
                    f"Leadership of a team of {n} stated without a management "
                    "title nearby.",
                    "SENIORITY_ANOMALY:scope_vs_title",
                )
            )

    return hits, table
