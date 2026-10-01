---
draft: true
date: 2026-10-15
categories:
  - Ensayos
title: "Lo que no se ve: inferencia estadística sobre vacantes"
description: Borrador — esquema, argumento capturado y referencias. Pendiente de escribir en prosa.
---

# Lo que no se ve: inferencia estadística sobre vacantes

!!! note "Borrador — no publicar"

    Notas de investigación y esqueleto con referencias verificadas (DOIs). La prosa
    la escribe el autor. No es un texto terminado.

## Tesis (para reescribir en voz propia)

Si la Posición es una entidad distinta del Aviso (post 2), entonces la Posición es
una **variable latente**: nunca la observas, solo observas **emisiones ruidosas** de
ella (Avistamientos, avisos, movimientos en LinkedIn, un reclutador que escribe). Y
la **ausencia** de un Avistamiento no es un dato faltante neutro: es **informativa**,
igual que no ver una especie en un transecto informa sobre su presencia. La
estadística para esto ya existe y viene de la **ecología** (modelos de ocupación) y
de la **captura-recaptura**. Con eso se puede estimar el tamaño de lo que ninguna
fuente vio, y —lo esencial— reportarlo **con intervalo**, no como veredicto.

<!-- more -->

## El argumento, capturado

### 1. Planteamiento: latente + emisión ruidosa

- Posición = latente; Avistamiento = emisión. Probabilidad de detección `p` distinta
  por fuente y por tipo de empresa (un ATS público no se "ve" igual que un portal
  detrás de un CDN — ver la medición de bloqueos por IP de datacenter en este mismo
  blog).
- Falsos positivos: el Aviso que existe **sin** Posición detrás (el ghost job del
  post 2). El modelo tiene que admitir emisión sin fuente.

### 2. La ausencia es informativa (el punto que ordena todo)

- Rubin (1976) formaliza los mecanismos de datos faltantes: MCAR / MAR / **MNAR**.
  "No apareció en el portal" **no es MCAR**: la probabilidad de no observarlo depende
  del propio estado que queremos estimar → es *missingness* **informativa** (MNAR).
  Tratar la ausencia como un cero introduce sesgo, y del lado peor.
    - Donald B. Rubin, *Inference and missing data*, Biometrika 63(3):581–592, 1976,
      DOI [10.1093/biomet/63.3.581](https://doi.org/10.1093/biomet/63.3.581).

### 3. Modelos de ocupación (ecología) — la herramienta correcta

- Idea: separan **ocupación** `ψ` (¿la posición existe?) de **detección** `p`
  (¿la habría visto si existiera?). Es exactamente la distinción "no está" vs "está y
  no la detecté".
    - MacKenzie et al. (2002), *Estimating site occupancy rates when detection
      probabilities are less than one*, Ecology 83(8):2248–2255, DOI
      [10.1890/0012-9658(2002)083\[2248:ESORWD\]2.0.CO;2](https://doi.org/10.1890/0012-9658(2002)083[2248:ESORWD]2.0.CO;2).
    - Mapeo del vocabulario: **sitio → empresa/consulta**; **visita → consulta a una
      fuente en una fecha**; **especie presente → posición abierta**.
- **Diseño de visitas repetidas = por qué existe un cron diario.** El motivo del cron
  no es la *frescura*: es la **identificabilidad**. Sin visitas repetidas no se pueden
  separar `ψ` y `p`. Esta es la justificación estadística del cron, no una de producto.
    - MacKenzie & Royle (2005), *Designing occupancy studies: general advice and
      allocating survey effort*, Journal of Applied Ecology 42(6):1105–1114, DOI
      [10.1111/j.1365-2664.2005.01098.x](https://doi.org/10.1111/j.1365-2664.2005.01098.x).
- Extensión útil (abundancia a partir de conteos de detección/no-detección):
    - Royle & Nichols (2003), *Estimating abundance from repeated presence–absence
      data or point counts*, Ecology 84(3):777–790, DOI
      [10.1890/0012-9658(2003)084\[0777:EAFRPA\]2.0.CO;2](https://doi.org/10.1890/0012-9658(2003)084[0777:EAFRPA]2.0.CO;2).
- Software de referencia (no reinventar el estimador):
    - Fiske & Chandler (2011), *unmarked: An R Package for Fitting Hierarchical
      Models of Wildlife Occurrence and Abundance*, Journal of Statistical Software
      43(10), DOI [10.18637/jss.v043.i10](https://doi.org/10.18637/jss.v043.i10).

### 4. Captura-recaptura: estimar el **tamaño del mercado oculto**

- Dos fuentes independientes (p. ej. un portal **y** el ATS directo de la empresa).
  Lo que ninguna vio se estima desde el solapamiento. Estimador clásico:
  **Lincoln-Petersen**; la hipótesis frágil es la **independencia** de fuentes.
    - Revisión moderna: Bird & King (2018), *Multiple Systems Estimation (or
      Capture-Recapture Estimation) to Inform Public Policy*, Annual Review of
      Statistics and Its Application 5:95–118, DOI
      [10.1146/annurev-statistics-031017-100641](https://doi.org/10.1146/annurev-statistics-031017-100641).
    - Listas escasas / no solapadas: Chan, Silverman & Vincent (2021), *Estimating
      the Size of Hidden Populations Using Sparse Capture-Recapture Data*, JASA
      116(535):1105–1119, DOI
      [10.1080/01621459.2019.1708748](https://doi.org/10.1080/01621459.2019.1708748).
    - Heterogeneidad de captura (unidades más "capturables" que otras):
      Chao (1987), *Estimating the population size for capture-recapture data with
      unequal catchability*, Biometrics 43(4):783–791, DOI
      [10.2307/2531532](https://doi.org/10.2307/2531532).

### 5. Orden de envío (qué se ships primero, y por qué en ese orden)

- **(a) Curva de supervivencia (Kaplan-Meier) de la longevidad del aviso**, por
  empresa / por ATS. Es lo más barato y ya interpretable: **una cola larga = señal de
  ghost** (avisos que "viven" mucho más de lo plausible para un cupo real).
    - Kaplan & Meier (1958), *Nonparametric estimation from incomplete
      observations*, JASA 53(282):457–481, DOI
      [10.1080/01621459.1958.10501452](https://doi.org/10.1080/01621459.1958.10501452).
    - Cox (1972), *Regression models and life-tables*, JRSS B 34(2):**187–202**
      (¡no 187–220!), DOI
      [10.1111/j.2517-6161.1972.tb00899.x](https://doi.org/10.1111/j.2517-6161.1972.tb00899.x).
- **(b) Distribución de tiempos de respuesta con censura por la derecha.** Las
  postulaciones **nunca respondidas** son **censuradas**, no ceros. Meterlas como
  ceros arruina la estimación; censurarlas es lo correcto.
- **(c) Captura-recaptura** para el tamaño del mercado oculto (sección 4).
- **Más adelante:** modelo de ocupación completo + **HMM** para el ciclo de estados de
  la Posición (abierta → congelada → llena…), tratando los estados como cadena oculta.
    - Baum, Petrie, Soules & Weiss (1970), *A maximization technique occurring in the
      statistical analysis of probabilistic functions of Markov chains*, Annals of
      Mathematical Statistics 41(1):164–171, DOI
      [10.1214/aoms/1177697196](https://doi.org/10.1214/aoms/1177697196).
    - Rabiner (1989), *A tutorial on hidden Markov models and selected applications
      in speech recognition*, Proceedings of the IEEE 77(2):257–286, DOI
      [10.1109/5.18626](https://doi.org/10.1109/5.18626).

### 6. El puente Husserl → estimador

- "El objeto es lo idéntico a través del *manifold* de apariciones" (post 2) =
  "**el factor latente es lo común a las mediciones ruidosas**". Es la misma
  estructura formal: una identidad que no es ninguna de las apariciones y que, sin
  embargo, es lo que todas ellas manifiestan. La fenomenología nombra lo que el
  estimador calcula.

### 7. Restricciones de honestidad (esto NO es negociable en el post)

- **Reportar incertidumbre**: una *probabilidad de ghost con intervalo*, nunca un
  veredicto binario. El output honesto es "0.7 [0.5, 0.85]", no "es un ghost".
- **Todo es condicional a la rebanada del usuario** (país / sector / sus queries),
  **no** "el mercado". No existe "el mercado" en estos datos; existe *lo que este
  usuario pudo observar*.
- **Sin contrafactual no hay causalidad**: esto es **descripción**, no causación. No
  se afirma "esta empresa hace X porque…"; se describe un patrón observado.
- **Federación** (si varios usuarios aportan datos): hace falta modelar **efectos de
  detección por contribuyente** → jerárquico, con **partial pooling**. Y tiene
  **superficie adversarial**: alguien puede inyectar avistamientos falsos.
- **Goodhart / efecto reflexivo**: publicar un "ghost score" **cambia la conducta que
  se mide** (las empresas ajustan sus avisos para no puntuar mal). "When a measure
  becomes a target, it ceases to be a good measure."
    - Marilyn Strathern (1997), *'Improving ratings': audit in the British
      University system*, European Review 5(3):305–321, DOI
      [10.1002/(SICI)1234-981X(199707)5:3<305::AID-EURO184>3.0.CO;2-4](https://doi.org/10.1002/(SICI)1234-981X(199707)5:3%3C305::AID-EURO184%3E3.0.CO;2-4).

## Qué se puede calcular hoy con lo que JobBot ya guarda

- Con el registro de empresas (avistamientos fechados con fuente) y un cron, (a) y
  (b) son alcanzables ya. Para (c) hace falta registrar de forma explícita
  **no-hallazgos** (la fuente se consultó y no devolvió el aviso), la **cadencia** y
  la **fuente** de cada consulta. Sin registrar el no-hallazgo, el modelo no puede
  distinguir "no está" de "no miré".

## Cierre / enlace

- Un requisito publicado es una de esas emisiones cuya interpretación depende del
  **estado de mercado**, no solo del trabajo → sigue en el post 4.

## Referencias

(Todas listadas inline arriba, con DOI. Verificar además que la ecuación de
Lincoln-Petersen y sus supuestos de independencia queden explícitos en la prosa.)

## Enlaces internos

- Viene de: [La ontología de una oferta laboral](draft-ontologia-oferta-laboral.md).
- Sigue en: [Un requisito publicado es una regla de racionamiento sobre la
  cola](draft-requisitos-como-racionamiento.md).
