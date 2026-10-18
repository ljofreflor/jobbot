---
date: 2026-10-19
slug: tutoriales-01-primeros-pasos
categories:
  - Tutoriales
title: "Tutorial 1 — Primeros pasos: install, perfil y CLI"
description: >-
  Instalar JobBot, crear ~/postulaciones, importar o validar profile.yaml y
  conocer jobbot --help sin tocar portales todavía.
---

# Tutorial 1 — Primeros pasos: install, perfil y CLI

Antes del loop de cargo: tener el binario, una carpeta de trabajo y un perfil que JobBot pueda
validar. Todo local; nada de “subí tu CV a nuestra nube”.

<!-- more -->

## Instalación rápida (sin clonar)

```bash
curl -fsSL https://raw.githubusercontent.com/ljofreflor/jobbot/main/scripts/install.sh | bash
mkdir -p ~/postulaciones && cd ~/postulaciones
jobbot init
jobbot version
```

`jobbot init` crea `.jobbot.toml` y `.local/` (perfil, SQLite, `output/`, plantillas). Podés
sincronizar `~/postulaciones` con Drive o Syncthing; `browser-data/` puede ser pesado y atado
a una máquina.

Detalle de Docker, `jobbot update` y requisitos: [instalación](../../instalacion.md).

## Contribuir o usar un chat con acceso al repo

```bash
git clone https://github.com/ljofreflor/jobbot.git && cd jobbot
uv sync --group dev
cp data/profile.example.yaml data/profile.yaml
make hooks   # PII guard + tests antes de cada commit
uv run jobbot --help
```

Chromium de Playwright solo hace falta cuando un comando abre portales:

```bash
uv run playwright install chromium
```

## Tu perfil (fuente de verdad)

Desde `~/postulaciones`:

```bash
jobbot profile import-pdf ~/Descargas/CV.pdf --promote
# o editá .local/profile.yaml a mano
jobbot profile validate
jobbot profile show
```

Desde el clon:

```bash
uv run jobbot profile validate
uv run jobbot profile import-latex /path/to/cv.tex   # → profile.generated.yaml
uv run jobbot profile promote-generated              # solo después de revisar
```

Los importadores **no** pisan `profile.yaml` sin que lo revises (`promote-generated` /
`--promote`). JobBot no inventa roles ni métricas que no estén en el material de entrada.

## Explorar sin escribir en portales

```bash
uv run jobbot jobs list          # vacío al principio; normal
uv run jobbot portals list
uv run jobbot browser sessions   # evidencia local; no auto-login
```

`browser sessions` informa si hay pestaña firmada; JobBot **no** adjunta solo a Chrome ni
resuelve CAPTCHA por vos.

## Workspaces (varios CV de prueba)

Si tenés más de un candidato en el mismo checkout:

```bash
uv run jobbot workspace new demo-cv
uv run jobbot --workspace demo-cv profile validate
```

Sin `--workspace`, el directorio actual es la raíz del workspace (comportamiento habitual en
`~/postulaciones`).

## Checklist de esta parte

- [ ] `jobbot version` o `uv run jobbot version` responde
- [ ] `profile validate` pasa
- [ ] Entendés dónde vive el perfil (`.local/` vs `data/` en clon)

**Anterior:** [Índice de la serie](2026-10-18-tutoriales-serie-indice.md) ·
**Siguiente:** [Parte 2 — Loop de cargo](2026-10-20-tutoriales-02-loop-cargo.md)
