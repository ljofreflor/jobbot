---
draft: true
date: 2026-11-19
categories:
  - Ensayos
title: "El método: ficción como levantamiento de requerimientos"
description: Borrador — esquema, argumento capturado y referencias. Pendiente de escribir en prosa.
---

# El método: ficción como levantamiento de requerimientos

!!! note "Borrador — no publicar"

    Notas de investigación y esqueleto. La prosa la escribe el autor. Este post es el
    **meta-post**: explica el método con el que se produjeron los otros siete.

## Tesis (para reescribir en voz propia)

Una *user story* codifica una **intención** — y por eso su techo son las intenciones.
Pero una **historia** también **muestra un mundo**: **exhibe condiciones de
posibilidad**. Y las condiciones de posibilidad son la **notación natural de los
equilibrios** — es decir, de los requisitos que hay que **disolver**, no satisfacer.
La ficción, bien usada, no es adorno: es una **técnica de levantamiento de
requerimientos** que alcanza una capa que el empirismo no puede tocar.

<!-- more -->

## El argumento, capturado

### 1. Intención vs mundo: qué codifica una historia

- Una historia "como X quiero Y para Z" codifica una **intención**. Su techo son las
  intenciones **declaradas**: no ve más allá de lo que el sujeto ya se propone.
- Pero **narrar una escena completa** hace otra cosa: **muestra un mundo** con sus
  reglas, sus fricciones, sus imposibilidades. Ese mundo **exhibe condiciones de
  posibilidad** (lo que tiene que ser cierto para que la escena ocurra).
- Y las condiciones de posibilidad son la **notación natural de un equilibrio**: si
  quieres cambiar el resultado, no "satisfaces" los requisitos del equilibrio actual,
  **disuelves** la condición que lo sostiene. (Enlace directo con el post 4: el
  requisito de la cola es una condición de equilibrio, no una spec.)

### 2. Por qué la fenomenología llega donde el empirismo no

- Una **condición de posibilidad no está entre los fenómenos**: no es un dato más que
  se pueda observar junto a los otros. Por eso es **inalcanzable** por entrevistas,
  analytics o A/B tests — esos métodos muestrean **fenómenos**, y la condición es lo
  que hace posible que haya fenómenos.
- Solo se alcanza **interpretando la experiencia vivida como una huella** de la
  estructura que la produjo. Linaje de esta operación:
    - **Sartre**, *Crítica de la razón dialéctica* (1960): la experiencia individual
      como cifra de estructuras materiales/históricas.
    - **Fanon**: la vivencia (p. ej. la del racismo) leída como síntoma de una
      estructura, no como dato psicológico aislado.
    - **Bourdieu**, el ***habitus***: disposiciones incorporadas que son la huella de
      una estructura social en el cuerpo y la práctica.

### 3. Evidencia de que el método funciona (falsable, ojo)

- El método **predijo el punto ciego**: el lugar donde **~40 proyectos empíricos
  convergieron en *throughput*** (optimizar el flujo dentro del marco dado) — y por lo
  tanto donde **ninguno** cuestionó el marco. Que el método **anticipe dónde el
  empirismo se queda corto** es una predicción concreta, no una autofelicitación.
  (Verificar/aterrizar el "40" con la lista real al escribir.)

### 4. División del trabajo (quién genera qué, y dónde cada uno es inútil)

- **La DETECCIÓN de condiciones es del humano.** Es **generativa** al nivel de
  **condiciones / requisitos**: ahí la filosofía produce.
- **La filosofía no genera nada al nivel de mecanismos / soluciones.** Ejemplos
  brutales y honestos:
    - **Heidegger** detecta el ***Gestell*** (la "estructura de emplazamiento" de la
      técnica) de forma brillante — y prescribe **Gelassenheit** (serenidad,
      "dejar-ser"), que es **inútil** como mecanismo. Diagnóstico genial, receta vacía.
    - **Illich** diagnostica el monopolio radical y la contraproductividad (post 6) —
      y **no envía nada**. Cero producto.
- Moraleja: usar la filosofía para lo que sirve (detectar condiciones) y **no** para
  lo que no sirve (diseñar el mecanismo).

### 5. El rol de la IA es DESPUÉS del handoff (y por qué)

- La IA entra **después** de que el humano detecta la condición. Su trabajo:
    - encontrar **quién más chocó** con esta condición,
    - qué **precedente / mecanismo** existe,
    - qué **restricciones técnicas** aplican,
    - **escribir la segunda historia** (ver §6).
- La IA **NO** inventa la feature a partir del análisis. Razón dura: **un LLM siempre
  encuentra una conexión plausible para cualquier análisis, incluido uno equivocado**.
  Su modo de falla es **sonar bien**. Por eso no se le confía la detección de
  condiciones (donde un error suena tan convincente como un acierto), solo la
  ejecución posterior, que es verificable.

### 6. La compuerta de falsación que el humano se queda: la SEGUNDA HISTORIA

- Regla: escribir la **segunda historia** = **la misma persona dos años después**, en
  un mundo donde **la herramienta funcionó perfectamente** — y el **resultado es malo**.
- Eso es **variación eidética husserliana aplicada a futuros**: variar imaginariamente
  el caso para ver qué **estructura invariante** aparece (aquí: ¿el éxito de la
  herramienta produce un mal resultado por su propia lógica?).
- **Criterio de descarte**: si la segunda historia **se escribe sola**, la dirección
  estaba mal. Caso real: la **segunda historia del "instrumento de carrera"** (post 7,
  dirección A) **se escribe sola** — optimizarte para el mercado dos años seguidos te
  deja más atrapado en la ficción, no más libre. **Por eso esa dirección murió.**

### 7. Comparación con frameworks de innovación (dónde se ubica esto)

- Este método es un **cambiador de marco**, no un **optimizador**. Es una **capa por
  encima** de:
    - **Design Thinking** — se detiene en la **experiencia declarada**.
    - **Jobs-to-be-Done** — se detiene en la **intención** ("el trabajo que el cliente
      quiere lograr").
    - **Lean Startup** — **búsqueda local dentro del marco** en el que ya entraste
      (mejora el *fit*, no cambia el juego).
    - **TRIZ** — hace el **mismo movimiento** (buscar y disolver contradicciones) pero
      en el **dominio físico/ingenieril**, no en el de las condiciones sociales.
- Convergencia independiente que da confianza: **Donella Meadows**, *Leverage Points:
  Places to Intervene in a System* — el **punto de palanca #6 = flujos de información**
  coincide con **"hacer legible la abstención"** (post 7). Es decir, la **dinámica de
  sistemas** llega, por otro camino, a la misma intervención. Dos métodos distintos,
  mismo punto de palanca → señal de que no es casualidad.

### 8. Riesgo a declarar con honestidad (autocrítica obligatoria)

- "Mi método ve lo que el empirismo no puede" es **estructuralmente infalsable**, igual
  que la defensa de la astrología ("no funcionó porque no creíste"). Es una afirmación
  peligrosa.
- Lo único que la **salva** es **terminar en algo enviable que alguien use**. La
  falsación no está en el discurso; está en el **shipping**. Si el método no produce
  software que alguien adopte, es astrología. (Por eso el post 8 cierra la serie: el
  método se juzga por los siete posts anteriores y por el código, no por sí mismo.)

## Referencias (verificadas)

- Jean-Paul Sartre, *Critique de la raison dialectique*, Gallimard, 1960. Español:
  *Crítica de la razón dialéctica*. Sin DOI.
- Frantz Fanon, *Peau noire, masques blancs* (1952) / *Les damnés de la terre* (1961).
  Español: *Piel negra, máscaras blancas* / *Los condenados de la tierra*. Sin DOI.
- Pierre Bourdieu, *Esquisse d'une théorie de la pratique* (1972) / *Le sens pratique*
  (1980). (Habitus.) Sin DOI.
- Martin Heidegger, *Die Frage nach der Technik* (1954) — *Gestell*; *Gelassenheit*
  (1959). Español: *La pregunta por la técnica*; *Serenidad*. Sin DOI.
- Donella H. Meadows, *Leverage Points: Places to Intervene in a System*, The
  Sustainability Institute, 1999 (recogido en *Thinking in Systems*, 2008). Sin DOI.
- Edmund Husserl, variación eidética / *Wesensschau* (*Ideas I*). Sin DOI.
- Marco de referencia (frameworks): Design Thinking; Christensen et al. (JTBD); Eric
  Ries, *The Lean Startup* (2011); Genrich Altshuller (TRIZ). Sin DOI.

## Enlaces internos

- Cierra la serie. Índice: [La serie de ensayos de
  JobBot](draft-serie-ensayos-indice.md).
- La bifurcación que este método resolvió: [Invertir la mirada: el trabajo como
  mercancía ficticia](draft-trabajo-mercancia-ficticia.md).
