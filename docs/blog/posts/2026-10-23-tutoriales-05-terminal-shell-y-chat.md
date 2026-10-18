---
date: 2026-10-23
slug: tutoriales-05-terminal-shell-y-chat
categories:
  - Tutoriales
title: "Tutorial 5 — Terminal local y chat con shell"
description: >-
  Dónde correr jobbot, uv run jobbot, agentes con acceso a shell vs copy-paste,
  browser sessions, workspaces y preview del sitio.
---

# Tutorial 5 — Terminal local y chat con shell

**Búsqueda mientras programás** implica un solo lugar donde manda el binario: una terminal en
**tu** máquina. El chat — Cursor, Claude, ChatGPT, Codex, Gemini, Copilot — es el copiloto;
JobBot es la herramienta de oficio.

<!-- more -->

## Dónde correr comandos

| Setup | Directorio | Invocación |
| --- | --- | --- |
| Usuario curl / `jobbot init` | `~/postulaciones` | `jobbot …` |
| Clon para dev o agente en el repo | `…/jobbot` | `uv run jobbot …` |
| Sandbox de prueba | `sandboxes/NAME/` vía flag | `uv run jobbot --workspace NAME …` |

Comprobación:

```bash
jobbot version
# o
cd /path/to/jobbot && uv run jobbot version
```

Terminales válidas: integrada del IDE (Cursor, VS Code), iTerm, Warp, tmux, SSH a tu laptop —
lo importante es que sea **local** y con acceso a tu perfil gitignored.

## Flujo A — Chat sin shell (copy-paste)

1. Describís el objetivo en lenguaje natural (ver [Parte 4](2026-10-22-tutoriales-04-lenguaje-natural-en-chat.md)).
2. El chat devuelve comandos `jobbot` / `uv run jobbot`.
3. Los ejecutás, copiás **stdout/stderr** de vuelta al hilo.
4. Repetís hasta `--apply`; ahí **vos** confirmás en el portal y resolvés CAPTCHA/2FA si aparece.

Útil en ChatGPT, Claude web, Gemini cuando no montan tu disco.

## Flujo B — Agente con acceso a shell

Productos que suelen encajar: **Cursor Agent**, **Claude Code**, **Codex** CLI, algunos
plugins de VS Code con permiso de terminal.

Pedido mínimo:

```text
En este repo, lee AGENTS.md. Ejecuta con uv run jobbot:
profile validate, luego jobs shortlist si hay jobs.
No uses --apply. Muestra la salida completa del CLI.
```

El agente no debe “inventar” resultados de match: la fuente es el exit code y el texto del
comando.

Para issues o PRs **sin** tu PII real, pedí fixtures y `--workspace` — no asumir `J0047` en tu
SQLite.

## Variables y rutas

| Variable / archivo | Rol |
| --- | --- |
| `JOBBOT_WORKSPACE` | Equivalente a `--workspace NAME` |
| `.local/profile.yaml` | Perfil en workspace `init` |
| `data/profile.yaml` | Perfil en clon (gitignored; SoT en dev) |
| `output/` | Jobs, CVs, logs (gitignored) |

## Navegador y CDP (siempre HITL)

```bash
uv run jobbot browser chrome-debug --site gmail --port 9223
uv run jobbot browser sessions
uv run jobbot application apply J0001 --apply --cdp http://127.0.0.1:9223
```

Pestañas en segundo plano por defecto (`JOBBOT_BROWSER_FOCUS=1` las trae al frente). Cuenta
equivocada → `wrong_account` y el CLI frena.

## Contribuir docs o código (clon)

```bash
uv sync --group dev
make hooks
uv run ruff check .
uv run pytest tests/unit/test_docs_links.py
make docs-build
make docs-serve    # preview blog + tutoriales
```

En GitHub Pages la base es `/jobbot/`; localmente MkDocs sirve desde raíz.

## Cierre de la serie

- [Índice](2026-10-18-tutoriales-serie-indice.md)
- [Instalación](../../instalacion.md) · [Comandos](../../comandos.md) · [Manifiesto](../../manifesto.md)

El chat coordina; **`profile.yaml`** manda; el envío al ATS lo hacés vos.

**Anterior:** [Parte 4 — Lenguaje natural](2026-10-22-tutoriales-04-lenguaje-natural-en-chat.md)
