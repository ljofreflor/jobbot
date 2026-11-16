"""A low stored match warns before --apply. Dry-run does not ask."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.applications.preflight import below_threshold, threshold_percent
from jobbot.exit_codes import SUCCESS, USER_CANCEL, VALIDATION_FAILURE
from jobbot.models.job import JobPosting


def test_fraction_and_percent_are_the_same_bar() -> None:
    assert threshold_percent(0.7) == 70
    assert threshold_percent(70) == 70
    assert below_threshold(40, 70) is True
    assert below_threshold(40, threshold_percent(0.3)) is False
    assert below_threshold(70, 70) is False
    assert below_threshold(None, 70) is False


def test_apply_below_threshold_asks_and_a_no_leaves_the_profile(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    stored = JobRepository(session).upsert_external(
        JobPosting(
            id="PENDING",
            title="Analista",
            company="Servicio Neutro",
            url="https://boards.greenhouse.io/acme/jobs/1",
            description="- Manejo de WordPress",
            match_score=40,
        )
    )
    profile = tmp_path / "data" / "profile.yaml"
    before = profile.read_bytes()
    monkeypatch.setattr("typer.confirm", lambda *_a, **_k: False)

    code = run_cli(["application", "apply", stored.id, "--apply"], standalone_mode=False)

    assert code == USER_CANCEL
    out = capsys.readouterr().out
    assert "below" in out
    assert "WordPress" in out
    assert profile.read_bytes() == before


def test_yes_still_prints_the_warning_and_dry_run_does_not_ask(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    def fail_confirm(*_a: object, **_k: object) -> bool:
        raise AssertionError("dry-run must not ask")

    monkeypatch.setattr("typer.confirm", fail_confirm)
    monkeypatch.setattr("jobbot.browser.background.open_url", lambda url, **_k: url)
    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    stored = JobRepository(session).upsert_external(
        JobPosting(
            id="PENDING",
            title="Analista",
            company="Servicio Neutro",
            url="https://boards.greenhouse.io/acme/jobs/1",
            description="Un aviso.",
            match_score=40,
        )
    )

    dry = run_cli(["application", "apply", stored.id], standalone_mode=False)
    assert dry == SUCCESS
    assert "below" not in capsys.readouterr().out

    monkeypatch.setattr("typer.confirm", lambda *_a, **_k: False)
    warned = run_cli(
        ["application", "apply", stored.id, "--apply", "--yes", "--min-match", "0.7"],
        standalone_mode=False,
    )
    assert warned == SUCCESS
    assert "below" in capsys.readouterr().out


def test_invalid_min_match_exits_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli

    code = run_cli(
        ["application", "apply", "J0001", "--min-match", "101"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
