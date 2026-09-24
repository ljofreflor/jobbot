---
draft: true
date: 2026-10-08
categories:
  - Ensayos
title: La ontología de una oferta laboral
description: Borrador — esquema, pendiente de escribir.
---

# La ontología de una oferta laboral

!!! note "Borrador"

    Esto es un esquema, no un texto. No publicar hasta escribirlo.

## Tesis

Lo que llamamos "una oferta laboral" son en realidad cuatro entidades distintas que
el lenguaje cotidiano —y casi todo modelo de datos— colapsa en una sola: **el
trabajo** (las tareas que alguien va a hacer), **la posición o requisición** (un
hecho institucional: existe un cupo aprobado y presupuestado), **el aviso** (un
documento que afirma algo sobre esa posición) y **el avistamiento** (un evento de
observación: yo vi este documento en este lugar en esta fecha). Un *ghost job* es,
con precisión, un aviso cuya posición no existe; y un modelo de datos plano, con
una tabla `jobs`, literalmente no puede representar esa situación.

<!-- more -->

## Esquema

- Las cuatro entidades, una por una.
    - Trabajo: el conjunto de tareas. Persiste aunque no haya cupo.
    - Posición / requisición: hecho institucional, con estado y presupuesto.
    - Aviso: un documento; puede haber varios por posición, y variar entre sí.
    - Avistamiento: una observación fechada, con fuente y URL.
- Las cardinalidades que el colapso destruye.
    - Una posición con N avisos en M portales.
    - Un aviso reposteado: mismos bytes, distintos avistamientos.
    - Un aviso sin posición; una posición sin aviso (mercado oculto).
- Definición precisa de *ghost job* en este vocabulario.
    - Y sus vecinos: aviso vencido, pipeline building, posición ya llenada.
- Por qué una tabla plana `jobs` no puede expresarlo.
    - Qué pregunta deja de poder hacerse.
    - Qué se rompe al deduplicar por título + empresa.
- Consecuencias para el esquema de JobBot.
    - Qué tablas implicaría y qué costo tiene.
    - Qué se gana en las consultas que hoy no se pueden hacer.
- Enlace con el siguiente post: si la posición no se observa directamente, es una
  variable latente.
