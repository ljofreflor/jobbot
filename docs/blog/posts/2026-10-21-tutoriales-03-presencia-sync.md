---
date: 2026-10-21
slug: tutoriales-03-presencia-sync
categories:
  - Tutoriales
title: "Tutorial 3 — Presencia: cv sync, portales y status"
description: >-
  Mantener perfiles permanentes y portales activos al día — cv sync, cv advise,
  indeed/linkedin sync con dry-run y jobbot status.
---

# Tutorial 3 — Presencia: cv sync, portales y status

Además del loop por aviso (`J0001`), JobBot cubre **presencia**: que tu CV y campos conocidos
estén al día en portales permanentes (Indeed, LinkedIn, Get on Board) y, en evolución, en el
mapa colaborativo empresa↔portal (`companies`).

<!-- more -->

## Ver evidencia local

```bash
uv run jobbot status
# alias histórico: uv run jobbot cv status
```

Muestra qué destinos permanentes y portales de empresa **activos** tienen evidencia de sync en
tu máquina — no promete que el remoto esté perfecto si no hay sesión.

## Plan de sync (sin escribir)

```bash
uv run jobbot cv sync
uv run jobbot cv propagate    # alias: solo destinos permanentes, sin filas companies
```

`cv sync` arma un plan: permanentes + empresas `active` en tu base local. Por defecto es
**dry-run**: ves qué haría cada adapter.

## Aplicar con HITL

```bash
uv run jobbot cv sync --apply
```

Confirma destino por destino. Indeed y LinkedIn **exigen** `--apply` para escribir; sin eso
solo `pull`/`diff`/plan.

Ejemplos por portal:

```bash
uv run jobbot indeed diff
uv run jobbot indeed sync --section headline        # plan
uv run jobbot indeed sync --section headline --apply

uv run jobbot linkedin pull
uv run jobbot linkedin sync --section publications --apply  # confirma cada ítem
```

Get on Board (perfil acumulativo):

```bash
uv run jobbot getonboard prepare
uv run jobbot getonboard upload-cv --apply --cdp http://127.0.0.1:9224
```

## Asesoría antes de propagar

```bash
uv run jobbot cv advise
uv run jobbot profile suggest-from-market          # sugerencias; --promote confirma gaps
```

`suggest-from-market --promote` puede proponer refrases o skills **confirmadas por vos**;
nunca borra hechos baseline ni inventa empleadores.

## Portales de empresa (mapa público)

Conocimiento **público** (sin PII en git):

```bash
uv run jobbot companies list
uv run jobbot companies signup NOMBRE              # hoja: qué pide vs perfil
uv run jobbot companies signup NOMBRE --apply        # rellena lo conocido; vos creás cuenta
```

`companies discover` es **oneshot** → candidatos en `output/discovery/`; solo `promote` activa.
JobBot no inventa contraseña ni acepta términos solo.

## Sesiones antes de sync con navegador

```bash
uv run jobbot browser sessions
uv run jobbot browser login                        # plan: gaps de login
uv run jobbot browser login --apply                # abre el siguiente portal; vos entrás
```

Si el perfil de Chrome está ocupado por otra instancia, verás `profile_busy` — no pisa sesiones
ajenas.

## Checklist

- [ ] `status` refleja lo que esperás en permanentes
- [ ] Corriste `cv sync` en dry-run antes de `--apply`
- [ ] CAPTCHA/2FA los resolviste vos si el portal los pidió

**Anterior:** [Parte 2 — Loop de cargo](2026-10-20-tutoriales-02-loop-cargo.md) ·
**Siguiente:** [Parte 4 — Lenguaje natural en chat](2026-10-22-tutoriales-04-lenguaje-natural-en-chat.md)
