# JobBot Agent Skills

Procedural skills for Cursor (and compatible agents) that work **in this repo**.
Policy and product rules live in [`AGENTS.md`](../../AGENTS.md) — skills teach *when*
and *how* to run the loop; they do not replace that file.

| Skill | Use when |
| --- | --- |
| [`jobbot-cargo`](jobbot-cargo/SKILL.md) | Search → match → package → apply |
| [`jobbot-hitl-writes`](jobbot-hitl-writes/SKILL.md) | Any write to portals / profile with `--apply` |
| [`jobbot-presence`](jobbot-presence/SKILL.md) | Standing presence: sync, status, companies, signup |
| [`jobbot-ops-failures`](jobbot-ops-failures/SKILL.md) | Local ops failures → issue → branch → PR |
| [`jobbot-profile-truth`](jobbot-profile-truth/SKILL.md) | Import, market suggest, CV advise — never invent |

**Not here:** Cursor built-in skills (`~/.cursor/skills-cursor/`), personal skills,
or `.cursor/rules/` (rules stay local / gitignored).

Commands: prefer `uv run jobbot …` from the checkout (or `--workspace NAME`).
