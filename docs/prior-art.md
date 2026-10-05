---
title: Prior art
description: Otros proyectos open source que resuelven partes del mismo problema.
---

# Prior art

JobBot no inventó nada de esto solo. Estos proyectos abiertos cubren partes del
mismo problema — scraping de vacantes, CV como datos, matching — y conviene
conocerlos antes de escribir código propio. Una línea neutral cada uno.

- **[JobFunnel](https://github.com/PaulMcInnis/JobFunnel)** (archivado) — scrapea
  varios sitios de empleo a una única planilla sin duplicados; el repositorio está
  archivado y ya no recibe cambios.

- **[JobSpy](https://github.com/speedyapply/JobSpy)** — librería de Python para
  extraer avisos de LinkedIn, Indeed, Glassdoor, Google y ZipRecruiter con una API
  común.

- **[Reactive-Resume](https://github.com/reactive-resume/reactive-resume)** —
  constructor de currículums con foco en privacidad, self-hosteable, con plantillas
  y exportación.

- **[RenderCV](https://github.com/rendercv/rendercv)** — genera un CV en PDF a
  partir de un archivo YAML versionable, orientado a perfiles académicos y de
  ingeniería.

- **[JSON Resume](https://jsonresume.org/)** — esquema abierto para describir un
  currículum como JSON, con un ecosistema de themes y exportadores.

- **[Resume-Matcher](https://github.com/srbhr/Resume-Matcher)** — compara un CV
  contra una descripción de cargo y sugiere ajustes, con soporte para modelos
  locales.

## Homónimos JobBot

Varios productos y repos se llaman igual. No competimos la marca: se les roban
**casos de uso** (CV por aviso sin inventar, gaps honestos, digest de la cola HITL)
y se rechaza el medio (auto-submit, CV en la nube, cron desde datacenter). Mapa en
[#164](https://github.com/ljofreflor/jobbot/issues/164).

- **[jobbot.io](https://jobbot.io/en)** — un aviso → un CV y una carta; afirma no
  inventar; import desde PDF de LinkedIn. El ciclo «pegar el JD» ya es `get` /
  `jobs add`; la carta y el idioma del aviso son #33 / #34.
- **[shruthi-hariprasad/jobbot](https://github.com/shruthi-hariprasad/jobbot)** —
  skills del aviso vs CV, gap crítico/menor, bullets con cita. Taxonomía ESCO no
  es un gate nuestro; sí la distinción *hay evidencia* / *hay que preguntar*.
- **[Devpost JobBot](https://devpost.com/software/jobbot-jg2l9h)** (hackathon) —
  extensión + visión que envía Easy Apply. El wait-for-login es #56; el submit
  automático no.
- **[kottanaindrakiran/-jobbot](https://github.com/kottanaindrakiran/-jobbot)** —
  pipeline nocturno (scrape, auto-apply, digest Gmail, Sheets). El digest de *la
  cola* es #154; el cron contra LinkedIn desde Actions no (IP de datacenter).
- **[techsin/JobBot](https://github.com/techsin/JobBot)** — easy-apply multi-board
  y alta en talent networks. Detectar ATS ya está; la presencia en esos portales
  es #150, no un bot de «sign up all».
- **[JobBotPro](https://jobbotpro.carrd.co/)** / **[jobbot.biz](https://jobbot.biz/)** —
  match y auto-apply hospedados. Throughput; ver anti-patrones abajo.

## Qué toma JobBot de acá

La idea de **el CV como datos estructurados y versionables** (JSON Resume, RenderCV)
y la de **puntuar un CV contra una descripción de cargo** (Resume-Matcher) no son
nuevas. Lo que JobBot agrega es el ciclo completo en un solo CLI local —
descubrimiento, matching, CV derivado y paquete de postulación — con la regla de
que nada se envía sin que una persona lo revise y que ningún dato tuyo sale de tu
máquina.

## Anti-patrones comerciales (no clonar)

Herramientas tipo **AI Apply / Resumly Autopilot / xApply** venden el contraste
*3 horas · 2 respuestas · 0 entrevistas* → *30 minutos · inbox lleno* vía
auto-submit y volumen. JobBot **roba el outcome medible** (tiempo de ciclo,
respuestas e entrevistas registradas) y **rechaza el medio** (autopilot, OAuth
de bandeja, spray del mismo CV). Ver [#105](https://github.com/ljofreflor/jobbot/issues/105)
y el mapa de casos en [#155](https://github.com/ljofreflor/jobbot/issues/155).

## Talleres de «IA que busca por ti»

Una clase en Luma ([Pon la IA a buscar trabajo por ti](https://luma.com/o156agl9),
Arcon Labs) vende el mismo ciclo como **tres miniagentes**: uno afina el CV, otro
rastrea vacantes que encajan, otro se ocupa de las postulaciones para que dejes
de copiar datos. Eso **ya es** JobBot (`cv advise` / match / `application apply`)
y el frente de tres comandos ([#108](https://github.com/ljofreflor/jobbot/issues/108)).
Se roba el *equipo de tres* y el CV frío de entrada; se rechaza el título «por ti»
y el envío automático. Mapa en [#168](https://github.com/ljofreflor/jobbot/issues/168).
