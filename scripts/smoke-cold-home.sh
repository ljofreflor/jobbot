#!/usr/bin/env bash
# Cold smoke A: host PATH install → ~/postulaciones → Carolina Baeza CV.
# Usage (from repo root, after building a wheel):
#   JOBBOT_SOURCE=wheel:/tmp/jobbot-wheels/jobbot-0.1.0-py3-none-any.whl ./scripts/smoke-cold-home.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAROLINA="${CAROLINA_CV_PDF:-$ROOT/tests/fixtures/cvs/carolina_baeza/CV_Carolina_Baeza_2026.pdf}"
HOME_DIR="${HOME:?HOME must be set}"
WS="${HOME_DIR}/postulaciones"

if [[ ! -f "${CAROLINA}" ]]; then
  echo "missing Carolina fixture: ${CAROLINA}" >&2
  exit 1
fi

echo "== install jobbot on PATH =="
bash "${ROOT}/scripts/install.sh"
export PATH="${HOME_DIR}/.local/bin:${PATH}"
if command -v uv >/dev/null 2>&1; then
  UV_BIN="$(uv tool dir --bin 2>/dev/null || true)"
  [[ -n "${UV_BIN}" ]] && export PATH="${UV_BIN}:${PATH}"
fi
command -v jobbot
jobbot version

echo "== cold folder ${WS} =="
rm -rf "${WS}"
mkdir -p "${WS}"
cd "${WS}"
jobbot init
test -f "${WS}/.jobbot.toml"
test -f "${WS}/.local/profile.yaml"

echo "== import Carolina Baeza =="
cp "${CAROLINA}" "${WS}/CV_Carolina_Baeza_2026.pdf"
jobbot profile import-pdf "${WS}/CV_Carolina_Baeza_2026.pdf" --promote
jobbot profile validate
NAME="$(python3 -c "import yaml; print(yaml.safe_load(open('.local/profile.yaml'))['personal']['name'])")"
echo "profile name: ${NAME}"
echo "${NAME}" | grep -qi carolina
echo "${NAME}" | grep -qi baeza

jobbot cv build --target ats || true

echo "== walk-up from subdirectory =="
mkdir -p "${WS}/notas"
cd "${WS}/notas"
jobbot profile validate

echo "OK smoke-cold-home (${WS})"
