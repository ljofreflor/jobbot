"""The matcher must not inflate a fit with loose words nor punish it with page noise (#179).

A public-health profile looking for non-academic roles saw a teaching post ranked
first: its headline (a list of degrees) counted as a title held, words from
different claims added up to a 'strong' match, page chrome (deadlines, links,
deliverable tables, legal footers) counted as missing requirements, and an English
posting could not be read against a Spanish profile. Every name here is fictitious.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jobbot.jobs.normalization import WordIndex
from jobbot.jobs.parsing import degree_fields, looks_like_page_metadata, parse_job_text
from jobbot.matching.analyzer import RuleBasedJobAnalyzer, requirement_evidence
from jobbot.matching.scoring import blind_matcher_warning, match_reasons
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.models.match import JobMatch, MatchStrength
from tests.fixtures.profile import surveillance_profile_dict

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "jobs"

TEACHING = "docente_vinculacion_medio_es.txt"
SURVEILLANCE = "surveillance_data_consultant_en.txt"
SALES = "kam_farmaceutico_es.txt"
WORKDAY = "workday_laboratory_officer_en.txt"


def _candidate(raw: dict[str, Any] | None = None) -> Candidate:
    return Candidate.model_validate(raw or surveillance_profile_dict())


def _job(name: str, job_id: str = "J0900") -> JobPosting:
    return parse_job_text((FIXTURES / name).read_text(encoding="utf-8"), job_id=job_id)


def _match(name: str, candidate: Candidate | None = None) -> JobMatch:
    return RuleBasedJobAnalyzer().analyze(candidate or _candidate(), _job(name))


def _missing(match: JobMatch) -> str:
    return " | ".join(item.label for item in match.by_strength(MatchStrength.MISSING))


def _role(match: JobMatch):
    return next(item for item in match.items if item.label.startswith("role:"))


def _profile(**overrides: Any) -> dict[str, Any]:
    raw = surveillance_profile_dict()
    raw.update(overrides)
    return raw


# ── ranking ──────────────────────────────────────────────────────────────────


def test_the_english_surveillance_consultancy_outranks_the_teaching_post() -> None:
    """Regression: a teaching post ranked first on the words of a degree headline."""
    scores = {name: _match(name).score for name in (TEACHING, SURVEILLANCE, SALES, WORKDAY)}

    assert scores[SURVEILLANCE] > scores[TEACHING]
    assert max(scores, key=lambda name: scores[name]) == SURVEILLANCE
    assert scores[SALES] < scores[TEACHING]


def test_the_surveillance_consultancy_is_read_across_languages() -> None:
    match = _match(SURVEILLANCE)
    strong = " | ".join(item.label for item in match.by_strength(MatchStrength.STRONG))

    assert "profile:Vigilancia epidemiológica" in strong
    assert "profile:Investigación de brotes" in strong
    assert _role(match).strength == MatchStrength.STRONG


# ── page chrome ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", [TEACHING, SURVEILLANCE, SALES, WORKDAY])
def test_page_chrome_is_never_a_missing_requirement(name: str) -> None:
    missing = _missing(_match(name))

    for chrome in (
        "Apply",
        "locations",
        "time type",
        "Posted",
        "R-104233",
        "Off Site",
        "P3",
        "Temporary Appointment",
        "USD",
        "Deadline",
        "Deliverable",
        "Product",
        "Value",
        "Total",
        "WHED",
        "IAU",
        "UNESCO",
        "www",
        "default.asp",
        "nces",
        "home.php",
        "e-Manual",
        "LinkedIn",
        "ReqID",
        "Síguenos",
        "facebook",
        "@uficticia",
        "Acerca de",
        "Descripción del cargo",
        "QUALIFICATIONS",
        "Jornada completa",
    ):
        assert chrome not in missing, (name, chrome)


def test_company_section_links_and_prose_acronyms_are_not_requirements() -> None:
    text = (
        "Title: Analista de Programas\n"
        "Company: Empresa Ficticia\n"
        "Acerca de Empresa Ficticia\n"
        "Somos una empresa con presencia en todo el país y valores claros.\n"
        "Síguenos en www.facebook.com/ficticia\n"
        "Funciones:\n"
        "El cargo exige coordinación con la ARS y el INSF para la ejecución del programa "
        "regional de atención primaria en comunas rurales.\n"
        "Requisitos:\n"
        "- Gestión de proyectos sociales.\n"
    )
    job = parse_job_text(text, job_id="J0901")
    skills = " | ".join(job.skills)

    for noise in ("Acerca", "Somos", "Síguenos", "www.facebook", "ARS", "INSF"):
        assert noise not in skills, noise
    assert "Gestión de proyectos sociales" in skills


def test_a_tool_named_in_prose_after_a_lead_in_is_still_read() -> None:
    text = (
        "Title: Analista\n"
        "El equipo busca una persona con experiencia en SAP y manejo de BigQuery para "
        "consolidar los reportes mensuales de todas las áreas de la empresa.\n"
    )

    skills = parse_job_text(text, job_id="J0902").skills

    assert "SAP" in skills
    assert "BigQuery" in skills


def test_public_board_row_labels_are_page_metadata() -> None:
    for label in ("TÍTULO AVISO", "Nº DE VACANTES", "CIUDAD", "RENTA BRUTA", "Rango 1-2-3-4", "N°"):
        assert looks_like_page_metadata(label), label
    for skill in ("Gestión de redes", "Rango dinámico", "SIVI"):
        assert not looks_like_page_metadata(skill), skill


def test_a_workday_label_takes_its_value_with_it() -> None:
    job = _job(WORKDAY)
    skills = " | ".join(job.skills)

    for value in ("Remote", "Full time", "Posted 30+ Days Ago", "Off Site", "Temporary"):
        assert value not in skills
    assert "Coordinate the regional laboratory network" in skills


# ── evidence comes from one claim ────────────────────────────────────────────


def _commercial_profile(degree: str) -> dict[str, Any]:
    raw = surveillance_profile_dict()
    raw["experience"][3]["title"] = "Ejecutiva comercial"
    raw["education"] = [
        {
            "id": "pregrado",
            "institution": "Universidad Ficticia del Sur",
            "degree": degree,
            "start_date": "2002-03",
            "end_date": "2007-12",
        }
    ]
    return raw


def test_a_degree_in_another_field_does_not_meet_a_degree_requirement() -> None:
    """'Ingeniería' from a degree plus 'comercial' from a job title is not that degree."""
    candidate = _candidate(_commercial_profile("Ingeniería en Alimentos"))

    evidence = requirement_evidence(candidate, "Título de Ingeniería Comercial")

    assert evidence is not None
    assert evidence[0] == MatchStrength.MISSING
    assert "degree not in profile" in evidence[1]


def test_the_same_degree_meets_the_degree_requirement() -> None:
    candidate = _candidate(_commercial_profile("Ingeniería Comercial"))

    evidence = requirement_evidence(candidate, "Título de Ingeniería Comercial")

    assert evidence is not None
    assert evidence[0] == MatchStrength.STRONG


def test_degree_fields_drop_filler_and_qualifiers() -> None:
    assert degree_fields("Título de Ingeniería Comercial o carrera afín.") == [
        "ingenieria comercial"
    ]
    accepted = degree_fields("Degree in veterinary medicine, epidemiology or public health")
    assert accepted == ["veterinary medicine", "epidemiology", "public health"]
    assert degree_fields("Título de Enfermera Universitaria con registro vigente.") == ["enfermera"]
    assert degree_fields("Ingeniería de datos en la nube") is None
    assert degree_fields("Experiencia en vigilancia epidemiológica") is None


def test_words_from_different_claims_are_only_partial() -> None:
    candidate = _candidate()

    evidence = requirement_evidence(candidate, "Coordinación de brotes hospitalarios")

    assert evidence is not None
    assert evidence[0] == MatchStrength.PARTIAL
    assert "Investigación de brotes" in evidence[1]
    assert "Coordinación interinstitucional" in evidence[1]


def test_two_words_of_one_claim_are_strong() -> None:
    evidence = requirement_evidence(_candidate(), "Coordinadora de laboratorios clínicos")

    assert evidence is not None
    assert evidence[0] == MatchStrength.STRONG
    assert "Coordinadora de Red de Laboratorios" in evidence[1]


def test_an_acronym_inside_a_compound_or_parentheses_is_evidence() -> None:
    candidate = _candidate()

    for acronym in ("SIVI", "PIZ"):
        evidence = requirement_evidence(candidate, acronym)
        assert evidence is not None, acronym
        assert evidence[0] == MatchStrength.STRONG, acronym
    assert requirement_evidence(candidate, "ZZTOP") is None


# ── the headline is not a title held ─────────────────────────────────────────


def test_a_degree_headline_does_not_make_a_teaching_post_a_held_role() -> None:
    raw = _profile(
        personal={
            "name": "Valeria Ejemplo Ficticia",
            "headline": "Doctor (c) en Ciencias Ficticias · Magíster en Gestión Ficticia",
            "country": "Chile",
        }
    )
    job = JobPosting(
        id="J0903",
        title="Docente de Magíster en Gestión Ficticia",
        company="Universidad Ficticia del Norte",
        description="Docencia de posgrado.",
    )

    role = _role(RuleBasedJobAnalyzer().analyze(_candidate(raw), job))

    assert role.strength != MatchStrength.STRONG
    assert "headline" in (role.detail or "")


def test_a_title_actually_held_still_makes_a_strong_role() -> None:
    job = JobPosting(
        id="J0904",
        title="Coordinadora de Red de Laboratorios",
        company="Instituto Ficticio",
        description="Coordinación de la red de laboratorios.",
    )

    assert _role(RuleBasedJobAnalyzer().analyze(_candidate(), job)).strength == MatchStrength.STRONG


# ── cross-language words ─────────────────────────────────────────────────────


def test_spanish_and_english_names_of_the_same_thing_match() -> None:
    spanish = WordIndex({"vigilancia", "investigacion", "epidemiologia", "brotes", "sistemas"})

    for english in ("surveillance", "investigation", "epidemiology", "outbreaks", "systems"):
        assert spanish.has(english), english


def test_an_unknown_word_falls_through_the_equivalence_table() -> None:
    spanish = WordIndex({"vigilancia", "sistemas"})

    assert not spanish.has("rubella")
    assert not spanish.has("sales")


# ── output ───────────────────────────────────────────────────────────────────


def test_shortlist_reasons_say_why_a_teaching_post_scored() -> None:
    reasons = match_reasons(_match(TEACHING))

    assert 1 <= len(reasons) <= 3
    assert reasons[0].startswith("~ role:")
    assert "headline" in reasons[0]
    assert any(reason.startswith("✗") for reason in reasons)


def test_shortlist_reasons_lead_with_a_held_title() -> None:
    reasons = match_reasons(_match(SURVEILLANCE))

    assert reasons[0].startswith("✓ role:")
    assert "Consultora en Sistemas de Información de Vigilancia" in reasons[0]


def test_every_job_near_zero_is_a_matcher_alert() -> None:
    warning = blind_matcher_warning([0.0, 1.0, 2.5])

    assert warning is not None
    assert "under 5%" in warning
    assert blind_matcher_warning([0.0, 5.0]) is None
