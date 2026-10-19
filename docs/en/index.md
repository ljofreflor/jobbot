---
template: home.html
title: Jobbot — search while you code
description: >-
  Local CLI for job hunting without leaving the editor: find where they publish,
  prepare without inventing, apply with you in control. Human + bot, on your machine.
hide:
  - navigation
  - toc
---

<section class="jb-section" markdown="1">

## People · opportunities · technology

A craftsman's tool: **search while you code**. No invented product.
Full voice (Spanish): [Manifiesto](../manifesto.md).

<ul class="jb-benefits">
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    </div>
    <strong>Find where they publish</strong>
    <span>ATS hosts, boards, sweeps — openings that fit your real profile, not an invented CV.</span>
  </li>
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M7 3h10v18H7z"/><path d="M10 8h4M10 12h4M10 16h2"/><path d="M9 21l1.5-1.5L13 21"/></svg>
    </div>
    <strong>Prepare without inventing</strong>
    <span>Build the package from facts you already have; you press send.</span>
  </li>
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M4 19V9M10 19V5M16 19v-7M20 19H3"/></svg>
    </div>
    <strong>Apply with you in control</strong>
    <span>Matching, shortlist and evidence — HITL, no account, no telemetry.</span>
  </li>
</ul>

<p class="jb-pillars">More opportunities. A better tomorrow. Without leaving the terminal.</p>

</section>

<section class="jb-section" markdown="1">

## Two loops, one source of truth

The channel may be the terminal or an agent (Cursor, VS Code, Claude Code…).
The product is the local CLI. Two loops; one SoT: `data/profile.yaml`.

**1 · Apply to a vacancy** — match → CV → plan; **you submit**.

```bash
jobbot linkedin sweep "machine learning"
jobbot jobs match J0002
jobbot cv build --job J0002
jobbot application apply J0002        # plan only; you submit
```

**2 · Standing presence** — improve how you present facts you already have, and
keep the CV current on active portals (HITL; never invents).

```bash
jobbot cv advise --apply              # presentation; confirm one by one
jobbot cv sync --apply                # permanent + active company portals
jobbot status                         # local evidence of what is up to date
```

[Install & quickstart](../instalacion.md) · [Every command](#commands) ·
[Flag reference](../comandos.md) · [Manifesto](../manifesto.md)

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Privacy on your machine

Your profile, sessions, and outputs stay on disk. No Jobbot account, no
telemetry — failures live in your local SQLite.

<ul class="jb-evidence">
  <li><code>data/profile.yaml</code>, SQLite, <code>browser-data/</code>, and <code>output/</code> are gitignored</li>
  <li>Pre-commit hook (<code>make hooks</code>) blocks PII even with <code>git add -f</code></li>
  <li>Human-in-the-loop: prepares the package; <strong>you submit</strong></li>
  <li>No CAPTCHA or 2FA bypass — when a portal challenges you, it hands you the keyboard</li>
</ul>

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Find recent openings

Indeed, Get on Board, and LinkedIn recruiter posts. Freshness filters, country
per role, and multi-vacancy posts split into independent jobs.

```bash
jobbot jobs search "Senior Data Scientist" --location Santiago
jobbot getonboard search "data scientist"
jobbot linkedin sweep "machine learning" --country CL --max-age-days 30
```

One SoftServe post with five roles → five jobs, each with its own country and
ATS URL. Match and apply per role, not per post.

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## One source of truth

<code>data/profile.yaml</code> is the professional SoT. LaTeX, PDF, Indeed, and LinkedIn
are views or adapters. The adapted CV reorders evidence; it never invents experience.

```bash
jobbot profile validate
jobbot cv build --job J0002          # derived from profile + JD
jobbot profile suggest-from-market   # suggestions; you confirm gaps
```

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Sync to the portals

Indeed, LinkedIn, and Get on Board adapters: login, inspect, pull, diff, and sync
(dry-run by default). Standing presence is `cv sync` (HITL per destination).

```bash
jobbot indeed sync --section headline   # plan; --apply writes
jobbot linkedin sync --section publications --apply
jobbot cv sync --apply                  # presence; confirm per destination
```

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Open source, on your machine

Local CLI. No Jobbot SaaS backend. The channel is Cursor, VS Code, Claude Code,
or another agent — not a proprietary Jobbot chat. You run the binary; you decide
what leaves disk.

```bash
curl -fsSL https://raw.githubusercontent.com/ljofreflor/jobbot/main/scripts/install.sh | bash
mkdir -p ~/postulaciones && cd ~/postulaciones && jobbot init
jobbot version
# later: jobbot update
```

Contributing to the code? Then `git clone` + `uv sync --group dev` (see [install](../instalacion.md)).

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Match, ATS, and Latam

Scores against your profile, ATS detection (Greenhouse, Lever, Workday, Teamtailor
even on custom hosts, Get on Board…), a portal registry that learns from evidence,
and Chile / Latam focus in searches and roundups.

<ul class="jb-evidence">
  <li><code>jobs match</code> / <code>shortlist</code> — scores; does not decide for you</li>
  <li><code>portals detect</code> + <code>companies learn</code> — public topology, no PII</li>
  <li><code>application apply --apply</code> — opens the form; you submit</li>
  <li>Latam roundups: country per role (<code>--country CL</code>), not per whole post</li>
</ul>

</section>

<section class="jb-section jb-section--cmds jb-cmds-en" markdown="1">

## The commands {#commands}

Every public command in `src/jobbot/cli.py`, one line each. Flags are in the
[reference](../comandos.md) (Spanish). `jobbot <command> --help` prints the rest.
Nothing in this list submits alone or invents a fact. Rows marked **apply** (cobalt) or **presence** (navy) are the seven steps above; the mark returns to that step in the loop. In the bar, **CV**, **Vacancies**, and **Applications** are underlined: that is where those seven live.

<nav class="jb-cmdnav" aria-label="Command groups">
  <a href="#cmd-machine" aria-controls="cmd-machine">On your machine</a>
  <a href="#cmd-profile" aria-controls="cmd-profile">Profile</a>
  <a href="#cmd-cv" aria-controls="cmd-cv" class="jb-cmdnav__story" data-story-cmds="build advise sync" title="Apply and presence steps">CV</a>
  <a href="#cmd-vacancies" aria-controls="cmd-vacancies" class="jb-cmdnav__story is-pin-step" data-story-cmds="get match conditions" title="Apply steps">Vacancies</a>
  <a href="#cmd-applications" aria-controls="cmd-applications" class="jb-cmdnav__story" data-story-cmds="apply" title="Apply steps">Applications</a>
  <a href="#cmd-portals" aria-controls="cmd-portals">Portals</a>
  <a href="#cmd-browser" aria-controls="cmd-browser">Browser</a>
  <a href="#cmd-companies" aria-controls="cmd-companies">Companies</a>
  <a href="#cmd-ops" aria-controls="cmd-ops">Operations</a>
</nav>

### On your machine {#cmd-machine}

| Command | What it does |
|---------|----------------|
| `jobbot init [DIR]` | Creates the workspace in that folder: config, `AGENTS.md`, and local data. |
| `jobbot update` | Reinstalls the executable from GitHub. `--check` only compares with `main`. `--schedule daily`, `off`, or `status` sets, removes, or shows the daily check. |
| `jobbot version` | Prints the installed version. |
| `jobbot status` | Local evidence for the CV and active portals. Without evidence it does not claim you are up to date. |
| `jobbot capture URL` | Keeps a shared link as a candidate, with no download. `--list` shows what is still pending. |
| `jobbot workspace list` | Lists sandboxes. Also `new`, `show`, `adopt`, `delete`. |
| `jobbot workspace consent` | Records consent and a deletion date for one sandbox. |
| `jobbot advisor status` | One line per sandbox: fingerprint, counts, proposal, retention. Never the name. |
| `jobbot advisor report` | Writes the redacted summary for the selected workspace. |

### Profile {#cmd-profile}

| Command | What it does |
|---------|----------------|
| `jobbot profile validate` | Checks the local YAML. |
| `jobbot profile show` | Short profile summary. |
| `jobbot profile import-pdf PATH` | Reads the PDF text layer into a generated file. No OCR. |
| `jobbot profile import-latex [PATH]` | Imports a legacy LaTeX CV into the generated file. |
| `jobbot profile promote-generated` | Copies the generated file onto `profile.yaml` after you confirm. |
| `jobbot profile suggest-from-market` | Suggests wording from stored postings. It does not touch the profile without `--promote` and your yes. |
| `jobbot profile queries` | Derives searches from your experience. `--apply` saves them if you confirm. |
| `jobbot profile status` | Consistency between local data and portal snapshots. |
| `jobbot profile diff` | Shows that diff. |

### CV {#cmd-cv}

| Command | What it does |
|---------|----------------|
| <span id="cmd-build" class="jb-in-story"><code>jobbot cv build</code> <a class="jb-in-story__tag" href="#story-build" aria-controls="story-build" aria-label="Step 3, apply, build">apply</a></span> | Builds the CV from the profile. `--job` orders it for one posting; `--full` keeps every role. `--target cv` or `ats`. |
| <span id="cmd-advise" class="jb-in-story"><code>jobbot cv advise</code> <a class="jb-in-story__tag jb-in-story__tag--presence" href="#story-advise" aria-controls="story-advise" aria-label="Step 6, presence, advise">presence</a></span> | A few presentation edits. `--apply` confirms them one by one. |
| `jobbot cv tune-for Jxxxx` | The same advise, scoped to one posting or one link. |
| `jobbot cv propagate` | Plan for permanent profiles. `--apply` confirms each destination. |
| <span id="cmd-sync" class="jb-in-story"><code>jobbot cv sync</code> <a class="jb-in-story__tag jb-in-story__tag--presence" href="#story-sync" aria-controls="story-sync" aria-label="Step 7, presence, sync">presence</a></span> | Standing presence: permanent profiles and active companies. `--apply` waits for you. |
| `jobbot cv status` | Alias of `jobbot status`. |

### Vacancies {#cmd-vacancies .is-pin-step}

| Command | What it does |
|---------|----------------|
| <span id="cmd-get" class="jb-in-story"><code>jobbot get URL</code> <a class="jb-in-story__tag" href="#story-get" aria-controls="story-get" aria-current="step" aria-label="Step 1, apply, get">apply</a></span> | Downloads one posting (Get on Board, Indeed, Workday), builds the CV and the package. It does not send. |
| `jobbot jobs add` | Stores a vacancy from a file or stdin. |
| `jobbot jobs search QUERY` | Searches Indeed and stores results locally. |
| `jobbot jobs discover` | Discovers via a public API: `--source workday` or `--source un-careers`. `--dry-run` writes nothing. |
| `jobbot jobs queries` | Prints web-search queries for ATS hosts. It does not search. |
| `jobbot jobs show Jxxxx` | Shows a stored posting, including its close date when the posting publishes one. |
| <span id="cmd-match" class="jb-in-story"><code>jobbot jobs match Jxxxx</code> <a class="jb-in-story__tag" href="#story-match" aria-controls="story-match" aria-label="Step 2, apply, match">apply</a></span> | Scores it against the profile. It helps you decide; it does not decide. |
| <span id="cmd-conditions" class="jb-in-story"><code>jobbot jobs conditions Jxxxx</code> <a class="jb-in-story__tag" href="#story-conditions" aria-controls="story-conditions" aria-label="Step 4, apply, conditions">apply</a></span> | Posting conditions: met, a question, or a blocker. Offline. |
| `jobbot jobs check-open` | Checks again whether a stored posting is still open. Read-only. |
| `jobbot jobs shortlist` | Sorts by score and marks expired or closing-soon rows. |
| `jobbot jobs backfill-dates` | Dates already stored postings from the URL id. Offline. |
| `jobbot jobs note Jxxxx TEXT` | Attaches a free-text note. |
| `jobbot jobs audit --source indeed` | Lists Indeed decoys and duplicates. `--apply` marks them; it does not delete submitted applications. |

### Applications {#cmd-applications}

| Command | What it does |
|---------|----------------|
| `jobbot application prepare Jxxxx` | Builds the package. It does not invent answers. |
| `jobbot application show Jxxxx` | Path and status of the package. |
| `jobbot application open Jxxxx` | Opens the posting or ATS URL. It does not apply. |
| <span id="cmd-apply" class="jb-in-story"><code>jobbot application apply Jxxxx</code> <a class="jb-in-story__tag" href="#story-apply" aria-controls="story-apply" aria-label="Step 5, apply, apply">apply</a></span> | Prefill plan. `--apply` opens the form; you submit. `--all` walks the queue, pausing between jobs. |
| `jobbot application check-answer Jxxxx` | Checks a free-text answer against the profile and the posting. Motivation stays yours. |
| `jobbot applications list` | Lists recorded applications. Alias: `applications status`. |

### Standing portals {#cmd-portals}

| Command | What it does |
|---------|----------------|
| `jobbot indeed login` | Opens Indeed so you can sign in. Also `status`, `inspect`, `prepare`, `pull`, `diff`, `sync`. Sync writes only with `--apply`. |
| `jobbot linkedin login` | The same for LinkedIn: `status`, `inspect`, `pull`, `diff`, `sync`. |
| `jobbot linkedin sync --section publications` | Writes Publications. With `--apply`, each item waits for you. |
| `jobbot linkedin sweep [QUERY]` | Reads recruiter posts and stores vacancies. With no query it uses the profile's searches. |
| `jobbot getonboard prepare` | Refines the permanent-profile draft from your facts. |
| `jobbot getonboard show-profile` | Shows the local draft. |
| `jobbot getonboard open-profile` | Opens the editor in the browser. It does not save on its own. |
| `jobbot getonboard open-cvs` | Opens the CV page. |
| `jobbot getonboard upload-cv` | Validates the PDF. `--apply` uploads it; you confirm. |
| `jobbot getonboard sync` | Propagates the profile. Dry-run unless `--apply`. |
| `jobbot getonboard search [QUERY]` | Searches the board. With no query it uses the profile's searches. |
| `jobbot torre search [QUERY]` | Public Torre search. The full posting is opened separately. |
| `jobbot empleospublicos search [QUERY]` | Open Chilean civil-service contests from open data. `--dry-run` writes nothing. |

### Browser {#cmd-browser}

| Command | What it does |
|---------|----------------|
| `jobbot browser chrome-debug` | Opens Chrome with debugging so you can solve CAPTCHA or 2FA. It does not solve them. |
| `jobbot browser sessions` | Reports session state from evidence. It never attaches on its own. |
| `jobbot browser login` | Lists portals with no proven session. `--apply` opens the next one; you sign in. |

### Companies, forms, and hiring practice {#cmd-companies}

| Command | What it does |
|---------|----------------|
| `jobbot portals list` | Lists known portals. |
| `jobbot portals detect URL` | Detects the ATS kind. |
| `jobbot portals add` | Adds or updates a portal. |
| `jobbot portals form-learn URL` | Reads what a form asks. It does not store what you type and it does not submit. |
| `jobbot portals profile status` | Coverage of tracked portals. It opens nothing. |
| `jobbot portals profile sheet PORTAL` | Fill sheet from the profile. It does not open a browser. |
| `jobbot portals profile mark-updated` | Records local evidence that a section was updated. |
| `jobbot portals profile import` | Seeds state from a CSV. Without `--apply` it writes nothing. |
| `jobbot portals profile seed` | Registers known career portals that are missing. Dry-run unless `--apply`. |
| `jobbot portals profile push PORTAL` | Refuses to type into the portal. The fill is the sheet. |
| `jobbot companies detect URL` | Classifies a URL. It writes nothing. |
| `jobbot companies learn URL` | Records a company and portal as a candidate. |
| `jobbot companies list` | Lists companies and their career sites. |
| `jobbot companies show NAME` | One company, its portals, and contradictions. |
| `jobbot companies recon NAME` | Learns ATS and questions from HTML. `--apply` stores the observation. |
| `jobbot companies signup NAME` | Opens signup and lists what the profile already answers. `--apply` fills known fields; creating the account is yours. |
| `jobbot companies promote NAME` | Promotes a candidate to active. That is the only way it becomes truth. |
| `jobbot companies reject NAME` | Marks a discovered portal as wrong. |
| `jobbot companies discover SEEDS` | One-shot: candidates under `output/`. It does not touch the registry. |
| `jobbot companies import FILE` | Merges those candidates. They stay candidates. |
| `jobbot companies export` | Shareable snapshot: active rows only, no PII. |
| `jobbot companies sites` | Portals the vacancy discovery can reuse. |
| `jobbot recruiters discover URL` | Stores public hiring practice, not people. |
| `jobbot recruiters list` | Lists practices. Also `show`, `promote`, `reject`, `export`. |

### Operations and secrets {#cmd-ops}

| Command | What it does |
|---------|----------------|
| `jobbot ops failures` | Lists local failures, grouped. |
| `jobbot ops failure show Fxxxx` | Shows one failure. `triage` changes its status. |
| `jobbot ops failure issue Fxxxx` | Opens a GitHub issue if you confirm. It does not open one on crash. |
| `jobbot ops failure work Fxxxx` | Prints the issue, branch, and PR lane. `--apply` opens the issue and the branch; it does not commit or push. |
| `jobbot ops symptom note` | Records a local symptom, redacted on write. Also `list`, `show`, `plan`, `triage`, `issue`. |
| `jobbot ops loop` | Repeats a maintenance step. On failure it stores `Fxxxx` and continues. |
| `jobbot ops capabilities` | Index of what the code already does. `--write` regenerates the doc. |
| `jobbot secrets init` | Creates an empty local vault, mode 0600. It invents no entries. |
| `jobbot secrets list` | Lists sites. It never prints the value. |
| `jobbot secrets set SITE` | Asks for the password without putting it on the command line. |
| `jobbot secrets delete SITE` | Deletes that entry. |
| `jobbot secrets allow-fill` | Consent for a future fill. CAPTCHA, 2FA, and submit stay yours. |
| `jobbot secrets deny-fill` | Turns that consent off. |

</section>

<section class="jb-section" markdown="1">

## What Jobbot will not do

Product rules, not slogans.

<ul class="jb-principles">
  <li><strong>Never submits for you</strong> Human-in-the-loop: it prepares the package and opens the form. Sending is yours.</li>
  <li><strong>Never invents facts about you</strong> <code>data/profile.yaml</code> is the only source of truth. Advise, tune, and sync reorder or ask — they do not fabricate experience.</li>
  <li><strong>Never syncs portals silently</strong> <code>cv sync --apply</code> confirms destination by destination. Without local evidence, <code>status</code> does not invent that you are “up to date”.</li>
  <li><strong>Never leaves your disk</strong> Profile, SQLite, browser sessions and <code>output/</code> are gitignored.</li>
  <li><strong>No CAPTCHA bypass</strong> When a portal challenges you, it hands you the keyboard.</li>
</ul>

</section>

<section class="jb-section jb-section--measure" markdown="1">

## Measured, not guessed

Which job sites answer from a datacenter IP, and which do not.

[Read the measurement](../blog/posts/2026-09-24-datacenter-ip-blocking.md){ .jb-btn .jb-btn--primary }
[Sitio en español](../index.md){ .jb-btn .jb-btn--ghost }

</section>

<section class="jb-section jb-section--close" markdown="1">

## Get started

Curl or Docker, a `~/postulaciones` folder, then `jobbot init`. Details in the guide.

```bash
curl -fsSL https://raw.githubusercontent.com/ljofreflor/jobbot/main/scripts/install.sh | bash
mkdir -p ~/postulaciones && cd ~/postulaciones && jobbot init
jobbot profile import-pdf ~/Downloads/CV.pdf --promote   # or edit .local/profile.yaml
# later: jobbot update
#
# Docker: docker pull ghcr.io/ljofreflor/jobbot:latest
#         docker compose run --rm -v "$HOME/postulaciones:/work" -w /work jobbot init
```

[Install](../instalacion.md){ .jb-btn .jb-btn--primary }
[Prior art](../prior-art.md){ .jb-btn .jb-btn--ghost }

</section>
