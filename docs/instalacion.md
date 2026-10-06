---
title: Instalación y quickstart
description: Curl o Docker, carpeta ~/postulaciones con .local/, y el primer ciclo de JobBot.
---

# Instalación y quickstart

No necesitas clonar el repo. Hay **dos formas equivalentes** de obtener `jobbot`; después
creas una carpeta de postulaciones con estado en `.local/` (sincronizable con Drive, Dropbox,
Syncthing, etc.).

## Opción A — curl (ejecutable en el host)

```bash
curl -fsSL https://raw.githubusercontent.com/ljofreflor/jobbot/main/scripts/install.sh | bash
which jobbot
```

El script instala [uv](https://docs.astral.sh/uv/) si hace falta y deja `jobbot` en tu `PATH`
(estilo Homebrew). Audita el script en
[scripts/install.sh](https://github.com/ljofreflor/jobbot/blob/main/scripts/install.sh).

Para instalar desde otra rama, tag o SHA (URL del script y paquete deben coincidir):

```bash
REF=v0.1.0   # o una rama / SHA
curl -fsSL "https://raw.githubusercontent.com/ljofreflor/jobbot/${REF}/scripts/install.sh" \
  | JOBBOT_REF="$REF" bash
```

Actualizar el ejecutable más adelante:

```bash
jobbot update                    # tipicamente main
JOBBOT_REF=v0.1.0 jobbot update  # o un tag / SHA / rama
```

## Opción B — Docker (imagen lista)

```bash
mkdir -p ~/postulaciones
docker pull ghcr.io/ljofreflor/jobbot:latest   # o: docker compose build
docker compose run --rm -v "$HOME/postulaciones:/work" -w /work jobbot version
```

La imagen trae la herramienta; **tu carpeta** montada es el workspace (perfil, DB, output).

Actualizar la imagen (en el host, no con `jobbot update` dentro del contenedor):

```bash
docker pull ghcr.io/ljofreflor/jobbot:latest
# o: docker compose pull && docker compose build
```

## Crear la carpeta (común a A y B)

`jobbot init [DIR]` escribe `.jobbot.toml` y `.local/` **dentro de DIR** (default: el
directorio actual). Ejemplo recomendado:

```bash
mkdir -p ~/postulaciones && cd ~/postulaciones
jobbot init
# equivalente: jobbot init ~/postulaciones
# o con Docker:
# docker compose run --rm -v "$HOME/postulaciones:/work" -w /work jobbot init
```

```text
~/postulaciones/
  .jobbot.toml
  .gitignore          # .local/ y tmp/ (andamiaje temporal)
  .local/
    profile.yaml
    jobbot.sqlite
    portals.yaml
    companies.yaml
    browser-data/
    output/
    templates/
  tmp/                # dumps y probes; ignorado por git
```

`jobbot init` escribe o completa `.gitignore` con `.local/` y `tmp/` (sin borrar
líneas tuyas). El estado privado y el andamiaje temporal no deben versionarse.

Importa un CV en PDF (o edita el YAML a mano):

```bash
jobbot profile import-pdf ~/Descargas/CV.pdf --promote
jobbot profile validate
```

Sincroniza **toda** la carpeta `~/postulaciones` (incluye `.local/`). `browser-data/` puede ser
grande y atar cookies a una máquina.

## Requisitos (host / curl)

- Python 3.12+ (el instalador puede pedirlo vía uv).
- XeLaTeX, **solo** si quieres el PDF. El CV en texto plano para ATS no lo necesita.
    - macOS: `brew install --cask basictex` (o `mactex-no-gui`) y deja `xelatex` en el `PATH`.
- Chromium de Playwright para comandos de portal (o usa la imagen Docker).

## Contribuir (clon del repo)

```bash
git clone https://github.com/ljofreflor/jobbot.git && cd jobbot
uv sync --group dev
cp data/profile.example.yaml data/profile.yaml
make hooks        # git config core.hooksPath .githooks
```

!!! warning "Límite de datos personales"

    En un clon: `data/profile.yaml`, `portals.yaml`, `output/`, `browser-data/`, `.env`
    y SQLite van gitignoreados. En un workspace frío el estado vive en `.local/` y no
    es un repo git salvo que tú lo inicialices.

## Tu perfil es la fuente de verdad

Edita `.local/profile.yaml` (workspace frío) o `data/profile.yaml` (clon) con IDs estables:

```yaml
experience:
  - id: acme-ds
    company: Acme
    title: Data Scientist
    start_date: 2022-04
    current: true
    achievements:
      - id: acme-forecast
        text: Built demand forecasting for 2M SKUs.
        tags: [machine-learning, retail]
        metrics:
          skus: 2000000
```

Valida y revisa:

```bash
jobbot profile validate
jobbot profile show
```

¿Vienes de un CV en LaTeX (moderncv)? Impórtalo sin sobrescribir nada:

```bash
jobbot profile import-latex /path/to/cv.tex   # → profile.generated.yaml
jobbot profile promote-generated              # después de revisarlo a mano
jobbot profile validate
```

## Generar el CV

```bash
jobbot cv build                  # .local/output/base/… (workspace frío)
jobbot cv build --target ats     # texto plano ATS
jobbot cv build --style plain    # diseño portable en vez de moderncv
```

## Primer ciclo completo

```bash
jobbot getonboard search "data scientist" --limit 20
jobbot jobs shortlist
jobbot jobs match J0001
jobbot cv build --job J0001
jobbot application prepare J0001
jobbot application apply J0001       # plan de prellenado; el envío es tuyo
jobbot applications list
```

Alternativa sin navegador, si ya tienes la descripción del cargo en un archivo:

```bash
jobbot jobs add --file path/to/jd.txt
```

!!! tip "Dónde corre bien cada cosa"

    Los comandos que abren un navegador (`indeed`, `linkedin`, `getonboard`,
    `browser chrome-debug`) están pensados para tu máquina y tu conexión
    residencial. El descubrimiento vía APIs públicas de ATS funciona desde
    cualquier parte. El porqué está medido en
    [este post](blog/posts/2026-09-24-bloqueos-ip-datacenter.md).

## Desarrollo y calidad

```bash
make install     # uv sync --group dev
make lint        # uv run ruff check .
make typecheck   # uv run mypy src
make test        # uv run pytest
make format      # uv run ruff format .
```

Cold smoke (carpeta fría en `$HOME`):

```bash
uv build --wheel -o /tmp/jobbot-wheels
JOBBOT_SOURCE=wheel:/tmp/jobbot-wheels/jobbot-0.1.0-py3-none-any.whl ./scripts/smoke-cold-home.sh
./scripts/smoke-cold-docker.sh   # requiere Docker
```

## Documentación (este sitio)

```bash
make docs-serve  # http://127.0.0.1:8000 con recarga en vivo
make docs-build  # build estricto a site/
```

## Problemas frecuentes

| Problema | Solución |
|----------|----------|
| `jobbot: command not found` | Añade `~/.local/bin` (o `$(uv tool dir --bin)`) al `PATH` |
| `xelatex` not found | Instala BasicTeX/MacTeX, abre una shell nueva, verifica con `which xelatex` |
| `PROFILE INVALID` | Corrige fechas, IDs y correos que reporta `profile validate` |
| PDF sin texto | Re-exporta el CV con capa de texto; JobBot no hace OCR |
