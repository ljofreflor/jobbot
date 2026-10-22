---
name: jobbot-profile-truth
description: >-
  Keeps data/profile.yaml as the only professional source of truth: never invent
  experience, never delete baseline facts silently. Use when importing CV/LaTeX/PDF,
  advising or tuning the CV, or promoting market suggestions.
---

# JobBot profile truth

## Invariants

1. `data/profile.yaml` is the only professional source of truth.
2. Never invent experience, employers, skills, or metrics to match a job.
3. Never delete existing baseline facts without explicit user confirmation.
4. Do not commit real PII — `data/profile.yaml` stays gitignored; use `*.example.yaml`.

## Safe commands

```bash
uv run jobbot profile validate
uv run jobbot profile import-latex|import-pdf …   # review generated YAML
uv run jobbot profile promote-generated           # after human review
uv run jobbot cv advise [--job Jxxxx]             # deterministic; --apply one-by-one
uv run jobbot cv tune-for Jxxxx|URL               # ~5% baseline from a posting; --apply HITL
uv run jobbot profile suggest-from-market         # no stdin; --ask for gaps
uv run jobbot profile suggest-from-market --promote   # confirm each
```

## Daily CV ritual (agents)

If local data exists and `output/cv/improvement_proposal.yaml` is missing or
`last_proposed` is before today: propose **one** improvement (advise or market),
update the marker, apply nothing without an explicit yes. See AGENTS.md
«Mejora diaria del CV».
