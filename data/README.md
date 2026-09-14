# data/ — local vs tracked

| File | In git? | Why |
|------|---------|-----|
| `profile.example.yaml` | yes | Fake PII template for demos/tests |
| `portals.example.yaml` | yes | Seed ATS domains (no personal accounts) |
| `profile.yaml` | **no** | Real candidate SoT (name, email, phone, CV facts) |
| `profile.generated.yaml` / `*.suggested.yaml` / `*.bak` | **no** | Derived / personal |
| `portals.yaml` | **no** | May contain real job URLs from sweeps |
| `*.sqlite` | **no** | Jobs, applications, ops failures |

## Private LaTeX CV

Tracked dummy: [`latex/cv.tex.demo`](../latex/cv.tex.demo). Real CV: outside the repo or
gitignored `latex/cv.tex`. See [`latex/README.md`](../latex/README.md).

```bash
cp data/profile.example.yaml data/profile.yaml
cp data/portals.example.yaml data/portals.yaml   # optional seed
# Demo import (safe):
#   uv run jobbot profile import-latex latex/cv.tex.demo
```
