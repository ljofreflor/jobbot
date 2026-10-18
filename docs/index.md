---
template: home.html
title: Jobbot — búsqueda mientras programas
description: >-
  CLI local para buscar trabajo sin salir del editor: encuentra dónde publican,
  prepara sin inventar, postula con vos al mando. Humano + bot, en tu máquina.
hide:
  - navigation
  - toc
---

<section class="jb-section" markdown="1">

## Personas · oportunidades · tecnología

Herramienta de oficio: **búsqueda mientras programas**. Sin inventar un producto
que no existe. [Manifiesto completo](manifesto.md).

<ul class="jb-benefits">
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    </div>
    <strong>Encuentra donde publican</strong>
    <span>ATS, boards y sweeps — vacantes que encajan con tu perfil real, no con un CV inventado.</span>
  </li>
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M7 3h10v18H7z"/><path d="M10 8h4M10 12h4M10 16h2"/><path d="M9 21l1.5-1.5L13 21"/></svg>
    </div>
    <strong>Prepara sin inventar</strong>
    <span>Arma el paquete desde hechos que ya existen; el envío queda en tus manos.</span>
  </li>
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M4 19V9M10 19V5M16 19v-7M20 19H3"/></svg>
    </div>
    <strong>Postula con vos al mando</strong>
    <span>Matching, shortlist y evidencia — HITL, sin telemetría ni cuenta.</span>
  </li>
</ul>

<p class="jb-pillars">Más oportunidades. Un mejor mañana. Sin salir de la terminal.</p>

</section>

<section class="jb-section" markdown="1">

## El ciclo, en tu agente

En Cursor, VS Code, Claude Code u otro agente: pegas un link o describes lo que
buscas. Jobbot — CLI local — lee, hace match, arma el CV y deja el formulario
listo. El envío lo haces tú.

```bash
# mismos pasos vía CLI — lo que el agente ejecuta en tu máquina
jobbot linkedin sweep "machine learning"
jobbot jobs match J0002
jobbot cv build --job J0002
jobbot application apply J0002        # plan; tú envías
```

[Instalación y quickstart](instalacion.md) · [Referencia de comandos](comandos.md)

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Privacidad en tu máquina

Tu perfil, sesiones y salidas se quedan en el disco. No hay cuenta Jobbot ni
telemetría: las fallas se guardan en tu SQLite local.

<ul class="jb-evidence">
  <li><code>data/profile.yaml</code>, SQLite, <code>browser-data/</code> y <code>output/</code> están gitignoreados</li>
  <li>Hook pre-commit (<code>make hooks</code>) bloquea PII aunque uses <code>git add -f</code></li>
  <li>Human-in-the-loop: prepara el paquete; <strong>tú envías</strong></li>
  <li>Sin bypass de CAPTCHA ni 2FA — si el portal desafía, te pasa el teclado</li>
</ul>

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Buscar cargos recientes

Indeed, Get on Board y posts de reclutadores en LinkedIn. Filtros de frescura,
país por rol y posts con varias vacantes en uno.

```bash
jobbot jobs search "Senior Data Scientist" --location Santiago
jobbot getonboard search "data scientist"
jobbot linkedin sweep "machine learning" --country CL --max-age-days 30
```

Un post con cinco roles SoftServe → cinco vacantes independientes, cada una con
su país y su URL de ATS. Match y postulación por rol, no por post.

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Una sola fuente de verdad

<code>data/profile.yaml</code> es el SoT profesional. LaTeX, PDF, Indeed y LinkedIn
son vistas o adapters. El CV adaptado reordena evidencia; no inventa experiencia.

```bash
jobbot profile validate
jobbot cv build --job J0002          # derivado del perfil + JD
jobbot profile suggest-from-market   # sugerencias; confirmas gaps
```

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Sincronizar a los portales

Adapters de Indeed, LinkedIn y Get on Board: login, inspect, pull, diff y sync
(dry-run por defecto). Un comando propaga el CV base a los perfiles permanentes.

```bash
jobbot indeed sync --section headline   # plan; --apply escribe
jobbot linkedin sync --section publications --apply
jobbot cv propagate                     # plan HITL; --apply confirma
```

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Open source, en tu máquina

CLI local. Sin backend SaaS de Jobbot. El canal es Cursor, VS Code, Claude Code
u otro agente — no un chat propietario. Corres el binario; decides qué sale
de tu disco.

```bash
curl -fsSL https://raw.githubusercontent.com/ljofreflor/jobbot/main/scripts/install.sh | bash
mkdir -p ~/postulaciones && cd ~/postulaciones && jobbot init
jobbot version
# más adelante: jobbot update
```

¿Contribuís al código? Ahí sí: `git clone` + `uv sync --group dev` (ver [instalación](instalacion.md)).

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Match, ATS y Latam

Scores contra tu perfil, detección de ATS (Greenhouse, Lever, Workday, Teamtailor
incluso en hosts propios, Get on Board…), registro de portales que aprende con
evidencia, y foco en Chile / Latam en búsquedas y roundups.

<ul class="jb-evidence">
  <li><code>jobs match</code> / <code>shortlist</code> — puntúa; no decide por ti</li>
  <li><code>portals detect</code> + <code>companies learn</code> — topología pública, sin PII</li>
  <li><code>application apply --apply</code> — abre el formulario; el envío es tuyo</li>
  <li>Roundups Latam: país por rol (<code>--country CL</code>), no por post entero</li>
</ul>

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

Curl o Docker, carpeta `~/postulaciones`, `jobbot init`. El resto está en la guía.

```bash
curl -fsSL https://raw.githubusercontent.com/ljofreflor/jobbot/main/scripts/install.sh | bash
mkdir -p ~/postulaciones && cd ~/postulaciones && jobbot init
jobbot profile import-pdf ~/Descargas/CV.pdf --promote   # o edita .local/profile.yaml
# más adelante: jobbot update
#
# Docker: docker pull ghcr.io/ljofreflor/jobbot:latest
#         docker compose run --rm -v "$HOME/postulaciones:/work" -w /work jobbot init
```

[Instalación](instalacion.md){ .jb-btn .jb-btn--primary }
[Prior art](prior-art.md){ .jb-btn .jb-btn--ghost }

</section>
