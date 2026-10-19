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
| Language names (`jobs/conditions.py`) | a hand-written list of languages | `babel.Locale(...).languages` | "Inglés", "English" and "portugués" resolve to ISO 639-1 from CLDR; only two-letter codes and names of four letters or more are read, so short words never pass for a language |
| PDF text extraction (`profile/importer_pdf.py`) | nothing: PDFs could not be imported | `pypdf` | Pure-python, offline, no models; it also tells us when a PDF has no text layer, which is the signal we need to refuse a scan instead of importing an empty profile. The CV layout rules (sections, bullets, date lines) stay ours: no library knows them |
| Canonical career URLs (`companies/urls.py` `public_url`) | hand-rolled `urlparse` | `httpx.URL` (already a dependency) | IDNA, default ports, dot-segments and percent-decoding are solved; `www.`, query/fragment drops and LinkedIn tracking parameters stay ours |
| Cities the curated list never named (`jobs/geo.py`) | nothing: Quito stayed undetectable | snapshot `resources/cities_100k.json` (GeoNames, CC-BY 4.0) | `geonamescache` is 33 MB, mostly alternate names. The wheel ships primary names of cities at or above 100k inhabitants. A hit needs a location frame (`en`, `in`, `ubicación:`); a name in several countries is used only when one has 8× the population of the next, or when the text names one of those countries. Anything closer stays undetectable |
| Generic secrets (`ops/pii_guard.py`) | no secret scan | `detect-secrets` AWS-key and private-key plugins | Keyword and entropy plugins stay off, so the word "password" is not a secret. Chilean RUT, phone, email and home path stay ours. The package pulls `requests`; the guard never opens a connection |

## Kept ours, on purpose

| Area | Library considered | Why we keep ours |
| --- | --- | --- |
| Month abbreviations (`_ES_MONTHS`) | `babel.dates.format_date` | CLDR abbreviates September as "sept"; this CV uses three letters ("Sep") everywhere. The month name is a design decision of the CV, so adopting the library here would have silently changed the document |
| LaTeX escaping (`cv/renderer.py`) | `pylatexenc.latexencode` | It rewrites accents as macros, which is wrong for our XeLaTeX + fontspec CV. Ten lines of escaping beat fighting the library |
| Post date from URL (`adapters/linkedin/sweep.py`) | none | `activity id >> 22` is LinkedIn-specific; no library knows it |
| Apply-intent phrases (`_APPLY_HINTS`) | NER models | Domain wording in Spanish/English, and the heavy option is banned by the dependency policy |
| LinkedIn/Gmail selectors | none | Site-specific and changes weekly; a library would lag behind |
| Company provenance rules (`companies/`) | none | Our own knowledge model, not a generic problem |
| Opening pages without focus (`browser/background.py`) | `webbrowser` alone | Stdlib `webbrowser` is still the fallback (`autoraise=False`), but on macOS it runs AppleScript `open location` and ignores `autoraise`, so the browser comes forward. `open -g` and CDP `Target.createTarget {background: true}` are the documented no-focus paths; no library wraps them |
| Password vault (`vault.py`) | `keyring`, `cryptography` (Fernet) | OS keyring is not pure-python/offline on every host; Fernet adds a native extra. The opt-in file is `chmod 0600` YAML next to the profile — same trust boundary as SSH keys / `.netrc`. Passphrase wrap is a later issue if sync becomes a real need ([#157](https://github.com/ljofreflor/jobbot/issues/157)) |
| Reserved example domains (`companies/urls.py` `is_reserved_host`) | `tldextract`, `publicsuffix2` | The public suffix list does not mark RFC 2606/6761 names as reserved, and `tldextract` downloads its list at runtime. Three domains and four TLDs fixed by RFC are a constant, not a dependency |
| ToUnicode repair (`profile/pdf_glyphs.py`) | `pypdf._cmap`, `fontTools` | pypdf parses a /ToUnicode map but exposes no way to complete one, and its private `_cmap` is not an API to depend on. `fontTools` reads the embedded font, which is exactly where the answer is missing: Word's subsets carry no `post` table, so there are no glyph names and the advance widths in `/Widths` are the only evidence left |
| Posting language (`jobs/language.py`) | `langdetect`, `lingua-language-detector` | Only Spanish vs English is needed, and an unclear text must fall back to the CV's language instead of guessing. `langdetect` is random unless seeded and unreliable on short summaries; `lingua` ships large models. A function-word majority is deterministic and testable |
| ORCID check digit (`models/candidate.py`) | `python-stdnum` (`iso7064.mod_11_2`) | A whole dependency for a six-line ISO 7064 11,2 loop that never changes; the shape regex and the checksum are covered by unit tests |
| UN Careers feed (`adapters/un_careers/feed.py`) | `feedparser`, `defusedxml` | One RSS 2.0 document with four fields per item; stdlib `xml.etree` reads it, and Python ≥ 3.12 ships an expat that refuses entity-expansion bombs and never fetches external entities. The fields that matter live in a `Key : value` block inside `description`, which no feed library parses |
| Curated country markers (`_COUNTRY_MARKERS`) | `geonamescache` as a runtime dependency | Currencies, demonyms and the cities already decided (Santiago → CL) stay in the list. The package is 33 MB; the long tail is the snapshot above, and a close population race is still "undetectable" |
| Skill aliases (`jobs/normalization.py`) | `rapidfuzz` | `sklearn` / `scikit-learn` and `ml` / `machine learning` are already exact aliases, and an unknown term falls through unchanged. A fuzzy `extractOne` would merge skills that only look alike. The internship that scored 100% for a senior profile was a missing level cap, not a fuzzy-match gap |
| SQLite migrations (`db/engine.py`) | `alembic` | New nullable columns are added from the ORM on every table, so the hand list is gone. Alembic's revision directory pays off when a migration must rename, drop, or backfill; this local database has not needed that |
| Landing scrollytelling (`docs/overrides/home.html`) | `scrollama`, GSAP ScrollTrigger, CSS `animation-timeline` | Six beats that swap one terminal line. Scrollama (MIT, IntersectionObserver, last release 3.2.0 in 2022) only names the step; we already write that observer in a few lines and avoid a vendored script. GSAP ScrollTrigger is a motion runtime we do not need for opacity and a text swap. CSS scroll-driven animations are not Baseline (no Firefox release as of 2026) and cannot choose which command to show. Sticky graphic + `IntersectionObserver`, with the step text in the HTML so the story works if the script does not run |

## Tracked as issues (behaviour changes or weight)

| Area | Library | Note | Issue |
| --- | --- | --- | --- |
| Legacy CV import (`profile/importer_latex.py`) | `TexSoup`, `pylatexenc.latexwalker` | 700 lines of hand parsing; highest potential saving, highest regression risk | [#10](https://github.com/ljofreflor/jobbot/issues/10) |
| Config (`config.py`) | `pydantic-settings` | Growing `[search]` section would come for free | [#11](https://github.com/ljofreflor/jobbot/issues/11) |
