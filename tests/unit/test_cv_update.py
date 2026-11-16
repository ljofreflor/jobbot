"""cv update names active portals the workspace has not integrated."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.cli import run_cli
from tests.fixtures.profile import sample_profile_dict

_COMPANIES = {
    "version": 1,
    "companies": [
        {
            "id": "servicio",
            "name": "Servicio Neutro",
            "country": "CL",
            "career_sites": [
                {
                    "url": "https://careers.example.com/jobs",
                    "domain": "careers.example.com",
                    "status": "active",
                },
                {
                    "url": "https://careers.example.com/soon",
                    "domain": "careers.example.com",
                    "status": "candidate",
                },
            ],
        },
        {
            "id": "bolsa",
            "name": "Bolsa Neutra",
            "country": "CL",
            "career_sites": [
                {
                    "url": "https://bolsa.example.com/careers",
                    "domain": "bolsa.example.com",
                    "status": "active",
                }
            ],
        },
    ],
}


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(sample_profile_dict(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / "data" / "companies.yaml").write_text(
        yaml.safe_dump(_COMPANIES, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_an_unseen_active_portal_is_listed(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    log = tmp_path / "output" / "cv"
    log.mkdir()
    (log / "integration_log.yaml").write_text(
        "seen:\n  - https://bolsa.example.com/careers?utm=1\n",
        encoding="utf-8",
    )
    before = (tmp_path / "data" / "profile.yaml").read_bytes()

    code = run_cli(["cv", "update"], standalone_mode=False)

    out = capsys.readouterr().out
    assert code == 0
    assert "new: Servicio Neutro https://careers.example.com/jobs" in out
    assert "soon" not in out
    assert "Bolsa Neutra" not in out
    assert (tmp_path / "data" / "profile.yaml").read_bytes() == before


def test_every_active_portal_seen_prints_none(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    log = tmp_path / "output" / "cv"
    log.mkdir()
    (log / "integration_log.yaml").write_text(
        "seen:\n"
        "  - https://careers.example.com/jobs\n"
        "  - https://bolsa.example.com/careers\n",
        encoding="utf-8",
    )

    code = run_cli(["cv", "update"], standalone_mode=False)

    assert code == 0
    assert "no new portals" in capsys.readouterr().out
