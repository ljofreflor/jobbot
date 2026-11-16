"""Laborum stays unread until the terms decision is recorded as allowed."""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest
import yaml

from jobbot.cli import run_cli


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
        ["jobs", "discover", "--source", "laborum", "--query", "coordinador"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "decisión de términos no está tomada" in captured.out
    assert "2026-10-08" in captured.out
    assert "jobs add --file" in captured.out
