---
draft: true
date: 2026-11-26
categories:
  - Ensayos
title: "Disolver la necesidad: software que elimina condiciones de posibilidad"
description: Borrador — esquema, argumento capturado y referencias. Pendiente de escribir en prosa.
---

# Disolver la necesidad: software que elimina condiciones de posibilidad

!!! note "Borrador — no publicar"

    Notas de investigación y esqueleto. La prosa la escribe el autor. Este es el
    **ensayo-columna vertebral** del método: los demás posts son aplicaciones de esta
    operación. No es un texto terminado.

## Tesis (para reescribir en voz propia)

El diseño de software **no** debería transformar una **necesidad** en un **requisito**.
Debería **descomponer** la necesidad en sus **condiciones de posibilidad** y usar un
artefacto para **eliminar** un subconjunto de ellas, de modo que la necesidad
**se disuelva** y **deje de ser necesaria**. La ingeniería de requisitos clásica trata
la necesidad como un **átomo** y la traduce en *features*; este método trata la
necesidad como **derivada** de condiciones y **fabrica la desaparición** de algunas de
esas condiciones.

<!-- more -->

## El argumento, capturado

### 1. Definición: la reducción trascendental aplicada al diseño

- La pregunta que organiza todo es kantiana/husserliana: **"¿qué tiene que ser cierto
  para que X sea posible?"**. Kant la llama **condición de posibilidad**; Husserl monta
  encima la **reducción** (la *epojé*: poner entre paréntesis lo dado para ver su
  estructura).
- **Fenomenología del software** = aplicar la *epojé* **a una necesidad**: en vez de
  tomar la necesidad como dada y servirla, la ponemos entre paréntesis y buscamos
  **cuáles de sus condiciones de posibilidad se pueden fabricar-fuera** (ingeniar su
  desaparición).
- Es el **inverso exacto** del *requirements elicitation* clásico:
    - **Elicitation clásica**: necesidad → requisito → *feature* que la **satisface**.
      La necesidad queda intacta; se le da de comer.
    - **Este método**: necesidad → **descomposición** en condiciones → artefacto que
      **elimina** una condición → la necesidad **se disuelve**. No se le da de comer;
      se le quita el suelo.
- Enlace con el post-método: allí la **historia** exhibe condiciones de posibilidad
  (es la *notación* del equilibrio); aquí se nombra **qué se hace** con esa notación:
  **borrar** una línea del sistema de condiciones, no cumplir sus requisitos.

### 2. La ventaja de reusabilidad (el upside) — con su cota

- **Una condición es más general que una necesidad.** En un grafo de dependencias, la
  necesidad es **código de aplicación** y la condición es una **librería de la que
  cuelgan muchas necesidades**. Por eso, **quitar una condición puede disolver varias
  necesidades a la vez**.
    - Ejemplo JobBot: **la opacidad del empleador** es una condición compartida.
      Disolverla disuelve de un golpe: *trackear postulaciones* + *detectar ghost jobs*
      + *negociar a ciegas*. Tres necesidades, una condición.
- **Pero la generalidad tiene techo (regreso al infinito).** Cuanto **más general** es
  la condición, **más disuelve** y **más imposible** es removerla con un artefacto
  pequeño:
    - `asimetría de información` → disuelve **mucho** (varias necesidades).
    - `capitalismo` → disuelve **todo**… y **ningún software lo remueve**. La condición
      se vuelve tan general que el artefacto ya no la alcanza.
- **La banda viable**: existe un rango **suficientemente general para reusar** y a la
  vez **suficientemente local para que un artefacto llegue**. Ni tan específico que no
  reuse nada, ni tan abstracto que ningún software lo toque.
- **Regla de parada** (la que hay que citar): **desciende hasta la primera condición
  que puedas afectar y que le pague al primer participante.** Ese es el fondo del pozo:
  no la condición más profunda, sino la más profunda **accionable con retorno para
  alguien hoy**.

### 3. Por qué nadie paga (el downside) — afilado en TRES mecanismos distintos

No es "un" problema económico: son **tres** mecanismos independientes, y conviene no
mezclarlos.

- **a. La disolución mata la recurrencia.**
    - Una necesidad **satisfecha vuelve** (por eso el SaaS: te suscribes porque la
      necesidad recurre y hay que darle de comer cada mes).
    - Una necesidad **disuelta no vuelve**. El método es **anti-modelo-de-negocio por
      construcción**, no por accidente: su éxito es eliminar la recurrencia de la que
      vive un negocio.
- **b. Externalidad (problema de acción colectiva).**
    - La condición removida es **infraestructura compartida**. El valor **se escapa a
      quienes no pagan**, incluidos **competidores**. Quien financia la remoción
      subsidia a todos los demás → nadie tiene incentivo individual a pagar por un bien
      del que no puede excluir a nadie.
- **c. (nuevo, y el más profundo) Una necesidad disuelta es fenomenológicamente INVISIBLE.**
    - Una necesidad **satisfecha aparece como fenómeno** al que atribuyes valor:
      *"conseguí el trabajo **gracias a** X"*. Hay un evento, un antes/después, un
      objeto de gratitud.
    - Una necesidad **disuelta nunca aparece**: el problema **no llegó a manifestarse**,
      así que **nadie percibe una ausencia** por la que estar agradecido. **No pagas lo
      que evitó un problema que nunca tuviste.**
    - La **prevención es epistémicamente invisible**; el método **produce bienes
      invisibles**. Es la **maldición del plomero que lo arregló antes de que se
      rompiera**: como no se rompió, parece que no hizo nada.

### 4. El remate: la economía del método ES la economía de la infraestructura open-source

- Los tres mecanismos de §3 (no-recurrencia + externalidad + invisibilidad) son,
  juntos, **exactamente** la economía del **open-source de infraestructura**. Por eso
  el **mantenedor de una librería crítica que sostiene medio internet no gana nada**:
  no hay recurrencia que cobrar, el valor se externaliza a todos, y su trabajo es
  invisible mientras **no** se rompe.
- Giro central: **"nadie paga" no es un defecto a arreglar; es la prueba de que la
  arquitectura de comunes ya elegida es la entrega honesta.** El método, si funciona,
  produce bienes públicos; los bienes públicos **no tienen** modelo de negocio, y eso
  está bien.
- **Cadena de implicación (UNA, no tres decisiones sueltas):**
    1. el método produce **bienes públicos** →
    2. por lo tanto la **entrega debe ser un común** (abierto, bifurcable) →
    3. por lo tanto **no hay modelo de negocio** ni **servidor central** que **cercar**
       (*enclose*).
- Corolario que hay que decir con todas las letras: **decir "nadie paga por esto" es
  derivar la federación sin nombrarla.** La arquitectura *local-first* / comunes no es
  una preferencia estética añadida al final; es lo que **se sigue** de la economía del
  método.

### 5. El vacío ético (la crítica que NO se omite)

- El método **no tiene criterio propio** sobre **cuáles** necesidades disolver. Sabe
  descomponer y sabe eliminar; **no sabe elegir**.
- **No toda necesidad es un sufrimiento a remover.** Algunas son **formas de vida a
  proteger**: el **trabajo con sentido**, el **reconocimiento**, la **conexión**.
  Tratarlas como condiciones a ingeniar-fuera es la violencia de **Scott** (*Seeing
  Like a State*): **simplificación por legibilidad** que **destruye lo que hacía que la
  cosa valiera la pena**.
- El caso duro: **dos necesidades pueden descomponerse idénticamente** y sin embargo
  **una debe disolverse y la otra defenderse**. El método, **solo**, **no puede
  distinguirlas** — la estructura formal es la misma.
- **Lo que sí las distingue**: la **compuerta de falsación de la SEGUNDA HISTORIA**
  (variación eidética husserliana). **Escribe la historia en la que disolviste la
  condición y salió mal.** Criterio:
    - si esa historia **se escribe sola**, la necesidad era una **forma de vida** y **no
      había que tocarla**;
    - si cuesta escribirla (no hay un futuro plausible donde disolverla empeore las
      cosas), la necesidad era **sufrimiento** y disolverla estaba bien.
- Por eso la **variación eidética hace doble trabajo**:
    1. **falsa features** (post-método: descarta la dirección cuya segunda historia se
       escribe sola), y
    2. **decide qué necesidades son sagradas** (aquí: protege las formas de vida de la
       máquina de disolver).

## Aterrizaje en JobBot (concreto, no solo abstracto)

Aplicar la operación necesidad → condición → disolución a casos reales del proyecto:

- **"Necesito trackear mis postulaciones."**
    - Condición: **el empleador no expone mi estado** (opacidad del proceso).
    - Disolución: hacer **legible el comportamiento del empleador** → la necesidad de
      trackear **se debilita** (si el estado fuera visible, no habría que perseguirlo).
- **"Necesito saber si un aviso es real."**
    - Condición: **publicar un ghost job es gratis e inatribuible.**
    - Disolución: el **mapa compartido** vuelve el fantasmeo costoso/atribuible → la
      necesidad de adivinar **se disuelve** al hacerse visible quién fantasmea.
- **"Necesito negociar bien."**
    - Condición: **asimetría de información sobre bandas salariales.**
    - Disolución **parcial** por **divulgación**. **Límite honesto**: esta condición la
      disuelve **más la legislación** (transparencia salarial) **que el software**. Hay
      que decirlo: no todo lo disuelve un artefacto, y fingir lo contrario es
      deshonesto.
- **Contraste (el control negativo):** las herramientas de *throughput* que
  **satisfacen** *"postular más rápido"* **no disuelven nada** — dejan intactas todas
  las condiciones y por eso **recurren** (necesidad que vuelve) y **tienen modelo de
  negocio** (te cobran por seguir dándole de comer). Son la prueba por contraste de que
  satisfacer y disolver son operaciones opuestas.

## Referencias (por verificar/afinar al escribir)

- Immanuel Kant, *Kritik der reinen Vernunft* (1781/1787) — **condiciones de
  posibilidad** (argumento trascendental). Español: *Crítica de la razón pura*. Sin DOI.
- Edmund Husserl, *Ideen I* (1913) — **reducción / epojé** y **variación eidética**
  (*Wesensschau*); *Die Krisis…* (1936) para *Lebenswelt*. Español: *Ideas relativas a
  una fenomenología pura…*. Sin DOI.
- James C. Scott, *Seeing Like a State*, Yale University Press, 1998. Español: *Lo que
  ve el Estado*, FCE. (Legibilidad / destrucción de la *mētis*.) Sin DOI.
- Elinor Ostrom, *Governing the Commons*, Cambridge UP, 1990 — bienes comunes y acción
  colectiva (para §3b/§4). Sin DOI.
- Economía de bienes públicos / infraestructura open-source: Nadia Eghbal, *Working in
  Public: The Making and Maintenance of Open Source Software*, Stripe Press, 2020.
  (El mantenedor invisible.) Sin DOI.

## Enlaces internos

- **Cómo se detecta** la condición (la técnica que alimenta este método): [El método:
  ficción como levantamiento de requerimientos](draft-metodo-ficcion-requerimientos.md).
- **Qué recorta** el artefacto al idealizar (por qué toda disolución deja residuo):
  [Fenomenología del software: el esquema como
  Ideenkleid](draft-fenomenologia-software-ideenkleid.md).
- **La entrega como común** (por qué "nadie paga" deriva la federación): [Invertir la
  mirada: el trabajo como mercancía ficticia](draft-trabajo-mercancia-ficticia.md).
- Índice de la serie: [La serie de ensayos de JobBot](draft-serie-ensayos-indice.md).
