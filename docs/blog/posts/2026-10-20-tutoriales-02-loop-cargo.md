---
date: 2026-10-20
slug: tutoriales-02-loop-cargo
categories:
  - Tutoriales
title: "Tutorial 2 — Loop de cargo: buscar, match, CV y apply HITL"
description: >-
  jobs search, linkedin sweep, get, match, shortlist, cv build --job y
  application apply — dry-run primero, --apply con vos al mando.
---

# Tutorial 2 — Loop de cargo: buscar, match, CV y apply HITL

El loop principal: traer avisos a tu SQLite local, puntuar contra **hechos** del perfil, armar
CV derivado y paquete de postulación, abrir el ATS — **vos enviás**.

<!-- more -->

## Entrada de avisos (tres caminos habituales)

**Indeed / búsqueda explícita:**

```bash
uv run jobbot jobs search "Senior Data Scientist" --location Santiago
```

**LinkedIn — posts de reclutadores (lectura; no publica por vos):**

```bash
uv run jobbot linkedin sweep "machine learning" --country CL --max-age-days 30
```

**URL que ya tenés (Get on Board, Indeed viewjob, etc.):**

```bash
uv run jobbot get 'https://www.getonboard.com/empleos/.../slug'
# Indeed u otras formas: fixture o CDP si la página pide login/CAPTCHA
uv run jobbot capture 'https://…'    # desde el celular: inbox local, drenar en desktop
```

Torre (API pública, sin navegador):

```bash
uv run jobbot torre search --remote
```

Cada aviso guardado recibe un id `J0001`, `J0002`, … Artefactos derivados van bajo
`output/jobs/Jxxxx/` (gitignored en un clon).

## Match y shortlist

```bash
uv run jobbot jobs match J0002
uv run jobbot jobs shortlist
```

El matcher **solo suma** evidencia desde el perfil hacia el JD; no inventa skills. Si todos
los scores son 0 %, el CLI avisa — no es una lista vacía silenciosa.

## CV y paquete para ese rol

```bash
uv run jobbot cv build --job J0002
uv run jobbot application prepare J0002
```

`cv build --job` reordena y destaca lo que el aviso ya puede respaldar con tu perfil; no
fabrica experiencia.

Mejora de presentación (opcional, determinista por defecto):

```bash
uv run jobbot cv advise --job J0002
uv run jobbot cv advise --apply   # confirma una por una → profile.yaml con backup
```

## Postular: plan vs ejecución

```bash
uv run jobbot application apply J0002           # dry-run: plan de prefill
uv run jobbot application open J0002            # abre URL; no auto-submit
uv run jobbot application apply J0002 --apply     # abre ATS + hoja; tú envías
```

Con Chrome de debug (sesión humana previa):

```bash
uv run jobbot browser chrome-debug --site indeed
uv run jobbot application apply J0002 --apply --cdp http://127.0.0.1:9222
```

**Email-only** (`mailto:`): `--apply` puede abrir Gmail compose y adjuntar el PDF adaptado;
JobBot **no** pulsa Enviar.

Cola de elegibles:

```bash
uv run jobbot application apply --all           # dry-run
uv run jobbot application apply --all --apply   # uno por uno; HITL entre jobs
```

!!! warning "Un sí en el prompt no es comprobante"

    Sin evidencia del portal, el estado puede quedar en `prepared`. El envío final y cualquier
    CAPTCHA/2FA son humanos.

## Flujo mínimo en una tabla

| Paso | Comando |
| --- | --- |
| Descubrir | `jobs search` / `linkedin sweep` / `get URL` |
| Priorizar | `jobs match` → `jobs shortlist` |
| Artefactos | `cv build --job` → `application prepare` |
| Postular | `application apply --apply` (vos confirmás y enviás) |

**Anterior:** [Parte 1](2026-10-19-tutoriales-01-primeros-pasos.md) ·
**Siguiente:** [Parte 3 — Presencia y sync](2026-10-21-tutoriales-03-presencia-sync.md)
