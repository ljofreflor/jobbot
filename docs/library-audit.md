# Library audit

Why this file: JobBot grew a lot of hand-rolled parsing. Code another team already
maintains is cheaper and less buggy than ours. Before writing a new helper that
looks generic, check here — and add a row when you decide either way.

Dependency policy for this repo: light, pure-python, offline. No downloadable
models, no binaries, nothing that phones home (see the no-telemetry rule in
`AGENTS.md`).

For what already exists inside this repo, see [capabilities.md](capabilities.md):
that one is generated from the code, this one records decisions.

## Adopted

| Area | Was | Now | Why |
| --- | --- | --- | --- |
| Profile HTML (`adapters/html_parse.py`) | regex helpers `_meta`, `_tag_text`, `_section`, `_list_items` | `beautifulsoup4` (`html.parser`) | Regex over HTML breaks on every markup change and silently returns None; a parser handles nesting and entities |
| Short links (`portals/redirect.py`) | hand-rolled 8-hop loop over `urllib`, manual `Location` joining | `httpx` with `follow_redirects=True` | Redirect chains, relative locations and timeouts are solved problems; also gives a real mock transport for tests |
| Experience durations (`cv/renderer.py`) | hand-written plurals `f"{n} año"`/`f"{n} años"` | `babel.units.format_unit` | Pluralisation is CLDR data, not code |
| Post age (`jobs/freshness.py`) | manual day/week/month/year buckets | `babel.dates.format_timedelta` | Unit choice and plurals come from CLDR; we only set `threshold=1.0` so a 10-month-old post is never shown as "1 año" |
| Apply emails (`portals/email_apply.py`) | regex extraction, no validation | regex + `email-validator` | The dependency was already declared and unused; it drops malformed hits the regex accepts |
| Country names (`jobs/geo.py`) | hand-written `_COUNTRY_ALIASES` | `babel.Locale(...).territories` | Country names in Spanish and English are CLDR data; the list stops drifting |
| PDF text extraction (`profile/importer_pdf.py`) | nothing: PDFs could not be imported | `pypdf` | Pure-python, offline, no models; it also tells us when a PDF has no text layer, which is the signal we need to refuse a scan instead of importing an empty profile. The CV layout rules (sections, bullets, date lines) stay ours: no library knows them |
| Architecture diagrams (`docs/images/`) | hand-drawn ASCII in the README | `diagrams` (docs group only) + Graphviz | README needs a committed PNG; `make architecture` regenerates from `scripts/render_architecture.py`. Not a runtime dependency — Graphviz stays a system tool like XeLaTeX |

## Kept ours, on purpose

| Area | Library considered | Why we keep ours |
| --- | --- | --- |
| Month abbreviations (`_ES_MONTHS`) | `babel.dates.format_date` | CLDR abbreviates September as "sept"; this CV uses three letters ("Sep") everywhere. The month name is a design decision of the CV, so adopting the library here would have silently changed the document |
| LaTeX escaping (`cv/renderer.py`) | `pylatexenc.latexencode` | It rewrites accents as macros, which is wrong for our XeLaTeX + fontspec CV. Ten lines of escaping beat fighting the library |
| Post date from URL (`adapters/linkedin/sweep.py`) | none | `activity id >> 22` is LinkedIn-specific; no library knows it |
| Apply-intent phrases (`_APPLY_HINTS`) | NER models | Domain wording in Spanish/English, and the heavy option is banned by the dependency policy |
| LinkedIn/Gmail selectors | none | Site-specific and changes weekly; a library would lag behind |
| Company provenance rules (`companies/`) | none | Our own knowledge model, not a generic problem |
| ToUnicode repair (`profile/pdf_glyphs.py`) | `pypdf._cmap`, `fontTools` | pypdf parses a /ToUnicode map but exposes no way to complete one, and its private `_cmap` is not an API to depend on. `fontTools` reads the embedded font, which is exactly where the answer is missing: Word's subsets carry no `post` table, so there are no glyph names and the advance widths in `/Widths` are the only evidence left |
| City to country markers (`_COUNTRY_MARKERS`) | `geonamescache` | Ambiguity ("Santiago", "Córdoba") needs a tie-breaker before it can replace the curated list — tracked as [#8](https://github.com/ljofreflor/jobbot/issues/8). Country detection stays curated for the same reason: a wrong hit drops a job, and an undetectable country is kept on purpose |

## Tracked as issues (behaviour changes or weight)

| Area | Library | Note | Issue |
| --- | --- | --- | --- |
| Skills and seniority (`matching/analyzer.py`, `jobs/parsing.py`) | `rapidfuzz` | Root cause of an internship scoring 100% for a senior profile | [#6](https://github.com/ljofreflor/jobbot/issues/6) |
| SQLite migrations (`db/engine.py`) | `alembic` | Today `_migrate_sqlite` can only add columns | [#7](https://github.com/ljofreflor/jobbot/issues/7) |
| City to country (`jobs/geo.py`) | `geonamescache` | Needs a population/context tie-breaker; a wrong hit drops a job | [#8](https://github.com/ljofreflor/jobbot/issues/8) |
| Secret detection (`ops/pii_guard.py`) | `detect-secrets` | Keep the Chilean RUT and phone rules ours | [#9](https://github.com/ljofreflor/jobbot/issues/9) |
| Legacy CV import (`profile/importer_latex.py`) | `TexSoup`, `pylatexenc.latexwalker` | 700 lines of hand parsing; highest potential saving, highest regression risk | [#10](https://github.com/ljofreflor/jobbot/issues/10) |
| Config (`config.py`) | `pydantic-settings` | Growing `[search]` section would come for free | [#11](https://github.com/ljofreflor/jobbot/issues/11) |
| Canonical URLs (`companies/urls.py`) | `w3lib`, `url-normalize` | IDNA and percent-encoding edge cases in the dedup key | [#12](https://github.com/ljofreflor/jobbot/issues/12) |
