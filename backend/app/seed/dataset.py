"""Synthetic demo dataset — pure, deterministic, no database.

`build_dataset()` returns a list of `(SeedRole, [SeedCandidate])` covering ~6
roles and 120+ candidates. Every candidate is generated from a fixed
`random.Random(RANDOM_SEED)`, so the output is byte-identical across runs and
tests can assert on it. `app.seed` inserts the rows; candidates land in the
recruiter's pool and are not attached to any role.

What this module controls is *which requirement terms land in each resume*, via
an "archetype" per candidate, so the pool holds a realistic spread from resumes
that name every requirement to ones from an entirely different field:

    full_match       every requirement named
    keyword_stuffed  every requirement named, but the prose says
                     "haven't shipped since 2021"
    strong           one non-must dropped
    missing_must     one must-have dropped
    partial          one must + a few others
    adjacent         a single requirement
    prose_only       work described, no tool ever named
    off_domain       a resume from another field
"""

from __future__ import annotations

import random
from dataclasses import dataclass

RANDOM_SEED = 1_234_567

# The context date the rest of the repo is written against.
_CURRENT_YEAR = 2026


@dataclass(frozen=True)
class SeedRequirement:
    label: str
    weight: str  # "must" | "important" | "nice" — keys of app.utilities.common.WEIGHT_VALUES
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SeedRole:
    title: str
    description: str
    requirements: tuple[SeedRequirement, ...]


@dataclass(frozen=True)
class SeedCandidate:
    name: str
    email: str | None
    resume_text: str
    source: str  # "paste" | "upload"
    original_filename: str | None


# --------------------------------------------------------------------------- #
# Roles. Every role sums to a total weight of 12 (two musts, two importants,   #
# two nices) so the archetype -> score mapping is the same everywhere.         #
# --------------------------------------------------------------------------- #

SEED_ROLES: tuple[SeedRole, ...] = (
    SeedRole(
        title="Senior Backend Engineer",
        description=(
            "Owns our payments and billing services. Works close to the data "
            "model and is comfortable operating what they ship."
        ),
        requirements=(
            SeedRequirement("Python", "must"),
            SeedRequirement("PostgreSQL", "must", ("postgres",)),
            SeedRequirement("Docker", "important", ("containers",)),
            SeedRequirement("Kubernetes", "important"),
            SeedRequirement("REST API", "nice", ("rest apis",)),
            SeedRequirement("Terraform", "nice", ("infrastructure as code",)),
        ),
    ),
    SeedRole(
        title="Frontend Engineer",
        description=(
            "Builds the recruiter-facing web app and owns the design system. "
            "Cares about accessibility and keeping the bundle honest."
        ),
        requirements=(
            SeedRequirement("TypeScript", "must", ("ts",)),
            SeedRequirement("React", "must", ("reactjs",)),
            SeedRequirement("CSS", "important", ("scss",)),
            SeedRequirement(
                "Automated testing", "important", ("test automation", "unit testing")
            ),
            SeedRequirement("Accessibility", "nice", ("a11y",)),
            SeedRequirement("Next.js", "nice"),
        ),
    ),
    SeedRole(
        title="Data Engineer",
        description=(
            "Owns the batch and streaming pipelines that feed reporting and the "
            "scoring warehouse. On call for the nightly loads."
        ),
        requirements=(
            SeedRequirement("Python", "must"),
            SeedRequirement("SQL", "must"),
            SeedRequirement("Airflow", "important", ("apache airflow",)),
            SeedRequirement("dbt", "important"),
            SeedRequirement("Spark", "nice", ("apache spark",)),
            SeedRequirement("AWS", "nice", ("amazon web services",)),
        ),
    ),
    SeedRole(
        title="Platform Engineer",
        description=(
            "Runs the clusters, the delivery pipeline and the paved road every "
            "other team ships on. Treats infrastructure as a product."
        ),
        requirements=(
            SeedRequirement("Kubernetes", "must", ("k8s",)),
            SeedRequirement("Terraform", "must", ("infrastructure as code",)),
            SeedRequirement("Docker", "important", ("containers",)),
            SeedRequirement("AWS", "important"),
            SeedRequirement("CI/CD", "nice", ("continuous integration",)),
            SeedRequirement("Linux", "nice"),
        ),
    ),
    SeedRole(
        title="Machine Learning Engineer",
        description=(
            "Takes models from a notebook to a served endpoint and keeps them "
            "healthy. Half research, half production engineering."
        ),
        requirements=(
            SeedRequirement("Python", "must"),
            SeedRequirement("Machine learning", "must", ("ml",)),
            SeedRequirement("PyTorch", "important"),
            SeedRequirement("SQL", "important"),
            SeedRequirement("NLP", "nice", ("natural language processing",)),
            SeedRequirement("Docker", "nice"),
        ),
    ),
    SeedRole(
        title="Full-Stack Engineer",
        description=(
            "Ships product end to end — schema, API and screen — for a small "
            "team that values breadth and follow-through."
        ),
        requirements=(
            SeedRequirement("TypeScript", "must"),
            SeedRequirement("React", "must"),
            SeedRequirement("Node.js", "important", ("nodejs",)),
            SeedRequirement("PostgreSQL", "important", ("postgres",)),
            SeedRequirement("REST API", "nice"),
            SeedRequirement("Docker", "nice"),
        ),
    ),
)

SEED_ROLE_TITLES: frozenset[str] = frozenset(role.title for role in SEED_ROLES)


# --------------------------------------------------------------------------- #
# Vocabulary                                                                   #
# --------------------------------------------------------------------------- #

# Per-role framing. Every value is checked to contain no requirement term (nor
# any built-in synonym) so it can never produce an accidental match.
ROLE_META: dict[str, dict[str, str]] = {
    "Senior Backend Engineer": {
        "headline": "Backend Engineer",
        "noun": "backend engineer",
        "domain": "payments and billing",
    },
    "Frontend Engineer": {
        "headline": "Frontend Engineer",
        "noun": "frontend engineer",
        "domain": "customer-facing web",
    },
    "Data Engineer": {
        "headline": "Data Engineer",
        "noun": "data engineer",
        "domain": "batch and streaming data",
    },
    "Platform Engineer": {
        "headline": "Platform Engineer",
        "noun": "platform engineer",
        "domain": "cloud platform and delivery",
    },
    "Machine Learning Engineer": {
        "headline": "Prediction Systems Engineer",
        "noun": "prediction-systems engineer",
        "domain": "applied prediction",
    },
    "Full-Stack Engineer": {
        "headline": "Full-Stack Engineer",
        "noun": "full-stack engineer",
        "domain": "end-to-end product",
    },
}

# How the `prose_only` archetype refers to each requirement without ever naming
# it. Keys cover every label used across SEED_ROLES.
PARAPHRASES: dict[str, str] = {
    "Python": "the language the codebase standardised on",
    "PostgreSQL": "the relational database everything is stored in",
    "Docker": "reproducible build-and-runtime images",
    "Kubernetes": "the container orchestration layer",
    "REST API": "resource-oriented HTTP services",
    "Terraform": "declarative infrastructure definitions",
    "TypeScript": "a statically typed browser language",
    "React": "a declarative component rendering library",
    "CSS": "the visual styling system",
    "Automated testing": "a fast regression safety net",
    "Accessibility": "first-class support for assistive technology",
    "Next.js": "a server-rendered web framework",
    "SQL": "hand-written analytical queries",
    "Airflow": "a scheduled pipeline orchestrator",
    "dbt": "a warehouse transformation framework",
    "Spark": "a distributed batch compute engine",
    "AWS": "a large public cloud footprint",
    "CI/CD": "an automated build and release pipeline",
    "Linux": "hardened server operating systems",
    "Machine learning": "predictive statistical models",
    "PyTorch": "a tensor and autograd framework",
    "NLP": "systems that read and classify free text",
    "Node.js": "a server-side scripting runtime",
}

FIRST_NAMES = [
    "Ana",
    "Bao",
    "Chika",
    "Dmitri",
    "Elena",
    "Farah",
    "Grace",
    "Hassan",
    "Ines",
    "Jamal",
    "Keiko",
    "Liam",
    "Mei",
    "Niamh",
    "Omar",
    "Priya",
    "Quinn",
    "Rosa",
    "Sanjay",
    "Tomas",
    "Uma",
    "Viktor",
    "Wen",
    "Xolani",
    "Yara",
    "Zane",
    "Aditi",
    "Bjorn",
    "Carlos",
    "Deepa",
    "Ewan",
    "Fatima",
    "Gabriel",
    "Hana",
    "Ivan",
    "Jing",
    "Kofi",
    "Lucia",
    "Marek",
    "Nadia",
]

LAST_NAMES = [
    "Adeyemi",
    "Bianchi",
    "Chen",
    "Dupont",
    "Eriksson",
    "Fernandez",
    "Gupta",
    "Haddad",
    "Ivanova",
    "Johansson",
    "Kaur",
    "Lindqvist",
    "Mwangi",
    "Nakamura",
    "Okafor",
    "Patel",
    "Quintero",
    "Rossi",
    "Silva",
    "Tanaka",
    "Ueda",
    "Volkov",
    "Watanabe",
    "Xu",
    "Yilmaz",
    "Zhang",
    "Andersson",
    "Bello",
    "Costa",
    "Diallo",
    "Nguyen",
    "OBrien",
    "Petrov",
    "Reyes",
    "Santos",
    "Thompson",
    "Novak",
    "Kowalski",
    "Muller",
    "Park",
]

LOCATIONS = [
    "Berlin",
    "Lisbon",
    "Toronto",
    "Bengaluru",
    "Sao Paulo",
    "Nairobi",
    "Manchester",
    "Austin",
    "Amsterdam",
    "Warsaw",
    "Singapore",
    "Dublin",
    "Melbourne",
    "Tallinn",
    "Bogota",
    "Cape Town",
]

COMPANIES = [
    "Northwind",
    "Aperture Labs",
    "Meridian",
    "BlueKite",
    "Fathom",
    "Cobalt",
    "Riverbank",
    "Larkspur",
    "Tessellate",
    "Wavelength",
    "Ironclad",
    "Sundial",
    "Halcyon",
    "Verdant",
    "Quorum",
    "Lattice Works",
]

UNIVERSITIES = [
    "TU Delft",
    "University of Manchester",
    "University of Toronto",
    "IIT Bombay",
    "University of Sao Paulo",
    "University of Nairobi",
    "UT Austin",
    "University of Amsterdam",
    "Warsaw University of Technology",
    "National University of Singapore",
    "Trinity College Dublin",
    "University of Melbourne",
]

DEGREES = [
    "BSc Computer Science",
    "MSc Software Engineering",
    "BEng Computer Engineering",
    "BSc Mathematics and Computing",
    "MSc Data Science",
]

JOB_TITLES = [
    "Software Engineer",
    "Senior Software Engineer",
    "Staff Engineer",
    "Senior Engineer",
]

# Skills that appear on every resume as filler. None is a requirement term or a
# built-in synonym of one.
NOISE_SKILLS = [
    "Git",
    "Agile",
    "Scrum",
    "Jira",
    "Confluence",
    "code review",
    "pair programming",
    "technical writing",
    "incident response",
    "on-call rotation",
    "stakeholder management",
    "roadmap planning",
    "mentoring",
    "Grafana dashboards",
    "feature flags",
]

SUMMARY_TEMPLATES = [
    "{noun} with {yrs} years shipping {domain} systems in production.",
    "{yrs} years as a {noun}, most recently owning {domain} at scale.",
    "Hands-on {noun} focused on {domain}, {yrs} years in.",
]

BULLET_TEMPLATES = [
    "Built and operated production services with {a} and {b}, cutting p95 latency by {pct}%.",
    "Led the {a} migration end to end across {n} teams with no customer-visible downtime.",
    "Introduced {a} into the delivery workflow, taking deploys from {hrs} hours to under {mins} minutes.",
    "Held on-call for {a} workloads and kept the error budget green for {q} straight quarters.",
    "Mentored {n} engineers on {a} and {b} and ran the internal {a} guild.",
    "Rewrote the {a} integration layer, removing {k} classes of recurring incident.",
]

# One reusable out-of-field resume. Contains none of the requirement terms for
# any role, so it scores 0 wherever it is added.
_OFF_DOMAIN_TEMPLATE = """{name}
{location} · Embedded Systems Engineer

SUMMARY
Firmware engineer with {yrs} years building real-time control systems for
medical and industrial devices.

EXPERIENCE
{company_a}, Senior Firmware Engineer ({start_a}–present)
- Wrote bare-metal and FreeRTOS firmware for ARM Cortex-M microcontrollers.
- Brought up custom PCBs over I2C, SPI, UART and CAN bus.
- Cut power draw {pct}% through sleep-state scheduling and clock gating.
- Ran MISRA static analysis and a hardware-in-the-loop test rig.

{company_b}, Firmware Engineer ({start_b}–{end_b})
- Implemented motor-control loops and sensor fusion on DSP targets.
- Chased timing faults with a logic analyser and an oscilloscope.

SKILLS
Embedded C, FreeRTOS, ARM Cortex-M, I2C, SPI, CAN bus, oscilloscope,
PCB bring-up, MISRA

EDUCATION
BEng Electronic Engineering, {university} ({grad})
"""


ARCHETYPE_MIX: tuple[tuple[str, int], ...] = (
    ("full_match", 2),
    ("keyword_stuffed", 1),
    ("strong", 5),
    ("missing_must", 4),
    ("partial", 4),
    ("adjacent", 2),
    ("prose_only", 1),
    ("off_domain", 1),
)  # 20 candidates per role


# --------------------------------------------------------------------------- #
# Generation                                                                   #
# --------------------------------------------------------------------------- #


def _sample(rng: random.Random, seq: list[str], k: int) -> list[str]:
    return rng.sample(seq, min(k, len(seq)))


def _pick_matches(
    reqs: tuple[SeedRequirement, ...], archetype: str, rng: random.Random
) -> list[SeedRequirement]:
    musts = [r for r in reqs if r.weight == "must"]
    others = [r for r in reqs if r.weight != "must"]

    if archetype in ("full_match", "keyword_stuffed"):
        return list(reqs)
    if archetype == "strong":
        dropped = rng.choice(others)
        return [r for r in reqs if r is not dropped]
    if archetype == "missing_must":
        dropped = rng.choice(musts)
        return [r for r in reqs if r is not dropped]
    if archetype == "partial":
        kept_must = rng.choice(musts)
        extras = rng.sample(others, k=rng.randint(0, min(2, len(others))))
        return [kept_must, *extras]
    if archetype == "adjacent":
        return rng.sample(list(reqs), k=1)
    return []  # prose_only, off_domain


def _experience_block(
    rng: random.Random,
    matched_terms: list[str],
    n_bullets: int,
    company: str,
    title: str,
    span: str,
) -> str:
    lines = [f"{company}, {title} ({span})"]
    pool = matched_terms or _sample(rng, NOISE_SKILLS, 4)
    for i, tmpl in enumerate(rng.sample(BULLET_TEMPLATES, k=n_bullets)):
        a = pool[i % len(pool)]
        b = pool[(i + 1) % len(pool)] if len(pool) > 1 else rng.choice(NOISE_SKILLS)
        lines.append(
            "- "
            + tmpl.format(
                a=a,
                b=b,
                pct=rng.randint(15, 60),
                n=rng.randint(2, 6),
                hrs=rng.randint(3, 8),
                mins=rng.randint(5, 20),
                q=rng.randint(2, 8),
                k=rng.randint(2, 5),
            )
        )
    return "\n".join(lines)


def _render_generic(
    rng: random.Random,
    name: str,
    role: SeedRole,
    matched: list[SeedRequirement],
    *,
    keyword_stuffed: bool = False,
) -> str:
    meta = ROLE_META[role.title]
    matched_labels = [r.label for r in matched]
    yrs = rng.randint(3, 14)
    summary = rng.choice(SUMMARY_TEMPLATES).format(
        noun=meta["noun"], yrs=yrs, domain=meta["domain"]
    )
    if keyword_stuffed:
        summary += (
            " These days I set technical direction and review designs; I have "
            "not shipped a production feature myself since 2021."
        )

    company_a, company_b = rng.sample(COMPANIES, 2)
    start_a = _CURRENT_YEAR - rng.randint(2, 6)
    end_b = start_a
    start_b = end_b - rng.randint(2, 5)
    grad = start_b - rng.randint(0, 3)

    exp_a = _experience_block(
        rng, matched_labels, 3, company_a, rng.choice(JOB_TITLES), f"{start_a}–present"
    )
    exp_b = _experience_block(
        rng, matched_labels, 2, company_b, rng.choice(JOB_TITLES), f"{start_b}–{end_b}"
    )
    skills = ", ".join(matched_labels + _sample(rng, NOISE_SKILLS, rng.randint(4, 6)))

    return "\n".join(
        [
            name,
            f"{rng.choice(LOCATIONS)} · {meta['headline']}",
            "",
            "SUMMARY",
            summary,
            "",
            "EXPERIENCE",
            exp_a,
            "",
            exp_b,
            "",
            "SKILLS",
            skills,
            "",
            "EDUCATION",
            f"{rng.choice(DEGREES)}, {rng.choice(UNIVERSITIES)} ({grad})",
        ]
    )


def _render_prose_only(rng: random.Random, name: str, role: SeedRole) -> str:
    paras = [PARAPHRASES[r.label] for r in role.requirements]
    company = rng.choice(COMPANIES)
    start = _CURRENT_YEAR - rng.randint(8, 14)
    return "\n".join(
        [
            name,
            f"{rng.choice(LOCATIONS)} · Principal Engineer",
            "",
            "SUMMARY",
            "Fourteen years building and running large systems. I describe what a "
            "system does rather than list the tools it happens to be built from.",
            "",
            "EXPERIENCE",
            f"{company}, Principal Engineer ({start}–present)",
            f"- Owned {paras[0]} and {paras[1]} for a platform serving millions of "
            "users a day.",
            f"- Moved the estate onto {paras[2]} and {paras[3]} with no "
            "customer-visible incident.",
            f"- Set the team's approach to {paras[4]} and {paras[5]}, and chaired "
            "the architecture review board.",
            "- Mentored the senior engineers and owned the on-call culture.",
            "",
            "EDUCATION",
            f"{rng.choice(DEGREES)}, {rng.choice(UNIVERSITIES)}",
        ]
    )


def _render_off_domain(rng: random.Random, name: str) -> str:
    company_a, company_b = rng.sample(COMPANIES, 2)
    start_a = _CURRENT_YEAR - rng.randint(3, 7)
    end_b = start_a
    start_b = end_b - rng.randint(2, 5)
    return _OFF_DOMAIN_TEMPLATE.format(
        name=name,
        location=rng.choice(LOCATIONS),
        yrs=rng.randint(6, 12),
        company_a=company_a,
        company_b=company_b,
        start_a=start_a,
        start_b=start_b,
        end_b=end_b,
        pct=rng.randint(20, 45),
        university=rng.choice(UNIVERSITIES),
        grad=start_b - rng.randint(0, 3),
    )


def _unique_name(rng: random.Random, used: set[str]) -> str:
    while True:
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        if name not in used:
            used.add(name)
            return name


def _email_for(name: str, rng: random.Random) -> str | None:
    if rng.random() < 0.3:
        return None
    first, last = name.lower().split(" ", 1)
    return f"{first}.{last}@example.com"


def build_dataset(
    rng: random.Random | None = None,
) -> list[tuple[SeedRole, list[SeedCandidate]]]:
    """The full synthetic dataset: ~6 roles, ~120 candidates, deterministic."""
    rng = rng or random.Random(RANDOM_SEED)
    used_names: set[str] = set()
    dataset: list[tuple[SeedRole, list[SeedCandidate]]] = []

    for role in SEED_ROLES:
        archetypes: list[str] = []
        for tag, count in ARCHETYPE_MIX:
            archetypes.extend([tag] * count)
        rng.shuffle(archetypes)

        candidates: list[SeedCandidate] = []
        for archetype in archetypes:
            name = _unique_name(rng, used_names)
            matched = _pick_matches(role.requirements, archetype, rng)

            if archetype == "prose_only":
                resume = _render_prose_only(rng, name, role)
            elif archetype == "off_domain":
                resume = _render_off_domain(rng, name)
            else:
                resume = _render_generic(
                    rng,
                    name,
                    role,
                    matched,
                    keyword_stuffed=(archetype == "keyword_stuffed"),
                )

            is_upload = rng.random() < 0.2
            slug = name.lower().replace(" ", "-")
            candidates.append(
                SeedCandidate(
                    name=name,
                    email=_email_for(name, rng),
                    resume_text=resume,
                    source="upload" if is_upload else "paste",
                    original_filename=(
                        f"{slug}-cv.{rng.choice(['pdf', 'docx'])}"
                        if is_upload
                        else None
                    ),
                )
            )

        dataset.append((role, candidates))

    return dataset
