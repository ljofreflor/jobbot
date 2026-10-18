---
date: 2026-10-22
slug: tutoriales-04-lenguaje-natural-en-chat
categories:
  - Tutoriales
title: "Tutorial 4 — Lenguaje natural en cualquier chat"
description: >-
  Prompts para Cursor, Claude, ChatGPT, Codex, Gemini, Copilot… mapeados a
  uv run jobbot — HITL, --apply, data/profile.yaml como SoT, sin CAPTCHA/2FA.
---

# Tutorial 4 — Lenguaje natural en cualquier chat

JobBot no vive en el chat: vive en **tu terminal**. El chat (Cursor Agent, Claude, ChatGPT,
Codex, Gemini, Copilot Chat, VS Code Copilot, etc.) sirve para **decidir** y **orquestar**;
la salida auditable es la del CLI.

Dos modos habituales:

1. **Copiar y pegar** — el chat te devuelve comandos; vos los corrés en una terminal local.
2. **Agente con shell** — el producto ejecuta `uv run jobbot …` en tu máquina cuando tiene
   acceso al repo o a `~/postulaciones` (Cursor Agent, Codex CLI, algunos flujos de Claude Code).

En ambos casos valen las mismas reglas de producto.

<!-- more -->

## Contrato (pegalo al inicio del hilo)

```text
JobBot es CLI local. Fuente de verdad: data/profile.yaml o .local/profile.yaml.
- No inventar experiencia para encajar un JD.
- Dry-run por defecto; --apply solo con mi confirmación explícita.
- No auto-submit, no bypass CAPTCHA/2FA, no stealth.
- En clon del repo: uv run jobbot … ; en ~/postulaciones: jobbot …
- No pegues contraseñas ni PII en el chat; leé AGENTS.md si tenés el repo.
```

## Ejemplos de prompt → comando real

(Mismo espíritu que [manifiesto §6](../../manifesto.md).)

“Validá mi perfil local”  
→ `uv run jobbot profile validate`

“Armame búsquedas desde mi experiencia y mostrame las queries”  
→ `uv run jobbot profile queries`

“Buscá en Indeed data scientist en Santiago y guardá en la base”  
→ `uv run jobbot jobs search "data scientist" --location Santiago`

“Hacé sweep en LinkedIn por machine learning, Chile, posts de los últimos 30 días”  
→ `uv run jobbot linkedin sweep "machine learning" --country CL --max-age-days 30`

“Guardá este link para procesarlo en el desktop” (desde el celular, sin fetch)  
→ `uv run jobbot capture 'https://…'`

“Ingerí esta URL de Get on Board / Indeed”  
→ `uv run jobbot get 'https://…'`

“¿Qué tan bien encajo con J0003?”  
→ `uv run jobbot jobs match J0003`

“Mostrame el shortlist”  
→ `uv run jobbot jobs shortlist`

“Generá el CV para J0003”  
→ `uv run jobbot cv build --job J0003`

“Prepará el paquete de postulación para J0003”  
→ `uv run jobbot application prepare J0003`

“Abrí el ATS y prellená lo que el perfil ya responde; yo envío”  
→ `uv run jobbot application apply J0003 --apply`  
(opcional: `--cdp http://127.0.0.1:9222` si ya hay Chrome debug)

“¿Qué portales tengo evidenciados?”  
→ `uv run jobbot status`

“Plan de sync a permanentes sin escribir todavía”  
→ `uv run jobbot cv sync`

“Sincronizá permanentes con confirmación”  
→ `uv run jobbot cv sync --apply`

“Sugerencias de mercado desde los JD guardados; no toques profile hasta que confirme”  
→ `uv run jobbot profile suggest-from-market`  
(promover hechos: `--promote` con confirmación)

“Revisá sesiones de navegador antes de Indeed”  
→ `uv run jobbot browser sessions`

“Cola de postulaciones elegibles, solo dry-run”  
→ `uv run jobbot application apply --all`

## Chat con herramientas vs chat sin terminal

| Situación | Qué pedir |
| --- | --- |
| ChatGPT / Claude web **sin** acceso a tu disco | “Dame los comandos exactos; yo los ejecuto y te pego la salida.” |
| Cursor / Codex / agente IDE **con** shell | “Ejecutá `uv run jobbot …` y mostrá stdout completo; no resumas el match.” |
| Copilot en VS Code | Terminal integrada: corrés vos, o `@workspace` + pedido de script que invoque jobbot |

Si el modelo **no** puede ejecutar nada, igual sirve: que traduzca tu intención a **una**
secuencia de comandos verificables, no a un CV en prosa.

## Prompts que no deberías usar

| Pedido | Por qué |
| --- | --- |
| “Inventá bullets para pasar el ATS de J0005” | Viola `profile.yaml`; usá `cv advise` y gaps confirmados |
| “Postulá solo a los cinco mejores sin preguntarme” | No hay auto-submit; `application apply --all --apply` + HITL |
| “Resolvé el CAPTCHA de Indeed” | Prohibido; parar y pasarte el teclado |
| “Logueate con mi password …” | No contraseñas en el chat; `browser login --apply` y entrás vos |
| “Actualizá profile.yaml con todo lo que pide el JD” | Solo con `suggest-from-market --promote` y confirmación |

## Secuencia bien pedida (copiable)

```text
Contexto: ~/postulaciones, jobbot init hecho. Sin --apply todavía.
1) linkedin sweep "backend python" --country CL --max-age-days 14
2) jobs shortlist — listá ids y títulos
3) Esperá mi elección de id antes de cv build --job
No modifiques profile.yaml ni inventes skills.
Pegá la salida del terminal, no un resumen.
```

## Cursor como un ejemplo entre varios

En **Cursor Agent**, el mismo bloque anterior funciona: el agente suele tener shell en el
workspace. También podés anclar política con `@AGENTS.md` en el clon. No es requisito: en
**Claude** o **ChatGPT** copiás el contrato + la secuencia y corrés vos en iTerm, Warp o la
terminal de VS Code.

**Anterior:** [Parte 3 — Presencia](2026-10-21-tutoriales-03-presencia-sync.md) ·
**Siguiente:** [Parte 5 — Terminal y ejecución](2026-10-23-tutoriales-05-terminal-shell-y-chat.md)
