---
title: Empezar — imagen lista y CLI
description: Camino recomendado con Docker; instalación local del CLI como opción avanzada.
---

# Empezar

Lo más simple: **correr Jobbot desde una imagen con Python, uv y Chromium ya
instalados**. Instalar el CLI a mano en tu máquina queda como camino avanzado
(desarrollo, contribuciones, o HITL con navegador headed en tu escritorio).

El canal sigue siendo Cursor, VS Code, Claude Code u otro agente/IDE: pegas un
link, pides postular, y el agente ejecuta `jobbot` — en el contenedor o en el
host.

## Imagen lista (recomendado)

Hoy no hay un binario SaaS: la “descarga” es una **imagen Docker** que construyes
desde este repo (o, cuando el workflow de GHCR publique en `main`, la tiras con
`docker pull`).

### 1. Requisitos del host

- [Docker](https://docs.docker.com/get-docker/) (Engine + Compose v2).
- Git, para clonar el repo y montar `data/`, `output/` y `browser-data/` en tu disco.

### 2. Clonar y perfil

```bash
git clone https://github.com/ljofreflor/jobbot.git && cd jobbot
cp data/profile.example.yaml data/profile.yaml
# opcional:
# cp .jobbot.toml.example .jobbot.toml
# cp data/portals.example.yaml data/portals.yaml
```

Edita `data/profile.yaml` en el host (sigue siendo la única fuente de verdad;
está gitignoreado).

### 3. Construir y probar

```bash
docker compose build
docker compose run --rm jobbot version
docker compose run --rm jobbot profile validate
```

Los volúmenes en `docker-compose.yml` montan `./data`, `./output` y
`./browser-data` — lo que generas queda en tu máquina, no dentro de la imagen.

### 4. Cuando exista en GHCR

Tras merge a `main`, el workflow [`.github/workflows/docker.yml`](https://github.com/ljofreflor/jobbot/blob/main/.github/workflows/docker.yml)
publica en GitHub Container Registry (si el repo tiene `packages: write`):

```bash
docker pull ghcr.io/ljofreflor/jobbot:latest
docker run --rm -v "$PWD/data:/app/data" -v "$PWD/output:/app/output" \
  ghcr.io/ljofreflor/jobbot:latest version
```

Hasta que esa imagen exista en el registry, usa `docker compose build` arriba.
No inventamos un tag publicado: si `docker pull` falla, construye local.

### Primer ciclo (sin navegador headed)

```bash
docker compose run --rm jobbot jobs add --file path/to/jd.txt   # o discovery vía API
docker compose run --rm jobbot jobs shortlist
docker compose run --rm jobbot jobs match J0001
docker compose run --rm jobbot cv build --job J0001 --target ats
docker compose run --rm jobbot application prepare J0001
```

Desde tu agente en Cursor/VS Code/Claude Code: mismos comandos, prefijados con
`docker compose run --rm jobbot …` (o apunta el agente al CLI del host; ver abajo).

### Qué sigue necesitando tu máquina (HITL)

Jobbot **no postula por ti**. Login persistente, CAPTCHAs y formularios headed
están pensados para **tu escritorio y tu IP residencial**:

| En la imagen | Mejor en el host |
|--------------|------------------|
| `profile validate` / `show` | `indeed login`, `linkedin` login / sweep live |
| `jobs match`, `shortlist`, `add --file` | `browser chrome-debug` + CAPTCHA |
| `cv build` (ATS texto; PDF si instalas TeX aparte) | Envios reales en el portal |
| Discovery vía APIs públicas de ATS | Scrapes que fallan desde IP de datacenter |

Medición: [bloqueos IP datacenter](blog/posts/2026-09-24-bloqueos-ip-datacenter.md).
Sesiones viven en `browser-data/` (gitignoreado). Secretos: `.env`,
`.jobbot.toml` — no van en la imagen.

XeLaTeX **no** viene en la imagen (es pesado). Para PDF usa el CLI en el host
con BasicTeX/MacTeX, o quédate con `--target ats`.

## CLI local (avanzado / desarrollo)

Si prefieres Python en el host, o vas a desarrollar:

### Requisitos

- Python 3.12 o superior.
- [uv](https://docs.astral.sh/uv/) para dependencias y ejecución.
- XeLaTeX, **solo** si quieres el PDF. El CV en texto plano para ATS no lo necesita.
    - macOS: `brew install --cask basictex` (o `mactex-no-gui`) y deja `xelatex` en el `PATH`.
    - Después de BasicTeX: `sudo tlmgr update --self && sudo tlmgr install collection-fontsrecommended`.
- Chromium de Playwright, solo para los comandos que abren un portal:
  `uv run playwright install chromium`.

### Instalación

```bash
git clone https://github.com/ljofreflor/jobbot.git && cd jobbot
uv sync --group dev
cp data/profile.example.yaml data/profile.yaml
```

Opcionales:

```bash
cp .jobbot.toml.example .jobbot.toml            # configuración local
cp data/portals.example.yaml data/portals.yaml  # semilla de portales ATS
```

Activa el guardián de PII una vez por clon, antes del primer commit:

```bash
make hooks        # git config core.hooksPath .githooks
make pii-check    # escanea el índice actual cuando quieras
```

!!! warning "Límite de datos personales"

    `data/profile.yaml`, `data/portals.yaml`, `output/`, `browser-data/`, `.env`
    y las bases SQLite están gitignoreados. Solo los archivos `*.example.yaml`
    son seguros de commitear. El hook de pre-commit bloquea el resto incluso con
    `git add -f`, y además marca correos, teléfonos, RUTs y rutas
    `/Users/<tu-usuario>/` que aparezcan en contenido staged.

## Tu perfil es la fuente de verdad

Edita `data/profile.yaml` con IDs estables para experiencias y logros:

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

Valida y revisa (imagen o CLI):

```bash
docker compose run --rm jobbot profile validate
# o: uv run jobbot profile validate
uv run jobbot profile show
```

¿Vienes de un CV en LaTeX (moderncv)? Impórtalo sin sobrescribir nada:

```bash
uv run jobbot profile import-latex /path/to/cv.tex   # → data/profile.generated.yaml
uv run jobbot profile promote-generated              # después de revisarlo a mano
uv run jobbot profile validate
```

## Generar el CV

```bash
uv run jobbot cv build                  # output/base/cv.tex + cv.pdf
uv run jobbot cv build --target ats     # output/base/cv_ats.txt
uv run jobbot cv build --style plain    # diseño portable en vez de moderncv
```

## Primer ciclo completo (CLI host + Playwright)

```bash
uv run playwright install chromium          # una vez, si vas a usar portales
uv run jobbot getonboard search "data scientist" --limit 20
uv run jobbot jobs shortlist
uv run jobbot jobs match J0001
uv run jobbot cv build --job J0001
uv run jobbot application prepare J0001
uv run jobbot application apply J0001       # plan de prellenado; el envío es tuyo
uv run jobbot applications list
```

Alternativa sin navegador, si ya tienes la descripción del cargo en un archivo:

```bash
uv run jobbot jobs add --file path/to/jd.txt
```

Con Indeed la ruta es la misma, agregando el login persistente:

```bash
uv run jobbot indeed login
uv run jobbot jobs search "Senior Data Scientist" --location Santiago --limit 20
```

!!! tip "Dónde corre bien cada cosa"

    Los comandos que abren un navegador (`indeed`, `linkedin`, `getonboard`,
    `browser chrome-debug`) están pensados para tu máquina y tu conexión
    residencial. El descubrimiento vía APIs públicas de ATS funciona desde
    cualquier parte (incluida la imagen). El porqué está medido en
    [este post](blog/posts/2026-09-24-bloqueos-ip-datacenter.md).

## Desarrollo y calidad

```bash
make install     # uv sync --group dev
make lint        # uv run ruff check .
make typecheck   # uv run mypy src
make test        # uv run pytest
make format      # uv run ruff format .
```

## Documentación (este sitio)

```bash
make docs-serve  # http://127.0.0.1:8000 con recarga en vivo
make docs-build  # build estricto a site/
```

Las dependencias del sitio viven en el grupo `docs` de `pyproject.toml`, aparte
del runtime: `uv sync --group docs`.

## Problemas frecuentes

| Problema | Solución |
|----------|----------|
| `docker compose build` lento / falla Playwright | Revisa red; la imagen instala Chromium con `--with-deps` |
| `ghcr.io/... pull` 404 | La imagen aún no está publicada; usa `docker compose build` |
| `xelatex` not found | En host: BasicTeX/MacTeX; en imagen: usa `--target ats` |
| Fuente no encontrada | La plantilla usa Times New Roman / Helvetica. En Linux instala esas fuentes o edita `templates/cv.tex.j2` |
| `PROFILE INVALID` | Corrige fechas, IDs y correos que reporta `profile validate` |
| PDF vacío | Revisa `output/base/build.log` |
