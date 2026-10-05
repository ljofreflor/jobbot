"""Root CLI usage: --version exists; typos are not ops failures (#187)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot import __version__
from jobbot.db.engine import make_engine, make_session_factory
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.ops.failures import list_failures


def _failures(tmp_path: Path) -> list:
    db = tmp_path / "data" / "jobbot.sqlite"
    if not db.is_file():
        return []
    session = make_session_factory(make_engine(db))()
    try:
        return list_failures(session, status="new")
    finally:
        session.close()


def test_version_flag_prints_and_does_not_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    for flag in ("--version", "-V"):
        code = run_cli([flag], standalone_mode=False)
        assert code == SUCCESS, flag
        out = capsys.readouterr().out
        assert __version__ in out, flag
        assert _failures(tmp_path) == [], flag


def test_unknown_option_is_usage_not_an_ops_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    code = run_cli(["jobs", "add", "--no-existe"], standalone_mode=False)
    captured = capsys.readouterr()
    blob = f"{captured.out}\n{captured.err}"
    assert code == VALIDATION_FAILURE
    assert "no-existe" in blob.casefold() or "no such option" in blob.casefold()
    assert "Unhandled error" not in captured.err
    assert _failures(tmp_path) == []


def test_jobs_without_args_shows_help_and_does_not_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    code = run_cli(["jobs"], standalone_mode=False)
    captured = capsys.readouterr()
    blob = f"{captured.out}\n{captured.err}"
    assert code in {SUCCESS, VALIDATION_FAILURE}
    assert "Usage:" in blob or "usage:" in blob.casefold()
    assert "Unhandled error" not in captured.err
    assert _failures(tmp_path) == []


def test_real_command_exception_still_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobbot.cli import run_cli
    from jobbot.exit_codes import UI_CHANGED

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    code = run_cli(["probe-exit", str(UI_CHANGED)], standalone_mode=False)
    assert code == UI_CHANGED
    rows = _failures(tmp_path)
    assert len(rows) == 1
    assert rows[0].exit_code == UI_CHANGED
