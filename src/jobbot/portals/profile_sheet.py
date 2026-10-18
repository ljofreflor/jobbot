"""Fill sheet for one portal, projected from the source of truth.

The sheet is what a person copies into a form jobbot cannot type into yet
(or must not type into, when the portal is bound to a state identity).
Nothing here opens a browser or clicks.
"""

from __future__ import annotations

from jobbot.models.candidate import Candidate
from jobbot.portals.fill_catalog import FillPortal
from jobbot.portals.profile_state import AccountState, PortalProfileState

_LABELS = {
    "es": {
        "identity": "Identidad",
        "headline": "Titular",
        "summary": "Resumen",
        "experience": "Experiencia",
        "education": "Formación",
        "languages": "Idiomas",
        "certifications": "Certificaciones",
        "skills": "Habilidades",
        "cv": "CV",
        "name": "Nombre",
        "city": "Ciudad",
        "country": "País",
        "phone": "Teléfono",
        "linkedin": "LinkedIn",
        "github": "GitHub",
        "orcid": "ORCID",
        "email": "Correo",
        "present": "actual",
    },
    "en": {
        "identity": "Identity",
        "headline": "Headline",
        "summary": "Summary",
        "experience": "Experience",
        "education": "Education",
        "languages": "Languages",
        "certifications": "Certifications",
        "skills": "Skills",
        "cv": "CV",
        "name": "Name",
        "city": "City",
        "country": "Country",
        "phone": "Phone",
        "linkedin": "LinkedIn",
        "github": "GitHub",
        "orcid": "ORCID",
        "email": "Email",
        "present": "present",
    },
}


def render_fill_sheet(
    state: PortalProfileState,
    candidate: Candidate,
    aliases: dict[str, str],
    *,
    lang: str = "es",
    catalog: FillPortal | None = None,
) -> str:
    """Markdown the person can copy. Uses the portal alias, never the SST email."""
    if lang not in _LABELS:
        msg = f"unknown language: {lang}"
        raise ValueError(msg)
    label = _LABELS[lang]
    title = catalog.name if catalog is not None else state.portal
    lines = [f"# {title}", "", f"Portal: `{state.portal}` · adapter: `{state.adapter}`", ""]
    if state.account is AccountState.identity_bound or state.adapter == "identity_bound":
        lines.append(
            "Este portal pide identidad estatal. jobbot no abre el navegador ni escribe. "
            "Copiar esta hoja a mano."
        )
        lines.append("")
    else:
        lines.append(
            "Hoja de llenado. jobbot no envía la postulación ni acepta términos. "
            "Guardar el perfil en el sitio queda para la persona."
        )
        lines.append("")
    for section in state.sections:
        lines.append(f"## {label.get(section, section)}")
        lines.append("")
        lines.extend(_section_lines(section, candidate, state, aliases, label))
        lines.append("")
    extra = [gap for gap in state.gaps if gap not in state.sections]
    if extra:
        lines.append("## Datos que el portal pide y el SST no tiene")
        lines.append("")
        for gap in extra:
            lines.append(f"- [falta en el SST: {gap}]")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _missing(fact: str) -> str:
    return f"[falta en el SST: {fact}]"


def _line(label: str, value: str | None, fact: str) -> str:
    shown = value.strip() if value else ""
    if not shown:
        return f"- {label}: {_missing(fact)}"
    return f"- {label}: {shown}"


def _section_lines(
    section: str,
    candidate: Candidate,
    state: PortalProfileState,
    aliases: dict[str, str],
    label: dict[str, str],
) -> list[str]:
    personal = candidate.personal
    if section == "identity":
        email = _alias_email(state, aliases)
        return [
            _line(label["name"], personal.name, "name"),
            _line(label["city"], personal.city, "city"),
            _line(label["country"], personal.country, "country"),
            _line(label["phone"], personal.phone, "phone"),
            _line(label["linkedin"], personal.linkedin, "linkedin"),
            _line(label["github"], personal.github, "github"),
            _line(label["orcid"], personal.orcid, "orcid"),
            f"- {label['email']}: {email}",
        ]
    if section == "headline":
        return [_line(label["headline"], personal.headline, "headline")]
    if section == "summary":
        return [_line(label["summary"], candidate.summary, "summary")]
    if section == "experience":
        if not candidate.experience:
            return [f"- {_missing('experience')}"]
        rows: list[str] = []
        for item in candidate.experience:
            end = label["present"] if item.current else (item.end_date or _missing("end_date"))
            rows.append(f"- {item.title} — {item.company} ({item.start_date} – {end})")
            if item.location:
                rows.append(f"  - {item.location}")
            if item.description:
                rows.append(f"  - {item.description.strip()}")
            for achievement in item.achievements:
                rows.append(f"  - {achievement.text.strip()}")
        return rows
    if section == "education":
        if not candidate.education:
            return [f"- {_missing('education')}"]
        return [
            f"- {item.degree} — {item.institution}"
            + (f" ({item.end_date})" if item.end_date else "")
            for item in candidate.education
        ]
    if section == "languages":
        return [f"- {_missing('languages')}"]
    if section == "certifications":
        return [f"- {_missing('certifications')}"]
    if section == "skills":
        names = candidate.skills.all_skills()
        if not names and not candidate.specialties:
            return [f"- {_missing('skills')}"]
        rows = [f"- {name}" for name in names]
        rows.extend(f"- {name}" for name in candidate.specialties)
        return rows
    if section == "cv":
        return [
            f"- Variante: `{state.cv_variant}`",
            "- Adjuntar el PDF construido desde el SST (`jobbot cv build`).",
        ]
    return [f"- {_missing(section)}"]


def _alias_email(state: PortalProfileState, aliases: dict[str, str]) -> str:
    """The address for this portal's account. Never the address stored on the SST."""
    if not state.email_alias:
        return "[falta alias: portal]"
    resolved = aliases.get(state.email_alias)
    if not resolved:
        return f"[falta alias: {state.email_alias}]"
    return f"{state.email_alias} → {resolved}"
