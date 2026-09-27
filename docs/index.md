---
template: home.html
title: Jobbot — tu próximo paso, con inteligencia
description: >-
  CLI local para buscar trabajo: encuentra vacantes, prepara postulaciones y el
  envío lo haces tú. Humano + tecnología, en tu máquina.
hide:
  - navigation
  - toc
---

<section class="jb-section" markdown="1">

## Personas · oportunidades · tecnología

Tres cosas que Jobbot hace de verdad. Sin inventar un producto que no existe.

<ul class="jb-benefits">
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    </div>
    <strong>Encuentra oportunidades</strong>
    <span>Descubre vacantes que encajan con tu perfil real, no con un CV inventado.</span>
  </li>
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M7 3h10v18H7z"/><path d="M10 8h4M10 12h4M10 16h2"/><path d="M9 21l1.5-1.5L13 21"/></svg>
    </div>
    <strong>Postula más fácil</strong>
    <span>Arma el paquete, abre el formulario y deja el envío en tus manos.</span>
  </li>
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M4 19V9M10 19V5M16 19v-7M20 19H3"/></svg>
    </div>
    <strong>Avanza con confianza</strong>
    <span>Matching contra tu perfil, shortlist y evidencia — sin telemetría ni cuenta.</span>
  </li>
</ul>

<p class="jb-pillars">Más oportunidades. Un mejor mañana.</p>

</section>

<section class="jb-section" markdown="1">

## El ciclo, en tu agente

En Cursor, VS Code, Claude Code u otro agente: pegas un link o describes lo que
buscas. Jobbot — CLI local — lee, hace match, arma el CV y deja el formulario
listo. El envío lo haces tú.

```bash
# mismos pasos vía CLI — lo que el agente ejecuta en tu máquina
uv run jobbot linkedin sweep "machine learning"
uv run jobbot jobs match J0002
uv run jobbot cv build --job J0002
uv run jobbot application apply J0002        # plan; tú envías
```

[Instalación y quickstart](instalacion.md) · [Referencia de comandos](comandos.md)

</section>

<section class="jb-section" markdown="1">

## Lo que Jobbot no hace

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
