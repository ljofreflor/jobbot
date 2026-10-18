"""Cornerstone search stays blocked until a maintainer accepts the guest token."""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest
import yaml

from jobbot.cli import run_cli

SITE = "https://acme.csod.com/ux/ats/careersite/1/home?c=acme"


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    example = project_root / "data" / "profile.example.yaml"
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    (data / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_discover_refuses_without_opening_a_socket(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "cornerstone",
            "--site",
            "worldbankgroup",
            "--query",
            "health",
        ],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "requires session token" in captured.out
    assert "jobs add --file" in captured.out
    assert "bloqueado: token de sesión" in captured.out
    assert "bloqueado: robots" not in captured.out


def test_an_empty_site_is_rejected(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    code = run_cli(["jobs", "discover", "--source", "cornerstone"], standalone_mode=False)
    assert code == 2


def test_companies_learn_records_the_blocked_reason(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    code = run_cli(
        ["companies", "learn", SITE, "--company", "Ejemplo"],
        standalone_mode=False,
    )
    assert code == 0
    saved = yaml.safe_load((tmp_path / "data" / "companies.yaml").read_text(encoding="utf-8"))
    site = saved["companies"][0]["career_sites"][0]
    assert site["ats"] == "cornerstone"
    assert "discovery: blocked (requires session token)" in yaml.safe_dump(site)
