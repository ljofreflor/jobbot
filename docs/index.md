---
template: home.html
title: Jobbot — búsqueda mientras programas
description: >-
  CLI local para buscar trabajo sin salir del editor: encuentra dónde publican,
  prepara sin inventar, postula con el control en tus manos. Humano + bot, en tu máquina.
hide:
  - navigation
  - toc
---

<section class="jb-section" markdown="1">

## Personas · oportunidades · tecnología

Herramienta de oficio: **búsqueda mientras programas**. Sin inventar un producto
que no existe. [Manifiesto completo](manifesto.md).

<ul class="jb-benefits">
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    </div>
    <strong>Encuentra donde publican</strong>
    <span>ATS, boards y sweeps — vacantes que encajan con tu perfil real, no con un CV inventado.</span>
  </li>
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M7 3h10v18H7z"/><path d="M10 8h4M10 12h4M10 16h2"/><path d="M9 21l1.5-1.5L13 21"/></svg>
    </div>
    <strong>Prepara sin inventar</strong>
    <span>Arma el paquete desde hechos que ya existen; el envío queda en tus manos.</span>
  </li>
  <li>
    <div class="jb-benefits__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24"><path d="M4 19V9M10 19V5M16 19v-7M20 19H3"/></svg>
    </div>
    <strong>Postula con el control en tus manos</strong>
    <span>Matching, shortlist y evidencia — HITL, sin telemetría ni cuenta.</span>
  </li>
</ul>

<p class="jb-pillars">Más oportunidades. Un mejor mañana. Sin salir de la terminal.</p>

</section>

<section class="jb-section" markdown="1">

## Dos bucles, una fuente de verdad

El canal puede ser la terminal o un agente (Cursor, VS Code, Claude Code…).
El producto es el CLI local. Dos bucles; un solo SoT: `data/profile.yaml`.

**1 · Postular a una vacante** — match → CV → plan; **tú envías**.

```bash
jobbot linkedin sweep "machine learning"
jobbot jobs match J0002
jobbot cv build --job J0002
jobbot application apply J0002        # plan; tú envías
```

**2 · Presencia permanente** — mejorar cómo se presenta lo que ya hiciste y
dejar el CV al día en portales activos (HITL; nunca inventa hechos).

```bash
jobbot cv advise --apply              # presentación; confirmas una por una
jobbot cv sync --apply                # permanentes + companies active
jobbot status                         # evidencia local de qué quedó al día
```

[Instalación y quickstart](instalacion.md) · [Todos los comandos](#comandos) ·
[Referencia con banderas](comandos.md) · [Manifiesto](manifesto.md)

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Privacidad en tu máquina

Tu perfil, sesiones y salidas se quedan en el disco. No hay cuenta Jobbot ni
telemetría: las fallas se guardan en tu SQLite local.

<ul class="jb-evidence">
  <li><code>data/profile.yaml</code>, SQLite, <code>browser-data/</code> y <code>output/</code> están gitignoreados</li>
  <li>Hook pre-commit (<code>make hooks</code>) bloquea PII aunque uses <code>git add -f</code></li>
  <li>Human-in-the-loop: prepara el paquete; <strong>tú envías</strong></li>
  <li>Sin bypass de CAPTCHA ni 2FA — si el portal desafía, te pasa el teclado</li>
</ul>

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Buscar cargos recientes

Indeed, Get on Board y posts de reclutadores en LinkedIn. Filtros de frescura,
país por rol y posts con varias vacantes en uno.

```bash
jobbot jobs search "Senior Data Scientist" --location Santiago
jobbot getonboard search "data scientist"
jobbot linkedin sweep "machine learning" --country CL --max-age-days 30
```

Un post con cinco roles SoftServe → cinco vacantes independientes, cada una con
su país y su URL de ATS. Match y postulación por rol, no por post.

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Una sola fuente de verdad

<code>data/profile.yaml</code> es el SoT profesional. LaTeX, PDF, Indeed y LinkedIn
son vistas o adapters. El CV adaptado reordena evidencia; no inventa experiencia.

```bash
jobbot profile validate
jobbot cv build --job J0002          # derivado del perfil + JD
jobbot profile suggest-from-market   # sugerencias; confirmas gaps
```

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Sincronizar a los portales

Adapters de Indeed, LinkedIn y Get on Board: login, inspect, pull, diff y sync
(dry-run por defecto). La presencia permanente es `cv sync` (HITL por destino).

```bash
jobbot indeed sync --section headline   # plan; --apply escribe
jobbot linkedin sync --section publications --apply
jobbot cv sync --apply                  # presencia; confirmas por destino
```

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Open source, en tu máquina

CLI local. Sin backend SaaS de Jobbot. El canal es Cursor, VS Code, Claude Code
u otro agente — no un chat propietario. Corres el binario; decides qué sale
de tu disco.

```bash
curl -fsSL https://raw.githubusercontent.com/ljofreflor/jobbot/main/scripts/install.sh | bash
mkdir -p ~/postulaciones && cd ~/postulaciones && jobbot init
jobbot version
# más adelante: jobbot update
```

¿Contribuyes al código? Ahí sí: `git clone` + `uv sync --group dev` (ver [instalación](instalacion.md)).

</section>

<section class="jb-section jb-section--usecase" markdown="1">

## Match, ATS y Latam

Scores contra tu perfil, detección de ATS (Greenhouse, Lever, Workday, Teamtailor
incluso en hosts propios, Get on Board…), registro de portales que aprende con
evidencia, y foco en Chile / Latam en búsquedas y roundups.

<ul class="jb-evidence">
  <li><code>jobs match</code> / <code>shortlist</code> — puntúa; no decide por ti</li>
  <li><code>portals detect</code> + <code>companies learn</code> — topología pública, sin PII</li>
  <li><code>application apply --apply</code> — abre el formulario; el envío es tuyo</li>
  <li>Roundups Latam: país por rol (<code>--country CL</code>), no por post entero</li>
</ul>

</section>

<section class="jb-section jb-section--cmds" markdown="1">

## Los comandos {#comandos}

Cada comando público de `src/jobbot/cli.py`, en una línea. Las banderas están en la
[referencia](comandos.md). `jobbot <comando> --help` imprime el resto. Nada de esta
lista postula solo ni inventa un hecho. Los que llevan **postular** (cobalto) o **presencia** (navy) son los siete pasos de arriba; la marca vuelve a ese paso del bucle. En la barra, **CV**, **Vacantes** y **Postulaciones** van subrayados: ahí viven esos siete. Los demás grupos (y sus tablas) se atenúan; el que estás leyendo vuelve a pleno. Con el pin en Presencia, Vacantes y Postulaciones también se atenúan, salvo el grupo que lees. Las filas del relato del otro bucle se atenúan; hover, foco o un salto `#cmd-*` las recuperan (en Presencia, también su grupo en la barra).

<nav class="jb-cmdnav" aria-label="Grupos de comandos. Tab cae en el grupo actual; las flechas mueven entre grupos" aria-keyshortcuts="ArrowLeft ArrowRight Home End">
  <a href="#cmd-maquina" aria-controls="cmd-maquina">Máquina local</a>
  <a href="#cmd-perfil" aria-controls="cmd-perfil">Perfil</a>
  <a href="#cmd-cv" aria-controls="cmd-cv" class="jb-cmdnav__story" data-story-cmds="build advise sync" title="Pasos postular y presencia">CV</a>
  <a href="#cmd-vacantes" aria-controls="cmd-vacantes" class="jb-cmdnav__story is-pin-step" data-story-cmds="get match conditions" title="Pasos postular">Vacantes</a>
  <a href="#cmd-postulaciones" aria-controls="cmd-postulaciones" class="jb-cmdnav__story" data-story-cmds="apply" title="Pasos postular">Postulaciones</a>
  <a href="#cmd-portales" aria-controls="cmd-portales">Portales</a>
  <a href="#cmd-navegador" aria-controls="cmd-navegador">Navegador</a>
  <a href="#cmd-empresas" aria-controls="cmd-empresas">Empresas</a>
  <a href="#cmd-operacion" aria-controls="cmd-operacion">Operación</a>
</nav>

### Máquina local {#cmd-maquina}

| Comando | Qué hace |
|---------|----------|
| `jobbot init [DIR]` | Crea el workspace en esa carpeta: config, `AGENTS.md` y datos locales. |
| `jobbot update` | Reinstala el ejecutable desde GitHub. `--check` solo compara con `main`. `--schedule daily`, `off` o `status` agenda, quita o muestra la revisión diaria. |
| `jobbot version` | Muestra la versión instalada. |
| `jobbot status` | Evidencia local de CV y portales activos. Sin evidencia no dice que quedó al día. |
| `jobbot capture URL` | Deja un enlace compartido como candidato, sin descargar. `--list` muestra los pendientes. |
| `jobbot workspace list` | Lista sandboxes. También `new`, `show`, `adopt`, `delete`. |
| `jobbot workspace consent` | Anota consentimiento y fecha de borrado de un sandbox. |
| `jobbot advisor status` | Una línea por sandbox: huella, conteos, propuesta, retención. Sin el nombre. |
| `jobbot advisor report` | Escribe el resumen redactado del workspace elegido. |

### Perfil {#cmd-perfil}

| Comando | Qué hace |
|---------|----------|
| `jobbot profile validate` | Comprueba el YAML local. |
| `jobbot profile show` | Resumen del perfil. |
| `jobbot profile import-pdf RUTA` | Lee la capa de texto del PDF hacia un generado. Sin OCR. |
| `jobbot profile import-latex [RUTA]` | Importa un CV LaTeX legado al generado. |
| `jobbot profile promote-generated` | Copia el generado a `profile.yaml` después de que confirmas. |
| `jobbot profile suggest-from-market` | Propone redacción desde avisos guardados. No toca el perfil sin `--promote` y tu sí. |
| `jobbot profile queries` | Deriva búsquedas de tu experiencia. `--apply` las guarda si confirmas. |
| `jobbot profile status` | Consistencia entre lo local y los snapshots de portales. |
| `jobbot profile diff` | Muestra ese diff. |

### CV {#cmd-cv}

| Comando | Qué hace |
|---------|----------|
| <span id="cmd-build" class="jb-in-story"><code>jobbot cv build</code> <a class="jb-in-story__tag" href="#story-build" aria-controls="story-build" aria-label="Paso 3, postular, build">postular</a></span> | Arma el CV desde el perfil. `--job` lo ordena para un aviso; `--full` no descarta roles. `--target cv` o `ats`. |
| <span id="cmd-advise" class="jb-in-story"><code>jobbot cv advise</code> <a class="jb-in-story__tag jb-in-story__tag--presence" href="#story-advise" aria-controls="story-advise" aria-label="Paso 6, presencia, advise">presencia</a></span> | Pocas mejoras de presentación. `--apply` confirma una por una. |
| `jobbot cv tune-for Jxxxx` | El mismo advise, acotado a un aviso o a un enlace. |
| `jobbot cv propagate` | Plan de perfiles permanentes. `--apply` confirma destino por destino. |
| <span id="cmd-sync" class="jb-in-story"><code>jobbot cv sync</code> <a class="jb-in-story__tag jb-in-story__tag--presence" href="#story-sync" aria-controls="story-sync" aria-label="Paso 7, presencia, sync">presencia</a></span> | Presencia: permanentes y empresas activas. `--apply` espera tu confirmación. |
| `jobbot cv status` | Alias de `jobbot status`. |

### Vacantes {#cmd-vacantes .is-pin-step}

| Comando | Qué hace |
|---------|----------|
| <span id="cmd-get" class="jb-in-story"><code>jobbot get URL</code> <a class="jb-in-story__tag" href="#story-get" aria-controls="story-get" aria-current="step" aria-label="Paso 1, postular, get">postular</a></span> | Descarga un aviso puntual (Get on Board, Indeed, Workday), arma CV y paquete. No envía. |
| `jobbot jobs add` | Guarda una vacante desde un archivo o stdin. |
| `jobbot jobs search CONSULTA` | Busca en Indeed y guarda en local. |
| `jobbot jobs discover` | Descubre por API pública: `--source workday` o `--source un-careers`. `--dry-run` no escribe. |
| `jobbot jobs queries` | Imprime búsquedas web para hosts ATS. No busca. |
| `jobbot jobs show Jxxxx` | Muestra un aviso guardado, con su cierre si lo publica. |
| <span id="cmd-match" class="jb-in-story"><code>jobbot jobs match Jxxxx</code> <a class="jb-in-story__tag" href="#story-match" aria-controls="story-match" aria-label="Paso 2, postular, match">postular</a></span> | Puntúa contra el perfil. Ayuda a decidir; no decide. |
| <span id="cmd-conditions" class="jb-in-story"><code>jobbot jobs conditions Jxxxx</code> <a class="jb-in-story__tag" href="#story-conditions" aria-controls="story-conditions" aria-label="Paso 4, postular, conditions">postular</a></span> | Condiciones del aviso: cumple, pregunta o impedimento. Offline. |
| `jobbot jobs check-open` | Vuelve a mirar si el aviso sigue abierto. Solo lectura del estado. |
| `jobbot jobs shortlist` | Ordena por score y marca vencidos o por cerrar. |
| `jobbot jobs backfill-dates` | Fecha avisos ya guardados con el id de la URL. Offline. |
| `jobbot jobs note Jxxxx TEXTO` | Adjunta una nota libre. |
| `jobbot jobs audit --source indeed` | Lista señuelos y duplicados de Indeed. `--apply` los marca; no borra postulaciones enviadas. |

### Postulaciones {#cmd-postulaciones}

| Comando | Qué hace |
|---------|----------|
| `jobbot application prepare Jxxxx` | Arma el paquete. No inventa respuestas. |
| `jobbot application show Jxxxx` | Ruta y estado del paquete. |
| `jobbot application open Jxxxx` | Abre la URL del aviso o del ATS. No postula. |
| <span id="cmd-apply" class="jb-in-story"><code>jobbot application apply Jxxxx</code> <a class="jb-in-story__tag" href="#story-apply" aria-controls="story-apply" aria-label="Paso 5, postular, apply">postular</a></span> | Plan de prellenado. `--apply` abre; el envío es tuyo. `--all` recorre la cola, con pausa entre avisos. |
| `jobbot application check-answer Jxxxx` | Revisa una respuesta libre contra perfil y aviso. La motivación queda para ti. |
| `jobbot applications list` | Lista las postulaciones registradas. Alias: `applications status`. |

### Portales permanentes {#cmd-portales}

| Comando | Qué hace |
|---------|----------|
| `jobbot indeed login` | Abre Indeed para que entres. También `status`, `inspect`, `prepare`, `pull`, `diff`, `sync`. El sync escribe solo con `--apply`. |
| `jobbot linkedin login` | Igual para LinkedIn: `status`, `inspect`, `pull`, `diff`, `sync`. |
| `jobbot linkedin sync --section publications` | Escribe Publicaciones, con confirmación por ítem si pasas `--apply`. |
| `jobbot linkedin sweep [CONSULTA]` | Lee posts de reclutadores y guarda vacantes. Sin consulta usa las del perfil. |
| `jobbot getonboard prepare` | Refina el borrador del perfil permanente desde tus hechos. |
| `jobbot getonboard show-profile` | Muestra el borrador local. |
| `jobbot getonboard open-profile` | Abre el editor en el navegador. No guarda solo. |
| `jobbot getonboard open-cvs` | Abre la página de CVs. |
| `jobbot getonboard upload-cv` | Valida el PDF. `--apply` lo sube; tú confirmas. |
| `jobbot getonboard sync` | Propaga el perfil. Dry-run salvo `--apply`. |
| `jobbot getonboard search [CONSULTA]` | Busca en el board. Sin consulta usa las del perfil. |
| `jobbot torre search [CONSULTA]` | Búsqueda pública de Torre. El aviso completo se abre aparte. |
| `jobbot empleospublicos search [CONSULTA]` | Concursos abiertos del Servicio Civil (datos abiertos). `--dry-run` no escribe. |

### Navegador {#cmd-navegador}

| Comando | Qué hace |
|---------|----------|
| `jobbot browser chrome-debug` | Abre Chrome con depuración para que resuelvas CAPTCHA o 2FA. No los resuelve. |
| `jobbot browser sessions` | Informa el estado de sesión con evidencia. No se adjunta solo. |
| `jobbot browser login` | Lista portales sin sesión probada. `--apply` abre el siguiente; tú entras. |

### Empresas, formularios y prácticas {#cmd-empresas}

| Comando | Qué hace |
|---------|----------|
| `jobbot portals list` | Lista portales conocidos. |
| `jobbot portals detect URL` | Detecta el tipo de ATS. |
| `jobbot portals add` | Agrega o actualiza un portal. |
| `jobbot portals form-learn URL` | Lee qué pregunta un formulario. No guarda lo que escribes ni envía. |
| `jobbot portals profile status` | Cobertura de portales seguidos. No abre nada. |
| `jobbot portals profile sheet PORTAL` | Hoja de llenado desde el perfil. No abre el navegador. |
| `jobbot portals profile mark-updated` | Anota evidencia local de que una sección quedó actualizada. |
| `jobbot portals profile import` | Siembra estado desde un CSV. Sin `--apply` no escribe. |
| `jobbot portals profile seed` | Registra portales de carrera conocidos que faltan. Dry-run salvo `--apply`. |
| `jobbot portals profile push PORTAL` | Se niega a tipear en el portal. El llenado es la hoja. |
| `jobbot companies detect URL` | Clasifica una URL. No escribe. |
| `jobbot companies learn URL` | Registra empresa y portal como candidato. |
| `jobbot companies list` | Lista empresas y sus sitios de carrera. |
| `jobbot companies show NOMBRE` | Una empresa, sus portales y contradicciones. |
| `jobbot companies recon NOMBRE` | Aprende ATS y preguntas desde HTML. `--apply` guarda la observación. |
| `jobbot companies signup NOMBRE` | Abre el alta y lista qué pide el perfil. `--apply` rellena campos conocidos; crear la cuenta es tuyo. |
| `jobbot companies promote NOMBRE` | Pasa un candidato a activo. Es la única forma de volverlo verdad. |
| `jobbot companies reject NOMBRE` | Marca un portal descubierto como incorrecto. |
| `jobbot companies discover SEMILLAS` | One-shot: candidatos en `output/`. No toca el registro. |
| `jobbot companies import ARCHIVO` | Fusiona esos candidatos. Siguen siendo candidatos. |
| `jobbot companies export` | Snapshot compartible: solo activos, sin PII. |
| `jobbot companies sites` | Portales reutilizables para descubrir vacantes. |
| `jobbot recruiters discover URL` | Guarda prácticas públicas de reclutamiento, no personas. |
| `jobbot recruiters list` | Lista prácticas. También `show`, `promote`, `reject`, `export`. |

### Operación y secretos {#cmd-operacion}

| Comando | Qué hace |
|---------|----------|
| `jobbot ops failures` | Lista fallas locales, agrupadas. |
| `jobbot ops failure show Fxxxx` | Muestra una falla. `triage` cambia su estado. |
| `jobbot ops failure issue Fxxxx` | Abre un issue de GitHub si confirmas. No lo hace al fallar. |
| `jobbot ops failure work Fxxxx` | Imprime el carril issue, rama y PR. `--apply` abre el issue y la rama; no hace commit ni push. |
| `jobbot ops symptom note` | Anota un síntoma local, redactado al guardar. También `list`, `show`, `plan`, `triage`, `issue`. |
| `jobbot ops loop` | Repite un paso de mantención. Si falla, guarda `Fxxxx` y sigue. |
| `jobbot ops capabilities` | Índice de lo que el código ya sabe hacer. `--write` regenera el doc. |
| `jobbot secrets init` | Crea la bóveda local vacía, modo 0600. No inventa entradas. |
| `jobbot secrets list` | Lista sitios. Nunca imprime el valor. |
| `jobbot secrets set SITIO` | Pide la contraseña sin dejarla en el comando. |
| `jobbot secrets delete SITIO` | Borra esa entrada. |
| `jobbot secrets allow-fill` | Consentimiento para un llenado futuro. CAPTCHA, 2FA y enviar siguen tuyos. |
| `jobbot secrets deny-fill` | Apaga ese consentimiento. |

</section>

<section class="jb-section" markdown="1">

## Lo que Jobbot no hace

Reglas del producto, no del marketing.

<ul class="jb-principles">
  <li><strong>No postula por ti</strong> Human-in-the-loop: prepara el paquete y abre el formulario. Enviar es tuyo.</li>
  <li><strong>No inventa datos sobre ti</strong> <code>data/profile.yaml</code> es la única fuente de verdad. Advise, tune y sync reordenan o preguntan; no fabrican experiencia.</li>
  <li><strong>No sincroniza portales en silencio</strong> <code>cv sync --apply</code> confirma destino por destino. Sin evidencia local, <code>status</code> no inventa que “quedó al día”.</li>
  <li><strong>No sale de tu disco</strong> Perfil, SQLite, sesiones de navegador y <code>output/</code> están gitignoreados, con un hook que bloquea commitearlos.</li>
  <li><strong>No evade CAPTCHAs</strong> Cuando un portal pide un desafío, te pasa el teclado.</li>
</ul>

</section>

<section class="jb-section jb-section--measure" markdown="1">

## Medido, no opinado

Antes de scrapear a ciegas: qué sitios de empleo responden desde una IP de datacenter y cuáles no.

[Leer la medición](blog/posts/2026-09-24-bloqueos-ip-datacenter.md){ .jb-btn .jb-btn--primary }
[English](blog/posts/2026-09-24-datacenter-ip-blocking.md){ .jb-btn .jb-btn--ghost }

</section>

<section class="jb-section jb-section--close" markdown="1">

## Empezar

Curl o Docker, carpeta `~/postulaciones`, `jobbot init`. El resto está en la guía.

```bash
curl -fsSL https://raw.githubusercontent.com/ljofreflor/jobbot/main/scripts/install.sh | bash
mkdir -p ~/postulaciones && cd ~/postulaciones && jobbot init
jobbot profile import-pdf ~/Descargas/CV.pdf --promote   # o edita .local/profile.yaml
# más adelante: jobbot update
#
# Docker: docker pull ghcr.io/ljofreflor/jobbot:latest
#         docker compose run --rm -v "$HOME/postulaciones:/work" -w /work jobbot init
```

[Instalación](instalacion.md){ .jb-btn .jb-btn--primary }
[Prior art](prior-art.md){ .jb-btn .jb-btn--ghost }

</section>
