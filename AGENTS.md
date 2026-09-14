# AGENTS.md — JobBot

Instructions for AI agents and humans working on this repository.

## Product / endgame

JobBot is a **local terminal-only** tool. The endgame is **job matching to apply**:

```text
profile.yaml (Candidate)
      → match / shortlist
      → CV derivado + application package
      → portal adapters (Indeed, GetOnBoard, Greenhouse, …)
```

No web frontend. Facts live only in `data/profile.yaml`. Never invent experience to fit a job.

## Source of truth

```text
data/profile.yaml  →  Candidate (domain)
        │
   ┌────┼────┬─────────┐
   ▼    ▼    ▼         ▼
 LaTeX Indeed LinkedIn  future apply portals
```

## Cargo lifecycle (primary loop)

```bash
jobbot jobs search "Senior Data Scientist" --location Santiago
# or LinkedIn recruiter posts → ATS:
jobbot linkedin sweep "hiring data scientist" [--fixture PATH] [--cdp URL]
jobbot jobs match J0001
jobbot jobs shortlist
jobbot cv build --job J0001
jobbot application prepare J0001
jobbot application open J0001          # opens ATS/job URL; no auto-submit
jobbot application apply J0001         # dry-run prefill plan
jobbot application apply J0001 --apply # open ATS + prefill sheet (you submit)
jobbot profile suggest-from-market     # market language + ask gaps
```

Job descriptions are pulled from **Indeed** (`jobs search`) or **LinkedIn recruiter posts** (`linkedin sweep`). Manual `jobs add --file` is a fallback.
`profile.yaml` is never silently rewritten for an offer. Derived artifacts go under `output/jobs/Jxxxx/`.
Baseline may be updated only via **confirmed** market feedback (`profile suggest-from-market --promote`): rephrase/presentation and user-confirmed skills — never invented facts; never delete existing facts.

## MVP decisions (LinkedIn → ATS loop)

- **LinkedIn discovery:** recruiter **posts** with external ATS links (`linkedin sweep`); LinkedIn Jobs official is secondary.
- **ATS apply depth:** discover + store + detect portal + **prefill known fields**; user submits (`application apply --apply`). No auto-submit, no CAPTCHA bypass.
- **Market feedback:** `profile suggest-from-market` proposes rephrases and asks gap questions; `--promote` only after user confirms. Never invent; never delete baseline facts.
- **Get on Board:** mantenedor de **perfil permanente** con **computación acumulativa**:
  `getonboard prepare` refina el draft previo (no lo tira) usando `profile.yaml` como hechos;
  `--seed` importa texto viejo del portal; `--llm` usa LangChain si `jobbot[llm]` + `OPENAI_API_KEY`;
  `--cold` solo si quieres partir de cero. Historia en `output/getonboard/history/`.
  HITL: https://www.getonbrd.com/webpros/edit + Tus CVs. `application prepare` reusa los textos.

## Portal adapters

Matching and packages stay portal-agnostic. New sites implement:

- `JobSourceAdapter` — discovery via `get_job_source()` in [`src/jobbot/jobs/sources.py`](src/jobbot/jobs/sources.py) (Indeed, LinkedIn posts, GetOnBoard)
- `ApplicationPortalAdapter` — prefill/attach from Candidate + package ([`src/jobbot/adapters/base.py`](src/jobbot/adapters/base.py); registry in [`src/jobbot/adapters/ats/registry.py`](src/jobbot/adapters/ats/registry.py))
- Portal registry — `data/portals.yaml` via `jobbot portals list|add|detect`; auto-learned from sweep URLs

Inject only known fields; HITL for salary/visa/English/CAPTCHA. Adapter order: Indeed assisted apply → GetOnBoard → Greenhouse/Lever/Ashby → Workday.

## Domain direction

`DOMAIN (Candidate) → adapters` — never the reverse. One model: `Candidate`.

## Safety / platform

- Own accounts only. No CAPTCHA solving, 2FA bypass, stealth, proxies, telemetry.
- Failures: local `ops_failures` in SQLite + `output/ops/failures/`; GitHub issues only via HITL `jobbot ops failure issue` (never auto on crash).
- **PII:** never commit `data/profile.yaml`, `data/portals.yaml`, SQLite, `browser-data/`, or `output/`. Track only `*.example.yaml` templates.
- **Private LaTeX CV:** tracked dummy is `latex/cv.tex.demo` only; real `.tex`/`latex/cv.tex` stay gitignored. Prefer `paths.legacy_cv` outside the repo or a local ignored copy. See `latex/README.md`.
- LinkedIn: read-only audit by default. **Exception:** `linkedin sync --section publications`
  writes Publications only (dry-run default; `--apply` + per-item confirmation unless `--yes`).
- Indeed writes: dry-run default; `--apply` + confirmation.
- Removals ignored by default.

## Regression tests (mandatory)

Every bug/failure → unit test that fails first, then fix. Prefer fixtures over live portals.

## Verify

```bash
uv sync --group dev
uv run ruff check .
uv run mypy src
uv run pytest
```

## Key commands

```bash
uv run jobbot profile validate
uv run jobbot profile import-latex
uv run jobbot cv build
uv run jobbot cv build --job J0001
uv run jobbot jobs add --file tests/fixtures/jobs/senior_ds_retail.txt
uv run jobbot jobs match J0001
uv run jobbot application prepare J0001
uv run jobbot indeed login|pull|diff|sync --section headline
uv run jobbot linkedin login|pull|diff
uv run jobbot linkedin sync --section publications          # dry-run
uv run jobbot linkedin sync --section publications --apply  # confirm each
uv run jobbot linkedin sweep "hiring data scientist"
uv run jobbot getonboard prepare              # refine acumulativo (default)
uv run jobbot getonboard prepare --seed old_gob.txt
uv run jobbot getonboard prepare --llm        # LangChain (uv sync --extra llm)
uv run jobbot getonboard prepare --cold       # solo si quieres partir de cero
uv run jobbot getonboard show-profile
uv run jobbot getonboard open-profile
uv run jobbot getonboard open-cvs
uv run jobbot getonboard sync --apply
uv run jobbot getonboard search "data scientist"
uv run jobbot ops failures
uv run jobbot ops failure show F0001
uv run jobbot ops failure triage F0001 --status fixed
uv run jobbot ops failure issue F0001          # HITL → gh issue
uv run jobbot ops loop --cmd getonboard-prepare --interval 300
uv run jobbot portals list|add|detect
uv run jobbot application apply J0001
uv run jobbot profile suggest-from-market
```
