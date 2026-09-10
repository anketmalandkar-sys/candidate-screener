# The one way these checks are most likely to be wrong

A flagging system has its own bias risk: it can just as easily penalise an
**unusual but honest** résumé as catch a dishonest one. This note states the
single most likely failure mode and what we do about it. The same text is shown
in the app under "About screening".

## The failure mode

**Screening will flag the honest-but-atypical résumé as readily as the
dishonest one — and a false positive here has a real human cost.** Concretely:

- **`inflation_auditor`** misfires on people whose work genuinely *was*
  repetitive — agency and contract engineers doing the same migration for four
  clients, SREs describing on-call rotations, support engineers — and on anyone
  who learned résumé-writing from the same template, coach, or bootcamp.

- **`timeline_auditor`** misfires on non-linear careers: career changers,
  parental and caregiving leave, visa and relocation gaps, portfolio and
  contract careers with many short, sometimes overlapping engagements, and on
  **non-native English speakers** whose tense and date phrasing can read as
  contradictory when it is just a second language.

- **`manipulation_guard`** misfires on ordinary recruiter-facing notes
  ("authorised to work in the EU", "available from March"), academic CV
  formatting, extraction artefacts — and, distinctively, on candidates who
  legitimately **work in AI safety, prompt engineering, or LLM security**, whose
  résumés contain "prompt injection" or quote "ignore previous instructions" as
  the *subject* of their work, not as an instruction to the reader.

The demo pool already contains the trap: **Marcus Webb** describes every
technology indirectly and names almost none — an unusually *honest* senior
engineer a naive check reads as evasive.

## What we do about it

1. **Severity, never a veto.** Nothing is auto-rejected or removed from the
   ranking. `is_compromised` means "look at this", not "reject this". Screening
   annotates; the recruiter decides.

2. **Always exactly one explained entry per candidate.** The recruiter sees the
   quoted evidence and the reasoning and overrides in one click.

3. **A locked regression set of known-honest atypical résumés** — Marcus, the
   contractor / career-changer (fixture 13), the AI-safety researcher (fixture
   15). Every prompt or model change is scored against it. **Hard gate: nothing
   ships if any of them comes back compromised or with a `medium`+ finding**
   (`backend/tests/test_screening_bias.py`, and the live equivalent in
   `test_screening_live_smoke.py`).

4. **A mandatory `benign_explanation` on every finding.** If the synthesis
   engine cannot articulate a plausible innocent reading, it must lower the
   severity toward `info`. A deliberate brake on false positives.

5. **Copy discipline.** Reasons and recommended actions say "verify", "ask the
   candidate", "confirm in the screening call" — never "the candidate lied".
   Investigative, not a verdict.

6. **A pre-scan tuned for precision over recall.** The deterministic layer
   already skips an injection phrase when it sits amid security-research
   terminology (fixture 15 is clean at the pre-scan level), and the LLM agents
   are instructed to prefer the benign reading and `info`/`low` whenever an
   innocent explanation fits.

7. **The deterministic pre-scan is not optional.** Sub-agents 1–3 are
   tool-using agents (OpenAI `gpt-4.1-mini` by default), which adds a failure
   mode: an agent that over-trusts a single tool result, or never calls the
   manipulation tool at all, could miss an injection. The pre-scan still runs
   unconditionally and its coverage + canary check is still the floor — an
   un-explained manipulation hit is force-flagged regardless of what the agent
   returned. The tools return raw evidence, never verdicts, and every sub-agent
   call is `temperature=0` and bounded to `HF_SUBAGENT_MAX_TOOL_STEPS` rounds.

The honest framing for the recruiter: **screening narrows where you spend
attention; it does not make the call, and it is more likely to be wrong about
an unusual honest résumé than about a dishonest one — so treat a flag as a
question, not an answer.**
