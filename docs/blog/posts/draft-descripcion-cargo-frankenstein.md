---
draft: true
date: 2026-10-01
categories:
  - Ensayos
title: La descripción de cargo como criatura de Frankenstein
description: Borrador — esquema, argumento capturado y referencias. Pendiente de escribir en prosa.
---

# La descripción de cargo como criatura de Frankenstein

!!! note "Borrador — no publicar"

    Esto NO es un texto. Son notas de investigación y un esqueleto para escribir:
    tesis, argumento capturado en viñetas, y referencias verificadas. La prosa
    final la escribe el autor, en primera persona y con su voz. Todo lo que sigue
    está en registro de apunte, no de ensayo publicado.

## Tesis (para reescribir en voz propia)

Una descripción de cargo rara vez se escribe: se **ensambla**. Los párrafos vienen
de avisos anteriores, muertos, de otras empresas y de otros cargos; el boilerplate
legal viene de RR.HH.; la lista de tecnologías viene de un equipo que ya no es ese
equipo. Nadie es el autor del documento completo. Y sin embargo ese compuesto
—cosido con partes de cadáveres de otros avisos— queda en posición de **juzgar** a
personas reales que sí son una sola cosa. Las costuras son detectables, y
detectarlas es una funcionalidad, no una curiosidad.

<!-- more -->

## El argumento, capturado

### 1. El aviso como ensamblaje, no como redacción

- Un aviso no tiene un autor: tiene un **historial de commits sin firmar**. De
  dónde sale cada bloque:
    - plantilla corporativa (marca, "sobre nosotros", diversidad),
    - un aviso anterior de la misma empresa (a veces de otro cargo),
    - copy de un aviso de otra empresa (mismo rubro, competidor),
    - requerimiento suelto del hiring manager,
    - boilerplate legal de RR.HH.
- Pregunta operativa que nadie puede responder limpiamente: *¿quién escribió esto?*
  No hay un "esto"; hay capas sedimentadas.

### 2. La analogía con Shelley — y por qué la analogía es una **inversión**, no un adorno

- *Frankenstein; or, The Modern Prometheus* (Mary Shelley, 1818/1831). La criatura
  está cosida de partes de cadáveres.
- **Diferencia 1 — el autor.** La criatura de Shelley *tiene* creador: puede
  confrontarlo, exigirle cuentas, reclamarle una compañera. El aviso no: su "autor"
  está distribuido hasta desaparecer. No hay Victor Frankenstein a quien la
  criatura-aviso pueda ir a reclamar. El postulante tampoco: no hay a quién
  preguntarle "¿por qué este requisito?".
- **Diferencia 2 — la inversión del juicio (este es el corazón del post).**
    - En Shelley: el compuesto es juzgado por *no lograr* la forma humana. La
      sociedad rechaza a la criatura por no ser suficientemente persona.
    - Acá: es al revés. El **humano real** es rechazado por *no lograr* la forma del
      compuesto. La persona —que sí es una sola cosa, con un solo autor— es medida
      contra una quimera sin autor y declarada insuficiente.
    - Formular esto explícitamente: lo monstruoso no es el candidato que no encaja;
      lo monstruoso es el patrón de medición.

### 3. Las costuras son observables (y esto es lo técnicamente interesante)

- La tesis fuerte y demostrable: si el aviso está cosido, las suturas dejan marcas
  detectables en el texto. No hace falta teoría de la mente del reclutador; basta
  leer el documento como lo que es.
- Tipos de costura (esto se vuelve el diseño de una feature, ver abajo):
    - **Incoherencia de registro / idioma** dentro del mismo texto (párrafos en
      inglés y español; "tú" y "usted"; primera y tercera persona).
    - **Requisitos imposibles por fecha**: "10 años de experiencia en X" cuando X
      tiene 6 años de existencia.
    - **Tecnologías que no coexisten** en un stack real (combinaciones que delatan
      copy-paste de dos avisos distintos).
    - **Restos de otro cargo**: seniority que no cuadra, nombre de un área que no es
      la del puesto, pronombres o títulos huérfanos.
    - **Fósiles**: frases boilerplate que sobreviven de una versión a otra sin que
      nadie las relea.

### 4. Concepto de comando: `jobs anatomy`

- Idea: un comando que **disecciona** el aviso y marca las suturas, sin decidir por
  la persona. Devuelve etiquetas por fragmento, cada una con una confianza y la
  evidencia textual que la gatilla.
- Vocabulario de etiquetas (nombres provisionales, en español, deliberadamente
  anatómicos/forenses):
    - `costura` — límite entre dos bloques de origen distinto (salto de registro,
      idioma, formato).
    - `imposible` — requisito internamente contradictorio o imposible por fecha.
    - `injerto` — bloque claramente importado de otro aviso/empresa (copy-paste).
    - `huerfano` — resto de otro cargo: seniority, área o pronombre que no cuadra.
    - `fosil` — boilerplate muerto que sobrevive por inercia.
- Principio de diseño (enlaza con HITL en el resto del proyecto): **se muestra la
  costura, no se emite un veredicto**. La herramienta señala; la persona lee.

### 5. El aviso como *Ideenkleid* del trabajo real (puente a la fenomenología)

- Husserl, *Crisis*, §9: Galileo matematiza la naturaleza y **confunde la
  idealización con el ser** de lo idealizado. La malla de idealidades matemáticas
  es un *Ideenkleid* —un "vestido de ideas"— que se **superpone** al mundo de la
  vida y termina **sustituyéndolo**; después el origen de esa sustitución se olvida
  (sedimentación).
- Traslación: **el aviso es el *Ideenkleid* del trabajo real.** Es la idealización
  textual de una cosa concreta (lo que alguien hará de verdad), y en el mercado se
  la trata *como si fuera* el trabajo. Se juzga a la persona contra el vestido, no
  contra el cuerpo.
- Enlace hacia el post 5 (fenomenología del software): el mismo movimiento
  —idealización sustituida por lo idealizado, origen olvidado— reaparece cuando un
  `profile.yaml` sustituye a la persona. Aquí el aviso hace lo propio con el puesto.

### 6. Endogamia: un corpus de avisos estudia un **género literario**, no la demanda

- Si los avisos se reproducen copiándose entre sí (injertos), un corpus de avisos
  no es una muestra de la demanda laboral: es una muestra de **cómo se escriben los
  avisos**. Es filología, no economía del trabajo.
- Consecuencia dura para cualquier análisis "de mercado" hecho sobre texto de
  avisos: mide **convenciones de redacción reproducidas por endogamia**, no
  necesidades reales de contratación. (Este es el mismo cuidado que en el post 4
  aparece como la deriva de composición de Burning Glass/Lightcast, y en el post 3
  como la razón por la que "un corpus grande de avisos" no basta para inferir
  vacantes.)
- Frase para el cierre: leer un corpus de avisos y creer que se lee el mercado es
  como leer un corpus de sonetos y creer que se estudia el amor.

## Cierre (para escribir)

- Qué cambia en cómo lees un aviso cuando ves las suturas: dejas de leerlo como una
  especificación y empiezas a leerlo como un **texto compuesto y sin autor** que,
  además, te está midiendo. Ver la costura devuelve la asimetría al lugar correcto.

## Referencias (verificadas)

- Mary Shelley, *Frankenstein; or, The Modern Prometheus*. Lackington, Hughes,
  Harding, Mavor & Jones, 1818 (ed. revisada, 1831). (Sin DOI; obra literaria.)
- Edmund Husserl, *Die Krisis der europäischen Wissenschaften und die
  transzendentale Phänomenologie*, §9 (esp. §9a–§9h sobre Galileo y el
  *Ideenkleid*). Ed. de referencia en inglés: *The Crisis of European Sciences and
  Transcendental Phenomenology*, trad. David Carr, Northwestern University Press,
  1970. Edición en español: *La crisis de las ciencias europeas y la fenomenología
  trascendental*, trad. Julia V. Iribarne, Prometeo Libros, 2008. (Sin DOI.)

## Enlaces internos

- Sigue en: [La ontología de una oferta laboral](draft-ontologia-oferta-laboral.md)
  (el aviso es solo una de las cuatro entidades).
- Fondo filosófico: [Fenomenología del software: el esquema como
  Ideenkleid](draft-fenomenologia-software-ideenkleid.md).
