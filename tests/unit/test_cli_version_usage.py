"""``jobbot --version`` and usage errors must not pollute ops failures (#187)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from jobbot import __version__
from jobbot.cli import app, run_cli
from jobbot.db.engine import make_engine, make_session_factory
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.ops.failures import list_failures


def _seed_profile(root: Path) -> None:
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "profile.yaml").write_text(
        "personal:\n  name: Test User\nexperience: []\neducation: []\nskills: {}\n",
        encoding="utf-8",
    )


def test_cli_version_flag_prints_and_exits_zero() -> None:
    runner = CliRunner()
    for flag in ("--version", "-V"):
        outcome = runner.invoke(app, [flag])
        assert outcome.exit_code == 0, outcome.output
        assert outcome.stdout.strip() == __version__


def test_run_cli_version_flag_does_not_record_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_profile(tmp_path)
    code = run_cli(["--version"], standalone_mode=False)
    assert code == SUCCESS
    engine = make_engine(tmp_path / "data" / "jobbot.sqlite")
    session = make_session_factory(engine)()
    try:
        assert list_failures(session, status="new") == []
    finally:
        session.close()


def test_run_cli_unknown_option_is_validation_not_ops_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_profile(tmp_path)
    code = run_cli(["jobs", "add", "--no-existe"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    engine = make_engine(tmp_path / "data" / "jobbot.sqlite")
    session = make_session_factory(engine)()
    try:
        assert list_failures(session, status="new") == []
    finally:
        session.close()


def test_run_cli_bare_jobs_group_shows_help_without_ops_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed_profile(tmp_path)
    code = run_cli(["jobs"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    captured = capsys.readouterr()
    assert "shortlist" in captured.out.casefold() or "shortlist" in captured.err.casefold()
    assert "Unhandled error" not in captured.out
    assert "Unhandled error" not in captured.err
    engine = make_engine(tmp_path / "data" / "jobbot.sqlite")
    session = make_session_factory(engine)()
    try:
        assert list_failures(session, status="new") == []
    finally:
        session.close()
