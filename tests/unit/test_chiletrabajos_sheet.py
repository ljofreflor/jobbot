"""Chiletrabajos sheet: every field has a home or a reason, and no contact values (#293)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.jobs.eligibility import answer_key_refused, load_application_answers
from jobbot.models.candidate import Candidate
from jobbot.ops.pii_guard import scan_text
from jobbot.portals.chiletrabajos import (
    FIELDS,
    education_level,
    experience_bucket,
    experience_years,
    gender_label,
    render_chiletrabajos_sheet,
)
from jobbot.portals.profile_state import (
    AccountState,
    Drift,
    EvidenceKind,
    PortalProfileState,
    evaluate_portal,
    mark_updated,
)

NOW = datetime(2026, 10, 18, tzinfo=UTC)


def _candidate(*, years_end: str = "2026-01", degree: str = "Licenciatura en Letras") -> Candidate:
    return Candidate.model_validate(
        {
            "personal": {
                "name": "Ana Ejemplo",
                "headline": "Profesional",
                "email": "ana.ejemplo@example.com",
                "phone": "+56 9 8765 4321",
                "city": "Santiago",
            },
            "experience": [
                {
                    "id": "e1",
                    "company": "Organismo Ejemplo",
                    "title": "Profesional",
                    "start_date": "2022-01",
                    "end_date": years_end,
                }
            ],
            "education": [
                {
                    "id": "d1",
                    "institution": "Universidad Ejemplo",
                    "degree": degree,
                }
            ],
        }
    )


def test_every_field_has_a_home_or_an_explicit_reason() -> None:
    for field in FIELDS:
        assert field.home or field.needs_human
    labels = {field.label for field in FIELDS}
    for required in ("RUT", "Clave", "reCAPTCHA", "Referencias", "Género", "Comuna"):
        assert required in labels


def test_experience_and_education_land_in_the_portal_enums() -> None:
    candidate = _candidate()

    assert experience_bucket(experience_years(candidate.experience)) == "3-6"
    assert experience_bucket(0) == "Sin experiencia"
    assert experience_bucket(1) == "<2"
    assert experience_bucket(8) == "7-10"
    assert experience_bucket(12) == ">10"
    assert education_level(candidate.education) == "Universitaria"
    higher = _candidate(degree="Magíster en Letras")
    assert education_level(higher.education) == "Magíster"
    candidacy = _candidate(degree="Doctorado candidato")
    assert education_level(candidacy.education) is None


def test_the_last_month_worked_counts_as_experience() -> None:
    same_month = _candidate(years_end="2022-01")

    assert experience_years(same_month.experience) > 0
    assert experience_bucket(experience_years(same_month.experience)) == "<2"

    three_calendar_years = Candidate.model_validate(
        {
            **_candidate().model_dump(mode="json"),
            "experience": [
                {
                    "id": "e1",
                    "company": "Organismo Ejemplo",
                    "title": "Profesional",
                    "start_date": "2023-01",
                    "end_date": "2025-12",
                }
            ],
        }
    )
    assert experience_years(three_calendar_years.experience) == 3.0
    assert experience_bucket(experience_years(three_calendar_years.experience)) == "3-6"

    started_this_month = Candidate.model_validate(
        {
            **_candidate().model_dump(mode="json"),
            "experience": [
                {
                    "id": "e1",
                    "company": "Organismo Ejemplo",
                    "title": "Profesional",
                    "start_date": "2026-10",
                    "current": True,
                }
            ],
        }
    )
    years = experience_years(started_this_month.experience, today=NOW.date())
    assert experience_bucket(years) == "<2"


def test_desired_titles_do_not_answer_the_job_type_control() -> None:
    from jobbot.jobs.eligibility import ApplicationAnswers

    titles_only = render_chiletrabajos_sheet(
        _candidate(),
        ApplicationAnswers(desired_titles=["Profesional"]),
    )
    assert "Tipos de trabajo: [falta en el SST: job_types]" in titles_only

    typed = render_chiletrabajos_sheet(_candidate(), ApplicationAnswers(job_types=["full_time"]))
    assert "Tipos de trabajo: listo" in typed


def test_gender_outside_the_two_portal_options_stays_human() -> None:
    assert gender_label("female") == "Femenino"
    assert gender_label("male") == "Masculino"
    assert gender_label("prefer_not_to_say") is None
    assert gender_label("non_binary") is None

    from jobbot.jobs.eligibility import ApplicationAnswers

    text = render_chiletrabajos_sheet(
        _candidate(),
        ApplicationAnswers(identity={"gender_to_declare": "prefer_not_to_say"}),
    )
    assert "needs_human: el portal solo ofrece Masculino o Femenino" in text


def test_sheet_names_missing_preferences_and_hides_contact_values() -> None:
    from jobbot.jobs.eligibility import ApplicationAnswers

    text = render_chiletrabajos_sheet(_candidate(), ApplicationAnswers())

    for fact in ("comuna", "salary", "availability", "gender", "birth_date", "nationality"):
        assert f"[falta en el SST: {fact}]" in text
    assert "needs_human: no se guarda un identificador nacional" in text
    assert "ana.ejemplo@example.com" not in text
    assert "8765" not in text
    assert "Organismo Ejemplo" not in text
    assert scan_text(text, "sheet") == []


def test_a_national_id_is_still_refused(tmp_path: Path) -> None:
    assert answer_key_refused("rut")
    path = tmp_path / "application_answers.yaml"
    path.write_text("rut: no-se-guarda\n", encoding="utf-8")
    with pytest.raises(ValueError, match="rut"):
        load_application_answers(path)


def test_cv_section_is_covered_only_with_a_matching_hash() -> None:
    candidate = _candidate()
    state = PortalProfileState(
        portal="chiletrabajos",
        adapter="generic",
        account=AccountState.evidenced,
        sections=["cv"],
    )
    synced = mark_updated(
        state,
        sections=["cv"],
        evidence=EvidenceKind.receipt,
        by="manual",
        now=NOW,
        candidate=candidate,
        current_cv_sha256="abc",
    )
    view = evaluate_portal(synced, candidate, now=NOW, current_cv_sha256="abc")
    cv = view.sections[0]
    assert cv.status is Drift.in_sync
    assert cv.covered is True

    declared = mark_updated(
        state,
        sections=["cv"],
        evidence=EvidenceKind.none,
        by="manual",
        now=NOW,
        candidate=candidate,
        current_cv_sha256="abc",
    )
    blank = evaluate_portal(declared, candidate, now=NOW, current_cv_sha256="abc")
    assert blank.sections[0].status is Drift.unknown
    assert blank.sections[0].covered is False


def test_cli_sheet_hides_contact_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    profile = _candidate().model_dump(mode="json")
    (data / "profile.yaml").write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli

    code = run_cli(["portals", "profile", "sheet", "chiletrabajos"], standalone_mode=False)
    out = capsys.readouterr().out

    assert code == SUCCESS
    assert "[falta en el SST: salary]" in out
    assert "8765" not in out
    assert scan_text(out, "sheet") == []

    (data / "application_answers.yaml").write_text("run: no-se-guarda\n", encoding="utf-8")
    rejected = run_cli(["portals", "profile", "sheet", "chiletrabajos"], standalone_mode=False)
    assert rejected == VALIDATION_FAILURE
    assert "run" in capsys.readouterr().err
