"""An English overlay may only rephrase ids the base profile already has."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from jobbot.cli import run_cli
from jobbot.exit_codes import VALIDATION_FAILURE
from tests.fixtures.profile import sample_profile_dict


def _workspace(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch, raw: dict[str, Any]
) -> str:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    achievement = raw["experience"][0]["achievements"][0]
    achievement["text"] = "Cerré 40 turnos."
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return str(achievement["id"])


def test_unknown_overlay_id_is_exit_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch, sample_profile_dict())
    (tmp_path / "data" / "profile.en.yaml").write_text(
        yaml.safe_dump({"texts": {"ghost": "Closed 40 shifts."}}),
        encoding="utf-8",
    )
    before = (tmp_path / "data" / "profile.yaml").read_bytes()

    code = run_cli(["profile", "validate", "--lang", "en"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert "unknown id: ghost" in capsys.readouterr().err
    assert (tmp_path / "data" / "profile.yaml").read_bytes() == before


def test_changed_number_is_exit_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    achievement_id = _workspace(tmp_path, project_root, monkeypatch, sample_profile_dict())
    (tmp_path / "data" / "profile.en.yaml").write_text(
        yaml.safe_dump({"texts": {achievement_id: "Closed 45 shifts."}}),
        encoding="utf-8",
    )

    code = run_cli(["profile", "validate", "--lang", "en"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert f"{achievement_id}: number mismatch" in capsys.readouterr().err


def test_same_numbers_stay_valid(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    achievement_id = _workspace(tmp_path, project_root, monkeypatch, sample_profile_dict())
    (tmp_path / "data" / "profile.en.yaml").write_text(
        yaml.safe_dump({"texts": {achievement_id: "Closed 40 shifts."}}),
        encoding="utf-8",
    )
    before = (tmp_path / "data" / "profile.yaml").read_bytes()

    code = run_cli(["profile", "validate", "--lang", "en"], standalone_mode=False)

    captured = capsys.readouterr()
    assert code == 0
    assert "PROFILE VALID" in captured.out
    assert (tmp_path / "data" / "profile.yaml").read_bytes() == before
