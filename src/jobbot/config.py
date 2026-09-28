"""Configuration loading for JobBot."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PROFILE = Path("data/profile.yaml")
DEFAULT_GENERATED_PROFILE = Path("data/profile.generated.yaml")
DEFAULT_OUTPUT = Path("output")
DEFAULT_TEMPLATES = Path("templates")
DEFAULT_DB = Path("data/jobbot.sqlite")
DEFAULT_PORTALS = Path("data/portals.yaml")
DEFAULT_COMPANIES = Path("data/companies.yaml")
DEFAULT_BROWSER_DATA = Path("browser-data")
DEFAULT_COUNTRIES: tuple[str, ...] = ("CL",)
DEFAULT_MAX_AGE_DAYS = 30

CONFIG_FILENAME = ".jobbot.toml"
ENV_ROOT = "JOBBOT_ROOT"


@dataclass(frozen=True)
class PathsConfig:
    profile: Path = DEFAULT_PROFILE
    generated_profile: Path = DEFAULT_GENERATED_PROFILE
    output: Path = DEFAULT_OUTPUT
    templates: Path = DEFAULT_TEMPLATES
    database: Path = DEFAULT_DB
    portals: Path = DEFAULT_PORTALS
    companies: Path = DEFAULT_COMPANIES
    browser_data: Path = DEFAULT_BROWSER_DATA
    legacy_cv: Path | None = None


@dataclass(frozen=True)
class SearchConfig:
    """Where we want to work; overridable per command with --country."""

    countries: tuple[str, ...] = DEFAULT_COUNTRIES
    allow_remote: bool = True
    max_age_days: int = DEFAULT_MAX_AGE_DAYS


@dataclass(frozen=True)
class JobbotConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    root: Path = field(default_factory=Path.cwd)
    search: SearchConfig = field(default_factory=SearchConfig)

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
    def portals_path(self) -> Path:
        return self._resolve(self.paths.portals)

    @property
    def companies_path(self) -> Path:
        return self._resolve(self.paths.companies)

    @property
    def browser_data_dir(self) -> Path:
        return self._resolve(self.paths.browser_data)

    @property
    def legacy_cv_path(self) -> Path | None:
        if self.paths.legacy_cv is None:
            return None
        return self._resolve(self.paths.legacy_cv)

    def browser_profile_dir(self, site: str) -> Path:
        """Per-site Chrome profile directory under browser_data."""
        return self.browser_data_dir / site

    def _resolve(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return (self.root / path).resolve()


def resolve_workspace(start: Path | None = None) -> Path:
    """
    Directory that owns the JobBot workspace.

    Order: ``JOBBOT_ROOT`` → walk-up for ``.jobbot.toml`` → cwd (legacy checkout).
    """
    env = os.environ.get(ENV_ROOT, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / CONFIG_FILENAME).is_file():
            return candidate
    return here


def _find_config_file(workspace: Path) -> Path | None:
    """Prefer workspace ``.jobbot.toml``; else XDG global (paths still vs workspace)."""
    local = workspace / CONFIG_FILENAME
    if local.is_file():
        return local
    xdg = Path.home() / ".config" / "jobbot" / "config.toml"
    if xdg.is_file():
        return xdg
    return None


def load_config(root: Path | None = None) -> JobbotConfig:
    """Load config from ``.jobbot.toml`` (walk-up / JOBBOT_ROOT) or XDG fallback."""
    base = root.expanduser().resolve() if root is not None else resolve_workspace()
    config_path = _find_config_file(base)
    if config_path is None:
        return JobbotConfig(root=base)

    with config_path.open("rb") as fh:
        raw = tomllib.load(fh)

    return JobbotConfig(
        paths=_load_paths(raw),
        root=base,
        search=_load_search(raw),
    )


def _load_paths(raw: dict[str, object]) -> PathsConfig:
    paths_raw = raw.get("paths")
    data: dict[str, object] = paths_raw if isinstance(paths_raw, dict) else {}
    legacy = data.get("legacy_cv")
    return PathsConfig(
        profile=Path(str(data.get("profile", DEFAULT_PROFILE))),
        generated_profile=Path(str(data.get("generated_profile", DEFAULT_GENERATED_PROFILE))),
        output=Path(str(data.get("output", DEFAULT_OUTPUT))),
        templates=Path(str(data.get("templates", DEFAULT_TEMPLATES))),
        database=Path(str(data.get("database", DEFAULT_DB))),
        portals=Path(str(data.get("portals", DEFAULT_PORTALS))),
        companies=Path(str(data.get("companies", DEFAULT_COMPANIES))),
        browser_data=Path(str(data.get("browser_data", DEFAULT_BROWSER_DATA))),
        legacy_cv=Path(str(legacy)) if legacy else None,
    )


def _load_search(raw: dict[str, object]) -> SearchConfig:
    """[search] countries/allow_remote, falling back to [indeed].country."""
    from jobbot.jobs.geo import normalize_countries

    section = raw.get("search")
    search_raw: dict[str, object] = section if isinstance(section, dict) else {}
    countries_raw = search_raw.get("countries")
    if isinstance(countries_raw, str):
        countries_raw = [countries_raw]
    if not isinstance(countries_raw, list):
        indeed = raw.get("indeed")
        indeed_raw: dict[str, object] = indeed if isinstance(indeed, dict) else {}
        legacy_country = indeed_raw.get("country")
        countries_raw = [legacy_country] if isinstance(legacy_country, str) else []
    countries = normalize_countries([str(c) for c in countries_raw]) or DEFAULT_COUNTRIES
    allow_remote = search_raw.get("allow_remote", True)
    raw_age = search_raw.get("max_age_days", DEFAULT_MAX_AGE_DAYS)
    max_age = int(raw_age) if isinstance(raw_age, int | float | str) else DEFAULT_MAX_AGE_DAYS
    return SearchConfig(
        countries=countries,
        allow_remote=bool(allow_remote),
        max_age_days=max_age,
    )
