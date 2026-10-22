---
name: jobbot-hitl-writes
description: >-
  Enforces JobBot HITL for portal and profile writes: dry-run default, --apply
  plus confirmation, no CAPTCHA/2FA bypass, no auto-submit. Use when syncing
  LinkedIn/Indeed, applying, promoting market suggestions, or any --apply flag.
---

# JobBot HITL writes

## Default

Every write path is **dry-run** until `--apply` **and** an explicit confirmation
(default N / per-item). A yes at a prompt is **not** a receipt without portal evidence.

## Command patterns

| Area | Dry-run | Write |
| --- | --- | --- |
| Application | `application apply Jxxxx` | `… --apply` (+ CDP if needed); human clicks Submit/Send |
| Indeed | `indeed sync --section …` | `… --apply` + confirm |
| LinkedIn publications | `linkedin sync --section publications` | `… --apply` (+ confirm unless `--yes`) |
| CV advise / tune | `cv advise` / `cv tune-for` | `… --apply` (one-by-one) |
| Market → profile | `profile suggest-from-market` | `… --promote` (confirm; never invent) |
| Companies knowledge | candidates in `output/` | only `companies promote` activates |
| Signup fill | sheet only | `companies signup NAME --apply` — no invented password, no solo terms/CAPTCHA/create |

## Forbidden

- CAPTCHA solving, 2FA bypass, stealth, proxies, telemetry
- Auto-attach browser sessions (suggest `--cdp`; respect `profile_busy`)
- Committing `data/profile.yaml`, portals/companies local YAML, `browser-data/`, `output/`
