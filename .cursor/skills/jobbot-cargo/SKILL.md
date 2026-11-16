---
name: jobbot-cargo
description: >-
  Runs JobBot's cargo loop (discover → match → shortlist → CV → prepare → apply).
  Use when the user wants to search jobs, ingest a hard link, match/shortlist,
  build a CV for a job, or apply with HITL.
---

# JobBot cargo loop

Source of truth: `data/profile.yaml`. Full policy: repo root `AGENTS.md`.

## Loop

```bash
uv run jobbot jobs search "…" --location …
# or: uv run jobbot linkedin sweep [QUERY]
# or: uv run jobbot get 'https://…'          # hard link
# or: uv run jobbot capture 'https://…'    # phone inbox; drain later with get --parked
uv run jobbot jobs match Jxxxx
uv run jobbot jobs shortlist
uv run jobbot cv build --job Jxxxx
uv run jobbot application prepare Jxxxx
uv run jobbot application apply Jxxxx              # dry-run
uv run jobbot application apply Jxxxx --apply      # open/prefill; human submits
```

## Rules

- Never invent experience to match a posting.
- Validate posting URLs before handing them out (AGENTS.md Job URLs).
- Prefer fixtures over live portals in tests; CAPTCHA/2FA stay human.
- Derived artifacts under `output/jobs/Jxxxx/` — do not commit `output/` or PII.
