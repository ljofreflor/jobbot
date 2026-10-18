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


class _Page:
    def __init__(self, *, has_file_input: bool = True) -> None:
        self.has_file_input = has_file_input
        self.url = "https://mail.example.test/compose"
        self.gotos: list[str] = []
        self.attached: list[tuple[str, str]] = []

    def goto(self, url: str, **_: object) -> None:
        self.url = url
        self.gotos.append(url)

    def wait_for_selector(self, selector: str, **_: object) -> None:
        if not self.has_file_input:
            msg = f"no hay {selector}"
            raise RuntimeError(msg)

    def set_input_files(self, selector: str, files: str) -> None:
        self.attached.append((selector, files))


class _Session:
    def __init__(self, page: _Page) -> None:
        self.page = page

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_apply_uploads_on_the_indeed_cv_page_and_writes_the_receipt(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    pdf = tmp_path / "cv.pdf"
    write_sample_cv(pdf)
    page = _Page()
    monkeypatch.setattr(IndeedAdapter, "_session", lambda _self: _Session(page))
    code = run_cli(
        ["indeed", "upload-cv", "--apply", "--cv", str(pdf)],
        standalone_mode=False,
    )
    capsys.readouterr()
    assert code == 0
    assert page.gotos == ["https://profile.indeed.com/resume"]
    assert page.attached == [('input[type="file"]', str(pdf))]
    receipt = yaml.safe_load(
        (tmp_path / "output" / "indeed" / "cv_receipt.yaml").read_text(encoding="utf-8")
    )
    assert receipt["sha256"] == file_sha256(pdf)
    assert receipt["variant"] == "base_es"

    def refuse_session(_self: IndeedAdapter) -> None:
        raise AssertionError("un CV ya vigente no se sube")

    monkeypatch.setattr(IndeedAdapter, "_session", refuse_session)
    again = run_cli(
        ["indeed", "upload-cv", "--apply", "--cv", str(pdf)],
        standalone_mode=False,
    )
    assert again == 0
    assert "CV ya vigente" in capsys.readouterr().out


def test_apply_refuses_a_page_without_the_cv_control(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    pdf = tmp_path / "cv.pdf"
    write_sample_cv(pdf)
    page = _Page(has_file_input=False)
    monkeypatch.setattr(IndeedAdapter, "_session", lambda _self: _Session(page))
    code = run_cli(
        ["indeed", "upload-cv", "--apply", "--cv", str(pdf)],
        standalone_mode=False,
    )
    assert code == 5
    assert page.attached == []
    assert not (tmp_path / "output" / "indeed" / "cv_receipt.yaml").exists()


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
