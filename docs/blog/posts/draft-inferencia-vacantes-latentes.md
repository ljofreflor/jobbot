---
draft: true
date: 2026-10-15
categories:
  - Ensayos
title: "Lo que no se ve: inferencia estadística sobre vacantes"
description: Borrador — esquema, pendiente de escribir.
---

# Lo que no se ve: inferencia estadística sobre vacantes

!!! note "Borrador"

    Esto es un esquema, no un texto. No publicar hasta escribirlo.

## Tesis

Si la posición es una entidad distinta del aviso, entonces la posición es una
**variable latente**: nunca la observas, solo observas emisiones ruidosas de ella
(avisos, avistamientos, movimientos en LinkedIn, un reclutador que escribe). Y la
**ausencia** de un avistamiento no es un dato faltante neutro: es informativa, del
mismo modo en que no ver una especie en un transecto informa sobre su presencia.
La estadística para esto ya existe y viene de la ecología: los modelos de
ocupación separan "no está" de "está y no lo detecté", y el muestreo
captura-recaptura sobre dos fuentes independientes permite estimar el tamaño de lo
que ninguna de las dos vio.

<!-- more -->

## Esquema

- Planteamiento: posición latente, avistamiento como emisión ruidosa.
    - Probabilidad de detección por fuente y por tipo de empresa.
    - Falsos positivos: el aviso que existe sin posición detrás.
- Missingness informativo.
    - Por qué "no apareció en el portal" no es MCAR.
    - Sesgo que introduce tratar la ausencia como cero.
- Modelos de ocupación desde la ecología.
    - MacKenzie et al. (2002), *Estimating site occupancy rates when detection
      probabilities are less than one*, Ecology 83(8):2248–2255,
      [DOI 10.1890/0012-9658(2002)083\[2248:ESORWD\]2.0.CO;2](https://doi.org/10.1890/0012-9658(2002)083[2248:ESORWD]2.0.CO;2).
    - Mapeo del vocabulario: sitio → empresa; visita → consulta a una fuente;
      especie → posición abierta.
    - Qué requiere el modelo: visitas repetidas, y qué implica eso operativamente.
- Captura-recaptura entre dos fuentes.
    - Dos fuentes independientes (p. ej. un portal y el ATS de la empresa) para
      estimar el total no observado.
    - Estimador de Lincoln-Petersen y por qué la independencia es la hipótesis
      frágil acá.
    - Qué tan grande es el "mercado oculto" según esto, y con qué intervalo.
- Qué se puede calcular con los datos que JobBot ya guarda.
    - Qué falta registrar para que esto sea posible (cadencia de consulta, fuente,
      no-hallazgos).
- Honestidad sobre los supuestos: dónde se rompe cada uno y qué invalidaría el
  resultado.
