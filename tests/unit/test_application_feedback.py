"""Pasted employer messages update an application. No inbox, no invented motive."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.models.application import ApplicationStatus
from jobbot.models.job import JobPosting


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def _store_job(session: object, *, title: str, company: str, status: ApplicationStatus) -> str:
    from jobbot.applications.manager import ApplicationRepository
    from jobbot.jobs.repository import JobRepository

    stored = JobRepository(session).upsert_external(  # type: ignore[arg-type]
        JobPosting(
            id="PENDING",
            source="manual",
            title=title,
            company=company,
            description="Un aviso ficticio.",
        )
    )
    ApplicationRepository(session).upsert_for_job(stored.id, status=status)  # type: ignore[arg-type]
    return stored.id


_EN_REJECTION = """\
Dear Candidate, Thank you for your application of the Consultant - Topic X \
position at Organization Neutra. This is to inform you that we have now completed \
the selection process and your candidature was not retained at this time. \
Please update the preference section of your online profile if you wish to \
receive job posting notifications.
Write to persona@example.com or +56 9 8765 4321.
"""

_ES_REJECTION = """\
Hola. Gracias por postular al cargo Analista de turnos en Bolsa Neutra.
Lamentamos informar que no has sido seleccionado para continuar.
persona@example.com +56 9 8765 4321
"""

_INTERVIEW = """\
We invite you to an interview on 2026-11-02 for the cargo Analista de turnos \
en Bolsa Neutra.
"""

_ACK = """\
We have received your application for the cargo Analista de turnos en Bolsa Neutra.
Thank you for applying.
"""


def test_english_rejection_proposes_an_external_posting_and_a_preference_action() -> None:
    from jobbot.applications.feedback import FeedbackKind, read_feedback

    reading = read_feedback(_EN_REJECTION, [], [])

    assert reading.kind is FeedbackKind.REJECTED_NO_INTERVIEW
    assert reading.evidence == "not retained"
    assert reading.job_id == ""
    assert reading.title == "Consultant - Topic X"
    assert reading.employer == "Organization Neutra"
    assert reading.actions == ("actualizar preferencias del perfil en el portal",)
    assert "persona@example.com" not in " ".join(reading.lines())
    assert "+56" not in " ".join(reading.lines())


def test_spanish_rejection_links_the_stored_posting(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli
    from jobbot.applications.feedback import read_feedback
    from jobbot.applications.manager import ApplicationRepository
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    job_id = _store_job(
        session,
        title="Analista de turnos",
        company="Bolsa Neutra",
        status=ApplicationStatus.APPLIED,
    )
    reading = read_feedback(
        _ES_REJECTION,
        JobRepository(session).list_all(),
        ApplicationRepository(session).list_all(),
    )
    assert reading.job_id == job_id
    assert reading.next_status == "rejected"


def test_feedback_apply_writes_rejected_and_keeps_contact_in_local_only(
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

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    _store_job(
        session,
        title="Analista de turnos",
        company="Bolsa Neutra",
        status=ApplicationStatus.APPLIED,
    )
    path = tmp_path / "mensaje.txt"
    path.write_text(_ES_REJECTION, encoding="utf-8")
    before = ApplicationRepository(session).list_all()[0].status

    dry = run_cli(["applications", "feedback", "--file", str(path)], standalone_mode=False)
    assert dry == SUCCESS
    session.expire_all()
    assert ApplicationRepository(session).list_all()[0].status is before
    assert not (tmp_path / ".local").exists()

    code = run_cli(
        ["applications", "feedback", "--file", str(path), "--apply"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == SUCCESS
    assert "persona@example.com" not in captured.out
    assert "+56" not in captured.out
    session.expire_all()
    app = ApplicationRepository(session).list_all()[0]
    assert app.status is ApplicationStatus.REJECTED
    detail = ApplicationRepository(session).events_for(app.id)[-1].detail or ""
    assert "persona@example.com" not in detail
    stored = list((tmp_path / ".local" / "application-feedback").glob("*.txt"))
    assert stored
    text = stored[0].read_text(encoding="utf-8")
    assert "persona@example.com" not in text
    assert "[email]" in text
    assert "[phone]" in text


def test_interview_date_shows_on_status(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    _store_job(
        session,
        title="Analista de turnos",
        company="Bolsa Neutra",
        status=ApplicationStatus.APPLIED,
    )
    path = tmp_path / "entrevista.txt"
    path.write_text(_INTERVIEW, encoding="utf-8")
    assert (
        run_cli(
            ["applications", "feedback", "--file", str(path), "--apply"],
            standalone_mode=False,
        )
        == SUCCESS
    )
    capsys.readouterr()
    assert run_cli(["status"], standalone_mode=False) == SUCCESS
    out = capsys.readouterr().out
    assert "entrevista 2026-11-02" in out
    assert "Analista de turnos" in out


def test_acknowledgement_does_not_change_applied(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    import jobbot.cli as cli
    from jobbot.applications.manager import ApplicationRepository
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    _store_job(
        session,
        title="Analista de turnos",
        company="Bolsa Neutra",
        status=ApplicationStatus.APPLIED,
    )
    path = tmp_path / "acuse.txt"
    path.write_text(_ACK, encoding="utf-8")
    assert (
        run_cli(
            ["applications", "feedback", "--file", str(path), "--apply"],
            standalone_mode=False,
        )
        == SUCCESS
    )
    session.expire_all()
    assert ApplicationRepository(session).list_all()[0].status is ApplicationStatus.APPLIED


def test_rejection_does_not_replace_an_offer_without_yes(
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

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    _store_job(
        session,
        title="Analista de turnos",
        company="Bolsa Neutra",
        status=ApplicationStatus.OFFER,
    )
    path = tmp_path / "rechazo.txt"
    path.write_text(_ES_REJECTION, encoding="utf-8")
    code = run_cli(
        ["applications", "feedback", "--file", str(path), "--apply"],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    session.expire_all()
    assert ApplicationRepository(session).list_all()[0].status is ApplicationStatus.OFFER
    capsys.readouterr()
    assert (
        run_cli(
            ["applications", "feedback", "--file", str(path), "--apply", "--yes"],
            standalone_mode=False,
        )
        == SUCCESS
    )
    session.expire_all()
    assert ApplicationRepository(session).list_all()[0].status is ApplicationStatus.REJECTED


def test_report_counts_three_fictional_events(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli

    messages = {
        "en.txt": _EN_REJECTION,
        "es.txt": _ES_REJECTION,
        "iv.txt": _INTERVIEW,
    }
    for name, body in messages.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
        assert (
            run_cli(
                ["applications", "feedback", "--file", str(tmp_path / name), "--apply"],
                standalone_mode=False,
            )
            == SUCCESS
        )
    capsys.readouterr()
    assert run_cli(["applications", "report"], standalone_mode=False) == SUCCESS
    out = capsys.readouterr().out
    assert "Consultant - Topic X" in out
    assert "Analista de turnos" in out
    assert "entrevistas" in out
    assert "| 1 |" in out
