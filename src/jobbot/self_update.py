"""Reinstall / upgrade the ``jobbot`` executable on PATH."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REPO = "https://github.com/ljofreflor/jobbot"
DEFAULT_REF = "main"

_DOCKERENV = Path("/.dockerenv")


@dataclass(frozen=True)
class UpdateResult:
    ok: bool
    message: str
    version_line: str | None = None
    already_latest: bool = False


def _home() -> Path:
    return Path.home()


def _in_docker() -> bool:
    """JobBot's published image has ``/.dockerenv``. A cgroup mention of
    containerd is not enough — that also matches k8s and devcontainers where
    the user installed ``jobbot`` with uv and still needs ``jobbot update``.
    """
    return _DOCKERENV.is_file()


def _find_uv() -> str | None:
    found = shutil.which("uv")
    if found:
        return found
    extras = [
        _home() / ".local" / "bin" / "uv",
        _home() / ".cargo" / "bin" / "uv",
    ]
    jobbot = shutil.which("jobbot")
    if jobbot:
        extras.append(Path(jobbot).resolve().parent / "uv")
    for path in extras:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def _uv_tools_jobbot_dir() -> Path | None:
    override = os.environ.get("UV_TOOL_DIR")
    if override:
        candidate = Path(override) / "jobbot"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else _home() / ".local" / "share"
        candidate = base / "uv" / "tools" / "jobbot"
    return candidate if candidate.is_dir() else None


def _stamp_from_direct_url(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    vcs = data.get("vcs_info")
    if not isinstance(vcs, dict):
        return None
    commit = vcs.get("commit_id")
    if isinstance(commit, str) and commit.strip():
        return commit.strip()
    return None


def _path_install_stamp() -> str | None:
    """Git commit of the uv-tool install on disk (PEP 610), if present."""
    root = _uv_tools_jobbot_dir()
    if root is None:
        return None
    matches = sorted(root.glob("lib/python*/site-packages/jobbot-*.dist-info/direct_url.json"))
    for direct in matches:
        stamp = _stamp_from_direct_url(direct)
        if stamp:
            return stamp
    return None


def update_jobbot(
    *,
    ref: str | None = None,
    repo: str | None = None,
    source: str | None = None,
) -> UpdateResult:
    """
    Upgrade the uv-tool install of JobBot (same path as ``scripts/install.sh``).

    Production is GitHub ``main``. ``JOBBOT_REF`` / ``JOBBOT_REPO`` /
    ``JOBBOT_SOURCE`` apply when args are omitted. Inside the JobBot Docker
    image, returns a pull hint instead of mutating the image.
    """
    if _in_docker():
        return UpdateResult(
            ok=False,
            message=(
                "Running inside Docker — update the image on the host:\n"
                "  docker pull ghcr.io/ljofreflor/jobbot:latest\n"
                "  # or: docker compose pull && docker compose build"
            ),
        )

    uv = _find_uv()
    if uv is None:
        return UpdateResult(
            ok=False,
            message=(
                "uv not found on PATH. Re-run the installer:\n"
                "  curl -fsSL https://raw.githubusercontent.com/ljofreflor/jobbot/"
                "main/scripts/install.sh | bash"
            ),
        )

    if source is not None:
        resolved_source = source.strip()
    else:
        resolved_source = os.environ.get("JOBBOT_SOURCE", "").strip()
    resolved_repo = (repo or os.environ.get("JOBBOT_REPO") or DEFAULT_REPO).strip()
    resolved_ref = (ref or os.environ.get("JOBBOT_REF") or DEFAULT_REF).strip() or DEFAULT_REF

    if resolved_source:
        if not resolved_source.startswith("wheel:"):
            return UpdateResult(
                ok=False,
                message=(
                    f"Unknown JOBBOT_SOURCE={resolved_source!r} "
                    "(use wheel:/path/to.whl)"
                ),
            )
        target = resolved_source.removeprefix("wheel:")
        if not Path(target).is_file():
            return UpdateResult(ok=False, message=f"wheel not found: {target}")
        pkg = target
        label = f"wheel {target}"
    else:
        pkg = f"git+{resolved_repo}@{resolved_ref}"
        label = pkg

    before = _path_install_stamp()
    env = os.environ.copy()
    uv_dir = str(Path(uv).parent)
    path = env.get("PATH", "")
    if uv_dir and uv_dir not in path.split(os.pathsep):
        env["PATH"] = uv_dir + os.pathsep + path

    cmd = [uv, "tool", "install", "--force", "--python", "3.12", pkg]
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell
            cmd,
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError as exc:
        return UpdateResult(ok=False, message=f"Failed to run uv: {exc}")

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        return UpdateResult(
            ok=False,
            message=f"uv tool install failed for {label}\n{detail}",
        )

    version_line = _read_version()
    after = _path_install_stamp()
    production = resolved_ref == DEFAULT_REF and not resolved_source
    if before and after and before == after:
        where = "production (main)" if production else label
        return UpdateResult(
            ok=True,
            message=f"Already on latest {where}.",
            version_line=version_line,
            already_latest=True,
        )

    extra = (
        "Replaced the jobbot executable on PATH from production (main)."
        if production
        else f"Replaced the jobbot executable on PATH from {label}."
    )
    return UpdateResult(
        ok=True,
        message=f"Updated JobBot from {label}. {extra}",
        version_line=version_line,
    )


def _read_version() -> str | None:
    jobbot = shutil.which("jobbot")
    if jobbot is None:
        return None
    try:
        out = subprocess.run(  # noqa: S603
            [jobbot, "version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return (out.stdout or "").strip() or None
