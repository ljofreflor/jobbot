"""Configuration loading for JobBot."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PROFILE = Path("data/profile.yaml")
DEFAULT_GENERATED_PROFILE = Path("data/profile.generated.yaml")
DEFAULT_OUTPUT = Path("output")
DEFAULT_TEMPLATES = Path("templates")
DEFAULT_DB = Path("data/jobbot.sqlite")


@dataclass(frozen=True)
class PathsConfig:
    profile: Path = DEFAULT_PROFILE
    generated_profile: Path = DEFAULT_GENERATED_PROFILE
    output: Path = DEFAULT_OUTPUT
    templates: Path = DEFAULT_TEMPLATES
    database: Path = DEFAULT_DB
    legacy_cv: Path | None = None


@dataclass(frozen=True)
class JobbotConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    root: Path = field(default_factory=Path.cwd)

    @property
    def profile_path(self) -> Path:
        return self._resolve(self.paths.profile)

    @property
    def generated_profile_path(self) -> Path:
        return self._resolve(self.paths.generated_profile)

    @property
    def output_dir(self) -> Path:
        return self._resolve(self.paths.output)

    @property
    def templates_dir(self) -> Path:
        return self._resolve(self.paths.templates)

    @property
    def database_path(self) -> Path:
        return self._resolve(self.paths.database)

    @property
    def legacy_cv_path(self) -> Path | None:
        if self.paths.legacy_cv is None:
            return None
        return self._resolve(self.paths.legacy_cv)

    def _resolve(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return (self.root / path).resolve()


def _find_config_file(start: Path) -> Path | None:
    candidates = [
        start / ".jobbot.toml",
        Path.home() / ".config" / "jobbot" / "config.toml",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def load_config(root: Path | None = None) -> JobbotConfig:
    """Load config from .jobbot.toml or ~/.config/jobbot/config.toml."""
    base = (root or Path.cwd()).resolve()
    config_path = _find_config_file(base)
    if config_path is None:
        return JobbotConfig(root=base)

    with config_path.open("rb") as fh:
        raw = tomllib.load(fh)

    paths_raw = raw.get("paths", {})
    legacy = paths_raw.get("legacy_cv")
    paths = PathsConfig(
        profile=Path(paths_raw.get("profile", str(DEFAULT_PROFILE))),
        generated_profile=Path(
            paths_raw.get("generated_profile", str(DEFAULT_GENERATED_PROFILE))
        ),
        output=Path(paths_raw.get("output", str(DEFAULT_OUTPUT))),
        templates=Path(paths_raw.get("templates", str(DEFAULT_TEMPLATES))),
        database=Path(paths_raw.get("database", str(DEFAULT_DB))),
        legacy_cv=Path(legacy) if legacy else None,
    )
    return JobbotConfig(paths=paths, root=base)
