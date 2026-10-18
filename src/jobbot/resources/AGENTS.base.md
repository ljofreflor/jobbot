# AGENTS.md — JobBot workspace

Instructions for **you** and for **AI assistants** operating this folder. This is a
**candidate workspace** (cold install via `jobbot init`), not the JobBot source repository.

**Human in the loop (HITL).** JobBot prepares; you submit. Dry-run is the default.

## What JobBot is for

Two loops, one source of truth:

1. **Standing presence** — keep your CV/profile registered and up to date on portals you care about.
2. **Apply to a vacancy** — discover a role, match, build a tailored package, prefill the ATS; **you** click send.

Collaboration is about **public** knowledge (which companies use which portals). Your profile,
sessions, passwords, and applications stay **on this machine**.

## Source of truth

```text
.local/profile.yaml   ← professional facts (this workspace layout)
  or data/profile.yaml   ← when working inside a git clone instead of init
```

- **Never invent experience** to match a job. Rephrase and presentation only when the profile already supports the fact.
- Derived job artifacts live under `.local/output/` (or `output/` in a clone).
- Market suggestions (`profile suggest-from-market --promote`) need your confirmation before writing the profile.

Edit the seed profile after init, or import your CV:

```bash
jobbot profile import-pdf /path/to/cv.pdf --promote   # review before --promote
jobbot profile validate
```

## Cargo loop (apply to one job)

```bash
jobbot jobs search "ROLE" --location CITY          # or linkedin sweep, getonboard search, torre search
jobbot get 'https://…'                             # hard link → stored job
jobbot jobs match J0001
jobbot jobs shortlist
jobbot cv build --job J0001
jobbot cv advise                                   # presentation tips; --apply confirms each
jobbot application prepare J0001
jobbot application apply J0001                     # dry-run prefill plan
jobbot application apply J0001 --apply             # open ATS + sheet; you submit
```

Use `jobbot browser sessions` before writes that need login; attach your Chrome with `--cdp` when suggested.

## Standing presence (optional)

```bash
jobbot cv sync              # plan: permanent portals + active companies
jobbot cv sync --apply      # HITL per destination
jobbot status               # evidence of what is up to date
```

## Safety (non-negotiable)

- **Own accounts only.** JobBot does not invent passwords, accept terms alone, solve CAPTCHA/2FA, or auto-submit applications.
- **Writes need `--apply` plus confirmation** (Indeed profile edits, LinkedIn publications sync, portal signup fill, etc.).
- A “yes” at a prompt is **not** proof the application was sent; without portal evidence, status stays prepared.
- **No stealth, proxies, or telemetry.** Sessions live under `.local/browser-data/` (gitignored).
- **PII stays local.** Do not commit `.local/`, real profile YAML, SQLite, `browser-data/`, or `output/` to public git.

This workspace’s `.gitignore` already ignores `.local/` and `tmp/`.

## What not to commit

| Keep private (local / sync folder) | Safe templates in the JobBot repo |
| --- | --- |
| `.local/profile.yaml`, portals, companies | `*.example.yaml` |
| `.local/jobbot.sqlite`, `browser-data/` | — |
| `.local/output/`, form answers you typed | — |

If you version-control this folder, commit only non-sensitive notes; keep state in `.local/` or use private sync (Drive, Syncthing, etc.).

## More documentation

- Command reference: [docs/comandos.md](https://github.com/ljofreflor/jobbot/blob/main/docs/comandos.md)
- Install and quickstart: [docs/instalacion.md](https://github.com/ljofreflor/jobbot/blob/main/docs/instalacion.md)
- Product site (when built): `make site` in a clone, or the published docs linked from the [README](https://github.com/ljofreflor/jobbot/blob/main/README.md)
- Maintainer/agent policy for **contributing to JobBot itself** lives in the upstream repo’s root `AGENTS.md`, not in this file.

## Working inside a git clone (developers)

If you cloned [github.com/ljofreflor/jobbot](https://github.com/ljofreflor/jobbot) for development, paths default to `data/` and `output/` instead of `.local/`. Use `uv run jobbot …` from the checkout. Test CVs: `jobbot workspace new NAME` and `jobbot --workspace NAME …` — sandboxes are separate from this cold-install layout.
