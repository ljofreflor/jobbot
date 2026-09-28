#!/usr/bin/env bash
# Install the `jobbot` executable on PATH (Homebrew-style).
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ljofreflor/jobbot/main/scripts/install.sh | bash
#
# Optional env:
#   JOBBOT_REF=main|v0.1.0|<sha>   — git ref for git+https install (default: main)
#   JOBBOT_SOURCE=wheel:/path.whl  — offline/CI: install a local wheel instead of git
set -euo pipefail

REPO_URL="${JOBBOT_REPO:-https://github.com/ljofreflor/jobbot}"
REF="${JOBBOT_REF:-main}"
SOURCE="${JOBBOT_SOURCE:-}"

say() { printf '%s\n' "$*"; }
err() { printf 'jobbot-install: %s\n' "$*" >&2; }

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    return 1
  fi
  return 0
}

ensure_uv() {
  if need_cmd uv; then
    return 0
  fi
  say "Installing uv (https://astral.sh/uv)…"
  curl -fsSL https://astral.sh/uv/install.sh | sh
  # shellcheck disable=SC1090
  if [[ -f "${HOME}/.local/bin/env" ]]; then
    # uv installer may drop an env helper
    . "${HOME}/.local/bin/env" 2>/dev/null || true
  fi
  export PATH="${HOME}/.local/bin:${PATH}"
  if ! need_cmd uv; then
    err "uv not on PATH after install; add ${HOME}/.local/bin to PATH and re-run"
    exit 1
  fi
}

ensure_python() {
  if uv python find 3.12 >/dev/null 2>&1; then
    return 0
  fi
  say "Installing Python 3.12 via uv…"
  uv python install 3.12
}

install_jobbot() {
  if [[ -n "${SOURCE}" ]]; then
    case "${SOURCE}" in
      wheel:*)
        wheel_path="${SOURCE#wheel:}"
        if [[ ! -f "${wheel_path}" ]]; then
          err "wheel not found: ${wheel_path}"
          exit 1
        fi
        say "Installing JobBot from wheel ${wheel_path}…"
        uv tool install --force --python 3.12 "${wheel_path}"
        ;;
      *)
        err "Unknown JOBBOT_SOURCE=${SOURCE} (use wheel:/path/to.whl)"
        exit 1
        ;;
    esac
  else
    say "Installing JobBot from ${REPO_URL}@${REF}…"
    uv tool install --force --python 3.12 "git+${REPO_URL}@${REF}"
  fi
}

main() {
  ensure_uv
  ensure_python
  install_jobbot

  export PATH="${HOME}/.local/bin:${PATH}"
  if ! need_cmd jobbot; then
    # uv tool bin dir
    UV_TOOL_BIN="$(uv tool dir --bin 2>/dev/null || true)"
    if [[ -n "${UV_TOOL_BIN}" ]]; then
      export PATH="${UV_TOOL_BIN}:${PATH}"
    fi
  fi

  if ! need_cmd jobbot; then
    err "jobbot installed but not on PATH."
    err "Add to your shell rc:  export PATH=\"\$HOME/.local/bin:\$PATH\""
    err "Or:  export PATH=\"\$(uv tool dir --bin):\$PATH\""
    exit 1
  fi

  say ""
  say "Installed: $(command -v jobbot)"
  jobbot version
  say ""
  say "Next (cold workspace, no git clone):"
  say "  mkdir -p ~/postulaciones && cd ~/postulaciones"
  say "  jobbot init"
  say ""
  say "Or use Docker instead — see docs/instalacion.md"
}

main "$@"
