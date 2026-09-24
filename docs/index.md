---
title: JobBot — tu búsqueda de trabajo, en tu terminal
description: >-
  CLI local para buscar trabajo con un CV estructurado como fuente de verdad.
  Corre entero en tu máquina, nunca postula por ti y nunca inventa datos sobre ti.
---

# Tu búsqueda de trabajo, en tu terminal y en tu máquina

**JobBot es una herramienta de línea de comandos que mantiene tu CV como datos
estructurados, descubre vacantes, las puntúa contra tu perfil real y arma el paquete
de postulación.** Tú aprietas "enviar". Siempre.

No hay interfaz web, no hay servidor, no hay cuenta que crear. Es un binario de Python
que corre con `uv`, guarda todo en SQLite y archivos en tu disco, y no habla con
ningún backend nuestro porque no existe un backend nuestro.

## Instalar en tres comandos

```bash
git clone https://github.com/ljofreflor/jobbot.git && cd jobbot
uv sync --group dev
cp data/profile.example.yaml data/profile.yaml
```

Eso es todo lo mínimo. Edita `data/profile.yaml` con tus datos y valida:

```bash
uv run jobbot profile validate
uv run jobbot cv build
```

¿Detalles, requisitos y el resto del flujo? → [Instalación y quickstart](instalacion.md)

## Por qué es distinto

<div class="grid cards" markdown>

-   :material-laptop: __Corre entero en tu máquina__

    ---

    Python + SQLite + Playwright local. No hay servicio remoto, no hay telemetría,
    no hay cuenta. Si apagas el notebook, JobBot deja de existir.

-   :material-hand-back-right: __Nunca postula por ti__

    ---

    El flujo es *human-in-the-loop*: JobBot prepara el paquete, abre el formulario
    y planifica el prellenado. El envío lo haces tú, mirando lo que envías.

-   :material-shield-check: __Nunca inventa datos sobre ti__

    ---

    `data/profile.yaml` es la única fuente de verdad profesional. El CV adaptado a
    una vacante reordena y prioriza lo que ya existe; no fabrica experiencia,
    ni años, ni herramientas que no usaste.

-   :material-robot-off: __Sin bypass de CAPTCHA__

    ---

    Nada de resolver CAPTCHAs, saltarse 2FA ni evadir anti-bot. Cuando un portal
    pide un desafío, te pasa el teclado a ti.

-   :material-database-lock: __Tus datos no salen de tu disco__

    ---

    `data/profile.yaml`, `output/`, `browser-data/` y la base SQLite están en
    `.gitignore`, y un hook de pre-commit bloquea commitearlos por accidente.

-   :material-earth: __Pensado para el mercado chileno y LATAM__

    ---

    Get on Board, Indeed CL y LinkedIn, además de APIs públicas de ATS
    (Greenhouse, Lever, Ashby, SmartRecruiters, Workday…).

</div>

## El ciclo completo, en comandos que existen

```bash
uv run jobbot getonboard search "data scientist" --limit 20
uv run jobbot jobs shortlist
uv run jobbot jobs match J0001
uv run jobbot cv build --job J0001
uv run jobbot application prepare J0001
uv run jobbot application apply J0001        # plan; tú envías
```

Cada comando de esta página está en el CLI: mira la
[referencia de comandos](comandos.md), generada revisando `src/jobbot/cli.py`.

## Lo que JobBot no hace

- No envía tu CV a APIs de IA externas en el MVP.
- No resuelve CAPTCHAs ni evade detección de bots.
- No hace crawling masivo: el descubrimiento es secuencial, con pausas y volúmenes chicos.
- No guarda tus contraseñas: las sesiones de navegador viven en `browser-data/`, gitignoreado.

## Antes de escribir tu propio scraper, lee esto

Medimos, desde una IP de datacenter, qué sitios de empleo bloquean y cuáles no.
El resultado ordena dónde conviene poner cada parte del pipeline:

[Qué sitios de empleo te bloquean desde una IP de datacenter (medido)](blog/posts/2026-09-24-bloqueos-ip-datacenter.md){ .md-button .md-button--primary }
[English version](blog/posts/2026-09-24-datacenter-ip-blocking.md){ .md-button }

## Prior art

JobBot no nació en el vacío. Hay proyectos abiertos que resuelven partes de este
problema y vale la pena conocerlos antes de escribir código:
[Prior art](prior-art.md).
