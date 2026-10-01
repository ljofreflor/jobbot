#!/usr/bin/env bash
# Cold smoke B: Docker image → mount ~/postulaciones → Carolina Baeza CV.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAROLINA="${CAROLINA_CV_PDF:-$ROOT/tests/fixtures/cvs/carolina_baeza/CV_Carolina_Baeza_2026.pdf}"
HOME_DIR="${HOME:?HOME must be set}"
WS="${HOME_DIR}/postulaciones"

if [[ ! -f "${CAROLINA}" ]]; then
  echo "missing Carolina fixture: ${CAROLINA}" >&2
  exit 1
fi

echo "== build image =="
cd "${ROOT}"
docker compose build

echo "== cold folder ${WS} =="
rm -rf "${WS}"
mkdir -p "${WS}"
cp "${CAROLINA}" "${WS}/CV_Carolina_Baeza_2026.pdf"

export JOBBOT_HOME="${WS}"
docker compose run --rm jobbot init
test -f "${WS}/.jobbot.toml"
test -f "${WS}/.local/profile.yaml"

docker compose run --rm jobbot profile import-pdf /work/CV_Carolina_Baeza_2026.pdf --promote
docker compose run --rm jobbot profile validate

NAME="$(python3 -c "import yaml; print(yaml.safe_load(open('${WS}/.local/profile.yaml'))['personal']['name'])")"
echo "profile name: ${NAME}"
echo "${NAME}" | grep -qi carolina
echo "${NAME}" | grep -qi baeza

echo "OK smoke-cold-docker (${WS})"
