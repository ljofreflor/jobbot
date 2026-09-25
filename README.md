# JobBot

Local terminal tool for managing a job search: structured CV as source of truth, portal sync,
matching, adapted CVs, and assisted applications. **No web UI** — everything runs from the CLI.

## Why

Job search tooling usually optimizes *you* as a market commodity. JobBot points the other way:
make employers, portals, and postings **observable** — ghost jobs, silence, salary opacity,
career-site topology — and keep you in the loop.

- **`data/profile.yaml` is the source of truth.** LaTeX, PDF, Indeed, LinkedIn, and GetOnBoard are
  views or adapters. Facts are never invented to fit a posting.
- **Nothing to enclose.** AI runs on your machine (e.g. inside Cursor). JobBot does not host models
  or a central candidate DB. The shareable artifact is public employer knowledge (company↔ATS map),
  not your CV. Federated via files and git — if the maintainer disappears, forks keep working.
- **HITL by default.** Never auto-submits, no CAPTCHA bypass, dry-run unless you pass `--apply`.
- **A posting is not the job.** The public ad conflates the work, the requisition, the marketing
  text, and your observation of it. Flat “one URL = one truth” models hide ghosts and reposts.
  JobBot records observation and evidence (see `companies`) instead. Posted requirements often
  ration the applicant queue more than they specify the work.
- **Distributed AI load.** Designed to be driven by a coding agent calling the CLI; token cost stays
  with you. Agent-friendly structured output (`--json` on a few commands today) is a direction, not
  a finished surface.

## Architecture

```text
     profile.yaml (SoT, private)          companies.yaml (public knowledge)
              │                                      │
  ┌───────────┼──────────────┐                       │
  │           │              │                       ▼
  ▼           ▼              ▼                 company ↔ ATS map
LaTeX       Indeed        LinkedIn / GOB        (shareable, no PII)
  │           │              │
  ▼           ▼              ▼
 PDF    IndeedAdapter   portal adapters
```

`data/profile.yaml` stays local and gitignored. `data/companies.yaml` is the opposite kind of
artifact: reusable employer topology, safe to share or fork.

## Status

**Endgame:** match → decide → derived CV → application package → apply (more portals over time).

Working today:

- Profile validate / import-latex / promote
- `cv build` base and `--job Jxxxx`; `cv propagate` (dry-run default)
- `jobs add|show|match|shortlist|note`
- `application prepare|show|open|apply` + `applications list`
- Indeed/LinkedIn: `login|status|inspect|pull|diff`; Indeed `sync --section headline`; LinkedIn Publications sync + `sweep`
- GetOnBoard: `search` + permanent-profile sync via `cv propagate`
- `companies` registry (detect / learn / promote / discover / export)
- Protocols for future portals: `ApplicationPortalAdapter`, `JobSourceAdapter`

## Match → apply (happy path)

```bash
# Preferred: pull JDs from Indeed (cl.indeed.com)
uv run playwright install chromium   # once
uv run jobbot indeed login           # once; persist session
uv run jobbot jobs search "Senior Data Scientist" --location Santiago --limit 20
uv run jobbot jobs shortlist
uv run jobbot jobs match J0003
uv run jobbot cv build --job J0003
uv run jobbot application prepare J0003

# Manual fallback (paste JD file) still available:
# uv run jobbot jobs add --file path/to/jd.txt
```

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- XeLaTeX (for PDF only; ATS text does not need it)
  - macOS: `brew install --cask basictex` or `mactex-no-gui`, then ensure `xelatex` is on `PATH`
  - After BasicTeX: `sudo tlmgr update --self && sudo tlmgr install collection-fontsrecommended`
- Playwright Chromium for portal commands: `uv run playwright install chromium`

## Install

```bash
uv sync --group dev
cp .jobbot.toml.example .jobbot.toml   # optional
cp data/profile.example.yaml data/profile.yaml
cp data/portals.example.yaml data/portals.yaml       # optional ATS seed
cp data/companies.example.yaml data/companies.yaml   # optional company↔portal seed
```

**PII:** `data/profile.yaml` (and `portals.yaml`, `companies.yaml`, SQLite, `browser-data/`, `output/`) are
**gitignored**. Only `*.example.yaml` templates are safe to commit. See [data/README.md](data/README.md).

**Private LaTeX CV:** keep your real moderncv private. Use `latex/cv.tex.demo` (tracked
dummy) or set `paths.legacy_cv` in local `.jobbot.toml` to a path outside the repo / to
gitignored `latex/cv.tex`. See [latex/README.md](latex/README.md).

**PII pre-commit guard:** enable it once per clone so real data cannot be committed
(even with `git add -f`):

```bash
make hooks        # git config core.hooksPath .githooks
make pii-check    # scan the current index on demand
```

It blocks `data/profile.yaml`, `data/portals.yaml`, SQLite, `output/`, `browser-data/`,
`latex/cv.tex`, PDFs, and flags real-looking emails, phone numbers, RUTs, or
`/Users/<you>/` paths in staged content. Fixtures and `*.example.yaml` are allowlisted.

## Create or edit your profile

Edit `data/profile.yaml`. Use stable IDs for experiences and achievements:

```yaml
experience:
  - id: acme-ds
    company: Acme
    title: Data Scientist
    start_date: 2022-04
    current: true
    achievements:
      - id: acme-forecast
        text: Built demand forecasting for 2M SKUs.
        tags: [machine-learning, retail]
        metrics:
          skus: 2000000
```

Validate:

```bash
uv run jobbot profile validate
uv run jobbot profile show
```

## Generate CV

```bash
uv run jobbot cv build              # output/base/cv.tex + cv.pdf
uv run jobbot cv build --target ats # output/base/cv_ats.txt
```

If XeLaTeX is missing, PDF build fails with clear install instructions (ATS still works).

## Import from a legacy LaTeX CV

Use an existing moderncv `.tex` as the starting point (does **not** overwrite `profile.yaml`):

```bash
uv run jobbot profile import-latex /path/to/cv.tex
# writes data/profile.generated.yaml

# optional: set a default path in .jobbot.toml
# [paths]
# legacy_cv = "/path/to/cv.tex"
# then:
uv run jobbot profile import-latex

# after human review:
uv run jobbot profile promote-generated
uv run jobbot profile validate
uv run jobbot cv build
```

The importer detects name, headline, contact, summary, `\cventry` experience,
education, `\cvitem` skills, and publications. Review IDs, tags, and metrics before promoting.

## Indeed / LinkedIn / ATS loop

```bash
jobbot indeed login | inspect | pull | diff | sync --apply
jobbot linkedin login | inspect | pull | diff
jobbot linkedin sync --section publications --apply   # DOI + coauthors; confirm each
jobbot linkedin sweep "hiring data scientist" [--country CL] [--max-age-days 30] [--fixture PATH] [--cdp URL]
jobbot getonboard search "data scientist"
jobbot portals list | add | detect
jobbot jobs match J0001 | shortlist
jobbot cv build --job J0001
jobbot application prepare J0001
jobbot application apply J0001 [--apply]   # ATS prefill plan / open (you submit)
jobbot profile suggest-from-market [--ask] [--promote]
```

Recruiter posts → external ATS URL → portal registry → assisted apply (HITL). Market feedback suggests baseline wording; gaps require confirmation before `--promote`.

## Propagate the CV (permanent profiles)

One command rebuilds the base CV and pushes it outward to the profiles that live beyond a
single vacancy. Dry-run by default; `--apply` confirms destination by destination:

```bash
jobbot cv propagate                        # plan only (no browser, no writes)
jobbot cv propagate --apply                # rebuild CV, then Get on Board / Indeed / LinkedIn
jobbot cv propagate --targets cv,indeed --section headline --apply
jobbot cv propagate --apply --cdp http://127.0.0.1:9222   # reuse your logged-in Chrome
```

Planning is read-only and browser-free: Indeed diffs against the stored snapshot (it asks for
`jobbot indeed pull` when there is none), LinkedIn covers Publications only, and Get on Board
refines the permanent profile cumulatively. Writes stay HITL — nothing is submitted for you.
For a specific vacancy the path is still `cv build --job J0001` → `application prepare J0001`
→ `application apply J0001 --apply`.

## Company career platforms (who hires where)

Many employers never publish everything on LinkedIn/Indeed/GetOnBoard: they keep their own
portal, an employment subdomain, or a private ATS instance. `jobbot companies` learns that
topology as **public** knowledge — company, domains, career URLs, ATS, evidence, dates — and
never candidate PII.

```bash
jobbot companies detect https://empresa.wd3.myworkdayjobs.com/External   # classify only
jobbot companies learn https://trabajaenbci.cl --company BCI --country CL
jobbot companies list [--status candidate|active]
jobbot companies show bci
jobbot companies promote bci [--site URL]      # candidate → active (HITL)
jobbot companies reject bci --site URL
jobbot companies sites                          # reusable knowledge for job discovery
jobbot companies export                         # shareable snapshot (active only)
```

One company holds 0..N career sites (corporate portal, Workday, a subsidiary's Greenhouse…).
Each site keeps `first_seen`, `last_verified`, status, and one observation per sighting, so
several sources raise confidence instead of duplicating entries. A portal that changes ATS is
flagged `stale` with the contradiction recorded — stored facts are never overwritten silently,
and an ATS stays `unknown` without technical evidence (host rule, redirect, or embedded marker).

`linkedin sweep` and `jobs add` feed this registry automatically as **candidate** knowledge.

### One-shot seeding (not a crawler)

Seed a first base of employers from public sources, then review:

```bash
jobbot companies discover data/companies-cl.example.yaml   # banks, retail, telco, mining, tech, insurance
# → output/discovery/company_portals.generated.yaml   (status: candidate)
jobbot companies import output/discovery/company_portals.generated.yaml
jobbot companies promote COMPANY
```

The oneshot probes public career paths and subdomains on the official domain (sequentially,
with a delay) and accepts a candidate only with real evidence: an ATS marker, a redirect, or
employment wording on the page. HTTP 200 alone is not evidence. It writes candidates to
`output/` and never modifies `data/companies.yaml`. Web search hits obtained elsewhere can be
fed in with `--search-results FILE`; JobBot does not query a search engine itself.

Sessions persist under `browser-data/` (gitignored). Passwords are never stored.

## Tests & quality

```bash
make install
make lint
make typecheck
make test
# or:
uv run ruff check .
uv run mypy src
uv run pytest
```

## Security & privacy

- Runs locally; MVP does not send your CV to external AI APIs.
- No CAPTCHA solving, 2FA bypass, or anti-bot evasion.
- Do not commit `browser-data/`, `output/`, `.env`, or SQLite DBs.
- LinkedIn: audit; Publications sync; recruiter-post sweep → ATS registry; apply is HITL on the ATS.
- Market feedback: `profile suggest-from-market` (confirm gaps; never invent).

## Configuration

Copy `.jobbot.toml.example` to `.jobbot.toml` or `~/.config/jobbot/config.toml`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `xelatex` not found | Install BasicTeX/MacTeX; open a new shell; `which xelatex` |
| Font not found | Template uses Times New Roman / Helvetica (macOS). On Linux install those fonts or edit `templates/cv.tex.j2`. |
| PROFILE INVALID | Fix dates/IDs/emails reported by `profile validate` |
| Empty PDF | Check `output/base/build.log` |

## License

Private / personal use unless stated otherwise.
