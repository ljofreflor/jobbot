---
date: 2026-10-18
slug: teorias-reclutamiento-people-analytics
categories:
  - Ensayos
title: Teorías de reclutamiento y people analytics que el diseño todavía no tipa
description: >-
  Qué dice la literatura de selección de personal y people analytics que JobBot
  ya practica a medias, qué estamos pasando por alto, y next steps de diseño
  de clases (sin inventar experiencia ni culture-fit).
---

# Teorías de reclutamiento y people analytics que el diseño todavía no tipa

JobBot ya toma partido: perfil como fuente de verdad, match léxico sin inventar,
condiciones del aviso antes de postular, HITL en lo irreversible, prácticas de
reclutamiento públicas vía `recruiters` — no personas. Eso coincide con trozos
de la literatura de psicología industrial-organizacional (I-O) y de *people
analytics*. Otros trozos los estamos **re-derivando en chat** o dejando como
heurística en adapters. Este post mapea teorías citables a huecos del modelo de
dominio y a next steps concretos.

<!-- more -->

No es un manual de “cómo pasar el ATS”. Es un inventario de *condiciones de
posibilidad* del diseño: qué estructuras del mercado de selección ya están
estudiadas y cómo deberían aparecer como tipos, no como prompts.

## Lo que ya hacemos (y a qué teoría se parece)

| Práctica JobBot | Lectura teórica |
| --- | --- |
| Nunca inventar hechos; métricas solo del SST | **Señales honestas** (costosas / difíciles de falsificar) en selección como juego de señales (Bangerter, Roulin & König, 2012) |
| `jobs conditions` antes de apply | **Realistic Job Preview** del lado candidato: información equilibrada para auto-selección (Landis, Earnest & Allen; meta-análisis de atracción de Chapman / Uggerslev) |
| Matcher por evidencia del perfil vs aviso; alerta si todo es 0% | **Person–job fit** percibido vía KSAs (Kristof-Brown et al.), no *culture fit* vago |
| `cv advise` rechaza floritura e invención | Contra **impression management** de alta intensidad en el CV (autodescripciones que no aportan evidencia) |
| Prefill + humano envía; sin auto-submit | **Justicia procedimental** / reacciones del candidato (Gilliland): control y transparencia en el proceso |
| Sin proxies de profesión en el código; suite domain-agnostic | Evitar **proxy discrimination** / filtros no justificados por análisis del puesto (línea FINDHR / auditoría de recruiting algorítmico) |
| `recruiters discover` → prácticas, no autores | Separar *practice knowledge* de la persona reclutadora (el mapa, no el viajero) |

Eso es suelo, no techo.

## Lo que la literatura tipifica y nuestro dominio aún no

### 1. Job analysis → competencias → must-have vs nice-to-have

La secuencia clásica es: planificación de fuerza de trabajo → **análisis del
puesto** (tareas, condiciones, KSAs) → anuncio → selección (CIPD / revisiones
de recruitment & selection). Skills-first (OCDE) prioriza evidencia de
competencia sobre credencial cuando la credencial no es requisito legal.

**Hoy:** el aviso llega como prosa Frankenstein; `requirements` / `skills` son
listas de strings; excluyente vs deseable vive en parsers de `conditions`, no
como campo tipado del `JobPosting`.

**Hueco de clase:** `Requirement(kind: must\|want, evidence, source_span)` y
separar *credential filter* de *skill evidence*.

### 2. Person–job fit ≠ person–organization fit

Los reclutadores distinguen P–J (habilidades, experiencia, educación) de P–O
(valores, “encaje cultural”); ambos predicen recomendaciones, pero el P–O vago
es puerta a sesgo de similitud (Kristof-Brown, 2000; meta-análisis de atracción).

**Hoy:** el score es casi solo eco léxico del JD (P–J débil). No modelamos P–O
— y **no debemos inventarlo**.

**Hueco de clase:** dejar P–O fuera del matcher automático; si algún día hay
dato, que sea preferencia declarada del candidato (`ApplicationPreferences`),
nunca inferida del tono del aviso.

### 3. Jerarquía de evidencia (claim → verified competency)

Evaluaciones recientes de ATS con IA argumentan que “¿el CV se parece al
aviso?” es la pregunta equivocada. Proponen una escalera: *claim → experience →
evidence → assessment → verified competency*, con humano en el loop
(HLECEF / evidence-based ATS).

**Hoy:** un achievement con `metrics` ya es más “costoso” que un tag suelto, pero
el dominio no distingue niveles de evidencia. El matcher trata mucho como
presencia de token.

**Hueco de clase:** `EvidenceStrength` en logros / skills→roles (#195); el
paquete de `prepare` puede mostrar veredicto por requisito con esa escala (#186).

### 4. Validez de métodos de selección (Schmidt–Hunter y actualizaciones)

Décadas de meta-análisis ordenan predictores de desempeño: habilidad cognitiva,
entrevista **estructurada**, muestras de trabajo, conocimiento del puesto, etc.
Años de experiencia o de educación solos predicen poco. La entrevista
estructurada gana validez cuando las preguntas salen del análisis del puesto
(Campion; OPM).

**Hoy:** no tipamos preparación STAR ni banco de preguntas ancladas al aviso
(#203). `application prepare` empaqueta CV; no un *interview kit* grounded.

**Hueco de clase:** `InterviewPrompt` derivado solo de requisitos del posting +
hechos del perfil (Specification + HITL); nunca inventar anécdotas.

### 5. Screening del CV bajo certeza vs incertidumbre

Estudios de *policy capturing* (p. ej. Grobelny et al.) sugieren: con certeza,
los evaluadores usan componentes **relevantes** y reglas no compensatorias; con
incertidumbre, compensan con señales formales e irrelevantes (formato, “ruido”).

**Hoy:** cuando el JD es corto o chrome de ATS, el matcher y `cv build --job`
pueden colapsar (#178). No hay tipo “confianza del posting”.

**Hueco de clase:** `PostingClarity` / cobertura de requisitos parseados; si es
baja, shortlist y advise deben decirlo (no rellenar con sinonimia inventada).

### 6. Etapas de atracción (Uggerslev / Chapman)

La atracción del candidato cambia de etapa: características del proceso y del
reclutador pesan al inicio; las del **puesto** pesan más en la elección final.
Expectativas de oferta (*hiring expectancies*) importan; alternativas percibidas,
menos de lo que se cree.

**Hoy:** un solo `match_score` acompaña casi todo el funnel.

**Hueco de clase:** scores o veredictos por etapa (`discover` / `shortlist` /
`apply` / `choose`) alimentados por conditions + klarheit del aviso, no un
único porcentaje cosmética.

### 7. People analytics sin telemetría del candidato

*People analytics* en empresa suele ser predictivo sobre empleados. Del lado
candidato, el análogo ético es: **evidencia local, auditable, sin phoning home**.
JobBot ya elige eso (SQLite + YAML gitignored). Lo que falta no es un modelo de
riesgo en la nube: es tipar las variables que la literatura usa (competencias,
must/want, evidencia, RJP) para que el analytics sea `jobs conditions` +
`match` + paquete, no un LLM que adivina culture-fit.

## Next steps (diseño de clases / producto)

Ordenados por desbloqueo, no por moda:

1. **Tipar must-have vs nice-to-have** en el posting (job analysis mínimo) y
   exponerlos en `jobs conditions` / shortlist — issues #166, #186.
2. **Value objects** que la literatura asume y el YAML aplana: idiomas CEFR
   (#141), `Education.status` (#185), `unit` / `work_mode` (#144).
3. **`EvidenceStrength` + skills↔experiencia** (#195): la escalera claim→evidence
   sin salir del SST.
4. **Fact aggregate vs Preference aggregate:** elegibilidad y answers fuera de
   `Candidate` (#206), para no mezclar P–J facts con preferencias de postulación.
5. **Interview kit STAR** grounded (#203): Specification sobre requisitos del
   aviso + logros existentes; dry-run default.
6. **`PostingClarity`:** cuando el Frankenstein no alcanza para P–J, no
   compensar con ruido formal (#178).
7. **`recruiters discover`:** además de tips web, fuentes públicas de práctica
   I-O (guías OPM structured interview, resúmenes CIPD/OCDE skills-first) como
   *practices* promovibles hacia `cv advise` — sin autores ni empleadores.
8. **Documentar anti-metas:** no modelar P–O automático; no IQ/GMA del
   candidato; no adverse-impact “score” opaco. La validez Schmidt–Hunter informa
   *qué no fingir* (años de experiencia ≠ señal fuerte), no un test cognitivo
   embebido.

Patrones de diseño ya discutidos en el mapa de ingeniería
([software-design.md](../../software-design.md)): Specification para
condiciones, ACL de homologación portal→perfil (#94), Overlay i18n (#221),
Command/plan-then-apply. Este post les pone **ancla teórica** para no re-litigar
el “por qué” en cada issue.

## Lecturas (punto de entrada)

- Kristof-Brown, Zimmerman & Johnson — person–environment fit (meta-análisis).
- Bangerter, Roulin & König (2012) — *Personnel selection as a signaling game*.
- Chapman et al. (2005); Uggerslev, Fassina & Kraichy (2012) — atracción del
  candidato por etapas.
- Schmidt & Hunter (y actualizaciones Schmidt–Oh) — validez de métodos de
  selección (contexto: qué señales importan; JobBot no implementa tests).
- Campion / OPM — entrevistas estructuradas ancladas al puesto.
- OECD skills-first hiring; CIPD recruitment & selection overviews.
- Landis, Earnest & Allen — Realistic Job Previews.
- Trabajos recientes sobre ATS evidence-based / HLECEF (jerarquía de evidencia
  frente a similitud CV–JD).
- FINDHR / auditorías de recruiting algorítmico — fairness sin telemetría del
  candidato.

Las citas completas viven en esos DOIs y reportes; acá basta el ancla. Si un
next step no se puede falsificar con un test de fixture, no es next step de
JobBot: es ensayo.

## Relación con el resto del blog

- Anatomía del aviso: [descripción de cargo Frankenstein](draft-descripcion-cargo-frankenstein.md)
  (borrador).
- Requisitos como racionamiento: [draft](draft-requisitos-como-racionamiento.md).
- Mapa de ingeniería: [software-design.md](../../software-design.md) § Next steps.
