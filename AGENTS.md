# candidate-screener

## Agent skills

### Issue tracker

Issues live as markdown files under `.scratch/<feature-slug>/` in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, used verbatim as `Status:` values. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
Backend layering is described in `docs/architecture.md`; the screening pipeline
in `docs/screening.md`.

## Code conventions (backend)

Keep the codebase readable by someone who joined last week.

- **Docstrings** — every module gets a one-line summary of what it is for.
  Functions get a docstring only when the name and signature don't already say
  it; add `Args` / `Returns` / `Raises` sections only where a reader would
  otherwise guess wrong.
- **Comments explain *why*, not *what*.** Keep the rationale notes in `auth/`,
  `utilities/config.py`, `utilities/extract.py`, `models/screening.py`, and the
  screening guard rails — delete anything that just narrates the next line.
- **Imports at module top.** The only allowed function-local imports are
  genuinely optional heavy dependencies: `openai`, `huggingface_hub`,
  `transformers`, `torch`, and `app.seed` (pulled in only when
  `SEED_DEMO_DATA=true`).
- **Dict literals** use `{"key": value}`, not `dict(key=value)`.
- **Routers** are thin: one `APIRouter(prefix="/api/...")` per resource,
  delegate to a `services.*` function, let `response_model=` define the output.
- **Layers don't skip.** Routers call services, services call repositories,
  repositories are the only place with SQL. `db.commit()` lives in services.
- **Run before pushing:** `cd backend && ruff check . && ruff format --check . &&
  mypy app && python -m pytest -m no_db` (or `pre-commit run --all-files`).
