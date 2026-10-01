---
date: 2026-09-24
slug: bloqueos-ip-datacenter
categories:
  - Mediciones
title: Qué sitios de empleo te bloquean desde una IP de datacenter (medido)
description: >-
  Medición del 24 de septiembre de 2026 desde una IP de AWS (AS16509, us-west-2):
  Indeed, Get on Board y LinkedIn Voyager devuelven 403; las APIs públicas de ATS
  devuelven 200 sin excepción.
---

# Qué sitios de empleo te bloquean desde una IP de datacenter (medido)

Si escribes un scraper de vacantes y lo corres en un servidor, algunas fuentes te
van a responder 403 y otras no. Esto no es folclore: el 24 de septiembre de 2026
medí ambos grupos desde la misma IP, en la misma ventana de minutos, y la
separación es limpia. Acá están los números.

<!-- more -->

## Montaje

Todas las peticiones salieron de una instancia en AWS `us-west-2`, es decir una IP
de datacenter en **AS16509**. Misma máquina, misma IP, mismo rato, para las dos
familias de endpoints. Donde se indica navegador, se usó Chromium **real** en modo
headless vía Playwright, no un cliente HTTP disfrazado.

## Portales de empleo para consumidores

### Indeed

`indeed.com` y `cl.indeed.com` respondieron **HTTP 403**, con el header de
respuesta `cf-mitigated: challenge` y un widget de **Cloudflare Turnstile** en el
cuerpo.

Lo importante es lo que ya estaba controlado cuando eso pasó. El intento no fue con
`requests`: fue con Chromium headless real, que envía un *TLS fingerprint* de
navegador correcto, y además con

- User-Agent realista de Chrome,
- `locale=es-CL`,
- `timezone=America/Santiago`,
- `navigator.webdriver` parchado a `undefined`.

Con toda esa superficie en orden, el resultado siguió siendo 403. Es decir: **la
huella del navegador estaba bien y la variable descalificante fue la IP.**

`rss.indeed.com` también respondió **403**.

### Get on Board

Acá el patrón es más interesante porque no falla de inmediato. Una petición suelta
se ve perfectamente normal. La degradación aparece con el volumen:

| Ritmo | Resultado |
|-------|-----------|
| ~2 peticiones/segundo, 25 secuenciales | **17 de 25** devolvieron 403 |
| 1 petición cada 5 segundos | **3 de 5** siguieron fallando |

Los 403 traían `server: cloudflare` y `cf-cache-status: DYNAMIC`, pero **sin** el
header `cf-mitigated`. Bajar la frecuencia a un quinto no arregló el problema, lo
cual sugiere que el puntaje no depende solo del ritmo.

### LinkedIn

- API **Voyager**: **403**.
- Endpoint público de vacantes para usuarios deslogueados (*guest*): **25 de 25**
  peticiones exitosas a 1 por segundo.

O sea, dentro del mismo dominio conviven un endpoint que rechaza a la IP de
datacenter y uno que no.

## APIs públicas de job board de los ATS

En la misma IP y en el mismo minuto, **todas** las APIs JSON públicas de tableros de
empleo de ATS devolvieron **200**:

| Proveedor | Endpoint |
|-----------|----------|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{empresa}/jobs` |
| Lever | `api.lever.co/v0/postings/{empresa}` |
| Ashby | posting-api |
| SmartRecruiters | API pública de postings |
| Breezy | API pública de postings |
| BambooHR | API pública de postings |
| Personio | feed XML |
| Workday | **400** en GET; **200** en POST con cuerpo JSON |

El caso de Workday no es un bloqueo: es un endpoint que simplemente espera POST con
un cuerpo JSON y responde 400 a un GET.

### Prueba de estrés

Para descartar que el 200 fuera suerte o cortesía por bajo volumen:

| Prueba | Resultado |
|--------|-----------|
| 40 peticiones a Greenhouse sin ninguna pausa | **40/40 HTTP 200** |
| 30 peticiones rápidas a Lever | **30/30 HTTP 200** |

Y para descartar que el User-Agent fuera la variable relevante, se repitió contra
Greenhouse, Lever y Ashby con tres identidades distintas:

- `python-requests/2.32.3` → 200
- `curl/8.5.0` → 200
- User-Agent **vacío** → 200

Ni siquiera hace falta mentir sobre quién eres.

## Por qué la separación es tan limpia

La conclusión es fáctica, no ideológica.

Los portales de empleo para consumidores están detrás de **gestión de bots de un
CDN**, que puntúa a la baja a los ASN de datacenter. El tráfico que esperan es el de
una persona con un navegador en una conexión residencial, y todo lo que se aleje de
eso paga un costo — aunque el navegador sea auténtico, como quedó demostrado con
Chromium real y la huella en orden.

Las APIs de job board de los ATS son **los mismos endpoints que el widget de
carreras embebible de cada proveedor llama desde el navegador de un visitante
cualquiera**. Están diseñadas para que una página de empresa las consuma en
público, sin sesión y desde cualquier parte. No hay nada que hacer saltar.

### Qué significa para quien usa JobBot

- El trabajo con **portales vía navegador** (`indeed`, `linkedin`, `getonboard`)
  pertenece a **tu máquina y tu conexión residencial**. Eso es exactamente donde
  JobBot lo pone: sesiones locales en `browser-data/`, con el humano a cargo cuando
  aparece un desafío.
- El **descubrimiento directo contra ATS** puede correr donde quieras: un servidor,
  un contenedor, un cron. No necesita navegador ni sesión.

Si tu arquitectura asume lo contrario — scraping de portales desde la nube — vas a
gastar el presupuesto de ingeniería en pelear con un CDN, y el sitio va a seguir
ganando.

## Contexto: esto está medido en la literatura

No es una anécdota de una tarde. Gundelach, Muhlhauser y Herrmann (2026),
*"Detecting bot detection: prevalence, techniques, and implications for web
measurement research"*, [arXiv:2606.14525](https://arxiv.org/abs/2606.14525)
([DOI 10.48550/arXiv.2606.14525](https://doi.org/10.48550/arXiv.2606.14525)),
visitaron 10.000 sitios con 40.000 visitas de página en Playwright desde una IP de
datacenter:

- los sitios servidos detrás de **Cloudflare bloquearon el 37,0 %** de las visitas;
- los servidos detrás de **Akamai, el 26,4 %**;
- y el **83 % de los papers** publicados en venues de primer nivel **nunca mencionan**
  que la detección de bots pudo haber afectado sus resultados.

Ese último número es el incómodo: mucha investigación de medición web reporta
resultados obtenidos desde IPs de datacenter sin considerar que una fracción grande
de su muestra nunca respondió de verdad.

## Nota de ética y modales

Que un endpoint responda 200 no es una autorización.

Ninguno de estos proveedores de ATS documenta un límite de tasa de lectura. Eso es
una **razón para la contención, no un permiso**. La ausencia de un límite publicado
significa que no sabes cuál es el límite, no que no exista.

Recomendaciones concretas, que es lo que hace JobBot:

- **150–300 ms de espaciado** entre peticiones. Es gratis y elimina el caso
  patológico.
- Un **User-Agent real e identificable**, con forma de contacto. Si le molestas a
  alguien, que pueda pedirte que pares.
- **Backoff** ante `429` y ante cualquier `5xx`. Un 429 es una instrucción, no un
  error transitorio que se reintenta igual.
- Volúmenes chicos y secuenciales. JobBot no es un crawler y no debería
  convertirse en uno.

---

*Todos los números de este post se midieron el 24 de septiembre de 2026 desde una
IP de AWS en `us-west-2` (AS16509). Una medición desde otra red, otro ASN u otra
fecha puede dar distinto; ese es precisamente el punto.*

*English version: [Which job sites block you from a datacenter IP
(measured)](2026-09-24-datacenter-ip-blocking.md).*
