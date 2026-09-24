# Software design — JobBot

Ownership: architecture, design patterns, persistence layout, and technology stack.
Product rules and safety live in the README / agent policy; this document is the
engineering map.

## 1. Goals that shape the design

| Constraint | Design consequence |
| --- | --- |
| Local CLI only — no web UI | Typer + Rich; all flows are commands |
| `data/profile.yaml` is the only professional source of truth | Domain model `Candidate`; portals are adapters/views |
| Never invent experience | Adapters inject known fields only; HITL for the rest |
| PII stays off git | YAML + SQLite under `data/` are gitignored; examples only in repo |
| Light, offline-friendly deps | Prefer pure-Python libraries; optional LLM behind an extra |

```text
                         profile.yaml  (SoT)
                              │
              ┌───────────────┼────────────────┐
              │               │                │
              ▼               ▼                ▼
            LaTeX           Indeed          LinkedIn / ATS
              │               │                │
              ▼               ▼                ▼
             PDF       ProfileAdapter   ApplicationPortalAdapter
```

Direction of dependency: **domain → adapters**, never the reverse.

## 2. Layered structure

```text
cli.py                    presentation (Typer commands)
  │
  ├── profile / cv / matching / applications / companies / ops
  │         application services (use cases)
  │
  ├── models/             domain (Pydantic)
  ├── db/ + *Repository   persistence (SQLAlchemy ORM rows ↔ domain)
  ├── adapters/           external systems (Playwright, HTTP, HTML)
  └── templates/ + latex  rendering (Jinja2 → .tex / ATS text)
```

Packages under `src/jobbot/` map to bounded contexts:

| Package | Responsibility |
| --- | --- |
| `models/` | Domain types (`Candidate`, `JobPosting`, `Application`, …) |
| `profile/` | Load, validate, import, market suggestions |
| `cv/` | Selection, render, ATS text, optional LLM advice |
| `jobs/` | Parse, normalize, geo/freshness, repository, sources |
| `matching/` | Score profile vs JD |
| `applications/` | Package on disk + application tracking |
| `adapters/` | Indeed, LinkedIn, Get on Board, ATS, Gmail, HTML parse |
| `portals/` | ATS detect + local portal registry YAML |
| `companies/` | Shareable company ↔ career-site knowledge (no candidate PII) |
| `db/` | Engine, SQLite migrations helper, ORM tables |
| `browser/` | Playwright session helpers |
| `ops/` | Failures, PII guard, redaction |
| `nlp/` | Optional refine (LangChain behind `jobbot[llm]`) |

## 3. Design patterns in use

### 3.1 Ports and adapters (Hexagonal)

Protocols in `adapters/base.py` and `jobs/sources.py` are the ports:

- `ProfileAdapter` / `WritableProfileAdapter` — pull, diff, optional sync plan/apply
- `ApplicationPortalAdapter` — detect apply method, prefill, attach CV
- `JobSourceAdapter` — `search_jobs` / `get_job`
- `ApplicationPackage` — filesystem package contract

Concrete adapters (Indeed, LinkedIn, Greenhouse, …) implement those ports.
Matching and package preparation stay portal-agnostic.

### 3.2 Factory

`get_job_source(name, config)` (`jobs/sources.py`) and `adapter_for_kind` /
`adapter_for_job` (`adapters/ats/registry.py`) select the implementation.
CLI code depends on the protocol, not on a concrete portal module.

### 3.3 Repository

- `JobRepository` — `JobPosting` ↔ `jobs` table
- `ApplicationRepository` — `Application` ↔ `applications` + event append

Repositories own mapping (JSON columns ↔ lists) and ID allocation (`Jxxxx`, `Axxxx`).
Domain models never import SQLAlchemy.

### 3.4 Registry / Strategy

- **Portal registry** (`portals/registry.py`): YAML list of domains + ATS kind
- **ATS strategy map**: `AtsKind` → `ApplicationPortalAdapter`
- **Company registry** (`companies/registry.py`): company → career sites with
  candidate / active / stale / rejected lifecycle (promote is explicit HITL)

### 3.5 Template Method / plan-then-apply

Writable portals share the same shape:

1. Pull or load snapshot
2. Diff against `Candidate`
3. Build `SyncPlan`
4. Dry-run by default; `--apply` (+ confirmation) executes writes

Same idea for applications: `prepare` → `apply` (plan) → `apply --apply` (open + prefill; human submits).

### 3.6 Snapshot + event log

- `external_profile_snapshots` stores portal pulls for offline diff
- `application_events` append-only history of status transitions
- `ops_failures` local crash records (no telemetry)

### 3.7 Strategy for matching

`JobAnalyzer` protocol with `RuleBasedJobAnalyzer` as the default implementation
(`matching/analyzer.py`). Scoring stays swappable without touching the CLI.

### 3.8 Patterns we deliberately avoid

| Pattern | Why not |
| --- | --- |
| Full CQRS / event sourcing | Single-user local tool; overkill |
| Active Record on domain models | Keep Pydantic domain free of ORM |
| Service locator / DI container | Explicit constructors + Typer wiring are enough |
| Microservices / message bus | One process, one SQLite file |
| Auto-submit / stealth browser | Product and safety constraint |

## 4. Persistence model

Two stores, split by volatility and shareability:

### 4.1 Filesystem (source of truth and knowledge)

| Path | Contents | Git |
| --- | --- | --- |
| `data/profile.yaml` | Candidate SoT | **no** |
| `data/portals.yaml` | Personal ATS registry | **no** |
| `data/companies.yaml` | Company ↔ career sites (public facts) | **no** (examples yes) |
| `output/` | Built CVs, packages, snapshots, ops dumps | **no** |
| `browser-data/` | Playwright persistent sessions | **no** |
| `templates/*.j2` | CV / ATS templates | yes |
| `*.example.yaml` | Safe templates | yes |

### 4.2 SQLite (`data/jobbot.sqlite` by default)

Configured via `paths.database` in `.jobbot.toml`. Created on first use
(`create_all` + lightweight column adds in `db/engine.py`).

```text
jobs
  id PK (Jxxxx)
  source, source_job_id, url
  title, company, location
  description, raw_description
  requirements_json, skills_json, language_requirements_json
  seniority, employment_type, remote_type
  ats_url, ats_kind
  posted_at, discovered_at
  note, match_score

applications
  id PK (Axxxx)
  job_id (indexed)
  status
  created_at, updated_at
  package_dir

application_events
  id PK autoincrement
  application_id (indexed)
  event_type, detail, created_at

external_profile_snapshots
  id PK autoincrement
  source (indexed)
  payload_json, captured_at

ops_failures
  id PK (Fxxxx)
  ts, command, component, exit_code
  error_class, message, traceback
  context_json, fingerprint, status, issue_url
```

Logical relationships (no FK constraints today — keep SQLite migrations simple):

```text
jobs 1 ─── * applications 1 ─── * application_events
```

Application `status` values (`models/application.py`):
`discovered` → `shortlisted` → `prepared` → `applied` →
`screening` / `interview` / `technical_interview` / `offer` /
`rejected` / `withdrawn`.

### 4.3 Mapping rules

- ORM rows (`db/models.py`) are persistence DTOs; Pydantic models are the API.
- Lists (`requirements`, `skills`, …) serialize as JSON text columns.
- Upsert keys for external jobs: `(source, source_job_id)` then `url`.
- Companies / portals stay in YAML so shareable knowledge can be exported without
  dumping a personal SQLite file.

### 4.4 Migration policy

Today: `Base.metadata.create_all` plus `_JOB_EXTRA_COLUMNS` ALTER ADD for `jobs`
only (`db/engine.py`). Sufficient for nullable column adds on a single-user DB.

When a migration needs rename, drop, backfill, or multi-table changes, adopt
Alembic (tracked as issue [#7](https://github.com/ljofreflor/jobbot/issues/7)).
Do not expand the hand-rolled dict into a second migration framework.

## 5. Technology stack

### 5.1 Runtime

| Layer | Choice | Role |
| --- | --- | --- |
| Language | Python 3.12+ | Typed, strict mypy |
| Packaging | uv + hatchling | Lockfile `uv.lock`, `uv sync --group dev` |
| CLI | Typer | Command tree (`jobbot …`) |
| Terminal UX | Rich | Tables / panels |
| Domain validation | Pydantic v2 | `Candidate`, jobs, registries |
| Config | TOML (`tomllib`) | `.jobbot.toml` / `~/.config/jobbot/config.toml` |
| ORM / DB | SQLAlchemy 2.0 + SQLite | Jobs, applications, snapshots, ops |
| Templates | Jinja2 | LaTeX + ATS text |
| PDF | XeLaTeX (system) + pypdf | Build CV; inspect PDFs |
| Browser automation | Playwright (Chromium) | Portal login / pull / sync / prefill |
| HTTP | httpx | Redirects, light fetches |
| HTML | beautifulsoup4 (declared) | Prefer over regex for markup |
| i18n helpers | babel | Dates / units / territories where CLDR wins |
| Email validation | email-validator | Used via Pydantic `EmailStr` |
| Optional LLM | LangChain + OpenAI (`jobbot[llm]`) | Explicit opt-in; never invent facts |

### 5.2 Quality tooling

| Tool | Command |
| --- | --- |
| Ruff | `make lint` / `make format` |
| mypy (strict) | `make typecheck` |
| pytest | `make test` (default excludes `integration`) |
| PII pre-commit | `make hooks` → `.githooks/pre-commit` |

### 5.3 Dependency policy

1. Prefer a maintained pure-Python library over a new hand-rolled helper for
   generic problems (HTML, HTTP, dates, emails).
2. Keep domain rules ours: LaTeX CV layout, LinkedIn activity-id dates, ATS
   selectors, company provenance, HITL gates.
3. No downloadable ML models, no telemetry, nothing that phones home by default.
4. Before adding weight, check open library issues ([#6](https://github.com/ljofreflor/jobbot/issues/6)–[#12](https://github.com/ljofreflor/jobbot/issues/12)):
   rapidfuzz, alembic, geonamescache, detect-secrets, TexSoup, pydantic-settings,
   url-normalize.

### 5.4 What is explicitly out of stack

- Web frontend / React / REST API server
- Cloud-hosted database
- Captcha solvers, stealth/anti-detect browsers, residential proxies
- Auto-commit of agent maintainer lanes (ops failure work stays HITL bash)

## 6. Key flows (pattern view)

### Standing presence

```text
profile.yaml → cv build → adapter.diff / sync_plan → [--apply] portal write
```

### Match → apply

```text
JobSourceAdapter.search/get
  → JobRepository.upsert
  → match / shortlist
  → cv build --job
  → prepare package (filesystem)
  → ApplicationPortalAdapter.prefill
  → human submit
```

### Collaborative knowledge (no PII)

```text
URL / sweep → companies learn (candidate)
  → human promote → active site usable by discovery / presence
```

## 7. Extension checklist

When adding a portal or job board:

1. Domain stays untouched unless a new fact type is required on `Candidate`.
2. Implement the right protocol (`JobSourceAdapter` and/or
   `ApplicationPortalAdapter` / profile adapter).
3. Register in the factory/registry; add fixtures under `tests/fixtures/`.
4. Dry-run default; `--apply` for irreversible steps; never invent answers.
5. If SQLite shape changes beyond nullable columns on `jobs`, plan Alembic (#7).

## 8. Related documents

- [README.md](../README.md) — product overview and commands
- [data/README.md](../data/README.md) — what is gitignored under `data/`
- GitHub issues `#6`–`#12` — library / DB decisions still open
