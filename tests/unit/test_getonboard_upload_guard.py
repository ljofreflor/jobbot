"""After a CV upload, a rewritten Get on Board profile is shown and offered back (#287)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jobbot.adapters.getonboard.cv_upload import FILE_INPUT, RESUMES_URL, SUBMIT_BUTTON
from jobbot.adapters.getonboard.profile_edit import FIELDS
from jobbot.exit_codes import SUCCESS

SPANISH = (
    "Soy parte del equipo y trabajo con la comunidad para mejorar "
    "el cuidado de las personas en el territorio."
)
ENGLISH = (
    "I am part of the team and I work with the community to improve "
    "care for the people in our area."
)
DESCRIPTION = FIELDS[0].selectors[0]


class _File:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    def count(self) -> int:
        return 1

    @property
    def first(self) -> _File:
        return self

    def set_input_files(self, files: str) -> None:
        self._page.uploaded.append(files)


class _Description:
    def __init__(self, page: FakePage) -> None:
        self._page = page

    def input_value(self) -> str:
        return self._page.description

    def inner_text(self) -> str:
        return self._page.description


class FakePage:
    def __init__(self, *, flip: bool) -> None:
        self.description = SPANISH
        self.flip = flip
        self.parsing_left = 2
        self.uploaded: list[str] = []
        self.url = "about:blank"
        self.filled: dict[str, str] = {}
        self.checked: list[str] = []

    def goto(self, url: str, **_: Any) -> None:
        self.url = url

    def wait_for_timeout(self, _timeout: float) -> None:
        return None

    def locator(self, selector: str) -> _File:
        assert selector == FILE_INPUT
        return _File(self)

    def fill(self, selector: str, value: str) -> None:
        self.filled[selector] = value

    def check(self, selector: str) -> None:
        self.checked.append(selector)

    def click(self, selector: str, **_: Any) -> None:
        if selector == SUBMIT_BUTTON and self.flip:
            self.description = ENGLISH
        self.url = RESUMES_URL

    def content(self) -> str:
        body = "<div class='resume-item'>CV base</div>"
        if self.parsing_left:
            self.parsing_left -= 1
            return f"Estamos leyendo tu último CV {body}"
        return body

    def query_selector(self, selector: str) -> _Description | None:
        if selector == DESCRIPTION:
            return _Description(self)
        return None


class _Session:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    pdf = tmp_path / "cv.pdf"
    pdf.write_bytes(b"%PDF-1.4\n" + b"x" * 200)
    monkeypatch.chdir(tmp_path)
    return pdf


def test_upload_apply_reports_an_english_overwrite_and_offers_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pdf = _workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "jobbot.cli._getonboard_session",
        lambda *_a, **_k: _Session(FakePage(flip=True)),
    )
    from jobbot.cli import run_cli
    from tests.conftest import plain_cli_text

    code = run_cli(
        ["getonboard", "upload-cv", "--apply", "--yes", "--cv", str(pdf)],
        standalone_mode=False,
    )
    out = plain_cli_text(capsys.readouterr().out)

    assert code == SUCCESS
    assert "Descripción profesional:" in out
    assert "quedó en inglés" in out
    assert "Restaurar" in out


def test_upload_apply_with_no_change_records_no_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pdf = _workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "jobbot.cli._getonboard_session",
        lambda *_a, **_k: _Session(FakePage(flip=False)),
    )
    from jobbot.cli import run_cli
    from tests.conftest import plain_cli_text

    code = run_cli(
        ["getonboard", "upload-cv", "--apply", "--yes", "--cv", str(pdf)],
        standalone_mode=False,
    )
    out = plain_cli_text(capsys.readouterr().out)
    receipt = (tmp_path / "output" / "getonboard" / "cv_upload_receipt.yaml").read_text(
        encoding="utf-8"
    )

    assert code == SUCCESS
    assert "quedó en inglés" not in out
    assert "sin sobrescritura" in out
    assert "sin sobrescritura" in receipt
