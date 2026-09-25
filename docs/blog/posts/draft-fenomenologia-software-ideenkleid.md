---
draft: true
date: 2026-10-29
categories:
  - Ensayos
title: "Fenomenología del software: el esquema como Ideenkleid"
description: Borrador — esquema, argumento capturado y referencias. Pendiente de escribir en prosa.
---

# Fenomenología del software: el esquema como Ideenkleid

!!! note "Borrador — no publicar"

    Notas de investigación y esqueleto con referencias verificadas. La prosa la
    escribe el autor. No es un texto terminado.

## Tesis (para reescribir en voz propia)

Un esquema de datos no es una descripción neutra: es una **idealización** que, una
vez adoptada, tiende a **sustituir** a la cosa idealizada, y luego se olvida que
hubo sustitución. El `profile.yaml` de JobBot es el *Ideenkleid* (el "vestido de
ideas" de Husserl) de una persona: una idealización que se pone en lugar de la
persona, y cuyo origen —el gesto de idealizar— queda sedimentado y olvidado.
Diseñar software es, quiéralo o no, decidir qué del ser humano cabe en el vestido y
qué se recorta.

<!-- more -->

## El argumento, capturado

### 1. Husserl, *Crisis* §9: el *Ideenkleid* y el olvido del origen

- Galileo **matematiza la naturaleza** y comete un error de categoría: toma la
  **idealización matemática** por el **ser** de la naturaleza. La malla de idealidades
  se convierte en un *Ideenkleid* que se superpone al mundo de la vida
  (*Lebenswelt*) y termina pasando por la realidad misma.
- Dos movimientos clave a nombrar en la prosa:
    1. **sustitución**: lo idealizado ocupa el lugar de lo real;
    2. **sedimentación / olvido del origen**: el método se hereda ya hecho, y se
       olvida que fue un método, una decisión, un recorte.
- Traslación al software: el esquema (`profile.yaml`, la tabla `jobs`, cualquier
  modelo) es el *Ideenkleid*. Se lo trata como "la persona" o "el trabajo", y a las
  pocas versiones nadie recuerda que fue una **elección** con un afuera.
    - (Continuidad con el post 1: allí el **aviso** era el *Ideenkleid* del **puesto**;
      aquí el **perfil** es el *Ideenkleid* de la **persona**. Mismo error, otra capa.)

### 2. Bowker & Star: categorías residuales y *torque*

- *Sorting Things Out: Classification and Its Consequences* (1999). Toda
  clasificación produce **categorías residuales** ("otros", "no especificado"): el
  cajón donde va lo que no cupo. Y produce **torque** (torsión): una **biografía real
  torcida** para caber en la clasificación (su ejemplo canónico: pacientes cuya vida
  se deforma para encajar en categorías médicas/administrativas).
- Uso en el post: el `profile.yaml` produce residuo y torque. La pregunta de diseño
  no es "¿cómo evito el residuo?" (imposible) sino "¿qué hago con él?".
- Nota bibliográfica: **no hay edición en español**; citar en inglés.

### 3. Scott: legibilidad — y por qué *local-first* cambia el cálculo

- *Seeing Like a State* (1998): para volver algo **legible** (y así gobernable,
  agregable), el Estado **descarta el conocimiento local** (la *mētis*) que hacía que
  la cosa funcionara. La legibilidad tiene un costo: mata lo que no se deja contar.
- **El giro propio del post**: la razón por la que el Estado *debe* descartar lo que
  no encaja es que **necesita agregar**. En un sistema **local-first**, **nadie
  necesita tus categorías para agregar nada** → puedes darte el lujo de **guardar lo
  que no encaja** (texto libre, notas, excepciones) sin romper nada. La descentralización
  no es solo privacidad: **relaja la presión hacia la legibilidad** y por lo tanto
  hacia el torque.
- Edición en español: *Lo que ve el Estado*, Fondo de Cultura Económica (FCE).

### 4. Heidegger, *Ser y tiempo* §§14–18: la herramienta se retira en el uso

- La herramienta *zuhanden* (a-la-mano) **se retira** cuando se usa bien: no la
  notas, notas la tarea. La herramienta **aparece** solo en el **quiebre**.
- Los **tres modos de quiebre** (nombrarlos con precisión):
    - **Auffälligkeit** (llamatividad / *conspicuousness*): se rompe, salta a la vista.
    - **Aufdringlichkeit** (apremio / *obtrusiveness*): falta algo, estorba su ausencia.
    - **Aufsässigkeit** (rebeldía / *obstinacy*): se obstina, se pone en el medio.
- Uso en el post: un buen esquema es *zuhanden* — invisible en el uso; se hace visible
  (y se vuelve *vorhanden*, objeto de inspección) justo cuando el residuo/torque
  produce un quiebre. **El quiebre es diagnóstico**: donde el usuario pelea con el
  campo, ahí el vestido no calza. Diseñar para observar el quiebre, no para negarlo.
- Traducción de referencia: Jorge Eduardo Rivera (ed. española de *Ser y tiempo*).

### 5. Winograd & Flores: diseñar un espacio de compromisos, no un dominio

- *Understanding Computers and Cognition* (1986). El linaje **chileno** (Fernando
  Flores): el software no "modela un dominio"; **diseña un espacio de compromisos y
  conversaciones** (peticiones, promesas, declaraciones). El objeto del diseño no es
  la ontología del mundo, es la **acción** que el sistema hace posible.
- Uso en el post: reencuadra todo. Un `profile.yaml` no "describe a la persona";
  **habilita compromisos** (postular, abstenerse, declarar, ser olvidado). Si lo
  piensas como descripción, caes en el *Ideenkleid*; si lo piensas como espacio de
  compromisos, el residuo deja de ser un defecto y pasa a ser lo que aún no se
  comprometió.

### 6. Consecuencias de diseño (el "y entonces qué")

- Guardar el residuo en vez de forzarlo (permitido por local-first, §3).
- Instrumentar el **quiebre** (§4) como señal de dónde el esquema no calza.
- Pensar campos como **habilitadores de acción** (§5), no como espejos de la persona.
- Recordar el **origen** del esquema (§1): dejar por escrito que fue una decisión con
  un afuera, para que no se sedimente en "así es la realidad".

## Referencias (verificadas)

- Edmund Husserl, *The Crisis of European Sciences…*, §9 (Galileo / *Ideenkleid*),
  trad. Carr, Northwestern UP, 1970. Español: *La crisis de las ciencias europeas…*,
  Prometeo. Sin DOI.
- Geoffrey C. Bowker & Susan Leigh Star, *Sorting Things Out: Classification and Its
  Consequences*, MIT Press, 1999. (Sin edición en español.) DOI del libro:
  [10.7551/mitpress/6352.001.0001](https://doi.org/10.7551/mitpress/6352.001.0001).
- James C. Scott, *Seeing Like a State*, Yale University Press, 1998. Español: *Lo
  que ve el Estado*, FCE. Sin DOI.
- Martin Heidegger, *Sein und Zeit* (1927), §§14–18. Español: *Ser y tiempo*, trad.
  Jorge Eduardo Rivera. Sin DOI.
- Terry Winograd & Fernando Flores, *Understanding Computers and Cognition: A New
  Foundation for Design*, Ablex, 1986. Sin DOI.

## Enlaces internos

- Antecedente (el aviso como *Ideenkleid* del puesto): [La descripción de cargo como
  criatura de Frankenstein](draft-descripcion-cargo-frankenstein.md).
- Criterio de diseño derivado: [La convivencialidad como criterio de diseño (y el
  fantasma de Stata)](draft-convivencialidad-fantasma-stata.md).
