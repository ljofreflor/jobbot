"""Unit tests for Indeed resume edit helpers (no live browser)."""

from datetime import date

import pytest

from jobbot.adapters.indeed.resume_edit import (
    _MONTHS_ES,
    _experience_description,
    _parse_ym,
    add_missing_experiences,
    clamp_portal_ym,
    headline_visible_in_contact,
    parse_resume_page_text,
    roles_already_listed,
)
from jobbot.adapters.indeed.selectors import select_list_testid
from jobbot.models.candidate import Candidate
from jobbot.models.experience import Experience
from tests.fixtures.profile import sample_profile_dict


def test_parse_ym_and_months() -> None:
    assert _parse_ym("2025-10") == (2025, 10)
    assert _MONTHS_ES[10] == "Octubre"


def test_experience_description_includes_achievements() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    text = _experience_description(candidate.experience[0])
    assert "Share of Wallet" in text
    assert text.startswith("•") or "Customer analytics" in text


def _role(role_id: str, company: str, title: str, end: str) -> Experience:
    return Experience(
        id=role_id,
        company=company,
        title=title,
        start_date="2021-01",
        end_date=end,
        current=False,
    )


def test_future_end_month_keeps_the_year_indeed_will_list() -> None:
    """December 2026 is absent from the end-year menu in October 2026.

    The menu drops the year when the month is still ahead. Clamping the month
    to today keeps 2026 selectable. A past year is left alone.
    """
    assert clamp_portal_ym(2026, 12, date(2026, 10, 3)) == (2026, 10)
    assert clamp_portal_ym(2022, 12, date(2026, 10, 3)) == (2022, 12)
    assert clamp_portal_ym(2022, 1, date(2026, 10, 3)) == (2022, 1)


def test_year_option_comes_from_the_open_list() -> None:
    assert (
        select_list_testid("work-experience-date-range-to-year")
        == "container-work-experience-date-range-to-year-list"
    )


def test_company_mentioned_in_a_bullet_is_not_that_employer() -> None:
    section = (
        "Abogada Coordinadora\n"
        "Estudio Ejemplo S.A.\n"
        "• Representación de la empresa ante el Servicio Neutro de Defensa\n"
    )
    roles = [
        _role("role-1", "Servicio Neutro de Defensa", "Directora Administrativa", "2026-12"),
        _role("role-2", "Servicio Neutro de Defensa", "Jefa de Estudios", "2022-12"),
    ]
    assert roles_already_listed(section, roles) == set()


def test_one_title_on_the_page_does_not_cover_another_at_the_same_employer() -> None:
    section = (
        "Directora Administrativa\nServicio Neutro de Defensa\nDe enero de 2022 a octubre de 2026\n"
    )
    roles = [
        _role("role-1", "Servicio Neutro de Defensa", "Directora Administrativa", "2026-12"),
        _role("role-2", "Servicio Neutro de Defensa", "Jefa de Estudios", "2022-12"),
    ]
    listed = roles_already_listed(section, roles)
    assert ("servicio neutro de defensa", "directora administrativa") in listed
    assert ("servicio neutro de defensa", "jefa de estudios") not in listed


def test_failed_add_does_not_skip_sibling_at_same_employer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_add(page: object, exp: Experience) -> None:
        calls.append(exp.title)
        if exp.title == "Directora Administrativa":
            raise RuntimeError("Year option not found: 2026")

    monkeypatch.setattr("jobbot.adapters.indeed.resume_edit.add_experience", fake_add)
    roles = [
        _role("role-1", "Servicio Neutro de Defensa", "Directora Administrativa", "2026-12"),
        _role("role-2", "Servicio Neutro de Defensa", "Jefa de Estudios", "2022-12"),
    ]
    added, errors = add_missing_experiences(
        page=None,
        experiences=roles,
        section_text="• Representación de la empresa ante el Servicio Neutro de Defensa\n",
    )
    assert calls == ["Directora Administrativa", "Jefa de Estudios"]
    assert added == 1
    assert len(errors) == 1


def test_headline_is_not_saved_when_the_contact_block_has_no_title() -> None:
    contact = (
        "ana ejemplo\n+56 9 0000 0000\nana.ejemplo@example.com\nSantiago, Región Metropolitana\n"
    )
    headline = "Abogada | Magíster en Derecho Público"
    assert headline_visible_in_contact(contact, headline) is False
    shown = contact + "\n" + headline + "\n"
    assert headline_visible_in_contact(shown, headline) is True


def test_parse_resume_page_text_summary() -> None:
    body = """
Editar CV
Resumen
Senior Data Scientist con experiencia en fintech.
Datos personales
Destaca datos personales
Experiencia laboral
Habilidades
Python
SQL
Certificaciones y licencias
"""
    parsed = parse_resume_page_text(body)
    assert parsed["summary"] and "fintech" in str(parsed["summary"])
    assert "Python" in parsed["skills"]  # type: ignore[operator]
