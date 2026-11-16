"""A folder of PDFs names new and conflicting role ids and does not write the profile."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.cli import run_cli
from jobbot.profile.importer_pdf import import_pdf_cv
from tests.fixtures.profile import sample_profile_dict


def test_a_repeated_pdf_conflicts_once_and_does_not_write(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    sample_cv_pdf: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ids = [item["id"] for item in import_pdf_cv(sample_cv_pdf).data["experience"]]
    raw = sample_profile_dict()
    raw["experience"][0]["id"] = ids[0]
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    folder = tmp_path / "docs"
    folder.mkdir()
    payload = sample_cv_pdf.read_bytes()
    (folder / "a.pdf").write_bytes(payload)
    (folder / "b.pdf").write_bytes(payload)
    (folder / "notes.txt").write_text("not a cv", encoding="utf-8")
    (folder / "scan.pdf").write_bytes(b"not a pdf")
    before = (tmp_path / "data" / "profile.yaml").read_bytes()
    monkeypatch.chdir(tmp_path)

    code = run_cli(["profile", "import-folder", str(folder)], standalone_mode=False)

    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.count(f"conflict: {ids[0]}") == 1
    for role_id in ids[1:]:
        assert captured.out.count(f"new: {role_id}") == 1
    assert "notes.txt" not in captured.out
    assert "unread: scan.pdf" in captured.err
    assert (tmp_path / "data" / "profile.yaml").read_bytes() == before
