"""Reinstall / upgrade the ``jobbot`` executable on PATH."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_REPO = "https://github.com/ljofreflor/jobbot"
DEFAULT_REF = "main"


@dataclass(frozen=True)
class UpdateResult:
    ok: bool
    message: str
    version_line: str | None = None


def _in_docker() -> bool:
    if Path("/.dockerenv").is_file():
        return True
    cgroup = Path("/proc/1/cgroup")
    if cgroup.is_file():
        text = cgroup.read_text(encoding="utf-8", errors="replace")
        return "docker" in text or "containerd" in text
    return False


def update_jobbot(
    *,
    ref: str | None = None,
    repo: str | None = None,
    source: str | None = None,
) -> UpdateResult:
    """
    Upgrade the uv-tool install of JobBot (same path as ``scripts/install.sh``).

    ``JOBBOT_REF`` / ``JOBBOT_REPO`` / ``JOBBOT_SOURCE`` env vars apply when args
    are omitted. Inside Docker, returns a pull hint instead of mutating the image.
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

    uv = shutil.which("uv")
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
    resolved_ref = (ref or os.environ.get("JOBBOT_REF") or DEFAULT_REF).strip()

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

    cmd = [uv, "tool", "install", "--force", "--python", "3.12", pkg]
    try:
        completed = subprocess.run(  # noqa: S603 — fixed argv, no shell
            cmd,
            check=False,
            capture_output=True,
            text=True,
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
    return UpdateResult(
        ok=True,
        message=f"Updated JobBot from {label}",
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
