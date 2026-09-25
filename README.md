# JobBot

Local terminal tool for managing a job search: structured CV as source of truth, portal sync,
matching, adapted CVs, and assisted applications. **No web UI** — everything runs from the CLI.

New here? Start with the [tutorial](docs/tutorial.md): the loop end to end, the practices that
keep it safe, and the guarantees the code enforces.

## Why the compute spent here compounds

**Every token spent on this project is progress on everyone's CV, collaboratively.** A run that
figures out which portal a company hires through, which questions an application form asks, or
which wording a posting expects does not evaporate when the terminal closes: it is written down as
reusable knowledge. `data/companies.yaml` records company↔portal facts, `data/portals.yaml` the
platforms, and `companies export` produces a shareable snapshot so the next candidate does not pay
that cost again.

The product endgame for that map is **standing presence**: after you improve your CV, the active
portals in the shared base are kept up to date for *you* (assisted account + fill from
`profile.yaml` as far as automatable; password, terms, CAPTCHA and final submit stay HITL).
`companies discover` only finds candidate URLs — it does not register you or upload your CV.
When an active portal still has `ats=unknown`, `companies recon` learns ATS markers and form
questions from a page you entered ([#45](https://github.com/ljofreflor/jobbot/issues/45)) —
not by guessing from the hostname. `jobbot status` is how you see what is actually up on your machine.

What is shared is public knowledge about who hires where and how. What is never shared is you:
your profile, your sessions, your applications and your CV stay on your machine, enforced by the
PII guard (`make hooks`). The collaboration is on the map, not on the traveller.

## Architecture

```text
                         profile.yaml
                              │
     ┌────────────┬───────────┼───────────┬──────────────────┐
     ▼            ▼           ▼           ▼                  ▼
   LaTeX        Indeed     LinkedIn   permanent         active company
     │            │           │       portals           portals (shared
     ▼            ▼           ▼       (GoB, …)          companies base)
    PDF      IndeedAdapter  LinkedInAdapter
                              │
                              ▼
                     cv sync / propagate (#43)
                     + assisted signup (#44)
```

`data/profile.yaml` is the single source of professional truth. LaTeX, PDF, Indeed, LinkedIn,
and company career portals are views or adapters. Facts are never invented to fit a job posting.
Collaboration shares who hires where; each person's CV and accounts stay local.

## Status

**Endgame (standing presence first):** improve CV → keep this candidate registered and up to date
on every *active* portal in the collaborative company↔portal base (`cv sync` [#43](https://github.com/ljofreflor/jobbot/issues/43);
assisted signup fill [#44](https://github.com/ljofreflor/jobbot/issues/44)). Apply to a vacancy is
the second loop (`match` → package → `application apply`, HITL submit).

Working today:

- Profile validate / import-latex / import-pdf / promote
- `cv build` base and `--job Jxxxx`; `cv advise`; `cv sync` (permanent + active company HITL)
- `cv propagate` — permanent profiles only (subset of sync)
- `jobs add|show|match|shortlist|note`
- `get URL` — hard link → known portal → JD → CV + package (`--apply` opens ATS, you submit)
- `application prepare|show|open` + `applications list`
- Indeed/LinkedIn: `login|status|inspect|pull|diff`; Indeed `sync --section headline` (dry-run default, `--apply`)
- `companies signup` sheet + open (browser fill behind `--apply` is #44)
- `companies recon` — inside HTML → ATS observation + form questions (#45)
- Protocols for future portals: `ApplicationPortalAdapter`, `JobSourceAdapter`

## Match → apply (happy path)

```bash
# Preferred: pull JDs from Indeed (cl.indeed.com)
uv run playwright install chromium   # once
uv run jobbot indeed login           # once; persist session
uv run jobbot jobs search "Senior Data Scientist" --location Santiago --limit 20
uv run jobbot jobs shortlist
uv run jobbot jobs match J0003
# Optional: local BERT by JD language (BETO ES / MiniLM other) — uv sync --extra bert
# uv run jobbot jobs match J0003 --bert
# uv run jobbot cv fit J0003 [--bert]   # base vs adapted vs JD
uv run jobbot cv build --job J0003
uv run jobbot application prepare J0003

# Hard link you already have (portal must be known — seed/local/builtin):
# uv run jobbot get https://www.getonbrd.com/empleos/.../slug
# uv run jobbot get 'https://cl.indeed.com/viewjob?jk=...' [--fixture PATH]
# uv run jobbot get URL --park          # phone: queue URL, no fetch / no CAPTCHA
# uv run jobbot get --parked --cdp http://127.0.0.1:9222
# uv run jobbot get URL --apply --cdp http://127.0.0.1:9224

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

# Optional extras (not required for the default offline path):
# uv sync --extra bert   # BETO (ES JD) / MiniLM (other) for `jobs match --bert` / `cv fit`
# uv sync --extra llm    # only for optional --llm / chat-first LLM extract (needs OPENAI_API_KEY)
```

**PII:** `data/profile.yaml` (and `portals.yaml`, `companies.yaml`, SQLite, `browser-data/`, `output/`) are
**gitignored**. Only `*.example.yaml` templates are safe to commit. See [data/README.md](data/README.md).

**Private LaTeX CV:** keep your real moderncv private. Use `latex/cv.tex.demo` (tracked
dummy) or set `paths.legacy_cv` in local `.jobbot.toml` to a path outside the repo / to
gitignored `latex/cv.tex`. See [latex/README.md](latex/README.md).

**Pre-commit hook:** enable it once per clone so real data cannot be committed
(even with `git add -f`) and a red suite cannot be pushed:

```bash
make hooks         # git config core.hooksPath .githooks
make pii-check     # scan the current index on demand
make pre-commit    # run the whole hook without committing
make capabilities  # regenerate docs/capabilities.md after adding code
```

First the PII guard, then the unit tests. The guard blocks `data/profile.yaml`,
`data/portals.yaml`, `data/companies.yaml`, SQLite, `output/`, `browser-data/`,
`latex/cv.tex`, PDFs, and flags real-looking emails, phone numbers, RUTs, or
`/Users/<you>/` paths in staged content. Fixtures and `*.example.yaml` are allowlisted.

Tests only run when the commit stages code (`*.py`, `pyproject.toml`, `templates/`,
`tests/`), so a docs-only commit stays instant. While you are working test-first and the
suite is legitimately red, `JOBBOT_SKIP_TESTS=1 git commit …` commits anyway; the PII guard
still runs. `git commit --no-verify` skips both and should stay a last resort.

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

# or start from a CV exported as PDF (needs a text layer; no OCR):
uv run jobbot profile import-pdf /path/to/cv.pdf

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
jobbot linkedin sweep [QUERY] [--country CL] [--max-age-days 30] [--fixture PATH] [--cdp URL]
jobbot getonboard search [QUERY]   # sin QUERY usa el rol de tu perfil
jobbot torre search [QUERY] [--remote]   # LATAM/remoto; requisitos vienen estructurados
jobbot portals list | add | detect
jobbot portals form-learn URL --fetch      # what a form asks (reads only, never submits)
jobbot companies recon NOMBRE [--fixture|--cdp] [--apply]  # truth from inside (#45)
jobbot companies signup NOMBRE             # opens the registration; you create the account
jobbot recruiters discover URL             # public hiring practice → candidate knowledge
jobbot recruiters promote URL              # only then does it reach cv advise
jobbot jobs match J0001 | shortlist
jobbot cv build --job J0001
jobbot cv advise [--apply]                 # presentation only; adds no facts, deletes none
jobbot cv advise --llm --dry-run           # what an LLM run would cost, before spending it
jobbot application prepare J0001
jobbot application apply J0001 [--apply]   # ATS prefill plan / open (you submit)
jobbot profile suggest-from-market [--ask] [--promote]
```

Recruiter posts → external ATS URL → portal registry → assisted apply (HITL). Market feedback suggests baseline wording; gaps require confirmation before `--promote`.

## Propagate / sync the CV (standing presence)

**Preferred command:** `jobbot cv sync` ([#43](https://github.com/ljofreflor/jobbot/issues/43)).
Plan = permanent profiles ∪ *active* company career sites. Dry-run by default (writes nothing,
opens no browser). `--apply` confirms one destination at a time: permanent writers plus, for
active companies, either the assisted signup sheet when an account is needed and none is
evidenced ([#44](https://github.com/ljofreflor/jobbot/issues/44)), or open + fill known
`profile.yaml` fields and attach the built CV when no account is required or a session is
evidenced. The human submits. A yes is not a receipt; `jobbot status` shows company portals
from page evidence only.

**Today also:** `cv propagate` rebuilds the base CV and pushes **permanent** profiles only
(`--targets all` / `permanent` = local CV + GoB + Indeed + LinkedIn) — same writers as sync,
without the company plan rows.

Dry-run by default; `--apply` confirms destination by destination:

```bash
jobbot cv sync                             # plan: permanentes + companies active
jobbot cv sync --apply                     # HITL: permanentes + company fill/signup sheet
jobbot cv propagate                        # plan only, permanentes
jobbot cv propagate --apply                # rebuild CV, then Get on Board / Indeed / LinkedIn
jobbot cv propagate --targets permanent --apply
jobbot cv propagate --targets cv,indeed --section headline --apply
jobbot cv propagate --apply --cdp http://127.0.0.1:9222   # reuse your logged-in Chrome
jobbot status                              # what is up (local evidence)
```

Planning is read-only and browser-free: Indeed diffs against the stored snapshot (it asks for
`jobbot indeed pull` when there is none), LinkedIn covers Publications only, and Get on Board
refines the permanent profile cumulatively. Writes stay HITL — nothing is submitted for you.

The plan also runs a **session preflight** so a destination fails in the table instead of mid-write:

```bash
jobbot browser sessions                    # per site: ready | needs_login | unknown | profile_busy
jobbot browser sessions --site indeed --port 9222
```

A session is `ready` only when an open page proves it (a port answering proves nothing), and
JobBot never attaches on its own: it prints the `--cdp` command for you to run. When a leftover
Chrome still holds `browser-data/<site>`, that destination is reported `profile_busy` with the
PID — Chrome allows one instance per profile, so launching there could only fail.
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

`linkedin sweep`, `jobs search` and `jobs add` feed this registry automatically as **candidate**
knowledge. Postings that live on a job board (Indeed, LinkedIn, GetOnBoard) teach nothing about
who hires where, so they are skipped instead of stored.

### One-shot seeding (not a crawler)

Seed a first base of employers from public sources, then review:

```bash
jobbot companies discover data/companies-cl.example.yaml   # banks, retail, telco, mining, tech, insurance
# → output/discovery/company_portals.generated.yaml   (status: candidate)
jobbot companies import output/discovery/company_portals.generated.yaml
jobbot companies promote COMPANY
```

Probing is sequential and polite (own user-agent, `--delay`, no stealth), so plenty of sites
simply refuse it. Those are reported apart from the real gaps: a company that never answered is
listed as *refused our requests (unknown, not absent)*, while a company that answered without a
career path is a genuine gap — feed it a `--search-results` file or teach it with
`companies learn URL --company NAME`. Sites that only serve the `www.` host are retried there
automatically, and the knowledge is still stored www-free so dedup keeps working.

The oneshot probes public career paths and subdomains on the official domain (sequentially,
with a delay) and accepts a candidate only with real evidence: an ATS marker, a redirect, or
employment wording on the page. HTTP 200 alone is not evidence. It writes candidates to
`output/` and never modifies `data/companies.yaml`. Web search hits obtained elsewhere can be
fed in with `--search-results FILE`; JobBot does not query a search engine itself.

Sessions persist under `browser-data/` (gitignored). Passwords are never stored.

## Several candidates in one checkout (test CVs)

Each candidate gets a workspace with its own `data/`, `output/` and database, so nothing
depends on which directory you happen to be in:

```bash
uv run jobbot workspace new rocio        # creates sandboxes/rocio/{data,output}
cp /path/to/cv.pdf /tmp/ && uv run jobbot --workspace rocio profile import-pdf /tmp/cv.pdf
uv run jobbot --workspace rocio cv build --job J0001
uv run jobbot workspace list             # who lives here
uv run jobbot --workspace rocio workspace show
```

The first run stamps that `data/` and `output/` with a fingerprint of the profile's name
(a hash, not the name). If another candidate's profile is later used against them, the
command stops with exit `2` before writing, and you either pick the right workspace or
take it over on purpose with `jobbot workspace adopt`. `sandboxes/` is gitignored and
blocked by the PII guard: a test CV is somebody else's personal data, so delete the
workspace when you are done.

## Tests & quality

```bash
make install
make lint
make typecheck
make test
make coverage   # unit tests + ≥80% coverage gate
# or:
uv run ruff check .
uv run mypy src
uv run pytest
```

GitHub Actions (`.github/workflows/ci.yml`) runs lint, types, unit tests and the coverage gate
on pushes and PRs to `main` / `develop`. Merging **`develop` → `main`** additionally requires
at least **95%** of unit tests to pass (`jobbot.ops.test_gate`).

### Before writing a new helper

- [docs/capabilities.md](docs/capabilities.md) — every command and module with what it exports.
  Generated (`make capabilities`); the suite fails when it is stale, so it can be trusted.
- [docs/library-audit.md](docs/library-audit.md) — what we replaced with a maintained library,
  what we keep ours, and why.

Work that repeats is promoted into a tested function instead of being redone by hand each time;
the rule and its threshold live in `AGENTS.md`, section "Design economics".

## Security & privacy

- Runs locally. No LLM is contacted unless you pass `--llm`, and then only the smallest text unit
  needed, with contact data stripped from the prompt. See [the tutorial](docs/tutorial.md).
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
