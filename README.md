# Candidate Screener

An internal HR tool: define an open role with its must-have requirements, and
keep a pool of applicant résumés to work through.

- **Backend** — FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16
- **Frontend** — React 18, Vite, TypeScript
- **Auth** — email + password, Argon2id, JWT in an httpOnly cookie

---

## Running it

```bash
cp .env.example .env

# Generate a signing key and put it in .env as APP_SECRET_KEY.
# The app refuses to start without one — see "Auth" below.
openssl rand -hex 32

docker compose up --build     # Postgres + API; migrations run on startup
```

In a second terminal:

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Open http://localhost:5173, create an account, and you are in. There are no
seeded users and no demo credentials — registration is the only way in, which
is the point.

API docs are at http://localhost:8000/docs.

### Tests

```bash
docker compose exec backend pytest
```

The suite TRUNCATEs tables between cases, so it runs against an **isolated
database**, never the dev one. `conftest.py` rewrites `DATABASE_URL` to a
sibling database whose name ends in `_test` (`candidate_screener_test`) and
creates it on first run; `clean_database` refuses to truncate anything else.
Point it elsewhere with `TEST_DATABASE_URL` (must still end in `_test`). Tests
that touch no database are marked `no_db` and run standalone with
`python3 -m pytest -m no_db`.

### Trying it with the sample data

`samples/` has a role definition and eight résumés you can paste in, for the
**scoring** demo. Start with [`samples/ROLE.md`](samples/ROLE.md).

For the **screening** feature, [`samples/screening/`](samples/screening/) has 27
one-page résumé PDFs — nine finding scenarios, three résumés each, plus a
"clean" set that must stay `clear` — ready to upload. See
[`samples/screening/README.md`](samples/screening/README.md).

### Seeding a full demo dataset

Set `SEED_DEMO_DATA=true` in `.env`. Every account you register then gets its
own private copy of ~6 roles and 120+ synthetic candidates
(`backend/app/seed/dataset.py`) — so the demo data is there for everyone, with
no shared-ownership special cases.

This does **not** weaken the "no seeded credentials" stance above: seeding never
creates a login, it only fills an account you already registered.

For accounts that already exist, run it on demand (idempotent):

```bash
docker compose exec backend python -m app.seed                 # every account
docker compose exec backend python -m app.seed --email you@example.com
docker compose exec backend python -m app.seed --reset         # rebuild
```

### One-command UI walkthrough data

To click through **everything** — including the Screening section with real
`clear` / `review` / `high_concern` / compromised results — seed a dedicated
dev account that also loads the screening fixtures and runs a couple of
screenings in `stub` mode (no API keys, no network):

```bash
docker compose exec backend python -m app.seed.ui_demo
# -> account ui-demo@example.com / password UiDemo123!  (override with --email / --password; --reset rebuilds)
```

Then `cd frontend && npm run dev` and log in with the printed credentials. Like
`app.seed`, this only fills an account it creates on request — no special
powers, no shared state.

---

## Roles and requirements

Each requirement carries a weight — must (3), important (2), nice (1) — and an
optional list of recruiter-supplied aliases. Editing a role's requirement list
replaces it wholesale, in one transaction.

---

## Screening

The **Screening** section runs three integrity checks on each résumé before it
is scored — manipulation / prompt injection, internal-consistency, and
templated inflation — across isolated agents, and never acts on an instruction
found in a résumé nor silently drops a candidate. It runs in a no-network
`stub` mode by default; a `live` mode uses Hugging Face Inference for detection
and OpenAI for synthesis and comparison.

See [`docs/screening.md`](docs/screening.md) and, for the bias-risk note the
brief asks for, [`docs/screening-bias-note.md`](docs/screening-bias-note.md).

---

## Auth

The brief said this would be looked at closely, so here is what is there and why.

- **Argon2id** via `argon2-cffi`, in PHC string format so parameters travel with
  the hash. `check_needs_rehash` upgrades an existing user's hash transparently
  on their next successful login.
- **No credentials anywhere in the repo.** No seeded users, no demo account, no
  fallback admin. `.env` is gitignored; `.env.example` holds placeholders only.
- **The app refuses to boot** if `APP_SECRET_KEY` is missing, empty, still the
  `.env.example` placeholder, or under 32 characters
  ([`utilities/config.py`](backend/app/utilities/config.py)). A weak signing key is not a degraded
  mode — anyone can mint a token for any account — so it fails loudly instead.
- **Session JWT in an httpOnly, SameSite=Lax cookie**, never `localStorage`. A
  token readable from JavaScript is a token a single XSS exfiltrates. `Secure`
  is set when `COOKIE_SECURE=true`.
- **`algorithms` is pinned** to a single value on decode, which is what blocks
  the `alg: none` and RS256→HS256 confusion attacks. Tested.
- **No account enumeration.** Unknown email and wrong password return an
  identical status and an identical body, and the unknown-email path burns an
  Argon2 verify against a dummy hash so response timing does not leak either.
- **Login throttling** on failed attempts, keyed on client IP *and* submitted
  email, so one host cannot spray many addresses and one attacker cannot lock a
  specific user out from elsewhere. `X-Forwarded-For` is trusted only as far as
  `TRUSTED_PROXY_COUNT` says it should be.
- **Tenant isolation on every route.** Every resource is filtered by the owning
  user through one owned-resource dependency in
  [`auth/dependencies.py`](backend/app/auth/dependencies.py) — `get_owned_role`,
  `get_owned_candidate` — each resolving the current user through the same
  `get_current_user`. Fetching another recruiter's resource returns **404, not
  403** — a 403 confirms the id exists, which lets an attacker enumerate other
  tenants. There is a test for exactly this.
- Dev runs behind a Vite proxy on `/api`, so local development is same-origin
  and the cookie policy behaves identically to production.

Password policy is 8 to 10 characters, and must include at least one lowercase
letter, one uppercase letter, one digit, and one special character (anything
that is neither alphanumeric nor whitespace). The rules live in one place,
[`schemas/auth.py`](backend/app/schemas/auth.py), and the register form mirrors
them for fast feedback while the server stays authoritative.

---

## Data model

```
User ─┬─ Role ── Requirement
      └─ Candidate
```

A candidate is a **pool entry owned directly by the recruiter**. It carries one
résumé and is not attached to any role. Both `Role` and `Candidate` carry
`user_id`, so authorisation is a single filter on either side.

---

## File intake

Paste is the primary path. Upload accepts PDF, DOCX and TXT, validated
cheapest-check-first: size cap (5 MB), then extension allowlist, then **magic
bytes** — the extension is a claim, the leading bytes are evidence — then the
parse. Encrypted PDFs and image-only scans are rejected with a message written
to be shown to the recruiter as-is.

DOCX extraction reads table cells as well as paragraphs; plenty of résumés lay
everything out in a table, and skipping those would silently produce an empty
résumé.

**Only the extracted text is stored, never the uploaded binary.** A deliberate
cut: keeping the original would pull in blob storage, a retention policy, and
PII-at-rest questions the brief does not ask about, and the text is all the tool
needs.

---

## Deliberate cuts

Things a production version needs that this does not have, listed so they are
choices rather than oversights:

- **Rate limiting is in-process**, so it is per-instance — two API replicas would
  each allow the full budget. The fix is a shared Redis counter.
- **No password reset or email verification.** Both need an email provider and a
  token lifecycle, which is a feature in its own right.
- **No org/team sharing.** Data is scoped to a single recruiter. Teams need a
  membership model and a role hierarchy.
- **Pagination is offset-based** (`?limit=&offset=`), which is simple and fine at
  this scale; a very large, fast-changing pool would want keyset pagination so
  rows can't shift between pages.
- **Search is client-side**, over the current page only. A pool-wide search
  belongs in the query.
- **No audit log.** A hiring tool used for real should record who changed which
  requirement and when.
- **No duplicate detection** on résumés pasted twice.

## Layout

Package by layer. A request flows `routers → services → repositories → models`;
`schemas/` are the DTOs.

```
backend/
  app/
    main.py               # assembly: CORS + router mounts
    utilities/            # dependency-free helpers
      config.py           #   env-driven settings
      common.py           #   weight constants + utcnow
      extract.py          #   PDF/DOCX/TXT résumé extraction
    auth/                 # authentication: primitives + request guards
      security.py         #   Argon2, JWT, login throttle
      dependencies.py     #   get_current_user, get_owned_role, get_owned_candidate
    models/               # ORM entities, one per file
      base.py             #   the declarative Base
      user.py  role.py  requirement.py  candidate.py
    schemas/              # pydantic DTOs
      common.py  auth.py  role.py  candidate.py
    repositories/         # every SQLAlchemy query, keyed by aggregate
      database.py         #   engine / session / get_db
      users.py  roles.py  candidates.py
    services/             # business logic + transaction boundary
      auth.py  roles.py  candidates.py
    routers/              # thin HTTP controllers
      auth.py  roles.py  candidates.py
    seed/                 # demo-data tooling
      dataset.py  loader.py  __main__.py   # `python -m app.seed`
      ui_demo.py                           # `python -m app.seed.ui_demo` — pool + screening runs
  tests/
frontend/src/
  client.ts             # the shared fetch wrapper
  api.ts                # core endpoints, composed with candidates/api.ts
  candidates/            # the candidate pool page, AddCandidate, types + api
  components/            # RoleForm, RequirementRows
  pages/                # login, register, roles (management)
samples/                # a role and eight résumés (scoring); read ROLE.md
  screening/            # 27 résumé PDFs, 9 finding scenarios × 3 (screening)
```
