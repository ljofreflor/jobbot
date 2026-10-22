---
name: jobbot-ops-failures
description: >-
  Triages JobBot ops failures (SQLite + output/ops) and the maintainer lane
  issue→branch→PR. Use when a portal fetch fails, ops failure work, or opening
  a GitHub issue from a local failure.
---

# JobBot ops failures

Failures stay **local** until HITL opens a GitHub issue. Never auto-open on crash.

```bash
uv run jobbot ops failures
uv run jobbot ops failure show Fxxxx
uv run jobbot ops failure triage Fxxxx --status fixed
uv run jobbot ops failure issue Fxxxx          # HITL → gh issue
uv run jobbot ops failure work Fxxxx           # print lane
uv run jobbot ops failure work Fxxxx --apply   # issue + fetch + branch (no auto-merge)
```

## When opening issues

- Assign `cursoragent` when possible; else label `cursor` (AGENTS.md Planning).
- Feature/fix PRs target **`develop`**, not `main`.
- Every bug fix needs a **fail-first** regression unit test (fixtures > live portals).
- Strip tracking from stored commands in failure records.

## CI red

Read logs → fix root cause → push on the same branch. Ask before merge to
develop/main, force-push, or anything touching PII / live portals.
