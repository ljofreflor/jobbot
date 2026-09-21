# Tutorial: the loop, the practices, the guarantees

JobBot is a local tool with one fact base and many views. Collaboration shares the **map**
(who hires where, what forms ask); each person's CV, sessions and accounts stay on their
machine. This walks the loop once for a **new candidate**, then states the practices that keep
it usable and the guarantees the code actually enforces. Where a guarantee is enforced by a
test, the test is named: those are the ones that will fail if the guarantee breaks.

## 0. Install and enable the guard

```bash
uv sync --group dev
uv run playwright install chromium   # only for portals that need a browser
make hooks                           # PII guard + unit suite before every commit
```

`make hooks` is not optional in practice. It points `core.hooksPath` at `.githooks`, where two
things run before a commit: `jobbot.ops.pii_guard` refuses to let real candidate data into git, and
`jobbot.ops.precommit` decides whether this commit can change behaviour and runs the suite if so.
Policy counts as behaviour: editing `AGENTS.md` runs the tests, because for an agent working from a
clone that file is the whole policy.

## 1. Your facts (often a private LaTeX CV)

```bash
uv run jobbot profile validate
uv run jobbot profile import-latex          # or import-pdf /path/to/cv.pdf
uv run jobbot profile promote-generated     # after you review the YAML
```

`data/profile.yaml` is the only source of professional truth. The real LaTeX may live outside
the repo (`paths.legacy_cv`); never commit real `latex/cv.tex`. Importers write
`data/profile.generated.yaml` and stop there; nothing becomes a fact until you promote it.

## 2. Improve presentation

```bash
uv run jobbot cv advise                     # few concrete suggestions; invents nothing
uv run jobbot cv advise --apply             # confirm one by one → profile.yaml (with backup)
```

## 3. Standing presence (`cv sync`)

Keep this candidate registered and up to date on permanent profiles, and see every *active*
company portal from the collaborative base in the plan
([#43](https://github.com/ljofreflor/jobbot/issues/43)):

```bash
uv run jobbot browser sessions              # who is signed in, and on which port
uv run jobbot cv sync                       # plan: permanentes + companies active
uv run jobbot cv sync --apply --cdp http://127.0.0.1:9224
uv run jobbot status                        # what is up (local evidence)
```

`--apply` today writes permanent destinations (local CV + Get on Board + Indeed + LinkedIn).
Active company rows are **plan-only** until the rest of #43 lands; for those use
`companies signup NOMBRE` (sheet + open; fill behind `--apply` is
[#44](https://github.com/ljofreflor/jobbot/issues/44)) and/or `application apply Jxxxx`.
`cv propagate` is the permanente-only subset of the same writers.

`companies discover` only finds candidate URLs — it does not register you or upload your CV.
Only `promote`d sites appear in the sync plan. When a promoted site still has `ats=unknown`,
**go inside** and learn components (issue
[#45](https://github.com/ljofreflor/jobbot/issues/45)):

```bash
uv run jobbot companies recon NOMBRE --cdp http://127.0.0.1:9224   # open, you enter
uv run jobbot companies recon NOMBRE --fixture page.html --apply   # store ATS + form questions
```

Oneshot looks from the outside; recon stores technical evidence from a page you already
reached. It does not create the account (that is `companies signup` / #44).

## 4. Find work

```bash
uv run jobbot jobs search "Senior Data Scientist" --location Santiago
uv run jobbot getonboard search
uv run jobbot torre search --remote
uv run jobbot linkedin sweep "enviar CV" --country CL
uv run jobbot get https://www.getonbrd.com/empleos/.../slug   # hard link when you have one
```

Every source stores postings locally and teaches the registries what it saw: the platform in
`data/portals.yaml`, and the company↔portal relation in `data/companies.yaml` when the posting
points at a real employer portal rather than a job board.

## 5. Decide, build, apply

```bash
uv run jobbot jobs match J0001
uv run jobbot jobs shortlist
uv run jobbot cv build --job J0001
uv run jobbot application prepare J0001
uv run jobbot application apply J0001            # dry-run: the prefill plan
uv run jobbot application apply J0001 --apply    # opens the ATS and prefills; you submit
```

## 6. Close the loop

What the search teaches you comes back as proposals, never as silent edits:

```bash
uv run jobbot companies discover data/companies-cl.example.yaml   # map portals (candidates)
uv run jobbot companies recon NOMBRE --fixture page.html --apply  # truth from inside (#45)
uv run jobbot portals form-learn URL --fetch     # what a form asks; it submits nothing
uv run jobbot companies signup NOMBRE            # sheet + open; you finish irreversible steps
uv run jobbot recruiters discover URL            # public hiring practice, then promote it
uv run jobbot profile suggest-from-market        # market wording and gap questions
```

`cv advise` is where those threads meet: the postings give it the market's wording, the forms give it
the questions employers actually ask, and the practices you promoted give it what hiring looks for.
It stays deterministic and free by default. If you want a model to reword a line, `--llm` sends that
one line with your contact data stripped, and `--llm --dry-run` prices the run before you pay for it.
Whatever the model answers is validated the same way a hand-written suggestion is, and discarded if
it invents or loses something.

## Best practices

**Read the dry-run before you pass `--apply`.** Every command that writes anywhere defaults to
planning. The plan is not a formality: it prints the operations, and for portals it prints what the
destination holds today versus what would replace it.

**Let the session preflight tell you the port.** `jobbot browser sessions` reports per-site state
from evidence, and prints the exact `--cdp` flag for each. Guessing a port wastes a run.

**Fix a bug by writing the failing test first.** This is the repo's hardest rule and the reason the
suite is worth trusting. A fix without a test that failed before it is not finished.

**Prefer a maintained library to a clever function.** Before hand-rolling HTML, URL, date or email
handling, read [library-audit.md](library-audit.md), which records what was replaced, what stayed
ours, and why.

**Keep the compute cheap.** The deterministic path is the default everywhere. An LLM is a fallback
for judgement about wording, not a way to compute things a rule can decide.

**Review before you promote.** Importers, market feedback, discovery and the CV advisor all write
to a staging file or an `output/` artefact. `promote` is the only verb that changes your facts or
activates knowledge, and it asks first.

**Plan against open issues.** Before inventing a feature in chat, run `gh issue list --state open`
— standing presence is [#43](https://github.com/ljofreflor/jobbot/issues/43) / [#44](https://github.com/ljofreflor/jobbot/issues/44).

## Guarantees

These are properties of the code, not intentions.

**Your facts are never invented and never silently deleted.** Adapters read from `Candidate`; they
do not write back to it. Market feedback and the CV advisor produce proposals that need your
confirmation, and a proposal that would drop a fact is rejected before you see it. When an LLM is
involved, its output is validated deterministically against your profile and discarded if it
asserts something unbacked or loses a fact.

**Your PII does not enter git.** `data/profile.yaml`, `data/portals.yaml`, `data/companies.yaml`,
`data/form_knowledge.yaml`, the SQLite database, `browser-data/`, `output/` and the real
`latex/cv.tex` are ignored and additionally blocked by the pre-commit guard, which also detects
real-looking emails, phones, RUTs and home paths. Only `*.example.yaml` and `latex/cv.tex.demo` are
tracked.

**Nothing irreversible is done alone.** JobBot opens forms and may fill fields the profile already
answers (and attach the built CV). It never invents a password, never accepts terms alone, never
solves CAPTCHA/2FA, and never clicks create/submit/Send without your confirmation.

**No platform defences are circumvented.** No CAPTCHA solving, no 2FA bypass, no stealth, no
proxies, no telemetry. Own accounts only. A site that refuses us is reported as refusing, not as
empty, so a block never becomes a false conclusion.

**A busy browser profile is refused up front.** If another Chrome holds the profile, the session is
reported as `profile_busy` and the destination is blocked before an adapter is built, instead of
crashing mid-write.

**Web exploration is polite and bounded.** The one-shot discovery obeys `robots.txt`, waits between
requests, is capped per company, and writes only to `output/`. It never touches the active
registry: `companies promote` does that, after you look.

**Third parties are not collected.** A recruiter's name in a LinkedIn post, the people listed
behind a Torre opportunity, the author of a forum thread: none of them reach local storage. What is
kept is the company, the portal and the practice.

**Behaviour is not field-specific.** No module gates on the vocabulary of one profession, and none
holds a real employer, city or person. A nurse, a journalist and an engineer get the same
treatment; `tests/unit/test_domain_agnostic.py` keeps one test per module honest about it.

## When something breaks

```bash
uv run jobbot ops failures
uv run jobbot ops failure show F0001
uv run jobbot ops failure issue F0001    # HITL: you read the text before it goes to GitHub
```

Failures are recorded locally first. Nothing is reported anywhere automatically.
