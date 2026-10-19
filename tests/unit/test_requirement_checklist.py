"""A requirement the profile does not state stays [por confirmar]."""

from __future__ import annotations

from pathlib import Path

from jobbot.applications.checklist import render_requirement_checklist
from jobbot.applications.manager import prepare_application_package
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from tests.fixtures.profile import sample_profile_dict


def _candidate() -> Candidate:
    data = sample_profile_dict()
    data["skills"] = {"oficio": ["Ventilación mecánica"]}
    data["experience"] = [
        {
            "id": "role",
            "company": "Servicio Neutro",
            "title": "Analista",
            "start_date": "2020-01",
            "current": True,
            "achievements": [{"id": "a1", "text": "Cerré 12 turnos."}],
        }
    ]
    return Candidate.model_validate(data)


def _job() -> JobPosting:
    return JobPosting(
        id="J0001",
        title="Coordinador",
        company="Bolsa Neutra",
        description="",
        requirements=[
            "Experiencia en ventilación mecánica",
            "Cerré 12 turnos.",
            "Modelamiento estadístico",
        ],
    )


def test_a_gap_stays_unconfirmed_and_a_stated_skill_is_cited() -> None:
    text = render_requirement_checklist(_candidate(), _job())

    assert (
        "cumple: Experiencia en ventilación mecánica — el perfil dice «Ventilación mecánica»"
        in text
    )
    assert "cumple: Cerré 12 turnos. — el perfil dice «Cerré 12 turnos.»" in text
    assert "[por confirmar]: Modelamiento estadístico" in text
    assert "cumple: Modelamiento estadístico" not in text


def test_prepare_writes_the_checklist_and_leaves_the_profile_alone(tmp_path: Path) -> None:
    candidate = _candidate()
    before = candidate.model_dump()
    app_dir = prepare_application_package(_job(), tmp_path, candidate=candidate)

    written = (app_dir / "requirements.md").read_text(encoding="utf-8")
    assert "[por confirmar]: Modelamiento estadístico" in written
    assert candidate.model_dump() == before
