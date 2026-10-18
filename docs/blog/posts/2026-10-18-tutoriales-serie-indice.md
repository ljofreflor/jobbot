---
date: 2026-10-18
slug: tutoriales-serie-indice
categories:
  - Tutoriales
title: "Serie: JobBot en la terminal y desde cualquier chat"
description: >-
  Índice de tutoriales — búsqueda mientras programas: comandos reales, HITL,
  profile.yaml como SoT, sin inventar experiencia; chat agnóstico.
---

# Serie: JobBot en la terminal y desde cualquier chat

**Búsqueda mientras programas.** Esta serie no vende magia: enseña qué comandos existen,
cuándo correrlos en dry-run y cuándo hace falta `--apply` y tu confirmación.

JobBot es **CLI local**. Tu perfil, sesiones y postulaciones viven en tu disco; no hay cuenta
JobBot ni telemetría. Un chat (Cursor, Claude, ChatGPT, Codex, Gemini, Copilot…) puede
**sugerir o ejecutar** los mismos binarios que vos en una terminal local — pero **enviar** un
formulario, **aceptar** términos o **resolver** CAPTCHA/2FA siguen siendo tuyos.

<!-- more -->

## Qué vas a aprender

1. **[Primeros pasos](2026-10-19-tutoriales-01-primeros-pasos.md)** — instalación (curl o clon),
   carpeta `~/postulaciones`, `profile validate`, primeros comandos.
2. **[Loop de cargo](2026-10-20-tutoriales-02-loop-cargo.md)** — descubrir avisos, `jobs match`,
   `shortlist`, `cv build --job`, `application apply` (plan vs `--apply`).
3. **[Presencia y sync](2026-10-21-tutoriales-03-presencia-sync.md)** — perfiles permanentes,
   `cv sync`, `status`, Indeed/LinkedIn con dry-run por defecto.
4. **[Lenguaje natural en cualquier chat](2026-10-22-tutoriales-04-lenguaje-natural-en-chat.md)** —
   prompts → comandos; copy-paste o agente con shell; qué no pedir.
5. **[Terminal y ejecución](2026-10-23-tutoriales-05-terminal-shell-y-chat.md)** — `jobbot` vs
   `uv run jobbot`, flujos con/sin shell, workspaces, sesiones de navegador.

## Dos formas de invocar el CLI

| Contexto | Ejemplo |
| --- | --- |
| Instalación curl / carpeta `~/postulaciones` | `jobbot version` |
| Clon del repo (desarrollo o agente en el tree) | `uv run jobbot version` |

Los bloques de la serie usan `uv run jobbot …` cuando asumen el repo; en un workspace frío
reemplazá por `jobbot …` desde esa carpeta.

## Reglas que no cambian entre partes

- **`data/profile.yaml`** (o `.local/profile.yaml` en un workspace init) es la única fuente de
  verdad profesional. JobBot no rellena huecos con experiencia inventada.
- **Dry-run primero.** Escribir en Indeed/LinkedIn o “aplicar” requiere `--apply` y confirmación.
  Un “sí” en un prompt **no** prueba que el portal recibió la postulación.
- **Sin bypass** de CAPTCHA, 2FA, stealth ni auto-submit.

## Más referencia

- [Instalación y quickstart](../../instalacion.md)
- [Referencia de comandos](../../comandos.md)
- [Manifiesto](../../manifesto.md) — voz y principios
- [Tutorial largo (EN)](../../tutorial.md) — loop + garantías enlazadas a tests

**Siguiente:** [Parte 1 — Primeros pasos](2026-10-19-tutoriales-01-primeros-pasos.md)
