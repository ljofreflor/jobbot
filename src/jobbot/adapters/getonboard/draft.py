"""Permanent Get on Board profile fields from Candidate (facts only; Spanish).

GoB stores these texts on the professional account and reuses them on later
applications. JobBot is the maintainer: regenerate from profile.yaml, HITL paste
into https://www.getonbrd.com/webpros/edit, never invent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from jobbot.branding import MARK, stamp_description
from jobbot.models.candidate import Candidate
from jobbot.models.education import Education
from jobbot.models.experience import Experience
from jobbot.models.job import JobPosting

EXPERIENCE_MIN = 300
EXPERIENCE_MAX = 2000
EDUCATION_MIN = 100
EDUCATION_MAX = 2000
EDUCATION_ITEM_DETAIL_MAX = 220

JOBBOT_SIGNATURE = MARK


@dataclass(frozen=True)
class PermanentProfileFields:
    """Fields GoB keeps on the account for reuse across applications."""

    experiencia_y_perfil: str
    formacion_academica: str
    headline: str
    skills: list[str]
    signature: str = JOBBOT_SIGNATURE
    omitted_education: int = 0
    omitted_teaching: int = 0
    omitted_publications: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "experiencia_y_perfil": self.experiencia_y_perfil,
            "formacion_academica": self.formacion_academica,
            "headline": self.headline,
            "skills": list(self.skills),
            "signature": self.signature,
            "omitted_education": self.omitted_education,
            "omitted_teaching": self.omitted_teaching,
            "omitted_publications": self.omitted_publications,
            "limits": {
                "experiencia_chars": len(self.experiencia_y_perfil),
                "formacion_chars": len(self.formacion_academica),
                "experiencia_max": EXPERIENCE_MAX,
                "formacion_max": EDUCATION_MAX,
            },
        }


def build_permanent_profile_fields(candidate: Candidate) -> PermanentProfileFields:
    """Derive permanent GoB blurbs from profile.yaml facts only."""
    experience = stamp_description(
        _fit(_draft_experience(candidate), EXPERIENCE_MAX),
        max_len=EXPERIENCE_MAX,
    )
    education = _pack_education(candidate)
    return PermanentProfileFields(
        experiencia_y_perfil=experience,
        formacion_academica=education.text,
        headline=candidate.personal.headline,
        skills=list(candidate.skills.all_skills())[:10],
        omitted_education=education.omitted_education,
        omitted_teaching=education.omitted_teaching,
        omitted_publications=education.omitted_publications,
    )


def draft_getonboard_fields(
    candidate: Candidate,
    job: JobPosting | None = None,
    *,
    permanent: PermanentProfileFields | None = None,
) -> dict[str, str]:
    """Application-form fields; prefer permanent profile when available.

    A stored permanent profile keeps its wording, but it may predate profile.yaml
    (a new role, an end date), so it is refined against the profile before use.
    """
    _ = job
    if permanent is None:
        fields = build_permanent_profile_fields(candidate)
    else:
        from jobbot.nlp.refine import refine_permanent_profile

        fields = refine_permanent_profile(candidate, permanent).fields
    return {
        "experiencia_y_perfil": fields.experiencia_y_perfil,
        "formacion_academica": fields.formacion_academica,
        "signature": fields.signature,
    }


def omission_line(fields: PermanentProfileFields) -> str:
    """The warning when a whole education item, teaching line or publication did not fit."""
    if not (fields.omitted_education or fields.omitted_teaching or fields.omitted_publications):
        return ""
    return (
        "Omitido por largo: "
        f"{fields.omitted_education} ítems de formación, "
        f"{fields.omitted_teaching} de docencia, "
        f"{fields.omitted_publications} publicaciones"
    )


def render_permanent_profile_markdown(fields: PermanentProfileFields) -> str:
    notice = omission_line(fields)
    lines = [
        "# Get on Board — perfil permanente (mantenedor)",
        "",
        "Fuente: data/profile.yaml + iteración previa (computación acumulativa).",
        "No se descarta el texto anterior: se refina con hechos actuales.",
        "La descripción cierra con la firma. Pegala junto con el texto.",
        f"Firma: {fields.signature}",
        "",
        "URL: https://www.getonbrd.com/webpros/edit",
        "",
        "Orden HITL:",
        "1. Abre Editar perfil y reemplaza los textos anteriores por los de abajo.",
        "2. Pega los bloques de abajo (GoB los guarda para futuras postulaciones).",
        "3. Tus CVs: sube output/base/cv.pdf y márcalo default.",
        "4. Recién entonces postula a un cargo.",
        "",
        f"## Headline ({len(fields.headline)} chars)",
        "",
        fields.headline,
        "",
        f"## experiencia_y_perfil ({len(fields.experiencia_y_perfil)} chars; "
        f"límite {EXPERIENCE_MIN}–{EXPERIENCE_MAX})",
        "",
        fields.experiencia_y_perfil,
        "",
        f"## formacion_academica ({len(fields.formacion_academica)} chars; "
        f"límite {EDUCATION_MIN}–{EDUCATION_MAX})",
        "",
        fields.formacion_academica,
        "",
    ]
    if notice:
        lines.extend([notice, ""])
    lines.extend(
        [
            "## Skills (máx. 10 en GoB)",
            "",
            ", ".join(fields.skills) if fields.skills else "_(none)_",
            "",
        ]
    )
    return "\n".join(lines)


def render_getonboard_markdown(fields: dict[str, str], *, job: JobPosting) -> str:
    """Per-job paste sheet (reuses permanent body)."""
    return "\n".join(
        [
            "# Get on Board — textos para postulación (español)",
            f"# Job: {job.id} {job.title} @ {job.company}",
            "# Preferir perfil permanente actualizado en webpros/edit",
            f"# La descripción ya cierra con la firma: {fields.get('signature', JOBBOT_SIGNATURE)}",
            "",
            f"## experiencia_y_perfil ({len(fields['experiencia_y_perfil'])} chars)",
            "",
            fields["experiencia_y_perfil"],
            "",
            f"## formacion_academica ({len(fields['formacion_academica'])} chars)",
            "",
            fields["formacion_academica"],
            "",
        ]
    )


def permanent_profile_dir(root_output: Path) -> Path:
    return root_output / "getonboard"


def permanent_profile_yaml_path(root_output: Path) -> Path:
    return permanent_profile_dir(root_output) / "profile_permanent.yaml"


def permanent_profile_md_path(root_output: Path) -> Path:
    return permanent_profile_dir(root_output) / "profile_permanent.md"


def save_permanent_profile(
    fields: PermanentProfileFields,
    root_output: Path,
    *,
    archive_previous: bool = True,
) -> Path:
    out = permanent_profile_dir(root_output)
    out.mkdir(parents=True, exist_ok=True)
    yaml_path = permanent_profile_yaml_path(root_output)
    md_path = permanent_profile_md_path(root_output)
    if archive_previous and yaml_path.is_file():
        history = out / "history"
        history.mkdir(parents=True, exist_ok=True)
        from datetime import UTC, datetime

        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        archived = history / f"profile_permanent_{stamp}.yaml"
        archived.write_text(yaml_path.read_text(encoding="utf-8"), encoding="utf-8")
    yaml_path.write_text(
        yaml.safe_dump(fields.to_dict(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    md_path.write_text(render_permanent_profile_markdown(fields), encoding="utf-8")
    return md_path


def fields_from_seed_text(
    *,
    experiencia: str,
    formacion: str,
    candidate: Candidate,
) -> PermanentProfileFields:
    """Seed a PermanentProfileFields from pasted portal text (accumulated capital)."""
    packed = _pack_education(candidate)
    seeded = formacion.strip()
    return PermanentProfileFields(
        experiencia_y_perfil=stamp_description(experiencia, max_len=EXPERIENCE_MAX),
        formacion_academica=seeded or packed.text,
        headline=candidate.personal.headline,
        skills=list(candidate.skills.all_skills())[:10],
        omitted_education=0 if seeded else packed.omitted_education,
        omitted_teaching=0 if seeded else packed.omitted_teaching,
        omitted_publications=0 if seeded else packed.omitted_publications,
    )


def load_permanent_profile(root_output: Path) -> PermanentProfileFields | None:
    path = permanent_profile_yaml_path(root_output)
    if not path.is_file():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return None
    exp = str(raw.get("experiencia_y_perfil") or "").strip()
    edu = str(raw.get("formacion_academica") or "").strip()
    if not exp or not edu:
        return None
    skills = raw.get("skills") or []
    if not isinstance(skills, list):
        skills = []
    return PermanentProfileFields(
        experiencia_y_perfil=exp,
        formacion_academica=edu,
        headline=str(raw.get("headline") or ""),
        skills=[str(s) for s in skills][:10],
        signature=str(raw.get("signature") or JOBBOT_SIGNATURE),
        omitted_education=_nonnegative(raw.get("omitted_education")),
        omitted_teaching=_nonnegative(raw.get("omitted_teaching")),
        omitted_publications=_nonnegative(raw.get("omitted_publications")),
    )


def recent_roles(candidate: Candidate, limit: int = 2) -> list[Experience]:
    """Current roles first, then by end and start date; the YAML order is not a fact."""
    ordered = sorted(
        candidate.experience,
        key=lambda exp: (exp.current, exp.end_date or "", exp.start_date),
        reverse=True,
    )
    return ordered[:limit]


def role_label(exp: Experience) -> str:
    """How a draft names a role, before its period."""
    return f"{exp.title} en {exp.company}"


def role_head(exp: Experience) -> str:
    """Opening sentence of a role paragraph: who, where and the period profile.yaml states."""
    end = "actualidad" if exp.current else (exp.end_date or "")
    period = ""
    if exp.start_date:
        period = f" ({exp.start_date}–{end})" if end else f" ({exp.start_date})"
    return f"{role_label(exp)}{period}."


def _draft_experience(candidate: Candidate) -> str:
    paragraphs: list[str] = []

    for exp in recent_roles(candidate):
        head = role_head(exp)
        # One achievement per role keeps two roles under the GoB character cap.
        achs = [a.text.strip() for a in exp.achievements[:1] if a.text.strip()]
        if achs:
            paragraphs.append(_join_sentences([head, *achs]))
        elif exp.description:
            paragraphs.append(_join_sentences([head, exp.description.strip()]))
        else:
            paragraphs.append(_join_sentences([head]))

    skills = candidate.skills.all_skills()
    if skills:
        # Which skills matter is a question only this profile can answer: the ones
        # its own headline, summary and achievements already talk about come first.
        emphasis = " ".join(
            [
                candidate.personal.headline or "",
                candidate.summary or "",
                *(
                    f"{exp.title} {exp.description or ''} "
                    + " ".join(a.text for a in exp.achievements)
                    for exp in candidate.experience
                ),
                *candidate.specialties,
            ]
        ).casefold()
        highlighted = [skill for skill in skills if skill.casefold() in emphasis]
        shown = (highlighted + [s for s in skills if s not in highlighted])[:8]
        # The heading names the section. "Stack" assumed a software trade.
        paragraphs.append(_join_sentences(["Habilidades: " + ", ".join(shown)]))

    if candidate.summary:
        # The summary leads, but the roles own their space: it gets what is left of
        # the GoB cap, cut on a sentence so the portal never shows a dangling clause.
        room = EXPERIENCE_MAX - len("\n\n".join(paragraphs)) - 2
        summary = _sentence_prefix(candidate.summary.strip(), room)
        if summary:
            paragraphs.insert(0, summary)

    return "\n\n".join(paragraphs).strip()


def _sentence_prefix(text: str, maximum: int) -> str:
    """Longest prefix of whole sentences that fits, '' when not even one does."""
    if maximum <= 0:
        return ""
    if len(text) <= maximum:
        return text
    window = text[:maximum]
    cut = max(window.rfind(". "), window.rfind(".\n"))
    if cut > 0:
        return window[: cut + 1]
    return window if window.endswith(".") else ""


def _nonnegative(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value if value > 0 else 0


def _ends_sentence(text: str) -> bool:
    stripped = text.rstrip()
    return stripped.endswith((".", "!", "?", "…", "..."))


def _join_sentences(parts: list[str]) -> str:
    """Join clauses with a single stop. A part that already ends a sentence keeps its stop."""
    sentences: list[str] = []
    for part in parts:
        text = " ".join(part.split())
        if not text:
            continue
        if not _ends_sentence(text):
            text += "."
        sentences.append(text)
    return " ".join(sentences)


@dataclass(frozen=True)
class _EducationPack:
    text: str
    omitted_education: int = 0
    omitted_teaching: int = 0
    omitted_publications: int = 0


def _education_item(edu: Education) -> str:
    line = f"{edu.degree} — {edu.institution}"
    dates = "–".join(date for date in (edu.start_date, edu.end_date) if date)
    if dates:
        line += f" ({dates})"
    detail = _sentence_prefix((edu.details or "").strip(), EDUCATION_ITEM_DETAIL_MAX)
    if detail:
        return _join_sentences([line, detail])
    return _join_sentences([line])


def _teaching_line(candidate: Candidate) -> str:
    teaching: list[str] = []
    for exp in candidate.experience:
        title_l = exp.title.casefold()
        if any(
            k in title_l
            for k in (
                "profesor",
                "docente",
                "ayudante",
                "coordinador académico",
                "investigador",
            )
        ):
            teaching.append(f"{exp.title} en {exp.company}")
    if not teaching:
        return ""
    return _join_sentences(["He sido " + "; ".join(teaching)])


def _publications_line(candidate: Candidate) -> str:
    pubs: list[str] = []
    for pub in candidate.publications[:3]:
        bits = [pub.title]
        if pub.journal:
            bits.append(pub.journal)
        if pub.year:
            bits.append(str(pub.year))
        if pub.doi:
            bits.append(f"DOI {pub.doi}")
        pubs.append(" — ".join(bits))
    if not pubs:
        return ""
    return _join_sentences(["Publicaciones relevantes: " + "; ".join(pubs)])


def _pack_units(units: list[tuple[str, str]], maximum: int) -> _EducationPack:
    """Keep whole units in order. One that does not fit is skipped and counted."""
    kept: list[str] = []
    omitted = {"education": 0, "teaching": 0, "publications": 0}
    for kind, text in units:
        if not text:
            continue
        trial = "\n\n".join([*kept, text])
        if len(trial) <= maximum:
            kept.append(text)
        else:
            omitted[kind] += 1
    return _EducationPack(
        text="\n\n".join(kept),
        omitted_education=omitted["education"],
        omitted_teaching=omitted["teaching"],
        omitted_publications=omitted["publications"],
    )


def _pack_education(candidate: Candidate) -> _EducationPack:
    units = [("education", _education_item(edu)) for edu in candidate.education]
    units.append(("teaching", _teaching_line(candidate)))
    units.append(("publications", _publications_line(candidate)))
    return _pack_units(units, EDUCATION_MAX)


def _fit(text: str, maximum: int) -> str:
    """Keep under max by dropping trailing paragraphs (never invent)."""
    text = text.strip()
    if len(text) <= maximum:
        return text
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    kept: list[str] = []
    for part in parts:
        trial = "\n\n".join([*kept, part])
        if len(trial) <= maximum:
            kept.append(part)
        else:
            break
    if kept:
        return "\n\n".join(kept)
    # Single long paragraph: hard cut at word boundary
    cut = text[: maximum - 1].rsplit(" ", 1)[0]
    return cut
