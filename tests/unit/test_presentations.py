"""A presentation variant may not replace the headline or add a figure."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from jobbot.cli import run_cli
from jobbot.exit_codes import VALIDATION_FAILURE
from tests.fixtures.profile import sample_profile_dict


def _workspace(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    presentations: dict[str, Any],
) -> None:
    raw = sample_profile_dict()
    raw["experience"][0]["achievements"][0]["text"] = "Cerré 40 turnos."
    raw["presentations"] = presentations
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def _block(summary: str, variant: dict[str, Any]) -> dict[str, Any]:
    return {"fixed_sentence": summary, "variants": [variant]}


def test_a_headline_variant_is_exit_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = str(sample_profile_dict()["summary"])
    _workspace(
        tmp_path,
        project_root,
        monkeypatch,
        _block(summary, {"name": "acceso", "headline": "Otra frase"}),
    )
    before = (tmp_path / "data" / "profile.yaml").read_bytes()

    code = run_cli(["profile", "validate"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert "acceso: headline is not a variant" in capsys.readouterr().err
    assert (tmp_path / "data" / "profile.yaml").read_bytes() == before


def test_a_new_number_is_exit_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = str(sample_profile_dict()["summary"])
    _workspace(
        tmp_path,
        project_root,
        monkeypatch,
        _block(summary, {"name": "acceso", "summary_tail": "Cerré 99991 casos."}),
    )

    code = run_cli(["profile", "validate"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert "acceso: number mismatch" in capsys.readouterr().err


def test_a_fixed_sentence_that_is_not_the_prefix_is_exit_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(
        tmp_path,
        project_root,
        monkeypatch,
        _block("Otra frase.", {"name": "acceso", "summary_tail": "Sin cifras."}),
    )

    code = run_cli(["profile", "validate"], standalone_mode=False)

    assert code == VALIDATION_FAILURE
    assert "fixed_sentence is not a prefix of summary" in capsys.readouterr().err


def test_a_prefix_and_a_known_number_stay_valid(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    summary = str(sample_profile_dict()["summary"])
    _workspace(
        tmp_path,
        project_root,
        monkeypatch,
        _block(summary, {"name": "acceso", "summary_tail": "La misma cifra 40."}),
    )
    before = (tmp_path / "data" / "profile.yaml").read_bytes()

    code = run_cli(["profile", "validate"], standalone_mode=False)

    captured = capsys.readouterr()
    assert code == 0
    assert "PROFILE VALID" in captured.out
    assert "presentations:" not in captured.err
    assert (tmp_path / "data" / "profile.yaml").read_bytes() == before
