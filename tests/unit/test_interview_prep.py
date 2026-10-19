"""Interview prep cites only what the application package already sent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobbot.applications.interview import cards_for, format_cards, load_sent_selection
from jobbot.cv.selection import SelectedAchievement, SelectionResult
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting


def _candidate() -> Candidate:
    return Candidate.model_validate(
        {
            "personal": {
                "name": "Ana Ejemplo",
                "headline": "Analista",
                "email": "ana.ejemplo@example.com",
            },
            "experience": [
                {
                    "id": "bodega",
                    "company": "Casa Ficticia",
                    "title": "Encargada de bodega",
                    "start_date": "2020-01",
                    "end_date": "2023-01",
                    "current": False,
                    "achievements": [
                        {
                            "id": "inventario",
                            "text": "Mantuve el inventario de bodega al día.",
                        },
                        {
                            "id": "contrato",
                            "text": "Lideré la negociación del contrato marco.",
                        },
                    ],
                }
            ],
        }
    )


def _job(*requirements: str) -> JobPosting:
    return JobPosting(
        id="J0001",
        title="Un cargo",
        company="Casa Ficticia",
        requirements=list(requirements),
    )


def _selection(*achievement_ids: str) -> SelectionResult:
    return SelectionResult(
        experience_ids=["bodega"],
        selected_achievements=[
            SelectedAchievement(id=item, reason=["sent"]) for item in achievement_ids
        ],
        skill_names=[],
    )


def test_sent_achievement_is_quoted_and_the_other_is_not() -> None:
    cards = cards_for(
        _job("inventario de bodega"),
        _candidate(),
        _selection("inventario"),
    )
    assert cards[0].evidence_id == "inventario"
    assert cards[0].evidence_text == "Mantuve el inventario de bodega al día."
    assert cards[0].bridge is None
    rendered = format_cards(cards)
    assert "negociación del contrato marco" not in rendered


def test_requirement_without_evidence_is_a_bridge_not_a_new_achievement() -> None:
    cards = cards_for(
        _job("presupuesto anual del area"),
        _candidate(),
        _selection("inventario"),
    )
    assert cards[0].evidence_id is None
    assert cards[0].bridge == "no lo ejercí; sí Encargada de bodega en Casa Ficticia"
    rendered = format_cards(cards)
    assert "presupuesto anual" in rendered
    assert "Lideré" not in rendered


def test_a_shared_generic_word_is_not_evidence() -> None:
    """'Experiencia' in both lines says nothing about the requirement itself."""
    candidate = Candidate.model_validate(
        {
            "personal": {
                "name": "Ana Ejemplo",
                "headline": "Analista",
                "email": "ana.ejemplo@example.com",
            },
            "experience": [
                {
                    "id": "bodega",
                    "company": "Casa Ficticia",
                    "title": "Encargada de bodega",
                    "start_date": "2020-01",
                    "end_date": "2023-01",
                    "current": False,
                    "achievements": [
                        {
                            "id": "turnos",
                            "text": "Experiencia coordinando turnos con el equipo de sala.",
                        }
                    ],
                }
            ],
        }
    )
    cards = cards_for(
        _job("Experiencia con el sistema XJ-90"),
        candidate,
        _selection("turnos"),
    )
    assert cards[0].evidence_id is None
    assert cards[0].bridge == "no lo ejercí; sí Encargada de bodega en Casa Ficticia"


def test_interview_command_reads_the_package_selection(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    import jobbot.cli as cli
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    stored = JobRepository(session).upsert_external(
        JobPosting(
            id="PENDING",
            title="Un cargo",
            company="Casa Ficticia",
            requirements=["inventario de bodega"],
        )
    )
    app_dir = config.output_dir / "jobs" / stored.id / "application"
    app_dir.mkdir(parents=True)
    (app_dir / "selection.json").write_text(
        json.dumps(
            {
                "experience_ids": ["exp-retail"],
                "selected_achievements": [{"id": "ach-wallet", "reason": ["sent"]}],
                "skill_names": [],
            }
        ),
        encoding="utf-8",
    )
    code = run_cli(["application", "interview", stored.id], standalone_mode=False)
    out = capsys.readouterr().out
    assert code == SUCCESS
    assert "inventario de bodega" in out
    assert "puente:" in out or "evidencia:" in out


def test_missing_selection_refuses_to_invent(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    import jobbot.cli as cli
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    stored = JobRepository(session).upsert_external(
        JobPosting(id="PENDING", title="Un cargo", company="Casa Ficticia")
    )
    code = run_cli(["application", "interview", stored.id], standalone_mode=False)
    err = capsys.readouterr().err
    assert code == VALIDATION_FAILURE
    assert "selection.json" in err


def test_load_sent_selection_keeps_only_ids(tmp_path: Path) -> None:
    path = tmp_path / "selection.json"
    path.write_text(
        json.dumps(
            {
                "experience_ids": ["bodega"],
                "selected_achievements": [{"id": "inventario", "reason": ["sent"]}],
                "skill_names": [],
                "extra": "ignored",
            }
        ),
        encoding="utf-8",
    )
    loaded = load_sent_selection(path)
    assert loaded.experience_ids == ["bodega"]
    assert [item.id for item in loaded.selected_achievements] == ["inventario"]
