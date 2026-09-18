"""Workspaces: one isolated home per candidate in a single checkout.

A checkout may hold several test CVs next to the real profile. Relying on the current
directory is not enough, because every workspace numbers its jobs from `J0001`: one
command run from the wrong folder overwrites another person's artifacts under the same
file names. So a workspace is selected explicitly (`--workspace`, `JOBBOT_WORKSPACE`)
and both its `data/` and its `output/` are stamped with a fingerprint of the profile
that owns them. A profile that does not match the stamp stops the command.

The stamp holds a hash, never a name: it must stay safe to sit next to gitignored data.
"""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

STAMP_NAME = ".jobbot-owner.json"
SANDBOXES_DIRNAME = "sandboxes"
DEFAULT_LABEL = "default"

_ENV_WORKSPACE = "JOBBOT_WORKSPACE"
_ENV_SANDBOXES = "JOBBOT_SANDBOXES"

_active: str | None = None


class WorkspaceOwnerError(Exception):
    """Raised when a profile does not own the data or output it was pointed at."""


@dataclass(frozen=True)
class OwnerStamp:
    """Who a `data/` or `output/` directory belongs to, as a fingerprint."""

    label: str
    fingerprint: str


def set_active_workspace(name: str | None) -> None:
    """Select the workspace for this process (the CLI's `--workspace`)."""
    global _active
    _active = name or None


def active_workspace() -> str | None:
    """Workspace chosen by the CLI flag, else by the environment."""
    if _active:
        return _active
    return os.environ.get(_ENV_WORKSPACE) or None


def repo_root() -> Path:
    """The checkout this package was imported from (`src/jobbot/workspace.py`)."""
    return Path(__file__).resolve().parents[2]


def sandboxes_dir() -> Path:
    """Where workspaces live: `<checkout>/sandboxes`, overridable for tests."""
    override = os.environ.get(_ENV_SANDBOXES)
    if override:
        return Path(override).expanduser().resolve()
    return repo_root() / SANDBOXES_DIRNAME


def workspace_root(name: str) -> Path:
    return sandboxes_dir() / name


def list_workspaces() -> list[str]:
    root = sandboxes_dir()
    if not root.is_dir():
        return []
    return sorted(entry.name for entry in root.iterdir() if entry.is_dir())


def resolve_root(cwd: Path) -> tuple[Path, str | None]:
    """Root for this run and the workspace name, when one was selected."""
    name = active_workspace()
    if name is None:
        return cwd.resolve(), None
    return workspace_root(name), name


def owner_fingerprint(name: str) -> str:
    """Stable hash of a candidate's name, accent- and case-insensitive."""
    folded = unicodedata.normalize("NFKD", name.strip().casefold())
    ascii_name = "".join(char for char in folded if not unicodedata.combining(char))
    collapsed = " ".join(ascii_name.split())
    return hashlib.sha256(collapsed.encode("utf-8")).hexdigest()[:16]


def read_stamp(path: Path) -> OwnerStamp | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    fingerprint = raw.get("fingerprint")
    if not isinstance(fingerprint, str):
        return None
    label = raw.get("label")
    return OwnerStamp(
        label=label if isinstance(label, str) else DEFAULT_LABEL,
        fingerprint=fingerprint,
    )


def write_stamp(path: Path, *, label: str, fingerprint: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "label": label,
        "fingerprint": fingerprint,
        "stamped_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def profile_owner(profile_path: Path) -> str | None:
    """`personal.name` read as plain YAML: no validation, no import cycle."""
    if not profile_path.is_file():
        return None
    try:
        import yaml

        raw = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - a broken profile is reported by the loader
        return None
    if not isinstance(raw, dict):
        return None
    personal = raw.get("personal")
    if not isinstance(personal, dict):
        return None
    name = personal.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def verify_owner(
    profile_path: Path,
    output_dir: Path,
    *,
    label: str,
) -> None:
    """Stamp `data/` and `output/` on first use, then refuse any other owner.

    Silent when there is no profile yet (a fresh clone) or when it carries no name.
    """
    owner = profile_owner(profile_path)
    if owner is None:
        return
    fingerprint = owner_fingerprint(owner)

    stamped = (
        (profile_path.parent / STAMP_NAME, "data"),
        (output_dir / STAMP_NAME, "output"),
    )
    for path, kind in stamped:
        stamp = read_stamp(path)
        if stamp is None:
            if kind == "data" or output_dir.is_dir():
                _stamp_quietly(path, label=label, fingerprint=fingerprint)
            continue
        if stamp.fingerprint != fingerprint:
            raise WorkspaceOwnerError(_mismatch_message(path, kind, profile_path, stamp, label))


def adopt(profile_path: Path, output_dir: Path, *, label: str) -> str | None:
    """Re-stamp both directories for the profile in use. Returns its fingerprint."""
    owner = profile_owner(profile_path)
    if owner is None:
        return None
    fingerprint = owner_fingerprint(owner)
    write_stamp(profile_path.parent / STAMP_NAME, label=label, fingerprint=fingerprint)
    if output_dir.is_dir():
        write_stamp(output_dir / STAMP_NAME, label=label, fingerprint=fingerprint)
    return fingerprint


def _mismatch_message(
    path: Path,
    kind: str,
    profile_path: Path,
    stamp: OwnerStamp,
    label: str,
) -> str:
    if stamp.label == label:
        origin = f"was created for another candidate: {path.parent}"
    else:
        origin = f"belongs to workspace '{stamp.label}': {path.parent}"
    return (
        f"This {kind} directory {origin}\n"
        f"The profile in use is {profile_path}.\n"
        "Pick the right workspace with --workspace, or take the directory over on "
        "purpose with `jobbot workspace adopt`."
    )


def _stamp_quietly(path: Path, *, label: str, fingerprint: str) -> None:
    """A read-only checkout must not break a command that only reads config."""
    try:
        write_stamp(path, label=label, fingerprint=fingerprint)
    except OSError:
        return
