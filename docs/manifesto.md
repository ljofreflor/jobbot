# Manifiesto JobBot

**Búsqueda mientras programas.**  
Humano al mando. Máquina al lado. Hechos, no teatro.

---

## 1. Quiénes somos

JobBot no es “una app de empleo con IA”.  
Es una **herramienta de oficio** para quien construye software y, al mismo tiempo, busca su próximo rol.

Nicho = **tecnología**.  
Canal = **donde ya trabajás**: la terminal, el editor, el repo — no el scroll de tips a las 11pm.

Unimos persona y automatización en un solo gesto (el rostro partido del logo):  
vos decidís; el bot prepara, difiere, prefill y espera.  
**HITL no es un disclaimer. Es el producto.**

---

## 2. La promesa

**Tu próximo paso, sin salir del flujo.**

- Encontrar señales donde el empleo *aparece* (ATS, boards, posts) — no solo donde el feed las proyecta.
- Organizar puestos, match y paquetes en local.
- Postular con asistencia — **vos enviás**.
- Nunca inventar experiencia para “ganar” un ATS.

| Uso | Texto |
| --- | --- |
| Tagline principal | **Búsqueda mientras programas.** |
| Tagline de marca | **Humano + bot. Vos al mando.** |
| Pie de marca | Personas · Oportunidades · Tecnología — *Más oportunidades. Un mejor mañana.* |

---

## 3. Principios (no negociables)

1. **Fuente de verdad** — `profile.yaml` (y lo que de ahí derive). Los portales son vistas. Los hechos no se fabrican.
2. **Pensar despacio una vez** — el vibecodeo descubre; el síntoma marca el retorno; comprimimos **condiciones de posibilidad** en comandos baratos. No cobramos System 2 dos veces en tokens del cliente.
3. **Fenomenología, no requerimientos clásicos** — no “satisfacemos un deseo”. Preguntamos qué hace *posible* que esa necesidad aparezca, y lo dejamos en código. Ver [software-design.md](software-design.md) §3.8 y [AGENTS.md](../AGENTS.md).
4. **Local por defecto** — PII, sesiones y base viven en tu máquina. Sin telemetría. Sin cloud de tu CV.
5. **Dry-run primero** — escribir en un portal o “aplicar” exige confirmación explícita (`--apply`). Un “sí” en un prompt no es comprobante de envío.
6. **LLM adentro, no en el chat eterno** — si hace falta prosa, vive dentro de una función (`--llm`), con hechos anclados y fallback determinista ([`nlp/gateway`](../src/jobbot/nlp/gateway.py)).
7. **Dominio-agnóstico** — enfermera, periodista o data scientist: ninguna regla gatea por el vocabulario de un solo oficio.

---

## 4. Lo que rechazamos

- Auto-submit, bypass de CAPTCHA/2FA, stealth, proxies “anti-bot”.
- Reescribir el CV para un score de ATS inventando bullets.
- Apps que te sacan del editor para “gestionar tu carrera” en otro dashboard.
- Publicidad que promete sueldos de escaparate o magia de Google.
- Dejar insights solo en el chat de un agente: si vuelve, es síntoma → se captura redactado (`jobbot ops symptom note`) → se comprime a feature.

---

## 5. Tres pilares

**Encuentra donde publican**  
No solo el agregador. Hosts ATS, boards, sweeps. Queries que vos corrés; JobBot no telefonea al buscador (`jobbot jobs queries`).

**Prepara sin inventar**  
Match, CV derivado, paquete de postulación desde hechos que ya existen. Huecos = preguntas, no relleno.

**Postula con vos al mando**  
Prefill, adjunto, Gmail compose, plan dry-run. El clic final es humano. Siempre.

---

## 6. Lenguaje natural → oficio

En posts y docs, el contrato es el mismo: lo que pedís en natural se vuelve un comando, no un milagro.  
(LinkedIn no admite tablas: usar líneas con `→`.)

“Armame búsquedas en Ashby/Greenhouse/Lever para remoto Chile / data scientist”  
→ `jobbot jobs queries --region Chile -k "data scientist"`

“Traé ofertas de Indeed a mi base”  
→ `jobbot jobs search "Senior Data Scientist" --location Santiago`

“¿Qué tan fit soy con esta oferta?”  
→ `jobbot jobs match J0003`

“CV para esa oferta”  
→ `jobbot cv build --job J0003`

“Preparate el paquete; yo postulo”  
→ `jobbot application prepare J0003`  
→ `jobbot application apply J0003 --apply`

---

## 7. Marca visual

- **Mitad humana / mitad bot** = colaboración, no reemplazo.
- **Una sola sonrisa** = un solo objetivo: el próximo paso, con criterio.
- **Job** (navy) + **Bot** (azul) = oficio + automatización.
- Iconos de app: avatar de marca; el producto sigue siendo **CLI**, no una promesa de “app store de empleo”.
- Paleta: navy, azul vivo, blanco — cercanía y claridad, sin estética genérica de “AI startup”.

El dibujo cuenta HITL. El copy debe decirlo: evitar “automatiza postulaciones” y “recomendaciones inteligentes” sin anclarlas a hechos + confirmación humana.

---

## 8. Voz

- Directa, técnica, sin humo.
- Español (o bilingüe) cuando el público es LATAM; comandos siempre en el idioma del CLI.
- Critica el packaging viral; respeta el insight estructural.
- CTA fijo: **GitHub** (vídeos / demos en el README) — <https://github.com/ljofreflor/jobbot>
- En LinkedIn: menos de ~3000 caracteres; natural → comando en líneas con `→`; sin tablas Markdown.

---

## 9. Cierre

JobBot no te busca el trabajo por vos.  
Te deja **buscar mientras construís** — con mapa (dónde publican), hechos (quién sos) y control (quién envía).

**Personas · Oportunidades · Tecnología**  
Más oportunidades. Un mejor mañana.  
**Sin salir de la terminal.**
