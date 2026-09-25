---
draft: true
date: 2026-11-05
categories:
  - Ensayos
title: La convivencialidad como criterio de diseño (y el fantasma de Stata)
description: Borrador — esquema, argumento capturado y referencias. Pendiente de escribir en prosa.
---

# La convivencialidad como criterio de diseño (y el fantasma de Stata)

!!! note "Borrador — no publicar"

    Notas de investigación y esqueleto. La prosa la escribe el autor. Los conteos de
    la CLI son observaciones del proceso de diseño: **verificar contra el estado
    actual del código** antes de publicar.

## Tesis (para reescribir en voz propia)

Illich da un criterio de diseño que se puede aplicar como **criterio de aceptación**:
una herramienta es **convivencial** si es *aprendible sin credencial*, *usable sin
permiso* y *abandonable sin pérdida*. Con esa vara, dos peligros concretos:
**monopolio radical** (una herramienta que destruye la posibilidad de resolver la
necesidad de cualquier otro modo — LinkedIn) y **contraproductividad** (el umbral a
partir del cual más herramienta produce menos bien). Y un caso de estudio de cómo una
herramienta se vuelve **no** convivencial por dentro: **Stata**, que no se pudrió por
tamaño sino porque **cada comando era su propio micro-lenguaje**.

<!-- more -->

## El argumento, capturado

### 1. Illich: monopolio radical y contraproductividad

- Ivan Illich, *La convivencialidad* (*Tools for Conviviality*, 1973).
- **Monopolio radical**: no es el monopolio de una marca sobre un mercado; es el de un
  **tipo de herramienta** sobre la **satisfacción de una necesidad**, al punto de
  **destruir las alternativas**. Ejemplo vivo: **LinkedIn** — vuelve casi impensable
  "buscar trabajo" sin pasar por ahí; no compite con otras formas, las **extingue**.
- **Contraproductividad**: toda herramienta tiene un **umbral** más allá del cual
  **más herramienta produce menos bien** (más tráfico → menos movilidad; más
  escolarización → menos aprendizaje). Hay un óptimo, y pasarse es empeorar.

### 2. El test convivencial como criterio de aceptación (lo operativo)

- Tres condiciones, usables como *checklist* de diseño:
    1. **Aprendible sin credencial** — no requiere un curso ni un gremio para
       entrarle.
    2. **Usable sin permiso** — no depende de que un tercero (plataforma) te habilite.
    3. **Abandonable sin pérdida** — puedes irte y llevarte lo tuyo; no te secuestra.
- (Enlace con el post 7: "abandonable sin pérdida" es hermano del **derecho al olvido**
  como primitiva, y "usable sin permiso" es lo contrario del monopolio radical.)

### 3. El fantasma de Stata: cómo se pudre una herramienta **por dentro**

- Tesis contraintuitiva: Stata no se degradó por ser **grande**, sino porque **cada
  comando es su propio micro-lenguaje**:
    - **argumentos posicionales** distintos por comando;
    - **abreviaturas** idiosincráticas;
    - **acumulación sin remoción** (se agrega, nunca se saca);
    - **ninguna gramática transferible**: saber un comando no ayuda a adivinar el
      siguiente.
- Moraleja: el enemigo de la convivencialidad de una CLI no es el número de comandos;
  es la **ausencia de gramática común**. Sin gramática, cada comando es una credencial
  nueva → falla el test (1).

### 4. Síntomas tempranos en JobBot (observaciones a verificar contra el código)

- **~61 comandos** (hoy ~63 decoradores de comando; verificar el número exacto).
- **`application` vs `applications`**: singular/plural incoherente entre comandos.
- **Tres comandos de búsqueda** distintos (fricción: ¿cuál uso?).
- **`indeed` / `linkedin` como comandos copy-paste** (mismo patrón duplicado por
  fuente en vez de una gramática única).
- **`apply --apply`**: tartamudeo (el flag repite el nombre del comando).
- **`--cdp` en ~14 comandos** (bandera repetida; hoy el string `cdp` aparece ~66 veces
  en `cli.py` — verificar a cuántos comandos corresponde).
- **`--json` en solo 3 de 61 comandos** (salida estructurada inconsistente; hoy el
  string `json` aparece ~19 veces — verificar la cobertura real por comando).
- Lectura: son **exactamente los síntomas de Stata** en etapa temprana. Barato de
  arreglar ahora, carísimo después.

### 5. Chat-first corta para los dos lados

- **A favor**: si un agente **emite** la sintaxis, el humano **nunca la memoriza** → se
  puede saltar el costo de aprendizaje (mitiga la falla del test (1)).
- **En contra**: sin usuarios expertos **molestos**, no hay quién **señale el dolor**
  de una sintaxis podrida. La pudrición avanza **sin auditoría** porque nadie se queja.
- Consecuencia de diseño: como el agente absorbe la fricción de entrada, hay que
  **mover la vara de calidad** desde "brevedad para el humano" hacia "**legibilidad de
  lo que el agente hizo**" (ver §6).

### 6. Defensas (el "y entonces qué")

- **Gramática fija sustantivo-verbo-flag** (`jobs search --…`, `application add --…`):
  saber una forma predice las demás.
- **Conjunto CERRADO y chico de verbos reutilizados** (add/list/show/remove/search/
  apply/forget…): no inventar un verbo por comando.
- **Optimizar la legibilidad de lo que el agente HIZO**, no la brevedad del input
  humano: **audit trail**, salida estructurada (`--json` consistente), no abreviaturas.
- **Consistencia por sobre potencia-por-comando**: preferir un comando predecible a uno
  poderoso-pero-único. (Es la lección exacta de Stata invertida.)

## Referencias (verificadas)

- Ivan Illich, *Tools for Conviviality*, Harper & Row, 1973. Español: *La
  convivencialidad*, Barral Editores, 1974 (reed. varias). Sin DOI.

## Enlaces internos

- Fondo filosófico del esquema: [Fenomenología del software: el esquema como
  Ideenkleid](draft-fenomenologia-software-ideenkleid.md).
- Por qué "abandonable sin pérdida" es político: [Invertir la mirada: el trabajo como
  mercancía ficticia](draft-trabajo-mercancia-ficticia.md).
