"""Unicode normalisation + hidden-character inventory.

Returns the cleaned text plus a record of every run of zero-width / bidi /
control characters that was removed, so the manipulation detector can raise a
``HIDDEN_PAYLOAD`` flag that quotes where it was.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Characters that carry no visible glyph but survive copy-paste and text
# extraction. Not an exhaustive list — the common smuggling set.
ZERO_WIDTH = {
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "⁠",  # word joiner
    "﻿",  # BOM / zero-width no-break space
}
BIDI_CONTROLS = {chr(c) for c in range(0x202A, 0x202F)} | {
    chr(c) for c in range(0x2066, 0x206A)
}
SUSPICIOUS = ZERO_WIDTH | BIDI_CONTROLS

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass
class Normalized:
    clean_text: str
    hidden_runs: list[dict] = field(default_factory=list)  # {start, end, kind, sample}


def normalize(text: str) -> Normalized:
    # NFKC folds homoglyph / compatibility forms so a later regex sees the
    # canonical spelling.
    nfkc = unicodedata.normalize("NFKC", text)

    hidden_runs: list[dict] = []
    out: list[str] = []
    run_start: int | None = None
    run_chars: list[str] = []

    def flush(end: int) -> None:
        nonlocal run_start, run_chars
        if run_start is not None and len(run_chars) >= 3:
            kind = (
                "bidi" if any(c in BIDI_CONTROLS for c in run_chars) else "zero_width"
            )
            hidden_runs.append(
                {
                    "start": run_start,
                    "end": end,
                    "kind": kind,
                    "sample": "".join(f"U+{ord(c):04X}" for c in run_chars[:8]),
                }
            )
        run_start = None
        run_chars = []

    for i, ch in enumerate(nfkc):
        if ch in SUSPICIOUS:
            if run_start is None:
                run_start = i
            run_chars.append(ch)
            continue
        flush(i)
        out.append(ch)
    flush(len(nfkc))

    clean = _CONTROL_RE.sub("", "".join(out))

    return Normalized(clean_text=clean, hidden_runs=hidden_runs)
