"""A preference or a working condition is not stored as a missing skill."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.cli import run_cli
from tests.fixtures.profile import sample_profile_dict


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(sample_profile_dict(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_a_preference_does_not_edit_the_profile(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    before = (tmp_path / "data" / "profile.yaml").read_bytes()

    code = run_cli(
        ["profile", "rejection", "--text", "Podría hacerlo, pero no quiero"],
        standalone_mode=False,
    )

    assert code == 0
    assert "preference: profile unchanged" in capsys.readouterr().out
    assert (tmp_path / "data" / "profile.yaml").read_bytes() == before


def test_a_schedule_is_a_condition(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    code = run_cli(
        ["profile", "rejection", "--text", "No me sirve la jornada"],
        standalone_mode=False,
    )

    assert code == 0
    assert "conditions: profile unchanged" in capsys.readouterr().out


def test_a_missing_fact_is_experience_and_still_unwritten(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    before = (tmp_path / "data" / "profile.yaml").read_bytes()

    code = run_cli(
        ["profile", "rejection", "--text", "No tengo esa experiencia"],
        standalone_mode=False,
    )

    assert code == 0
    assert "experience: not written" in capsys.readouterr().out
    assert (tmp_path / "data" / "profile.yaml").read_bytes() == before


def test_an_unclear_note_is_not_a_gap(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    code = run_cli(
        ["profile", "rejection", "--text", "Lo pienso"],
        standalone_mode=False,
    )

    assert code == 0
    assert "unclear: profile unchanged" in capsys.readouterr().out
