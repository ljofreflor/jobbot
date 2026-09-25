---
draft: true
date: 2026-10-08
categories:
  - Ensayos
title: La ontología de una oferta laboral
description: Borrador — esquema, argumento capturado y referencias. Pendiente de escribir en prosa.
---

# La ontología de una oferta laboral

!!! note "Borrador — no publicar"

    Notas de investigación y esqueleto. Tesis, argumento en viñetas y referencias
    verificadas para que el autor escriba la prosa en su voz. No es un texto
    terminado.

## Tesis (para reescribir en voz propia)

Lo que llamamos "una oferta laboral" son en realidad **cuatro entidades distintas**
que el lenguaje cotidiano —y casi todo modelo de datos— colapsa en una sola:

1. **El trabajo (Work)**: lo que alguien efectivamente haría. Rara vez observable;
   casi nunca está en el aviso.
2. **La posición / requisición (Position)**: un **hecho institucional** (en el
   sentido de Searle). Tiene estado: *financiada / abierta / congelada / llena /
   cancelada / fantasma*.
3. **El aviso (Posting)**: un documento, un **acto de habla**. Una Posición puede
   emitir **N** Avisos.
4. **El avistamiento (Sighting)**: un **evento de observación**. Yo vi *este* texto
   en *esta* URL en *este* momento.

La regla epistémica que ordena todo el post: **la Posición nunca se observa
directamente; solo se observan Avistamientos.** La arista Aviso → Posición es
**siempre una inferencia**, y por lo tanto debe llevar confianza + evidencia, nunca
afirmarse como un hecho.

<!-- more -->

## El argumento, capturado

### 1. Las cuatro entidades, y por qué el colapso destruye información

- **Work / Trabajo.** Persiste aunque no haya cupo. Es lo que el matching *debería*
  querer, y casi nunca puede ver. Recomendación de diseño (abajo): dejarlo
  **implícito** por ahora.
- **Position / Posición** = hecho institucional. Searle, *The Construction of Social
  Reality* (1995): un hecho institucional es una **función de estatus** de la forma
  "**X cuenta como Y en el contexto C**". "Existe un cupo aprobado y presupuestado
  para contratar a alguien" es exactamente eso: no es un hecho bruto del mundo
  físico, existe porque una institución lo declara y lo sostiene. Por eso tiene
  **ciclo de estados** (financiada/abierta/congelada/llena/cancelada/fantasma) y por
  eso puede *dejar de existir sin que ningún átomo del mundo cambie*.
- **Posting / Aviso** = documento + acto de habla. Afirma algo sobre una Posición.
  Cardinalidad clave: **1 Posición → N Avisos** (mismo cupo, portal + LinkedIn +
  ATS + agencia).
- **Sighting / Avistamiento** = observación fechada, con fuente y URL. Cardinalidad:
  **1 Aviso → N Avistamientos** (lo vi el lunes, y de nuevo el jueves).

### 2. Las tres definiciones que solo este vocabulario puede dar con precisión

- **Ghost job** = un **Aviso sin Posición confirmable**. No es "un aviso viejo": es
  un aviso cuya arista hacia una Posición no puede sostenerse con evidencia. **Un
  modelo plano no puede ni siquiera nombrar esto**, porque no tiene el nodo Posición
  que podría faltar. La ausencia que define al ghost job es, literalmente,
  inexpresable en una tabla `jobs`.
- **Repost / reposteo** = **dos Avisos, una Posición**. Por lo tanto **deduplicar es
  una afirmación de identidad** ("estos dos Avisos apuntan a la misma Posición"), no
  una heurística de string sobre URL o título+empresa. La dedup deja de ser
  limpieza de datos y pasa a ser inferencia con confianza.
- **Vacante muerta** = **ausencia de Avistamientos**. Ojo: es un hecho **sobre la
  observación**, no sobre la Posición. "Dejé de verlo" no es "se cerró"; es "no lo
  vi". (Esto es exactamente la *missingness informativa* del post 3.)

### 3. Por qué una tabla plana `jobs` no puede expresarlo (con el código en la mano)

- El modelo actual `JobPosting` (`src/jobbot/models/job.py`) es **plano**: un `id`,
  una `url`, un `title`, una `company`, un único `discovered_at`. Colapsa Posting y
  Sighting en una fila y **no tiene** Posición.
    - No puede representar "dos avisos, una posición" salvo borrando uno (pérdida de
      información).
    - No puede representar "aviso sin posición" porque no hay posición.
    - Deduplicar por `title + company` **fabrica** identidad donde debería inferirse.

### 4. El hallazgo incómodo: **dos ontologías en un mismo repo**

- El registro de empresas (`src/jobbot/companies/models.py`) **ya tiene la
  epistemología correcta**, y el de vacantes **no**. En `companies`:
    - `Observation` = avistamiento fechado con `source`, `checked_at`, `evidence`,
      `observed_url`. Es exactamente un Sighting.
    - `CareerSite.confidence` = **número de fuentes independientes** que reportaron
      el sitio (la confianza *sube con evidencia independiente*, no se declara).
    - `CareerSite.conflicts` = las contradicciones se **guardan**, no se sobrescriben
      ("Kept even when they disagree", dice el propio comentario del modelo).
    - `ats` se queda en `AtsKind.UNKNOWN` **hasta que haya evidencia técnica**: no se
      adivina.
- Moraleja para el post: la epistemología correcta ya existe *en la casa*, aplicada
  a empresas. El trabajo es **portarla a las vacantes**. No hay que inventar nada;
  hay que ser consistente.

### 5. El puente fenomenológico (por qué esto no es solo modelado de datos)

- Husserl / Sokolowski: la Posición es el **objeto idéntico a través de un
  *manifold* (una multiplicidad) de apariciones**. Sokolowski, *Introduction to
  Phenomenology* (2000), lo llama "**identity in a manifold** of appearances": el
  mismo objeto se da en muchos perfiles/escorzos, y su identidad no es *otra*
  aparición más, sino lo idéntico que se mantiene a través de todas.
- Traslación exacta: los Avisos y Avistamientos son las **apariciones**; la Posición
  es la **identidad** que se mantiene a través de ellas. No la ves nunca "de frente"
  —solo perfiles— y aun así es lo que las apariciones son apariciones *de*.
- Este es el mismo puente que abre el post 3: "el objeto idéntico a través del
  manifold" = "la variable latente que es común a las mediciones ruidosas".

### 6. Recomendación de diseño (concreta, para no sobre-modelar)

- **Empezar con 3 clases**: `Sighting`, `Posting`, `Position`. Dejar `Work`
  **implícito** (no hay señal para poblarlo todavía).
- **Candidacy = la `Application` de hoy, repunteada**: hoy una postulación apunta a
  un `JobPosting` (un Aviso); debería apuntar a una **Posición** (a través de la
  inferencia con confianza). Es un *repoint*, no una clase nueva.
- Toda arista Posting → Position lleva `{confidence, evidence}`. Sin excepción.

## Cierre / enlace

- Si la Posición no se observa directamente, entonces es una **variable latente** y
  los Avistamientos son emisiones ruidosas de ella. Eso es literalmente un problema
  de estadística de lo no observado → sigue en el post 3.

## Referencias (verificadas)

- John R. Searle, *The Construction of Social Reality*. The Free Press / Penguin,
  1995. (Hechos institucionales; función de estatus "X counts as Y in C".) Sin DOI.
- Robert Sokolowski, *Introduction to Phenomenology*. Cambridge University Press,
  2000. DOI [10.1017/CBO9780511809118](https://doi.org/10.1017/CBO9780511809118).
  ("Identity in a manifold of appearances".)
- Edmund Husserl, *Ideas I* / *Cartesian Meditations* como fondo de la noción de
  identidad en la multiplicidad de escorzos (*Abschattungen*). Sin DOI.

## Enlaces internos

- Viene de: [La descripción de cargo como criatura de
  Frankenstein](draft-descripcion-cargo-frankenstein.md).
- Sigue en: [Lo que no se ve: inferencia estadística sobre
  vacantes](draft-inferencia-vacantes-latentes.md).
