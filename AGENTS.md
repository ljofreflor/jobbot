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
jobbot linkedin sweep [QUERY] [--country CL] [--fixture PATH] [--cdp URL]
jobbot jobs match J0001
jobbot jobs shortlist
jobbot cv build --job J0001
jobbot cv advise # mejoras de presentación (determinista; --apply confirma una por una)
jobbot cv propagate # CV base → perfiles permanentes (dry-run; --apply es HITL)
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
- **Post links:** modern LinkedIn cards expose no `urn:li:activity`, so `linkedin sweep` reads each
 post's own URL from its "…" menu ("Copy link to post" → clipboard), resolves `lnkd.in` and strips
 tracking (`utm_*`, `rcm=<member id>`). `--no-copy-links` skips the extra click; without a link the
 author's profile is stored as fallback. Read-only: the menu is opened and closed, nothing shared.
- **Country preference:** `[search].countries` (default `CL`, falls back to `[indeed].country`) drops
 posts detected in other countries; `--country XX` overrides per run, `--any-country` lifts it.
 Remote only rescues a foreign post when it is not tied to a place ("100% remoto para LATAM" sí,
 "remota con visitas a Monterrey" no); `allow_remote = false` quita ese rescate. Países
 indetectables nunca se descartan.
- **Freshness:** `[search].max_age_days` (default 30) descarta posts viejos usando la fecha real que
 trae el activity id del link (`id >> 22` = ms epoch); `--max-age-days N` / `--any-age` por corrida.
 Sin fecha conocida no se descarta. `jobbot jobs backfill-dates` fecha lo ya guardado, offline.
- **ATS apply depth:** discover + store + detect portal + **prefill known fields**; user submits (`application apply --apply`). No auto-submit, no CAPTCHA bypass.
- **Email-only apply:** posts whose only apply route is an address become `ats_kind=email`
 (`mailto:`), with the post body as JD. `application apply --apply` builds the CV adapted to the
 job, opens Gmail compose and **uploads the PDF** (Playwright; `--cdp` to reuse your logged-in
 Chrome, `--no-attach` for compose URL only). JobBot never clicks Send.
- **Market feedback:** `profile suggest-from-market` proposes rephrases and asks gap questions; `--promote` only after user confirms. Never invent; never delete baseline facts.
- **Domain-agnostic by rule:** the candidate may be a nurse, a journalist or an engineer, so **no
 module may gate behaviour on one field's vocabulary**, and none may hold a real employer, city or
 person. Enforced by `tests/unit/test_domain_agnostic.py`, one test per module.
 - JD skills come from the posting's own structure: list items, lead-ins (`Manejo de …`,
 `Experiencia en …`) and typography that marks a tool (`SEO`, `WordPress`, `C++`).
 - Requirement evidence comes from the profile's own wording, tolerating gender and plural
 (`geofísico`/`geofísica`). Role fit compares the job title against the titles actually held —
 there is no table of role families.
 - Market feedback reads its terms from the stored JDs; a confirmed skill lands in a neutral
 group; an imported CV keeps the skill groups its own sections used.
 - A post is discovered for saying it is hiring or how to apply, not for its field. Search
 defaults come from `personal.headline`; no default role lives in the code.
 - Equivalence tables (`jobs/normalization.py`) are allowed **because an unknown term falls
 through unchanged**: they add recall for names of the same thing, never a gate.
- **PDF CV import:** `profile import-pdf` reads the text layer only (no OCR, no models). A PDF has
 no structure, so the parser locates each role by its date (a range, a range whose months share
 one year — `julio – agosto 2026` — or a single right-aligned year) and then picks company and
 title by scoring the nearby lines, never by a fixed position. The employer may run long and end
 in a full stop, so the evidence that a line names one is the place it closes with, not its
 length. A company is never inherited unless a previous role actually named one.
 What it cannot resolve becomes a warning (glued text with no space glyphs, roles stranded
 outside the experience section when a two-column export interleaves columns); the generated YAML
 is always reviewed before `promote-generated`.
 Fixture PDFs are built at test time (`tests/fixtures/cv_pdf.py`): no binary CV is ever committed.
- **Broken font maps:** Word embeds one subset font per style and sometimes leaves a ligature out
 of `/ToUnicode`, so pypdf falls back to the raw byte and `instituciones` reads `insVtuciones`
 while the same font still writes a genuine `V`. `profile/pdf_glyphs.py` repairs the map before
 extraction, because after it the two characters are identical. The evidence is the advance width
 in `/Widths`: a glyph as wide as `t` plus `i`, and as wide as no other pair, is the `ti`
 ligature; a subset too small to prove it follows a sibling subset of the same base font at the
 same width. A width that fits two ligatures (`fi` and `fl` are the same) is reported, never
 guessed.
- **Torre:** `torre search` usa la búsqueda pública de oportunidades (JSON, sin navegador). El
 payload trae los requisitos con su experiencia exigida, así que las skills no salen de parsear
 prosa; el JD completo vive en una página client-rendered, por lo que una oferta de Torre es una
 pista para abrir, no un JD completo. El payload también lista a las personas detrás del aviso:
 nada bajo `members` llega nunca a un `JobPosting`. Cuando la oportunidad apunta a un ATS externo,
 esa URL es la que se guarda y alimenta el registro de empresas.
- **Company career platforms:** `jobbot companies` mantiene conocimiento **público** empresa↔portales
 (0..N career sites por empresa: portal propio, Workday, Greenhouse de filial…). Provenance por
 observación, dedup por URL canónica (sin query/fragment), contradicción → `stale` sin sobreescribir,
 y ATS `unknown` salvo evidencia técnica (host, redirect, marcador HTML embebido). `linkedin sweep`
 `jobs search` y `jobs add` alimentan candidatos (los job boards se omiten); solo `companies
 promote` los vuelve activos. `companies discover`
 es un **oneshot** que escribe candidatos en `output/discovery/` y nunca toca `data/companies.yaml`;
 HTTP 200 no es evidencia y un sitio que nos rechaza (403/conexión cortada) se reporta como
 desconocido, no como ausencia. Compartir siempre vía `companies export` (solo activos, sin PII).
- **Qué pide un formulario:** `portals form-learn URL --fetch|--fixture PATH` lee un formulario de
  postulación y guarda **solo las preguntas**: etiqueta, tipo, obligatoriedad, opciones de un select
  y qué archivos acepta. Nunca guarda un valor tipeado, un token oculto ni el teléfono de ejemplo de
  un placeholder, y no envía nada. `application apply --apply` lo aprende de paso, sin bloquear la
  postulación si la página no se puede leer (queda como `unknown`, no como formulario vacío).
  `data/form_knowledge.yaml` es local (gitignored + `pii_guard`) y no se comparte: es el insumo que
  `cv advise` usa para saber qué preguntan realmente las empresas.
- **Registro de cuenta:** `companies signup NOMBRE` abre el portal y lista qué datos pedirá, con lo
  que `profile.yaml` ya responde y lo que queda a tu criterio. No crea la cuenta, no fija contraseña
  y no acepta términos; `jobbot.companies.signup` no tiene cliente HTTP ni driver de navegador, y un
  test lo verifica leyendo su propio código. Los ATS que no requieren cuenta lo dicen (Greenhouse,
  Lever, Ashby); si no hay evidencia, es `unknown`, no una suposición.
- **Asesor de presentación:** `cv advise` propone **pocas** mejoras por corrida en tres ejes
  (legibilidad de máquina, lenguaje, puesta en página) usando JD guardados, formularios observados y
  prácticas de reclutamiento que promoviste. Dos invariantes se **verifican**, no se prometen: una
  sugerencia no puede afirmar nada que el perfil no respalde (reusa el detector de invención de
  `nlp/refine.py`) ni perder una cifra o un nombre propio del texto actual; lo que falla se descarta
  antes de mostrarse. `--apply` confirma una por una y respalda `profile.yaml`; la bitácora
  (`output/cv/advice_log.yaml`) evita repetir lo que ya rechazaste.
- **Economía de tokens:** el nivel determinista es el default y no contacta a nadie. `--llm` manda
  **una línea**, nunca el CV completo, con el contacto redactado del prompt; `--llm-deep` solo entra
  si el nivel barato no produjo algo válido. Caché por hash de contenido más modelo, presupuesto por
  corrida (`--max-llm-calls`) y `--dry-run` que imprime qué se enviaría y cuánto sin gastar. Toda
  salida del LLM pasa la misma validación determinista: si inventa o borra, se descarta y queda la
  sugerencia determinista. La suite corre sin red, sin API key y sin el extra `llm`.
- **Conocimiento de reclutamiento:** `recruiters discover|list|show|promote|reject|export` guarda
  **prácticas públicas**, no personas: el modelo no tiene campo para autor, empleador ni contacto.
  Respeta `robots.txt`, deja fuera lo que está detrás de login (no fue publicado para nosotros) y
  reporta un rechazo como rechazo. Candidato hasta que hagas `promote`; solo lo activo llega a
  `cv advise`. `data/recruiters.yaml` es local; se comparte vía `recruiters export`.
- **Get on Board:** mantenedor de **perfil permanente** con **computación acumulativa**:
  `getonboard prepare` refina el draft previo (no lo tira) usando `profile.yaml` como hechos;
  `--seed` importa texto viejo del portal; `--llm` usa LangChain si `jobbot[llm]` + `OPENAI_API_KEY`;
  `--cold` solo si quieres partir de cero. Historia en `output/getonboard/history/`.
  HITL: https://www.getonbrd.com/webpros/edit + Tus CVs. `application prepare` reusa los textos.

## Workspaces (several candidates, one checkout)

A checkout may hold test CVs next to the real profile. The current directory is not
enough to keep them apart: every workspace numbers its jobs from `J0001`, so one command
run from the wrong folder overwrites another person's `output/jobs/J0001/` under the same
file names, silently.

- **Selection is explicit:** `jobbot --workspace NAME …` (or `JOBBOT_WORKSPACE`) resolves
  `data/`, `output/` and the database under `sandboxes/NAME/`, whatever the current
  directory is. Templates come from the checkout, because they are code, not data.
  Without a workspace nothing changes: the current directory is the root, as before.
- **Owner stamp:** the first run stamps `data/` and `output/` with a fingerprint of the
  profile's name (`.jobbot-owner.json`, a hash — never the name). A profile that does not
  match the stamp stops the command with exit `2` before writing anything; taking a
  directory over is deliberate (`jobbot workspace adopt`). This also protects the real
  `data/` from a test CV dropped over `data/profile.yaml`.
- **A selected workspace ignores `~/.config/jobbot/config.toml`**, whose absolute paths
  would otherwise reach into the real profile from inside a sandbox.
- **`sandboxes/` is somebody else's PII:** gitignored and blocked by the PII guard.
  Delete a test CV's workspace when you are done with it.

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
- **PII:** never commit `data/profile.yaml`, `data/portals.yaml`, `data/companies.yaml`, SQLite, `browser-data/`, `sandboxes/`, or `output/`. Track only `*.example.yaml` templates.
- **PII guard:** `make hooks` enables `.githooks/pre-commit` (`jobbot.ops.pii_guard`) — blocked paths + real-looking email/phone/RUT/home-path detection. Fixtures and examples allowlisted. `pii_guard.redact()` is the one place that defines what counts as contact data, reused wherever text leaves your files (learned form labels, LLM prompts).
- **Which commits run the suite:** `jobbot.ops.precommit.tests_needed()` decides, and it is unit-tested instead of living as a shell regex. Policy counts as behaviour: editing **this file** runs the tests, because for an agent working from a clone this file is the whole policy.
- **Polite web reading:** the one-shot and `recruiters discover` obey `robots.txt` via `RobotsPolicy`, cached per host. Being told not to read a page is reported as *omitted*; being unable to read it (403, 429, 5xx, dropped connection) is reported as *refused*. Neither ever becomes "there is nothing there".
- **Private LaTeX CV:** tracked dummy is `latex/cv.tex.demo` only; real `.tex`/`latex/cv.tex` stay gitignored. Prefer `paths.legacy_cv` outside the repo or a local ignored copy. See `latex/README.md`.
- LinkedIn: read-only audit by default. **Exception:** `linkedin sync --section publications`
  writes Publications only (dry-run default; `--apply` + per-item confirmation unless `--yes`).
- Indeed writes: dry-run default; `--apply` + confirmation.
- **Session preflight:** `jobbot.browser.sessions` reports per-site state from evidence only
  (`ready` needs an open signed-in page; a live port proves nothing). JobBot never auto-attaches:
  it suggests `--cdp`. A persistent profile held by another Chrome is `profile_busy` and blocks
  that destination up front (`BrowserSession` also refuses to launch over it).
- Removals ignored by default.

## Regression tests (mandatory)

Every bug/failure → unit test that fails first, then fix. Prefer fixtures over live portals.

## Dependencies

Before hand-rolling something generic (HTML, URLs, dates, emails, secrets, LaTeX), read
[docs/library-audit.md](docs/library-audit.md): it records what we replaced with a maintained
library, what we keep ours and why, and which migrations are open issues. Add a row when you
decide either way. Dependencies must be light, pure-python and offline — no downloadable models,
no service that phones home.

## Design economics (slow once, fast after)

A model can answer many questions here without writing a file: read a posting, judge a match,
extract an address. That answer is expensive, unverifiable and gone at the end of the chat.
The same work as a function is cheap forever and can be tested. So work that repeats gets
**promoted** into code, and after that it gets **called**, not re-derived.

The practice is not ours: it is the rule of three (extract at the third duplication) plus
knowledge compilation (costly deliberate reasoning becomes an automatic procedure), and in
agent terms the split between making a tool once and using it many times.

**When to promote.** At the third time the same analysis is asked, or the first time if the
repetition is predictable: a step of the cargo loop, or anything another agent would have to
re-derive from the same inputs. Do not promote on a hunch — a speculative helper is dead code
with a test attached, the same waste wearing a convincing costume.

**What a promotion must ship.**

- The function in the module that owns the subject, not in `cli.py`.
- A CLI entry only if a human will run it.
- A test that fails first (see above). Untested code is not a promotion, it is a draft.
- Its line in [docs/capabilities.md](docs/capabilities.md), so the next agent finds it
  (`make capabilities` regenerates it; a stale index fails the suite).

**What to call instead of re-deriving.**

- Read [docs/capabilities.md](docs/capabilities.md) before searching the tree: 99 modules and
  491 public symbols make a blind `grep` more expensive than the index.
- Read [docs/library-audit.md](docs/library-audit.md) before hand-rolling something generic.
- Run `uv run jobbot …` instead of reasoning out an answer the CLI already prints, and read
  the command's output instead of pasting whole files into context.

This is not only about tokens. The deterministic path is the auditable one: never inventing
experience, and stopping for HITL, are guarantees that live in code and its tests — not in the
memory of a conversation.

## Remote agents (issues, cloud, CI)

An agent working from a clone only has what git tracks, and the PII lives outside git:
`data/profile.yaml`, `data/portals.yaml`, `data/companies.yaml`, the SQLite database,
`browser-data/`, `output/` and the real `latex/cv.tex` are **not** there.

So, when working on an issue without the local machine:

- Build the failing test from a fixture under `tests/fixtures/`; never assume stored jobs (`J0047`)
  or a real profile exist.
- If closing the issue needs real data (legacy CV import, a stored post, a logged-in browser),
  ship the code plus fixture tests and say in the PR which check the human has to run locally.
- Never add a fixture with real PII. `*.example.yaml` and `latex/cv.tex.demo` are the templates.
- `.cursor/` is local, so this file is the whole policy: read it before touching anything.

## Verify

```bash
uv sync --group dev
uv run ruff check .
uv run mypy src
uv run pytest
make coverage   # unit suite + ≥80% line gate (see [tool.coverage] in pyproject.toml)
```

CI (`.github/workflows/ci.yml`) runs the same checks on `develop` / `main` and on PRs.

Branch gates:

- **feature → `develop`:** 100% of unit tests must pass, coverage ≥80%.
- **`develop` → `main`:** at least **95%** of unit tests must pass, coverage ≥80%.

A change is not delivered until its behaviour has a unit test. `cli.py` and live
Playwright portal clients are omitted from the line count (they still have focused
unit tests) so the gate measures offline, fixture-backed code.

### CI failures (detect → fix)

When CI is red on a PR or push you are working on, **resolve it** — do not stop at reporting the check name.

1. **Read the failed logs** (`gh pr checks`, `gh run view <id> --log-failed`) until you know the first failing step and the concrete error (ruff/mypy/pytest/coverage).
2. **Fix the root cause** locally with the same Verify commands; push the fix on the same feature branch (or open a follow-up PR into `develop` if the breakage is already merged). Add a regression unit test when the failure is behavioural.
3. **HITL only where it matters:** ask before merging to `develop`/`main`, force-push, amending shared history, or anything that touches PII / live portals. The human does not need to approve reading logs or applying a mechanical lint/test fix.

Default posture: red CI → logs → fix → green CI. Summarize what broke and what you changed after the fix is in.

## Key commands

```bash
uv run jobbot profile validate
uv run jobbot profile import-latex
uv run jobbot profile import-pdf /path/to/cv.pdf # PDF con capa de texto; sin OCR
uv run jobbot cv build
uv run jobbot cv build --job J0001            # moderncv (tu diseño) por defecto
uv run jobbot cv build --job J0001 --style plain
uv run jobbot cv propagate                 # plan: CV base + perfiles permanentes
uv run jobbot cv propagate --apply         # HITL por destino (GoB, Indeed, LinkedIn)
uv run jobbot cv advise                    # determinista, sin tokens
uv run jobbot cv advise --apply            # confirma una por una → profile.yaml (con backup)
uv run jobbot cv advise --llm --dry-run    # qué se enviaría y cuánto, sin gastar
uv run jobbot cv advise --llm --max-llm-calls 3
uv run jobbot jobs add --file tests/fixtures/jobs/senior_ds_retail.txt
uv run jobbot jobs match J0001
uv run jobbot application prepare J0001
uv run jobbot indeed login|pull|diff|sync --section headline
uv run jobbot linkedin login|pull|diff
uv run jobbot linkedin sync --section publications          # dry-run
uv run jobbot linkedin sync --section publications --apply  # confirm each
uv run jobbot linkedin sweep                    # query desde personal.headline
uv run jobbot linkedin sweep "enviar CV" --country CL --country AR
uv run jobbot linkedin sweep "enviar CV" --any-country
uv run jobbot linkedin sweep "enviar CV" --no-copy-links   # sin abrir el menú "…"
uv run jobbot linkedin sweep "enviar CV" --max-age-days 7
uv run jobbot linkedin sweep "enviar CV" --any-age
uv run jobbot jobs backfill-dates
uv run jobbot getonboard prepare              # refine acumulativo (default)
uv run jobbot getonboard prepare --seed old_gob.txt
uv run jobbot getonboard prepare --llm        # LangChain (uv sync --extra llm)
uv run jobbot getonboard prepare --cold       # solo si quieres partir de cero
uv run jobbot getonboard show-profile
uv run jobbot getonboard open-profile
uv run jobbot getonboard open-cvs
uv run jobbot getonboard sync --apply
uv run jobbot getonboard search                 # query desde personal.headline
uv run jobbot torre search [--remote]           # Torre (LATAM/remoto), API pública
uv run jobbot ops failures
uv run jobbot ops failure show F0001
uv run jobbot ops failure triage F0001 --status fixed
uv run jobbot ops failure issue F0001          # HITL → gh issue
uv run jobbot ops loop --cmd getonboard-prepare --interval 300
uv run jobbot portals list|add|detect
uv run jobbot portals form-learn URL --fetch          # qué pide un formulario (solo lee)
uv run jobbot portals form-learn URL --fixture page.html
uv run jobbot recruiters discover URL                 # prácticas públicas → candidatas
uv run jobbot recruiters list|show|promote|reject|export
uv run jobbot companies detect URL
uv run jobbot companies learn URL --company NAME --country CL
uv run jobbot companies list|show|promote|reject|sites|export
uv run jobbot companies discover data/companies-cl.example.yaml   # oneshot → candidatos
uv run jobbot companies import output/discovery/company_portals.generated.yaml
uv run jobbot companies signup NOMBRE                 # abre el registro; no crea la cuenta
uv run jobbot application apply J0001
uv run jobbot application apply J0001 --apply           # email: adapted CV attached in Gmail
uv run jobbot browser sessions # preflight: ready | needs_login | unknown | profile_busy
uv run jobbot browser chrome-debug --site gmail --port 9223
uv run jobbot application apply J0001 --apply --cdp http://127.0.0.1:9223
uv run jobbot profile suggest-from-market
uv run jobbot workspace list|new NAME|show|adopt
uv run jobbot --workspace NAME cv build --job J0001  # runs against a test CV
```
