---
title: Referencia de comandos
description: Todos los comandos del CLI de JobBot, verificados contra src/jobbot/cli.py.
---

# Referencia de comandos

Tras [instalar con curl](instalacion.md), corre `jobbot <grupo> <comando>`. En un
clon del repo, `uv run jobbot …`. Esta página lista lo que existe hoy en
`src/jobbot/cli.py`; si un comando no aparece aquí, probablemente no existe.
Para las opciones completas, `jobbot <grupo> <comando> --help`.

## Workspace e instalación

| Comando | Qué hace |
|---------|----------|
| `init [DIR]` | Crea un workspace frío: `.jobbot.toml` y `.local/` **dentro de DIR** (default: el directorio actual). No usa `$HOME`, `JOBBOT_ROOT` ni el repo del paquete para ubicar `.local/`. `--force` sobrescribe semillas. |
| `update` | Reinstala el ejecutable en el `PATH` desde GitHub (`uv tool`). `JOBBOT_REF` / `--ref` eligen rama, tag o SHA. En Docker: actualiza la imagen en el host. |
| `version` | Muestra la versión de JobBot. |

```bash
mkdir -p ~/postulaciones && cd ~/postulaciones
jobbot init
# equivalente sin cd:
# jobbot init ~/postulaciones
jobbot update
JOBBOT_REF=v0.1.0 jobbot update
```

## Perfil

| Comando | Qué hace |
|---------|----------|
| `profile validate` | Valida el perfil (`.local/profile.yaml` o `data/profile.yaml`). |
| `profile show` | Resumen del perfil local. |
| `profile import-pdf RUTA` | Importa un CV PDF (capa de texto) a `profile.generated.yaml`. `--promote` lo copia a `profile.yaml` tras validar. |
| `profile import-latex [RUTA]` | Importa un CV LaTeX legado a `profile.generated.yaml`. |
| `profile promote-generated` | Copia `profile.generated.yaml` → `profile.yaml` tras confirmación. |
| `profile suggest-from-market` | Sugiere redacción base desde las JDs guardadas; pregunta antes de agregar skills. |
| `profile queries` | Deriva búsquedas desde la experiencia del perfil. `--apply` las guarda como `search_queries` (con confirmación). |
| `profile status` | Consistencia entre lo local y los snapshots de portales. |
| `profile diff` | Diff del perfil local contra los snapshots de portales. |

## CV

| Comando | Qué hace |
|---------|----------|
| `cv build` | Construye el CV desde `profile.yaml`. `--target cv\|ats`, `--job Jxxxx`, `--style moderncv\|plain`. |
| `cv propagate` | Reconstruye el CV base y lo propaga a los perfiles permanentes (HITL, dry-run por defecto). |

```bash
jobbot cv build --target ats
jobbot cv build --job J0001
jobbot cv propagate                 # solo plan
jobbot cv propagate --apply         # confirma destino por destino
```

## Vacantes

| Comando | Qué hace |
|---------|----------|
| `jobs add` | Agrega una vacante desde un archivo de texto o stdin (`--file`). |
| `jobs search QUERY` | Busca en Indeed y guarda las vacantes localmente. `--location`, `--limit`, `--remote`, `--cdp`. |
| `jobs show JOB_ID` | Muestra una vacante guardada. |
| `jobs match JOB_ID` | Puntúa la vacante contra el perfil local (ayuda a decidir, no decide). |
| `jobs shortlist` | Ordena las vacantes guardadas por score. |
| `jobs conditions JOB_ID… [--all-prepared]` | Lee las condiciones del aviso (cerrado, residencia, idioma, excluyentes, contrato, renta, modalidad) contra tu perfil y `data/application_answers.yaml`: ✅ cumple, ⚠️ pregunta exacta, ❌ impedimento (exit 1). Offline. |
| `jobs backfill-dates` | Data vacantes ya guardadas usando el activity id de la URL (offline). |
| `jobs note JOB_ID TEXTO` | Adjunta una nota libre a una vacante. |

## Postulaciones

| Comando | Qué hace |
|---------|----------|
| `application prepare JOB_ID` | Arma el paquete de postulación (no inventa respuestas). |
| `application show JOB_ID` | Ruta y estado del paquete. |
| `application open JOB_ID` | Abre la URL de la vacante o del ATS en el navegador (no postula). |
| `application apply JOB_ID` | Plan de prellenado ATS/Gmail. `--apply` abre; el envío lo haces tú. |
| `application check-answer JOB_ID -q PREGUNTA --text/--file` | Revisa una respuesta libre contra el perfil y el aviso: cifras, nombres, pares título–institución y lo dicho de la empresa. La motivación queda para ti (no pega nada). |
| `applications list` | Lista las postulaciones registradas (alias: `applications status`). |

## Portales

### Indeed

`indeed login`, `indeed status`, `indeed inspect`, `indeed prepare`, `indeed pull`,
`indeed diff`, `indeed sync` (dry-run por defecto; `--apply` escribe).

### LinkedIn

`linkedin login`, `linkedin status`, `linkedin inspect`, `linkedin pull`,
`linkedin diff`, `linkedin sync` (Publications, con DOI y coautores),
`linkedin sweep [QUERY]` (barrido de posts de reclutadores → vacantes + detección de ATS).
Sin `QUERY`, corre las `search_queries` del perfil (o las deriva). `--max-queries N` limita cuántas.

### Get on Board

`getonboard prepare`, `getonboard show-profile`, `getonboard open-profile`,
`getonboard open-cvs`, `getonboard sync`, `getonboard search [QUERY]`.
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
| `portals detect URL` | Detecta el tipo de ATS de una URL. |
| `portals add` | Agrega o actualiza un portal en el registro de portales. |
| `companies detect URL` | Clasifica una URL (aviso / portal / ATS / redirección). No escribe nada. |
| `companies learn URL` | Registra una relación empresa↔portal como conocimiento *candidate*. |
| `companies list` | Lista empresas y sus plataformas de carreras. |
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

## Misceláneos

| Comando | Qué hace |
|---------|----------|
| `--verbose` / `-v` | Logging de depuración (opción global, va antes del grupo). |
