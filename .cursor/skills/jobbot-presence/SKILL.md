---
name: jobbot-presence
description: >-
  Standing presence against collaborative portals: cv sync/status, companies
  discover/promote/recon/signup, form-learn. Use when registering on career
  sites, checking what is up to date, or maintaining the company↔portal map.
---

# JobBot standing presence

Collaboration is the **map** (companies/portals/forms). The CV and sessions stay
on the machine. Policy: `AGENTS.md` (Product / endgame, Company career platforms).

## Presence commands

```bash
uv run jobbot cv sync              # plan: permanentes + companies active
uv run jobbot cv sync --apply      # HITL per destination
uv run jobbot status               # evidence of what is up
uv run jobbot browser login        # dry-run gaps; --apply opens next
uv run jobbot browser sessions     # ready | needs_login | unknown | profile_busy
```

## Company ↔ portal map

```bash
uv run jobbot companies discover …   # oneshot → output/discovery/ only
uv run jobbot companies import …
uv run jobbot companies promote …    # only promote makes knowledge active
uv run jobbot companies export       # share actives → companies.shared.yaml
uv run jobbot companies recon NAME --fixture PATH|--cdp URL [--apply]
uv run jobbot companies signup NAME --apply [--cdp URL]
uv run jobbot portals form-learn URL --fetch|--fixture PATH
```

## Rules

- ATS kind stays `unknown` without technical evidence.
- `discover` never creates accounts or uploads CVs.
- Signup: fill known profile fields only; human for password, terms, CAPTCHA, final create.
- `data/companies.yaml` is local (gitignored); share via `export` only.
