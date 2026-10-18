"""Indeed PDF upload: same hash is already current; icon glyphs are refused."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.adapters.indeed.client import IndeedAdapter
from jobbot.adapters.indeed.cv_upload import file_sha256
from jobbot.cli import run_cli
from tests.fixtures.cv_pdf import SubsetFont, write_sample_cv, write_subset_font_cv


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    example = project_root / "data" / "profile.example.yaml"
    (data / "profile.yaml").write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_same_hash_does_not_upload(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    pdf = tmp_path / "cv.pdf"
    write_sample_cv(pdf)
    receipt = tmp_path / "output" / "indeed" / "cv_receipt.yaml"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        yaml.safe_dump({"sha256": file_sha256(pdf), "variant": "base_es"}),
        encoding="utf-8",
    )

    def refuse_session(_self: IndeedAdapter) -> None:
        raise AssertionError("un CV ya vigente no se sube")

    monkeypatch.setattr(IndeedAdapter, "_session", refuse_session)
    code = run_cli(
        ["indeed", "upload-cv", "--apply", "--cv", str(pdf)],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "CV ya vigente" in captured.out


def test_icon_glyphs_are_refused(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    pdf = tmp_path / "icons.pdf"
    font = SubsetFont(
        name="F1",
        base_font="AAAAAA+Wingdings",
        widths={65: 600, 66: 600, 67: 600, 68: 600},
        to_unicode={65: "\uf0b7", 66: "\uf0b8", 67: "\uf0b9", 68: "\uf0ba"},
    )
    write_subset_font_cv(pdf, [font], [("F1", "ABCD")])
    code = run_cli(["indeed", "upload-cv", "--cv", str(pdf)], standalone_mode=False)
    captured = capsys.readouterr()
    assert code == 2
    assert "glyphs" in captured.err
