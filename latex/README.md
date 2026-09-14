# latex/ — private moderncv vs demo

| File | In git? | Why |
|------|---------|-----|
| `cv.tex.demo` | yes | Dummy moderncv (fake PII) for docs / drills |
| `cv.tex` | **no** | Your real (or local) CV — private |
| `*.pdf` / aux files | **no** | Build artefacts |

JobBot’s render template stays in `templates/cv.tex.j2` (Jinja → `output/`).
This folder is for the **legacy moderncv** used by `jobbot profile import-latex`.

```bash
# Demo import (safe):
uv run jobbot profile import-latex latex/cv.tex.demo

# Local private CV inside the clone (still gitignored):
cp latex/cv.tex.demo latex/cv.tex
# edit latex/cv.tex with your facts — never commit it
```

In `.jobbot.toml` (gitignored):

```toml
[paths]
# Prefer an absolute path outside the repo for the real vitae, e.g.:
# legacy_cv = "/Users/you/Documents/vitae/cv/main.tex"
# Or a local ignored copy:
legacy_cv = "latex/cv.tex"
```
