# JobBot

Local terminal tool for managing a job search: structured CV as source of truth, portal sync,
matching, adapted CVs, and assisted applications. **No web UI** — everything runs from the CLI.

## Architecture

```text
                         profile.yaml
                              │
              ┌───────────────┼────────────────┐
              │               │                │
              ▼               ▼                ▼
            LaTeX           Indeed          LinkedIn
              │               │                │
              ▼               ▼                ▼
             PDF       IndeedAdapter     LinkedInAdapter
```

`data/profile.yaml` is the single source of professional truth. LaTeX, PDF, Indeed, and LinkedIn
are views or adapters. Facts are never invented to fit a job posting.

## Status

**Endgame:** match → decide → CV derivado → application package → postular (portales futuros).

Working today:

- Profile validate / import-latex / promote
- `cv build` base and `--job Jxxxx`
- `jobs add|show|match|shortlist|note`
- `application prepare|show|open` + `applications list`
- Indeed/LinkedIn: `login|status|inspect|pull|diff`; Indeed `sync --section headline` (dry-run default, `--apply`)
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
cp data/portals.example.yaml data/portals.yaml   # optional ATS seed
```

**PII:** `data/profile.yaml` (and `portals.yaml`, SQLite, `browser-data/`, `output/`) are
**gitignored**. Only `*.example.yaml` templates are safe to commit. See [data/README.md](data/README.md).

**Private LaTeX CV:** keep your real moderncv private. Use `latex/cv.tex.demo` (tracked
dummy) or set `paths.legacy_cv` in local `.jobbot.toml` to a path outside the repo / to
gitignored `latex/cv.tex`. See [latex/README.md](latex/README.md).

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
jobbot linkedin sweep "hiring data scientist" [--fixture PATH] [--cdp URL]
jobbot getonboard search "data scientist"
jobbot portals list | add | detect
jobbot jobs match J0001 | shortlist
jobbot cv build --job J0001
jobbot application prepare J0001
jobbot application apply J0001 [--apply]   # ATS prefill plan / open (you submit)
jobbot profile suggest-from-market [--ask] [--promote]
```

Recruiter posts → external ATS URL → portal registry → assisted apply (HITL). Market feedback suggests baseline wording; gaps require confirmation before `--promote`.

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
