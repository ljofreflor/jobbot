"""Active portals this workspace has not integrated yet. Nothing here writes the profile."""

from __future__ import annotations

from pathlib import Path

import yaml

from jobbot.companies.registry import CompanyRegistry, active_career_sites
from jobbot.companies.urls import canonical_key


def integration_log_path(output_dir: Path) -> Path:
    return output_dir / "cv" / "integration_log.yaml"


def load_seen(path: Path) -> set[str]:
    """Canonical keys already integrated. A missing or odd file is an empty log."""
    if not path.is_file():
        return set()
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return set()
    if not isinstance(loaded, dict) or not isinstance(loaded.get("seen"), list):
        return set()
    seen: set[str] = set()
    for item in loaded["seen"]:
        if isinstance(item, str) and item.strip():
            seen.add(canonical_key(item))
    return seen


def unseen_active_portals(registry: CompanyRegistry, seen: set[str]) -> list[tuple[str, str]]:
    """Active career sites whose canonical URL is not in the log. Candidates stay out."""
    found: list[tuple[str, str]] = []
    for record, site in active_career_sites(registry):
        if site.key in seen:
            continue
        found.append((record.name, site.url))
    return found


def format_new_portals(portals: list[tuple[str, str]]) -> list[str]:
    if not portals:
        return ["no new portals"]
    return [f"new: {name} {url}" for name, url in portals]
