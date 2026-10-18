"""CLI usage errors and --version must not register ops failures (#187)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from jobbot import __version__
from jobbot.db.engine import make_engine, make_session_factory
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.ops.failures import list_failures


def _session(tmp_path: Path) -> Session:
    engine = make_engine(tmp_path / "data" / "jobbot.sqlite")
    return make_session_factory(engine)()


def test_version_flags_print_version_without_ops_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobbot.cli import run_cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        "name: Test User\nemail: test@example.com\nexperience: []\n"
    )
    for flag in ("--version", "-V"):
        code = run_cli([flag], standalone_mode=False)
        assert code == SUCCESS
    session = _session(tmp_path)
    try:
        assert list_failures(session, limit=10) == []
    finally:
        session.close()


def test_bad_option_is_validation_not_ops_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobbot.cli import run_cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        "name: Test User\nemail: test@example.com\nexperience: []\n"
    )
    code = run_cli(["jobs", "add", "--no-existe"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    session = _session(tmp_path)
    try:
        assert list_failures(session, limit=10) == []
    finally:
        session.close()


def test_subcommand_without_args_shows_help_not_ops_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jobbot.cli import run_cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        "name: Test User\nemail: test@example.com\nexperience: []\n"
    )
    code = run_cli(["jobs"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    session = _session(tmp_path)
    try:
        assert list_failures(session, limit=10) == []
    finally:
        session.close()


def test_version_output_matches_package_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        "name: Test User\nemail: test@example.com\nexperience: []\n"
    )
    assert run_cli(["--version"], standalone_mode=False) == SUCCESS
    assert __version__ in capsys.readouterr().out
