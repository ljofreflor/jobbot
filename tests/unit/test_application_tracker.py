"""A stored job is saved until application status --set writes a row."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.applications.tracker import TrackerError, parse_status, status_label
from jobbot.exit_codes import SUCCESS, USER_CANCEL, VALIDATION_FAILURE
from jobbot.models.application import ApplicationStatus
from jobbot.models.job import JobPosting


def test_parse_status_maps_saved_and_rejects_unknown() -> None:
    assert parse_status("saved") is ApplicationStatus.DISCOVERED
    assert parse_status("Interview") is ApplicationStatus.INTERVIEW
    with pytest.raises(TrackerError):
        parse_status("nope")
    assert status_label(None) == "saved"


def test_tracker_lists_saved_jobs_and_set_confirms_applied(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli
    from jobbot.applications.manager import ApplicationRepository
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    JobRepository(session).save(
        JobPosting(
            id="J0002",
            title="Segundo aviso",
            company="Otro Servicio",
            url="https://boards.example/jobs/2",
            description="Aviso.",
        )
    )
    JobRepository(session).save(
        JobPosting(
            id="J0001",
            title="Analista",
            company="Servicio Neutro",
            url="https://boards.example/jobs/1",
            description="Aviso.",
            note="llamar el jueves",
        )
    )

    listed = run_cli(["application", "tracker"], standalone_mode=False)
    assert listed == SUCCESS
    output = capsys.readouterr().out
    assert output.index("J0001  saved") < output.index("J0002  saved")
    assert "llamar el jueves" in output
    assert config.database_path.is_relative_to(tmp_path)

    monkeypatch.setattr("typer.confirm", lambda *_a, **_k: False)
    denied = run_cli(["application", "status", "J0001", "--set", "applied"], standalone_mode=False)
    assert denied == USER_CANCEL
    assert ApplicationRepository(session).get_for_job("J0001") is None
    capsys.readouterr()

    moved = run_cli(
        ["application", "status", "J0001", "--set", "interview", "--yes"],
        standalone_mode=False,
    )
    assert moved == SUCCESS
    assert "J0001  interview" in capsys.readouterr().out
    assert (
        run_cli(
            ["application", "tracker", "--status", "interview"],
            standalone_mode=False,
        )
        == SUCCESS
    )
    filtered_out = capsys.readouterr().out
    assert "J0001  interview" in filtered_out
    assert "J0002" not in filtered_out

    unknown = run_cli(["application", "status", "J0001", "--set", "nope"], standalone_mode=False)
    assert unknown == VALIDATION_FAILURE
    bad_filter = run_cli(["application", "tracker", "--status", "nope"], standalone_mode=False)
    assert bad_filter == VALIDATION_FAILURE


def test_dry_run_apply_does_not_write_a_status(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli
    from jobbot.applications.manager import ApplicationRepository
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    def fail_confirm(*_a: object, **_k: object) -> bool:
        raise AssertionError("dry-run must not ask")

    monkeypatch.setattr("typer.confirm", fail_confirm)
    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    JobRepository(session).save(
        JobPosting(
            id="J0001",
            title="Analista",
            company="Servicio Neutro",
            url="https://boards.greenhouse.io/acme/jobs/1",
            description="Un aviso.",
        )
    )

    dry = run_cli(["application", "apply", "J0001"], standalone_mode=False)
    assert dry == SUCCESS
    assert ApplicationRepository(session).get_for_job("J0001") is None


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
