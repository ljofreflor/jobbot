"""Portal field labels → profile facts (#94).

A homologation table lists, for each fact in ``profile.yaml``, the portal
labels that mean that fact (ES/EN). Lookup is exact after folding — never by
substring — so \"Middle Name\" is not confused with \"name\", and new aliases
are added to the table instead of inventing matches at fill time.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum

from jobbot.jobs.eligibility import ApplicationAnswers
from jobbot.models.candidate import Candidate


class ProfileFact(StrEnum):
    """Canonical slot in the candidate profile a portal field may ask for."""

    FULL_NAME = "full_name"
    GIVEN_NAME = "given_name"
    FAMILY_NAME = "family_name"
    EMAIL = "email"
    PHONE = "phone"
    CITY = "city"
    COUNTRY = "country"
    LOCATION = "location"
    HEADLINE = "headline"
    LINKEDIN = "linkedin"
    GITHUB = "github"
    RESUME = "resume"
    BIRTH_DATE = "birth_date"
    NATIONALITY = "nationality"
    GENDER = "gender"
    COMUNA = "comuna"
    REGION = "region"
    SALARY_NET = "salary_net"
    SALARY_GROSS = "salary_gross"
    AVAILABILITY_DATE = "availability_date"


# One fact → many accepted portal labels. Unknown labels stay unmapped (HITL).
# Do not add "middle name", "father's family name", or "mother's family name"
# unless profile.yaml gains those facts.
_HOMOLOGATION: dict[ProfileFact, tuple[str, ...]] = {
    ProfileFact.FULL_NAME: (
        "full name",
        "name",
        "legal name",
        "nombre completo",
    ),
    ProfileFact.GIVEN_NAME: (
        "first name",
        "given name",
        "given name(s)",
        "nombre",
        "nombres",
    ),
    ProfileFact.FAMILY_NAME: (
        "last name",
        "family name",
        "surname",
        "apellido",
        "apellidos",
    ),
    ProfileFact.EMAIL: (
        "email",
        "email address",
        "e-mail",
        "correo",
        "correo electrónico",
        "correo electronico",
    ),
    ProfileFact.PHONE: (
        "phone",
        "phone number",
        "mobile",
        "móvil",
        "movil",
        "celular",
        "teléfono",
        "telefono",
    ),
    ProfileFact.CITY: ("city", "ciudad"),
    ProfileFact.COUNTRY: ("country", "país", "pais"),
    ProfileFact.LOCATION: ("location", "ubicación", "ubicacion"),
    ProfileFact.HEADLINE: (
        "headline",
        "current role",
        "current title",
        "cargo actual",
        # Indeed labels the resume title «Título» (contact form, headline-input).
        "título",
        "title",
    ),
    ProfileFact.LINKEDIN: (
        "linkedin",
        "linkedin profile",
        "linkedin url",
        "perfil linkedin",
    ),
    ProfileFact.GITHUB: ("github", "github profile", "github url"),
    ProfileFact.RESUME: (
        "resume",
        "resume/cv",
        "cv",
        "curriculum",
        "currículum",
        "currículum vitae",
        "curriculum vitae",
    ),
    ProfileFact.BIRTH_DATE: (
        "birth date",
        "date of birth",
        "fecha de nacimiento",
    ),
    ProfileFact.NATIONALITY: ("nationality", "nacionalidad"),
    ProfileFact.GENDER: ("gender", "género", "genero"),
    ProfileFact.COMUNA: ("comuna",),
    ProfileFact.REGION: ("region", "región"),
    ProfileFact.SALARY_NET: (
        "net salary",
        "renta líquida",
        "renta liquida",
        "sueldo líquido",
        "sueldo liquido",
    ),
    ProfileFact.SALARY_GROSS: (
        "gross salary",
        "renta bruta",
        "sueldo bruto",
    ),
    ProfileFact.AVAILABILITY_DATE: (
        "availability",
        "available from",
        "fecha de disponibilidad",
        "disponibilidad",
    ),
}

_NATIONAL_ID_LABELS = frozenset(
    {
        "run",
        "rut",
        "rol unico nacional",
        "national id",
        "dni",
    }
)
NEEDS_HUMAN = "needs_human"

_ALIAS_TO_FACT: dict[str, ProfileFact] = {}


def _fold(label: str) -> str:
    """Stable key for a portal label: casefold, strip *, collapse space."""
    text = label.casefold().replace("*", " ")
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_ish = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_ish).strip()


def _ensure_index() -> None:
    if _ALIAS_TO_FACT:
        return
    for fact, aliases in _HOMOLOGATION.items():
        for alias in aliases:
            key = _fold(alias)
            if key in _ALIAS_TO_FACT and _ALIAS_TO_FACT[key] is not fact:
                msg = f"homologation alias {alias!r} maps to two facts"
                raise RuntimeError(msg)
            _ALIAS_TO_FACT[key] = fact


def resolve_fact(label: str) -> ProfileFact | None:
    """Which profile fact this portal label asks for, or None if unknown."""
    _ensure_index()
    return _ALIAS_TO_FACT.get(_fold(label))


def aliases_for(fact: ProfileFact) -> tuple[str, ...]:
    """Accepted portal wordings for one fact (for docs/tests)."""
    return _HOMOLOGATION[fact]


def value_for_fact(candidate: Candidate, fact: ProfileFact) -> tuple[str, str]:
    """(value, source) from profile.yaml for this fact. Empty when unknown."""
    personal = candidate.personal
    if fact is ProfileFact.FULL_NAME:
        return _pair(personal.name, "personal.name")
    if fact is ProfileFact.GIVEN_NAME:
        given, _ = _split_name(personal.name)
        return _pair(given, "personal.name")
    if fact is ProfileFact.FAMILY_NAME:
        _, family = _split_name(personal.name)
        return _pair(family, "personal.name")
    if fact is ProfileFact.EMAIL:
        return _pair(personal.email, "personal.email")
    if fact is ProfileFact.PHONE:
        return _pair(personal.phone, "personal.phone")
    if fact is ProfileFact.CITY:
        return _pair(personal.city, "personal.city")
    if fact is ProfileFact.COUNTRY:
        return _pair(personal.country, "personal.country")
    if fact is ProfileFact.LOCATION:
        return _pair(personal.location_line(), "personal.city + country")
    if fact is ProfileFact.HEADLINE:
        return _pair(personal.headline, "personal.headline")
    if fact is ProfileFact.LINKEDIN:
        return _pair(personal.linkedin, "personal.linkedin")
    if fact is ProfileFact.GITHUB:
        return _pair(personal.github, "personal.github")
    if fact is ProfileFact.RESUME:
        return ("output/base/cv.pdf", "cv build")
    if fact in {
        ProfileFact.BIRTH_DATE,
        ProfileFact.NATIONALITY,
        ProfileFact.GENDER,
        ProfileFact.COMUNA,
        ProfileFact.REGION,
        ProfileFact.SALARY_NET,
        ProfileFact.SALARY_GROSS,
        ProfileFact.AVAILABILITY_DATE,
    }:
        return ("", NEEDS_HUMAN)
    return ("", "you decide: not a fact in the profile")


def project_answer(label: str, answers: ApplicationAnswers) -> str:
    """Value for a form label, or needs_human when the basis differs or the fact is blank.

    A national id is never read from the answers file.
    """
    if _fold(label) in _NATIONAL_ID_LABELS:
        return NEEDS_HUMAN
    fact = resolve_fact(label)
    if fact is None:
        return NEEDS_HUMAN
    return _from_answers(fact, answers)


def _from_answers(fact: ProfileFact, answers: ApplicationAnswers) -> str:
    identity = answers.identity
    if fact is ProfileFact.BIRTH_DATE:
        return identity.birth_date.isoformat() if identity.birth_date else NEEDS_HUMAN
    if fact is ProfileFact.NATIONALITY:
        return ", ".join(identity.nationality) if identity.nationality else NEEDS_HUMAN
    if fact is ProfileFact.GENDER:
        return identity.gender_to_declare or NEEDS_HUMAN
    if fact is ProfileFact.COMUNA:
        return identity.comuna or NEEDS_HUMAN
    if fact is ProfileFact.REGION:
        return identity.region or NEEDS_HUMAN
    if fact is ProfileFact.SALARY_NET:
        return _salary_for(answers, "net")
    if fact is ProfileFact.SALARY_GROSS:
        return _salary_for(answers, "gross")
    if fact is ProfileFact.AVAILABILITY_DATE:
        availability = answers.availability
        if availability is not None and availability.from_date is not None:
            return availability.from_date.isoformat()
        return NEEDS_HUMAN
    return NEEDS_HUMAN


def _salary_for(answers: ApplicationAnswers, basis: str) -> str:
    salary = answers.salary
    if salary is None or salary.amount is None or salary.basis != basis:
        return NEEDS_HUMAN
    return str(salary.amount)


def answer_for_label(candidate: Candidate, label: str) -> tuple[str, str]:
    """Resolve a portal label via the homologation table only."""
    fact = resolve_fact(label)
    if fact is None:
        return ("", "you decide: not a fact in the profile")
    return value_for_fact(candidate, fact)


def _pair(value: object, source: str) -> tuple[str, str]:
    text = str(value or "").strip()
    if not text:
        return ("", "you decide: not a fact in the profile")
    return (text, source)


def _split_name(full: str | None) -> tuple[str, str]:
    """Given / family split for Spanish two-of-each when four tokens."""
    parts = (full or "").split()
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")
    if len(parts) >= 4:
        return (" ".join(parts[:2]), " ".join(parts[2:]))
    return (parts[0], " ".join(parts[1:]))
