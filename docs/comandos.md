---
title: Referencia de comandos
description: Todos los comandos del CLI de JobBot, verificados contra src/jobbot/cli.py.
---

# Referencia de comandos

Tras [instalar con curl](instalacion.md), corre `jobbot <grupo> <comando>`. En un
clon del repo, `uv run jobbot …`. Esta página lista lo que existe hoy en
`src/jobbot/cli.py`, incluidas las tablas de abajo que completan grupos que el
texto largo no repetía. Si un comando no aparece aquí, probablemente no existe.
La [portada](index.md#comandos) los describe en una línea. Para las opciones
completas, `jobbot <grupo> <comando> --help`.

## Workspace e instalación

| Comando | Qué hace |
|---------|----------|
| `init [DIR]` | Crea un workspace frío: `.jobbot.toml`, `AGENTS.md`, `.local/` y `.gitignore` **dentro de DIR** (default: el directorio actual). No usa `$HOME`, `JOBBOT_ROOT` ni el repo del paquete para ubicar `.local/`. `--force` sobrescribe semillas. |
| `update` | Reinstala el ejecutable en el `PATH` desde GitHub (`uv tool`). `JOBBOT_REF` / `--ref` eligen rama, tag o SHA. En Docker: actualiza la imagen en el host. |
| `update --check` | Compara el commit instalado con el último de `main` (`git ls-remote`) sin instalar. Sale con `0` si estás al día, `10` si hay un commit nuevo y `1` si no pudo saberlo. |
| `update --schedule daily\|off\|status` | Agenda (o quita o muestra) un `jobbot update` diario: LaunchAgent en macOS y crontab en Linux. Si ya estás al día no reinstala; respeta `JOBBOT_AUTO_UPDATE=0` / `[update] auto = false`; no hace nada en Docker. Detalle en [Instalación](instalacion.md#actualizacion-diaria-automatica). |
| `version` | Muestra la versión de JobBot. |

```bash
mkdir -p ~/postulaciones && cd ~/postulaciones
jobbot init
# equivalente sin cd:
# jobbot init ~/postulaciones
jobbot update
JOBBOT_REF=v0.1.0 jobbot update
jobbot update --check                # exit 10 si hay un commit nuevo en main
jobbot update --schedule daily       # actualización diaria (launchd / crontab)
jobbot update --schedule status
```

## Perfil

| Comando | Qué hace |
|---------|----------|
| `profile validate` | Valida el perfil y `application_answers.yaml`. Una clave desconocida (por ejemplo `rut:`) sale con 2 y la nombra. Un título de grado que el perfil no respalda, o un grado `completed` sin `end_date`, avisa y sale 0. Si `salary_expectation` se lee sin ambigüedad, sugiere la migración y no escribe. |
| `profile answers show [--reveal]` | Muestra qué bloques de respuestas tienen datos. Sin `--reveal` no imprime valores. |
| `profile answers set CLAVE VALOR [--yes]` | Escribe una clave (por ejemplo `salary.amount`). Sin `--yes` no escribe. Se niega a guardar un RUN. |
| `profile show` | Resumen del perfil local, incluidos los grados abandonados que el CV omite. |
| `profile skills-map` | Asocia cada aptitud declarada al cargo o grado que ya la muestra. `--unbacked` lista las que no tienen evidencia. `--apply` escribe el vínculo tras confirmar y deja un respaldo. |
| `profile import-pdf RUTA` | Importa un CV PDF (capa de texto) a `profile.generated.yaml`. `--promote` lo copia a `profile.yaml` tras validar. |
| `profile import-latex [RUTA]` | Importa un CV LaTeX legado a `profile.generated.yaml`. |
| `profile promote-generated` | Copia `profile.generated.yaml` → `profile.yaml` tras confirmación. |
| `profile suggest-from-market` | Sugiere redacción base desde las JDs guardadas; pregunta antes de agregar skills. |
| `profile queries` | Deriva búsquedas desde la experiencia del perfil. `--apply` las guarda como `search_queries` (con confirmación). `--check` mide cada consulta contra fuentes de texto (getonboard, indeed, torre) sin guardar avisos ni tocar el perfil. |
| `profile status` | Consistencia entre lo local y los snapshots de portales. |
| `profile diff` | Diff del perfil local contra los snapshots de portales. |

## CV

| Comando | Qué hace |
|---------|----------|
| `cv build` | Construye el CV desde `profile.yaml`. `--target cv\|ats`, `--job Jxxxx`, `--style moderncv\|plain`. Con `--job`, `--full` conserva todos los roles y logros. Sin términos extraídos, elige por el eco del aviso y avisa para revisar `selection.json`. Un término del aviso que el perfil no tiene queda como brecha y no se escribe en el CV. `--strict` sale 2 si la capa de texto tiene un ícono, una viñeta rara o un término metido. |
| `cv propagate` | Reconstruye el CV base y lo propaga a los perfiles permanentes (HITL, dry-run por defecto). |

```bash
jobbot cv build --target ats
jobbot cv build --job J0001
jobbot cv build --job J0001 --full  # CV largo: nada se descarta
jobbot cv propagate                 # solo plan
jobbot cv propagate --apply         # confirma destino por destino
```

Una experiencia puede separar `unit` del empleador y anotar `work_mode` (`remote`, `onsite`, `hybrid`). Sin esos campos el CV sale igual que antes.

## Vacantes

| Comando | Qué hace |
|---------|----------|
| `get URL` | Aviso puntual: conoce el portal, descarga el aviso, arma CV y paquete. Descarga en vivo Get on Board, Indeed, Workday (vía CXS) y Ready ATS (`ready-ats-*.web.app`, JSON). `--fixture` lee HTML guardado o, en Ready, el JSON de careers. |
| `jobs add` | Agrega una vacante desde un archivo de texto o stdin (`--file`). Una URL de Workday sola (`--url`, sin `--file`) se descarga vía CXS. Una URL de PDF lee la capa de texto (sin OCR) y guarda el cierre en hora de Santiago. |
| `jobs search QUERY` | Busca en Indeed y guarda las vacantes. `--location`, `--limit`, `--remote`, `--cdp`. Si `--cdp` no engancha dentro de `--cdp-timeout` (15 s), sale con error y no dice "No jobs found". |
| `jobs discover --source workday --site URL` | Descubre avisos en career sites por API pública. `--query`, `--limit` (1–200), `--dry-run` (no escribe nada: ni DB, ni JSON, ni `companies.yaml`). Sin `--site`, usa los sitios Workday del registro de empresas. |
| `jobs discover --source un-careers` | Lee el feed RSS público de UN Careers (Secretaría de la ONU) y filtra en local. `--query`, `--location` (`remote` incluye «home-based»), `--level CON,P-3`, `--limit`, `--details`, `--dry-run`. No necesita `--site`. |
| `jobs discover --source buk --site URL` | Pide solo `robots.txt`. Si prohíbe `/`, no recorre el portal y sugiere `jobs add --file`. |
| `jobs discover --source pdf-index --url PAGINA --dry-run` | Lista los PDF del mismo host cuyo nombre contiene `--match` (por defecto `concurso`). No descarga los PDF y no escribe. |
| `jobs discover --source lumesse --site HOST` | No llama a TalentLink. `robots.txt` prohíbe `/fo/rest` para jobbot (revisado 2026-10-08); sale 2 y sugiere `jobs add --file`. |
| `jobs discover --source cornerstone --site TENANT` | No pide el token de invitado. `discovery: blocked (requires session token)`; sale 2 y sugiere `jobs add --file`. |
| `jobs discover --source unops` | Alias de Avature en `careers.unops.org/careersmarketplace`. Pagina `SearchJobs` y no pide URLs con `qtvc`. `--dry-run` no escribe. |
| `jobs discover --source impactpool` | No lee el tablero. Los términos prohíben copiar sin permiso (revisado 2026-10-08); sale 2 y sugiere `jobs add --file`. |
| `jobs discover --source unicef` | Alias de PageUp en `jobs.unicef.org`. Lee el listado público, pagina con `a.more-link` y no pide rutas que `robots.txt` prohíbe. `--dry-run` no escribe. Un listado con reCAPTCHA sale 4. |
| `jobs discover --source pjud` | Lee los concursos en postulación del Poder Judicial (una página, sin login). Sin `--query` trae todos; `--query` filtra por cargo y tribunal. `--dry-run` no escribe. Una grilla de otra forma sale 5. |
| `jobs discover --source smartrecruiters --company ID` | Lee la Posting API pública. Sin `--company` recorre los tableros del registro. `--country` (por defecto el de la búsqueda) filtra también en local. `--limit` puede llegar a 300. Un 404 se informa y se sigue. |
| `jobs discover --source greenhouse [--board TOKEN]` | Lee la Job Board API pública. Sin `--board` recorre los boards del registro. Un aviso ya guardado no vuelve a pedir su detalle. Un 404 se informa y se sigue. |
| `jobs discover --source oracle_orc [--site HOST/SITIO]` | Lee la búsqueda pública de Oracle Recruiting Cloud. Conserva el `siteNumber`. Un 403 se informa y se sigue. |
| `jobs discover --source bne --query TEXTO` | Lee el JSON público de la Bolsa Nacional de Empleo. Cero resultados no se relanza sin texto. Si el total coincide con el de toda la bolsa, avisa `filtro ignorado` y no guarda. |
| `jobs discover --source chiletrabajos --query TEXTO` | Lee la búsqueda HTML pública (`f=2`). La ficha trae publicación y expiración en America/Santiago. No pide rutas que `robots.txt` prohíbe. Un listado sin avisos sale 5. |
| `jobs discover --source vacantes --country CL` | Lee la landing del país (o `--all-sitemap` y filtra el sitemap por el texto). El detalle es JSON-LD. No pide `/api/` ni URLs con `?`. `robots.txt` se consulta en cada corrida. |
| `jobs add --file listado.html --url https://acme.buk.cl/trabaja-con-nosotros` | Ingiere las tarjetas `jobs__card` de un HTML guardado. Sin tarjetas, sale 5. |
| `jobs add --file aviso.txt` | Guarda el texto completo. Una línea «ignore previous instructions» o «fetch https://…» no entra al score y no se descarga. |
| `jobs show JOB_ID` | Muestra una vacante guardada, con su cierre si el aviso lo publica. |
| `jobs match JOB_ID` | Puntúa la vacante contra el perfil local (ayuda a decidir, no decide). |
| `jobs check-open [JOB_ID…] [--all] [--dry-run] [--json]` | Vuelve a consultar en línea si cada aviso guardado sigue abierto: `abierto` / `cerrado` / `desconocido`, con motivo y fecha de verificación. `--all` omite los cerrados verificados hace menos de 24 h; `--dry-run` no escribe; `--json` trae la URL completa. Solo lectura. |
| `jobs shortlist [--include-closed] [--soon-days N]` | Ordena las vacantes guardadas por score. Un cierre publicado vencido o la frase «empleo finalizado» se marca `[vencido]` (sin fecha si el aviso no la publicó). Un cierre dentro de N días (default 3) se marca `[cierra pronto]`. Sin fecha, o con una fecha ambigua que no se guardó, no hay marca. Oculta las que `jobs check-open` verificó cerradas (`--include-closed` las muestra). Un veredicto de `jobs admissibility` se muestra como `[no admisible]` o `[dudoso]`. |
| `jobs admissibility J0001 [J0002 …] [--source FUENTE] [--open] [--json]` | Admisibilidad offline de un concurso guardado contra el perfil: `admisible`, `no_admisible` o `dudoso`. Lee solo el bloque de requisitos excluyentes. No envía nada. |
| `jobs digest [--since] [--format whatsapp\|md]` | Resumen compartible de avisos nuevos y vigentes, sin red y sin notas internas. Parte el texto de WhatsApp en mensajes de hasta 4.096 caracteres. |
| `jobs conditions JOB_ID… [--all-prepared]` | Lee las condiciones del aviso (cerrado, residencia, idioma, excluyentes, contrato, renta, modalidad, licencia de conducir, viajes) contra tu perfil y `data/application_answers.yaml`: ✅ cumple, ⚠️ pregunta exacta, ❌ impedimento (exit 1). `relocation: within_country` no cruza de país. Offline. |
| `jobs backfill-dates` | Data vacantes ya guardadas usando el activity id de la URL (offline). |
| `jobs note JOB_ID TEXTO` | Adjunta una nota libre a una vacante. |

```bash
# vista previa: tabla con título, ubicación, cierre y decisión; no escribe nada
jobbot jobs discover --source workday \
  --site https://paho.wd5.myworkdayjobs.com/en-US/pahocareers --query health --dry-run
# guarda (deduplica por ID externo: volver a correrlo actualiza, no duplica)
jobbot jobs discover --source workday \
  --site https://paho.wd5.myworkdayjobs.com/en-US/pahocareers --query health
jobbot get https://paho.wd5.myworkdayjobs.com/en-US/pahocareers/job/Off-Site/Titulo_Req-00000
```

`jobs discover` lee la API pública CXS de cada tenant Workday (la misma que usa su
página): respeta `robots.txt`, se identifica con un User-Agent honesto, pausa 1 s
entre pedidos y no inicia sesión. El cierre sale de la línea «Closing Date» del
aviso. La hora queda solo si el aviso nombra una zona sin ambigüedad («Eastern
Time»); si no, se guarda solo la fecha, marcada «hora no publicada». El `endDate`
de Workday (cuándo el aviso deja el sitio) es el último recurso y se rotula así.
Los avisos vencidos o que ya no admiten postulación no se guardan. Exit: 0 si
algún sitio respondió; 5 si el único sitio pedido cambió la forma de su JSON; 1 si
todo falló.

```bash
jobbot jobs check-open --all --dry-run   # verifica y muestra; no toca la base
jobbot jobs check-open J0001 J0002       # guarda estado, motivo y fecha de verificación
jobbot jobs shortlist                    # ya sin los cerrados; «cierra pronto» si quedan ≤ 3 días
```

`jobs check-open` nunca inventa vigencia: sin una señal de la fuente, el aviso
queda `desconocido`. Respeta `robots.txt`, se identifica, pausa 1 s por host y
corta a los 10 s. Señales:

| Fuente | `abierto` | `cerrado` | `desconocido` |
|--------|-----------|-----------|---------------|
| Workday (API CXS) | `canApply: true` y cierre publicado no vencido | 404, 403 `S22`, `canApply: false`, `posted: false`, o cierre publicado vencido (fecha sin hora: se espera al fin de ese día en cualquier zona) | 406 persistente (tras reintentar con otro `Accept`), 403 sin `S22`, error de red, `robots.txt` lo prohíbe |
| Trabajando (`GET /api/ofertas/{id}`) | `estadoOferta: PUBLICADA` y `fechaExpiracionFormatoIngles` no vencida | otro `estadoOferta` (p. ej. `DESACTIVADA`), expiración vencida, 404/410 | 5xx (un id inexistente responde 500), JSON sin esos campos, red |
| Chiletrabajos (página del aviso) | fila «Expira» con fecha no vencida | «Este anuncio ha expirado o ha sido desactivado…», fila «Expira» vencida, 404/410 | lo mismo que cualquier otra página |
| Cualquier otra página (HTTP) | — (una página sin frase de cierre no prueba que siga abierta) | 404/410, frase de cierre visible («ya no acepta postulaciones», «Oferta finalizada», «This job is no longer available», «Este empleo caducó en Indeed»…) o «Closing Date» publicada y vencida | 401/403/429/5xx, sin conexión, `robots.txt` lo prohíbe, HTTP 200 sin señal |
| LinkedIn, PDF, `mailto:` | — | — | siempre, sin hacer pedidos (LinkedIn exige sesión) |

Si la fuente queda en `desconocido` pero el cierre guardado ya pasó, el aviso
queda `cerrado` con ese motivo. Las URLs con tildes o eñes se envían codificadas
(host IDNA, path y query con percent-encoding), también al leer `robots.txt`; un
error al verificar un aviso lo deja `desconocido` con el error como motivo y
`--all` sigue con el resto. En `--json`, el motivo va en `reason`.
Empleos Públicos responde 403 a pedidos automatizados (incluso a su `robots.txt`),
así que queda `desconocido`. Exit: 0 con cualquier mezcla de estados; 2 sin
`JOB_ID` ni `--all` o con un ID inexistente; 1 si la base no se puede leer o escribir.

```bash
# UN Careers: un solo pedido trae todo el feed; la búsqueda y los filtros son locales
jobbot jobs discover --source un-careers --query "public health" --dry-run
jobbot jobs discover --source un-careers --query "" --location Santiago --level P-3,NO-B --dry-run
jobbot jobs discover --source un-careers --query "health" --location remote --details
```

`--source un-careers` lee `https://careers.un.org/jobfeed` (RSS 2.0, todos los avisos
vigentes en una respuesta, sin login). Una búsqueda coincide si todas sus palabras
(sin tildes ni mayúsculas) están en el título, la familia, la red o la oficina; con
`--query ""` entra todo el feed. Guarda título, organismo (primer tramo de
«Department/Office»; el valor completo queda en la descripción), lugar de destino,
nivel (`CON`, `P-3`, `NO-B`, `I-1`…; `CON` es consultoría, `I-` pasantía) y el cierre
en hora de Nueva York con su zona. Solo «home-based» marca remoto: «Remote Sensing»
en un título no es modalidad. `--details` (apagado por defecto) pide el texto de cada
aviso filtrado a la API pública del portal, una vez por aviso y a 1 pedido/s; cada
lectura suma una visita al aviso. Si el `endDate` del detalle difiere del feed, gana
el detalle y queda anotado. Postular es en Inspira, con cuenta: JobBot no entra.
`robots.txt` hoy devuelve la página de la app (sin reglas); si algún día publica un
`Disallow` para el feed, la fuente se niega antes de pedirlo.

ReliefWeb ([#247](https://github.com/ljofreflor/jobbot/issues/247)) no es una fuente
todavía: su API v2 exige un `appname` aprobado por ReliefWeb (sin él responde 400; con
uno no aprobado, 403) y su sitio y RSS responden con un desafío anti-bot. Queda a la
espera de ese `appname`.

## Postulaciones

| Comando | Qué hace |
|---------|----------|
| `application prepare JOB_ID` | Arma el paquete de postulación (no inventa respuestas). |
| `application show JOB_ID` | Ruta y estado del paquete. |
| `application open JOB_ID` | Abre la URL de la vacante o del ATS en el navegador (no postula). |
| `application apply JOB_ID` | Plan de prellenado. Indeed que sale a otro portal no usa Indeed Apply. Con `--cdp` la sesión se consulta en ese host (`[::1]` sigue siendo `[::1]`); un adjunto que no vuelve no abre otro navegador. Sin `--cdp` un perfil ajeno no se lee y se abre el navegador por defecto. `--apply` abre; el envío lo haces tú. |
| `application check-answer JOB_ID -q PREGUNTA --text/--file` | Revisa una respuesta libre contra el perfil y el aviso. Sale 0 si todo está respaldado y 2 si una afirmación no lo está. Una carta o una pregunta de motivación sale 4: si las afirmaciones están respaldadas lo dice, y la motivación la confirma la persona. |
| `jobs describe JOB_ID --file aviso.txt` | Reemplaza la descripción de un aviso ya guardado. Conserva el id, la URL, la nota y la postulación. |
| `applications list` | Lista las postulaciones registradas (alias: `applications status`). |

## Portales

### Indeed

`indeed login`, `indeed status`, `indeed inspect`, `indeed prepare`, `indeed pull`,
`indeed diff`, `indeed sync` (dry-run por defecto; `--section preferences` planifica
cargos y sueldo; `--apply` escribe), `indeed upload-cv` (no sube si el hash ya está
en el recibo; niega un PDF de glyphs de íconos).

### LinkedIn

`linkedin login`, `linkedin status` (`valid`, `not authenticated` o `unreachable`), `linkedin inspect`, `linkedin pull`,
`linkedin diff`, `linkedin sync` (Publications, con DOI y coautores),
`linkedin sweep [QUERY]` (barrido de posts de reclutadores → vacantes + detección de ATS;
descarta "19 de ago." fuera de `--max-age-days` y un texto que nombra Madrid cuando el país es CL).
Sin `QUERY`, corre las `search_queries` del perfil (o las deriva). `--max-queries N` limita cuántas.
`linkedin jobs [QUERY] --fixture PATH` guarda avisos de una búsqueda (dedupe por `/jobs/view/<id>/`,
sin el panel "% de candidatos"). `--dry-run` no escribe. Sin `--fixture` ni `--cdp` no abre navegador.

### Get on Board

`getonboard prepare`, `getonboard show-profile`, `getonboard open-profile`,
`getonboard open-cvs`, `getonboard sync`, `getonboard search [QUERY]`.
`getonboard sync --section skills,seniority,english` proyecta como máximo 10 skills
(avisa el recorte; sin nivel queda `needs_human`), seniority e inglés, sin inventar.
`getonboard upload-cv --apply` compara el perfil antes y después: si no cambió, el
recibo dice «sin sobrescritura»; si un campo pasó a inglés, imprime el diff y ofrece restaurar.
Sin `QUERY`, usa las búsquedas del perfil; `--max-queries N` limita cuántas.

### Torre

`torre search [QUERY]` — mismas reglas de query / `--max-queries` que Get on Board.

### Sector público (Chile)

`empleospublicos search [QUERY] [--region R] [--dry-run]` — concursos **abiertos** (cierre
futuro en hora de Chile, no desiertos ni sin efecto) desde los
[datos abiertos del Servicio Civil](https://reporte.serviciocivil.cl/datos/convocatorias-empleos-publicos/).
Guarda cada aviso con fecha límite, renta bruta y grado (si el cargo lo nombra) en el texto, así
`jobs conditions` las lee offline. La renta `1` o `0` del archivo significa «no informada» y se
escribe así, nunca como $1. `--dry-run` muestra la tabla sin escribir la base, los JSON,
`portals.yaml` ni `companies.yaml`; `--location` es alias de `--region`. Una descarga por corrida
(~11 MB); `--fixture` reproduce un CSV guardado o un volcado JSON. Si el archivo lleva dos días o
más sin actualizarse (`Fecha_Actualizacion`), el comando lo avisa: los concursos publicados
después no están. El portal `empleospublicos.cl` responde 403 a cualquier cliente que se
identifica y JobBot no se disfraza de navegador: la ficha se abre a mano y entra con
`jobbot get URL --fixture ficha.html`.

Alta Dirección Pública (`adp.serviciocivil.cl`) se reconoce como bolsa, pero su `robots.txt`
prohíbe todo agente (`Disallow: /`): JobBot no la lee. Todavía no hay parser de la ficha ADP
(#228): copie el texto de la ficha y use `jobbot jobs add --file ficha.txt --url URL`.

### Navegador

`browser chrome-debug` abre un Chrome normal con CDP para que resuelvas a mano los
desafíos que aparezcan. No hay resolución automática de CAPTCHAs.

## Registro de ATS y empresas

| Comando | Qué hace |
|---------|----------|
| `portals list` | Lista los portales de reclutamiento conocidos. |
| `portals profile sheet chiletrabajos` | Hoja de llenado: cada campo tiene hogar en el SST o `needs_human`. No imprime correo, teléfono ni RUT. |
| `portals detect URL` | Detecta el tipo de ATS de una URL. |
| `portals add` | Agrega o actualiza un portal en el registro de portales. |
| `companies detect URL` | Clasifica una URL (aviso / portal / ATS / redirección). No escribe nada. |
| `companies learn URL` | Registra una relación empresa↔portal como conocimiento *candidate*. Una bolsa compartida (trabajando.cl, laborum, computrabajo, bumeran, chiletrabajos, empleos públicos) no se guarda; un subdominio de empresa en trabajando.cl sí, con ese ATS. |
| `companies list` | Lista empresas y sus plataformas de carreras. Un sitio cuyo host es una bolsa queda marcado «host de bolsa: revisar» y sugiere `companies reject`. |
| `companies show EMPRESA` | Una empresa con todos sus portales, observaciones y contradicciones. |
| `companies promote EMPRESA` | Candidate → active. Es la única forma de volverlo verdad. |
| `companies reject EMPRESA --site URL` | Marca un portal descubierto como incorrecto. |
| `companies discover SEEDS.yaml` | One-shot: siembra portales candidatos para una lista de empresas. |
| `companies import CANDIDATES.yaml` | Fusiona candidatos del one-shot al registro (siguen siendo candidate). |
| `companies export` | Snapshot compartible: solo entradas active, sin PII. |
| `companies sites` | Portales reutilizables por el descubrimiento de vacantes. |

`companies discover` sondea rutas y subdominios públicos de carreras de forma
secuencial y con pausa, y acepta un candidato solo con evidencia real: un marcador
de ATS, una redirección o texto de empleo en la página. Un HTTP 200 no es evidencia.
Escribe en `output/` y nunca toca el registro de empresas del workspace.

## Operación local

| Comando | Qué hace |
|---------|----------|
| `ops failures` | Lista fallas guardadas, agrupadas por fingerprint. |
| `ops failure` | Inspecciona y tría una falla puntual. |
| `ops loop` | Corre un paso de mantención en loop; persiste `Fxxxx` al fallar y sigue. |

No hay telemetría: las fallas se guardan en tu base local y se quedan ahí.

## Contraseñas (opt-in)

| Comando | Qué hace |
|---------|----------|
| `secrets init` | Crea `data/.vault.yaml` (o `.local/.vault.yaml`) con modo 0600. Vacío; no inventa. |
| `secrets list` | Sitios guardados. Nunca imprime el valor. |
| `secrets set SITIO` | Pide la contraseña dos veces (`getpass`). `--password-stdin` para scripts; nunca argv. |
| `secrets delete SITIO` | Borra esa entrada. |
| `secrets allow-fill` | Bandera de consentimiento para un fill futuro. CAPTCHA/2FA/enviar siguen tuyos. |
| `secrets deny-fill` | Apaga `fill_login`. |

Oculto ≠ cifrado. No sincronices el archivo a Drive/Dropbox. Ver issue #157.

## El resto del CLI

Estos comandos también están en `cli.py`. La portada los describe; aquí queda
el nombre para que la lista esté completa.

| Comando | Qué hace |
|---------|----------|
| `status` | Evidencia local de CV y portales activos. Alias: `cv status`. |
| `capture URL` | Deja un enlace como candidato, sin descarga. `--list` muestra pendientes. |
| `workspace list` / `new` / `show` / `adopt` / `delete` | Sandboxes de varios candidatos. |
| `workspace consent NOMBRE` | Consentimiento y fecha de borrado de un sandbox. |
| `advisor status` / `advisor report` | Estado cruzado y resumen redactado. Sin el nombre del candidato. |
| `cv advise` | Mejoras de presentación. `--apply` confirma una por una. |
| `cv tune-for Jxxxx` | Advise acotado a un aviso o a un enlace. |
| `cv sync` | Presencia: permanentes y empresas activas. `--apply` confirma. |
| `jobs queries` | Imprime búsquedas web para hosts ATS. No busca. |
| `jobs audit --source indeed` | Señuelos y duplicados de Indeed. `--apply` los marca. |
| `getonboard upload-cv` | Valida el PDF. `--apply` lo sube. |
| `portals form-learn URL` | Lee las preguntas de un formulario. No envía. |
| `portals profile status` / `sheet` / `mark-updated` / `import` / `seed` / `push` | Cobertura, hoja de llenado y seguimiento. `push` no tipea en el portal. |
| `companies recon NOMBRE` | Aprende ATS y preguntas desde HTML. |
| `companies signup NOMBRE` | Alta asistida. Crear la cuenta queda en tus manos. |
| `browser sessions` | Estado de sesión por evidencia. Sin `--cdp` no lee un perfil ajeno. No se adjunta solo. |
| `browser login` | Portales sin sesión probada. `--apply` abre el siguiente. |
| `ops failure show` / `triage` / `issue` / `work` | Una falla local. `issue` y `work --apply` son HITL; no hay commit ni push automáticos. |
| `ops symptom note` / `list` / `show` / `plan` / `triage` / `issue` | Síntomas locales, redactados al guardar. |
| `ops capabilities` | Índice de módulos. `--write` regenera `docs/capabilities.md`. |
| `recruiters discover` / `list` / `show` / `promote` / `reject` / `export` | Prácticas públicas de reclutamiento. Sin personas. |

## Misceláneos

| Comando | Qué hace |
|---------|----------|
| `--verbose` / `-v` | Logging de depuración (opción global, va antes del grupo). |
