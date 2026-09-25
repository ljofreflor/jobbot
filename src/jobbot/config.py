"""Configuration loading for JobBot."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from jobbot.workspace import DEFAULT_LABEL, repo_root, resolve_root, verify_owner

DEFAULT_PROFILE = Path("data/profile.yaml")
DEFAULT_GENERATED_PROFILE = Path("data/profile.generated.yaml")
DEFAULT_OUTPUT = Path("output")
DEFAULT_TEMPLATES = Path("templates")
DEFAULT_DB = Path("data/jobbot.sqlite")
DEFAULT_COUNTRIES: tuple[str, ...] = ("CL",)
DEFAULT_MAX_AGE_DAYS = 30


@dataclass(frozen=True)
class PathsConfig:
    profile: Path = DEFAULT_PROFILE
    generated_profile: Path = DEFAULT_GENERATED_PROFILE
    output: Path = DEFAULT_OUTPUT
    templates: Path = DEFAULT_TEMPLATES
    database: Path = DEFAULT_DB
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
    def legacy_cv_path(self) -> Path | None:
        if self.paths.legacy_cv is None:
            return None
        return self._resolve(self.paths.legacy_cv)

    def _resolve(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return (self.root / path).resolve()


def _user_config_path() -> Path:
    return Path.home() / ".config" / "jobbot" / "config.toml"


def _default_data_home() -> Path:
    """Personal data root when JobBot is run outside a checkout with .jobbot.toml.

    Override with JOBBOT_HOME. Prefer XDG on Linux; fall back to ~/.jobbot.
    """
    import os

    override = os.environ.get("JOBBOT_HOME")
    if override:
        return Path(override).expanduser().resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser().resolve() / "jobbot"
    return (Path.home() / ".local" / "share" / "jobbot").resolve()


def _find_config_file(start: Path, *, workspace: str | None) -> Path | None:
    """A workspace reads only its own file: the global one may point at another candidate."""
    local = start / ".jobbot.toml"
    if local.is_file():
        return local
    if workspace is not None:
        return None
    user = _user_config_path()
    return user if user.is_file() else None


def _default_templates(workspace: str | None) -> Path:
    """Templates are code, so a workspace borrows the checkout's instead of its own."""
    if workspace is None:
        return DEFAULT_TEMPLATES
    return repo_root() / DEFAULT_TEMPLATES


def load_config(root: Path | None = None) -> JobbotConfig:
    """Load config for the active workspace, else for the current directory.

    Personal data can live outside the checkout: set ``JOBBOT_HOME`` (or put
    absolute paths in ``~/.config/jobbot/config.toml``). When ``JOBBOT_HOME`` is
    set and there is no local ``.jobbot.toml``, that directory is the root so a
    global ``jobbot`` on PATH does not write PII into the package tree.
    """
    import os

    if root is None:
        base, workspace = resolve_root(Path.cwd())
    else:
        base, workspace = root.resolve(), None
    config_path = _find_config_file(base, workspace=workspace)
    home_override = os.environ.get("JOBBOT_HOME")
    if (
        config_path is None
        and workspace is None
        and root is None
        and home_override
        and not (base / ".jobbot.toml").is_file()
    ):
        base = Path(home_override).expanduser().resolve()
        base.mkdir(parents=True, exist_ok=True)
        (base / "data").mkdir(exist_ok=True)
        (base / "output").mkdir(exist_ok=True)
        config_path = _find_config_file(base, workspace=None)

    if config_path is None:
        config = JobbotConfig(
            paths=PathsConfig(templates=_default_templates(workspace)),
            root=base,
        )
        _verify(config, workspace)
        return config

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
        templates=Path(paths_raw.get("templates", str(_default_templates(workspace)))),
        database=Path(paths_raw.get("database", str(DEFAULT_DB))),
        legacy_cv=Path(legacy) if legacy else None,
    )
    config = JobbotConfig(paths=paths, root=base, search=_load_search(raw))
    _verify(config, workspace)
    return config


def _verify(config: JobbotConfig, workspace: str | None) -> None:
    verify_owner(
        config.profile_path,
        config.output_dir,
        label=workspace or DEFAULT_LABEL,
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
