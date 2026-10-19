"""A derived English phrase keeps the source figure, the company name, and no new skill."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.cli import run_cli
from jobbot.exit_codes import VALIDATION_FAILURE
from tests.fixtures.profile import sample_profile_dict


def _workspace(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    phrase: str | None,
) -> str:
    raw = sample_profile_dict()
    raw["experience"][0]["company"] = "Servicio Neutro"
    achievement = raw["experience"][0]["achievements"][0]
    achievement["text"] = "Cerré 30% en Servicio Neutro."
    raw["skills"]["programming"] = ["Ventilación mecánica"]
    (tmp_path / "data").mkdir()
    (tmp_path / "output" / "cv").mkdir(parents=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    if phrase is not None:
        (tmp_path / "output" / "cv" / "en.yaml").write_text(
            yaml.safe_dump({"texts": {achievement["id"]: phrase}}, allow_unicode=True),
            encoding="utf-8",
        )
    monkeypatch.chdir(tmp_path)
    return str(achievement["id"])


def test_a_missing_translation_keeps_the_source(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch, None)
    before = (tmp_path / "data" / "profile.yaml").read_bytes()

    code = run_cli(["cv", "translate", "--lang", "en"], standalone_mode=False)

    assert code == 0
    assert "no translation; the source text stays" in capsys.readouterr().out
    assert (tmp_path / "data" / "profile.yaml").read_bytes() == before


def test_the_same_figure_and_name_pass(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch, "Closed 30% at Servicio Neutro.")

    code = run_cli(["cv", "translate", "--lang", "en"], standalone_mode=False)

    assert code == 0
    assert "translation keeps the source" in capsys.readouterr().out


def test_a_changed_figure_is_exit_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    achievement_id = _workspace(
        tmp_path, project_root, monkeypatch, "Closed 40% at Servicio Neutro."
    )

    code = run_cli(["cv", "translate", "--lang", "en"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert f"{achievement_id}: number mismatch" in capsys.readouterr().err


def test_a_dropped_company_name_is_exit_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    achievement_id = _workspace(tmp_path, project_root, monkeypatch, "Closed 30% at the office.")

    code = run_cli(["cv", "translate", "--lang", "en"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert f"{achievement_id}: missing name" in capsys.readouterr().err


def test_an_added_skill_is_exit_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    achievement_id = _workspace(
        tmp_path,
        project_root,
        monkeypatch,
        "Closed 30% at Servicio Neutro with Ventilación mecánica.",
    )

    code = run_cli(["cv", "translate", "--lang", "en"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert f"{achievement_id}: extra skill" in capsys.readouterr().err
