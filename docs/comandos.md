---
title: Referencia de comandos
description: Todos los comandos del CLI de JobBot, verificados contra src/jobbot/cli.py.
---

# Referencia de comandos

Todo se ejecuta como `uv run jobbot <grupo> <comando>`. Esta página lista lo que
existe hoy en `src/jobbot/cli.py`; si un comando no aparece aquí, probablemente no
existe. Para las opciones completas, `uv run jobbot <grupo> <comando> --help`.

## Perfil

| Comando | Qué hace |
|---------|----------|
| `profile validate` | Valida `data/profile.yaml`. |
| `profile show` | Resumen del perfil local. |
| `profile import-latex [RUTA]` | Importa un CV LaTeX legado a `data/profile.generated.yaml`. |
| `profile promote-generated` | Copia `profile.generated.yaml` → `profile.yaml` tras confirmación. |
| `profile suggest-from-market` | Sugiere redacción base desde las JDs guardadas; pregunta antes de agregar skills. |
| `profile status` | Consistencia entre lo local y los snapshots de portales. |
| `profile diff` | Diff del perfil local contra los snapshots de portales. |

## CV

| Comando | Qué hace |
|---------|----------|
| `cv build` | Construye el CV desde `profile.yaml`. `--target cv\|ats`, `--job Jxxxx`, `--style moderncv\|plain`. |
| `cv propagate` | Reconstruye el CV base y lo propaga a los perfiles permanentes (HITL, dry-run por defecto). |

```bash
uv run jobbot cv build --target ats
uv run jobbot cv build --job J0001
uv run jobbot cv propagate                 # solo plan
uv run jobbot cv propagate --apply         # confirma destino por destino
```

## Vacantes

| Comando | Qué hace |
|---------|----------|
| `jobs add` | Agrega una vacante desde un archivo de texto o stdin (`--file`). |
| `jobs search QUERY` | Busca en Indeed y guarda las vacantes localmente. `--location`, `--limit`, `--remote`, `--cdp`. |
| `jobs show JOB_ID` | Muestra una vacante guardada. |
| `jobs match JOB_ID` | Puntúa la vacante contra el perfil local (ayuda a decidir, no decide). |
| `jobs shortlist` | Ordena las vacantes guardadas por score. |
| `jobs backfill-dates` | Data vacantes ya guardadas usando el activity id de la URL (offline). |
| `jobs note JOB_ID TEXTO` | Adjunta una nota libre a una vacante. |

## Postulaciones

| Comando | Qué hace |
|---------|----------|
| `application prepare JOB_ID` | Arma el paquete de postulación (no inventa respuestas). |
| `application show JOB_ID` | Ruta y estado del paquete. |
| `application open JOB_ID` | Abre la URL de la vacante o del ATS en el navegador (no postula). |
| `application apply JOB_ID` | Plan de prellenado ATS/Gmail. `--apply` abre; el envío lo haces tú. |
| `applications list` | Lista las postulaciones registradas (alias: `applications status`). |

## Portales

### Indeed

`indeed login`, `indeed status`, `indeed inspect`, `indeed prepare`, `indeed pull`,
`indeed diff`, `indeed sync` (dry-run por defecto; `--apply` escribe).

### LinkedIn

`linkedin login`, `linkedin status`, `linkedin inspect`, `linkedin pull`,
`linkedin diff`, `linkedin sync` (Publications, con DOI y coautores),
`linkedin sweep QUERY` (barrido de posts de reclutadores → vacantes + detección de ATS).

### Get on Board

`getonboard prepare`, `getonboard show-profile`, `getonboard open-profile`,
`getonboard open-cvs`, `getonboard sync`, `getonboard search QUERY`.

### Navegador

`browser chrome-debug` abre un Chrome normal con CDP para que resuelvas a mano los
desafíos que aparezcan. No hay resolución automática de CAPTCHAs.

## Registro de ATS y empresas

| Comando | Qué hace |
|---------|----------|
| `portals list` | Lista los portales de reclutamiento conocidos. |
| `portals detect URL` | Detecta el tipo de ATS de una URL. |
| `portals add` | Agrega o actualiza un portal en `data/portals.yaml`. |
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
Escribe en `output/` y nunca toca `data/companies.yaml`.

## Operación local

| Comando | Qué hace |
|---------|----------|
| `ops failures` | Lista fallas guardadas, agrupadas por fingerprint. |
| `ops failure` | Inspecciona y tría una falla puntual. |
| `ops loop` | Corre un paso de mantención en loop; persiste `Fxxxx` al fallar y sigue. |

No hay telemetría: las fallas se guardan en tu base local y se quedan ahí.

## Misceláneos

| Comando | Qué hace |
|---------|----------|
| `version` | Muestra la versión de JobBot. |
| `--verbose` / `-v` | Logging de depuración (opción global, va antes del grupo). |
