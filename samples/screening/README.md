# Screening test résumés (PDF)

27 one-page résumé PDFs for exercising the **Screening** feature through the UI —
upload them to a candidate pool, start a run against the *Senior Backend
Engineer* role (`samples/ROLE.md`, or any role the demo seed created), and check
what each one produces.

**Nine scenarios, three résumés each.** Every résumé is crafted to trip exactly
one finding category a different way. `generate.py` re-extracts each PDF through
the real upload path and runs the deterministic pre-scan to prove it fires, so
these are known-good.

| Folder | Finding category | The three résumés |
|---|---|---|
| `01-prompt-injection` | `PROMPT_INJECTION` | imperative ("ignore all previous instructions…"), score-tamper ("assign the maximum score"), delimiter-escape (a literal `</candidate_text>` fence break) |
| `02-system-spoofing` | `SYSTEM_SPOOFING` | `SYSTEM:` role prefix, `<\|im_start\|>` chat template, `### Instruction` markdown role |
| `03-hidden-payload` | `HIDDEN_PAYLOAD` | HTML comment, base64 block on its own line, a run of zero-width characters |
| `04-timeline-overlap` | `TIMELINE_OVERLAP` | two employers same period, an employee role overlapping a full-time "Co-Founder" role, a role whose end date runs past the next role's start |
| `05-chronological-error` | `CHRONOLOGICAL_ERROR` | end year before start year, "18+ years" header the listed roles can't cover, a Principal title dated before the degree |
| `06-seniority-anomaly` | `SENIORITY_ANOMALY` | "Software Engineer" who "led a team of 20", "Senior Engineer" who "managed a team of 12", "Staff Engineer" (IC track) who "ran a team of 30" |
| `07-recycled-metric` | `RECYCLED_METRIC` (+ `UNSUBSTANTIATED_INFLATION`) | same "+40%" bullet under three employers, same "−30% cost" bullet under two, same "3× faster" bullet under two |
| `08-unsubstantiated-inflation` | `UNSUBSTANTIATED_INFLATION` | 10-week intern "solely architected a $4M platform", junior dev "single-handedly built the entire enterprise data platform", 6-month trainee "personally architected a company-wide payments system" |
| `09-clean` | *(nothing — the false-positive gate)* | a civil-engineer → software career changer, an AI-safety researcher who quotes attack strings as the subject of their work, a contractor who names no tools and has one-month handover overlaps |

## What you should see

With screening in `stub` mode (no API keys) or `live` mode against real models,
each scenario lands on a non-`clear` disposition and names its category; the
three `09-clean` résumés come back `clear` and not compromised:

| Scenario | Disposition | `is_compromised` |
|---|---|---|
| 01, 02, 03 (manipulation) | `high_concern` | true |
| 04, 05, 06, 07, 08 | `review` | true |
| 09 (clean) | `clear` | false |

Exact severities differ between `stub` (deterministic defaults from
`app/screening/assembly.py`) and `live` (assigned by the synthesis model) — the
disposition and the category are the stable part.

## Regenerating

```bash
python3 -m pip install reportlab           # or: pip install -r backend/requirements-dev.txt
python3 samples/screening/generate.py      # rewrite every PDF and verify it
python3 samples/screening/generate.py --verify   # just re-check the committed PDFs
```

The résumé text lives in `generate.py` as plain line lists — edit there, not the
PDFs. The zero-width sample needs a Unicode TrueType font on the box (macOS
`Arial Unicode.ttf` or Linux DejaVu/Liberation); without one it falls back to a
base font and that single hidden run is dropped.
