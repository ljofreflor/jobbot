"""Chiletrabajos fill sheet projected from the source of truth.

Each observed field has a home in the profile or answers, or an explicit
needs_human reason. The sheet names the gap. It does not print contact values,
and it never stores a national id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from jobbot.jobs.eligibility import ApplicationAnswers
from jobbot.jobs.normalization import fold_text
from jobbot.models.candidate import Candidate
from jobbot.models.education import Education
from jobbot.models.experience import Experience

NEEDS_HUMAN = "needs_human"

_RANKS: tuple[tuple[str, str, int], ...] = (
    ("postdoctor", "Post Doctorado", 8),
    ("doctor", "Doctorado", 7),
    ("phd", "Doctorado", 7),
    ("magister", "Magíster", 6),
    ("master", "Magíster", 6),
    ("postgrado", "Postgrado", 5),
    ("diplomado", "Postgrado", 5),
    ("licenciatur", "Universitaria", 4),
    ("universitari", "Universitaria", 4),
    ("bachelor", "Universitaria", 4),
    ("tecnic", "Técnica", 3),
    ("secundar", "Media", 2),
    ("media", "Media", 2),
    ("basic", "Básica", 1),
)


@dataclass(frozen=True)
class PortalField:
    """One Chiletrabajos label and where it lives, or why a person must type it."""

    label: str
    home: str | None = None
    needs_human: str | None = None


# Inventory of the registration form and the profile editor. Order is the sheet order.
FIELDS: tuple[PortalField, ...] = (
    PortalField("Nombres", home="personal.name"),
    PortalField("Apellidos", home="personal.name"),
    PortalField("Nombre completo", home="personal.name"),
    PortalField("Correo", home="personal.email"),
    PortalField("Celular", home="personal.phone"),
    PortalField("Teléfono", needs_human="no hay un segundo teléfono en el SST"),
    PortalField("Ciudad", home="personal.city"),
    PortalField("Comuna", home="identity.comuna"),
    PortalField("Dirección", needs_human="la dirección no está en el SST"),
    PortalField("País de origen", home="identity.nationality"),
    PortalField("Fecha de nacimiento", home="identity.birth_date"),
    PortalField("Género", home="identity.gender_to_declare"),
    PortalField("RUT", needs_human="no se guarda un identificador nacional"),
    PortalField("Clave", needs_human="la clave no se guarda"),
    PortalField("Confirme clave", needs_human="la clave no se guarda"),
    PortalField("Experiencia laboral", home="experience"),
    PortalField("Años de experiencia", home="experience"),
    PortalField("Resumen educación", home="education"),
    PortalField("Nivel educacional", home="education"),
    PortalField("CV", home="cv"),
    PortalField("Disponibilidad", home="availability"),
    PortalField("Pretensiones de renta", home="salary"),
    PortalField("Tipos de trabajo", home="job_types"),
    PortalField("Ciudad deseada", needs_human="la ciudad deseada no está en el SST"),
    PortalField("Comentario", home="summary"),
    PortalField("Foto", needs_human="no hay un archivo de foto en el SST"),
    PortalField("Boletín", needs_human="preferencia de la cuenta, no es un hecho del perfil"),
    PortalField(
        "Notificación de empleos",
        needs_human="preferencia de la cuenta, no es un hecho del perfil",
    ),
    PortalField("CV en Internet", needs_human="preferencia de privacidad del portal"),
    PortalField("Datos anónimos", needs_human="preferencia de privacidad del portal"),
    PortalField("Referencias", needs_human="referencias de terceros"),
    PortalField("reCAPTCHA", needs_human="captcha"),
)


def experience_bucket(years: float) -> str | None:
    """Portal enum. A span the enum does not name stays None (needs_human)."""
    if years <= 0:
        return "Sin experiencia"
    if years < 2:
        return "<2"
    if 3 <= years <= 6:
        return "3-6"
    if 7 <= years <= 10:
        return "7-10"
    if years > 10:
        return ">10"
    return None


def education_level(items: list[Education]) -> str | None:
    """Highest completed level named by the degrees. A candidacy is not a degree."""
    best: tuple[int, str] | None = None
    for item in items:
        folded = fold_text(item.degree)
        if "candidato" in folded:
            continue
        for token, label, rank in _RANKS:
            if token in folded and (best is None or rank > best[0]):
                best = (rank, label)
                break
    return None if best is None else best[1]


def gender_label(value: str | None) -> str | None:
    """The portal only offers two options. Anything else is needs_human."""
    if value == "female":
        return "Femenino"
    if value == "male":
        return "Masculino"
    return None


def experience_years(roles: list[Experience], *, today: date | None = None) -> float:
    """Years covered by dated roles, overlaps merged. Undated roles add nothing."""
    when = today or date.today()
    spans: list[tuple[int, int]] = []
    for role in roles:
        start = _month(role.start_date)
        if role.end_date:
            last = _month(role.end_date)
        elif role.current:
            last = when.year * 12 + when.month
        else:
            continue
        if last >= start:
            # The dates name months, and the last one was worked: the span closes after it.
            spans.append((start, last + 1))
    if not spans:
        return 0.0
    ordered = sorted(spans)
    total = 0
    start, end = ordered[0]
    for nxt, nxt_end in ordered[1:]:
        if nxt <= end:
            end = max(end, nxt_end)
            continue
        total += end - start
        start, end = nxt, nxt_end
    total += end - start
    return total / 12


def render_chiletrabajos_sheet(candidate: Candidate, answers: ApplicationAnswers) -> str:
    """Markdown sheet. Contact values stay out; gaps and enums stay in."""
    lines = ["# Chiletrabajos", "", "Portal: `chiletrabajos`", ""]
    for field in FIELDS:
        lines.append(f"- {field.label}: {_cell(field, candidate, answers)}")
    lines.append("")
    return "\n".join(lines)


def _cell(field: PortalField, candidate: Candidate, answers: ApplicationAnswers) -> str:
    if field.needs_human:
        return f"{NEEDS_HUMAN}: {field.needs_human}"
    if field.label == "Género":
        if answers.identity.gender_to_declare is None:
            return _missing("gender")
        label = gender_label(answers.identity.gender_to_declare)
        if label is None:
            return f"{NEEDS_HUMAN}: el portal solo ofrece Masculino o Femenino"
        return label
    if field.label == "Años de experiencia":
        bucket = experience_bucket(experience_years(candidate.experience))
        if bucket is None:
            return f"{NEEDS_HUMAN}: los años no caen en un rango del portal"
        return bucket
    if field.label == "Nivel educacional":
        if not candidate.education:
            return _missing("education")
        level = education_level(candidate.education)
        if level is None:
            return f"{NEEDS_HUMAN}: el título no cae en un nivel del portal"
        return level
    if field.label == "Comuna":
        return "listo" if answers.identity.comuna else _missing("comuna")
    if field.label == "País de origen":
        return "listo" if answers.identity.nationality else _missing("nationality")
    if field.label == "Fecha de nacimiento":
        return "listo" if answers.identity.birth_date else _missing("birth_date")
    if field.label == "Disponibilidad":
        ready = answers.availability is not None and answers.availability.from_date is not None
        return "listo" if ready or answers.notice_period else _missing("availability")
    if field.label == "Pretensiones de renta":
        salary = answers.salary
        filled = salary is not None and any(
            (salary.amount, salary.currency, salary.period, salary.basis)
        )
        return "listo" if filled or answers.salary_expectation else _missing("salary")
    if field.label == "Tipos de trabajo":
        return "listo" if answers.job_types else _missing("job_types")
    if field.label == "Comentario":
        return "listo" if (candidate.summary or "").strip() else _missing("summary")
    if field.label == "Experiencia laboral":
        if not candidate.experience:
            return _missing("experience")
        return f"listo ({len(candidate.experience)})"
    if field.label == "Resumen educación":
        return "listo" if candidate.education else _missing("education")
    if field.label == "CV":
        return "listo"
    if field.home == "personal.name":
        return "listo" if candidate.personal.name.strip() else _missing("name")
    if field.home == "personal.email":
        return "listo" if candidate.personal.email else _missing("email")
    if field.home == "personal.phone":
        return "listo" if candidate.personal.phone else _missing("phone")
    if field.home == "personal.city":
        return "listo" if candidate.personal.city else _missing("city")
    return _missing(field.home or field.label)


def _missing(fact: str) -> str:
    return f"[falta en el SST: {fact}]"


def _month(value: str) -> int:
    year, month = value.split("-")
    return int(year) * 12 + int(month)
