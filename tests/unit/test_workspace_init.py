"""Cold-install workspace: discovery, init, .local paths."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from jobbot.config import CONFIG_FILENAME, load_config, resolve_workspace
from jobbot.workspace import WorkspaceExistsError, init_workspace


def test_resolve_workspace_walks_up_to_jobbot_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "postulaciones"
    nested = root / "notas" / "hoy"
    nested.mkdir(parents=True)
    (root / CONFIG_FILENAME).write_text("[search]\ncountries = [\"CL\"]\n", encoding="utf-8")
    monkeypatch.delenv("JOBBOT_ROOT", raising=False)
    monkeypatch.chdir(nested)
    assert resolve_workspace() == root.resolve()


def test_resolve_workspace_honours_jobbot_root_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("JOBBOT_ROOT", str(elsewhere))
    monkeypatch.chdir(tmp_path)
    assert resolve_workspace() == elsewhere.resolve()


def test_init_creates_local_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "postulaciones"
    result = init_workspace(target)
    assert result.root == target.resolve()
    assert (target / CONFIG_FILENAME).is_file()
    assert (target / ".local" / "profile.yaml").is_file()
    assert (target / ".local" / "portals.yaml").is_file()
    assert (target / ".local" / "companies.yaml").is_file()
    assert (target / ".local" / "templates" / "cv_ats.txt.j2").is_file()
    assert (target / ".local" / "output").is_dir()
    assert (target / ".local" / "browser-data").is_dir()

    monkeypatch.delenv("JOBBOT_ROOT", raising=False)
    monkeypatch.chdir(target)
    config = load_config()
    assert config.root == target.resolve()
    assert config.profile_path == (target / ".local" / "profile.yaml").resolve()
    assert config.database_path == (target / ".local" / "jobbot.sqlite").resolve()
    assert config.output_dir == (target / ".local" / "output").resolve()
    assert config.portals_path == (target / ".local" / "portals.yaml").resolve()
    assert config.companies_path == (target / ".local" / "companies.yaml").resolve()
    assert config.browser_data_dir == (target / ".local" / "browser-data").resolve()


def test_init_refuses_overwrite_without_force(tmp_path: Path) -> None:
    target = tmp_path / "ws"
    init_workspace(target)
    with pytest.raises(WorkspaceExistsError):
        init_workspace(target)


def test_legacy_cwd_without_toml_keeps_data_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JOBBOT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    config = load_config()
    assert config.root == tmp_path.resolve()
    assert config.profile_path == (tmp_path / "data" / "profile.yaml").resolve()
    assert config.output_dir == (tmp_path / "output").resolve()
    assert "JOBBOT_ROOT" not in os.environ
