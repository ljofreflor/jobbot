"""Impactpool stays unread: the terms forbid scraping, and it is a job board."""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest
import yaml

from jobbot.cli import run_cli
from jobbot.portals.detect import JOB_BOARD_KINDS, AtsKind, detect_ats

JOB = "https://www.impactpool.org/jobs/1238859"


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
        ["jobs", "discover", "--source", "impactpool", "--query", "health"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "no scraping without permission" in captured.out
    assert "2026-10-08" in captured.out
    assert "jobs add --file" in captured.out


def test_a_job_url_is_a_board_and_learn_does_not_store_an_employer(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    assert detect_ats(JOB) is AtsKind.IMPACTPOOL
    assert AtsKind.IMPACTPOOL in JOB_BOARD_KINDS
    code = run_cli(
        ["companies", "learn", JOB, "--company", "Ejemplo"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "Not company-specific" in captured.out
    assert not (tmp_path / "data" / "companies.yaml").exists()
