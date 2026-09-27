---
template: home.html
title: JobBot — tu búsqueda de trabajo, en tu máquina
description: >-
  CLI local para buscar trabajo con un CV estructurado como fuente de verdad.
  Corre entero en tu máquina, nunca postula por ti y nunca inventa datos sobre ti.
hide:
  - navigation
  - toc
---

<section class="jb-section" markdown="1">

## El ciclo, en comandos que existen

Descubrir, puntuar, armar el CV y preparar la postulación. El envío lo haces tú.

```bash
uv run jobbot getonboard search "data scientist" --limit 20
uv run jobbot jobs match J0001
uv run jobbot cv build --job J0001
uv run jobbot application apply J0001        # plan; tú envías
```

[Instalación y quickstart](instalacion.md) · [Referencia de comandos](comandos.md)

</section>

<section class="jb-section" markdown="1">

## Lo que JobBot no hace

Reglas del producto, no del marketing.

<ul class="jb-principles">
  <li><strong>No postula por ti</strong> Human-in-the-loop: prepara el paquete y abre el formulario. Enviar es tuyo.</li>
  <li><strong>No inventa datos sobre ti</strong> <code>data/profile.yaml</code> es la única fuente de verdad. El CV adaptado reordena; no fabrica experiencia.</li>
  <li><strong>No sale de tu disco</strong> Perfil, SQLite, sesiones de navegador y <code>output/</code> están gitignoreados, con un hook que bloquea commitearlos.</li>
  <li><strong>No evade CAPTCHAs</strong> Cuando un portal pide un desafío, te pasa el teclado.</li>
</ul>

</section>

<section class="jb-section jb-section--measure" markdown="1">

## Medido, no opinado

Antes de scrapear a ciegas: qué sitios de empleo responden desde una IP de datacenter y cuáles no.

[Leer la medición](blog/posts/2026-09-24-bloqueos-ip-datacenter.md){ .jb-btn .jb-btn--primary }
[English](blog/posts/2026-09-24-datacenter-ip-blocking.md){ .jb-btn .jb-btn--ghost }

</section>

<section class="jb-section jb-section--close" markdown="1">

## Empezar

Clona, sincroniza, copia el perfil de ejemplo. El resto está en la guía.

```bash
git clone https://github.com/ljofreflor/jobbot.git && cd jobbot
uv sync --group dev
cp data/profile.example.yaml data/profile.yaml
```

[Instalar](instalacion.md){ .jb-btn .jb-btn--primary }
[Prior art](prior-art.md){ .jb-btn .jb-btn--ghost }

</section>
