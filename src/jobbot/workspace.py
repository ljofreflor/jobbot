"""Cold-start workspace: ``jobbot init`` → ``.local/`` layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jobbot.config import CONFIG_FILENAME
from jobbot.resources import copy_templates, resource_text

INIT_TOML = """\
# JobBot workspace — sync this whole folder (including .local/) with any vendor.
# The `jobbot` executable is installed globally; this directory is your data.

[paths]
profile = ".local/profile.yaml"
generated_profile = ".local/profile.generated.yaml"
database = ".local/jobbot.sqlite"
output = ".local/output"
templates = ".local/templates"
portals = ".local/portals.yaml"
companies = ".local/companies.yaml"
browser_data = ".local/browser-data"

[search]
countries = ["CL"]
allow_remote = true
max_age_days = 30
"""


@dataclass(frozen=True)
class InitResult:
    root: Path
    created: tuple[Path, ...]
    forced: bool = False


class WorkspaceExistsError(FileExistsError):
    """``.jobbot.toml`` already present and ``--force`` was not set."""


def init_workspace(target: Path, *, force: bool = False) -> InitResult:
    """
    Create a portable postulaciones folder with ``.local/`` state.

    ``.jobbot.toml`` and ``.local/`` are always created **inside** ``target``
    (after ``expanduser`` + ``resolve``). Placement ignores ``JOBBOT_ROOT``,
    ``$HOME``, the package install dir, and git-root walk-up — seeds come from
    package resources, but the workspace folder is exactly ``target``.
    """
    root = target.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    marker = root / CONFIG_FILENAME
    if marker.is_file() and not force:
        raise WorkspaceExistsError(
            f"{marker} already exists (pass --force to overwrite seeds)"
        )

    local = root / ".local"
    output = local / "output"
    browser = local / "browser-data"
    templates = local / "templates"
    for directory in (local, output, browser, templates):
        directory.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    marker.write_text(INIT_TOML, encoding="utf-8")
    written.append(marker)

    profile = local / "profile.yaml"
    profile.write_text(resource_text("profile.example.yaml"), encoding="utf-8")
    written.append(profile)

    portals = local / "portals.yaml"
    portals.write_text(resource_text("portals.example.yaml"), encoding="utf-8")
    written.append(portals)

    companies = local / "companies.yaml"
    companies.write_text(resource_text("companies.example.yaml"), encoding="utf-8")
    written.append(companies)

    written.extend(copy_templates(templates))
    return InitResult(root=root, created=tuple(written), forced=force)
