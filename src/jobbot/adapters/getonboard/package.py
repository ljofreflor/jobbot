"""Get on Board profile + CV sync package from Candidate (facts only)."""

from __future__ import annotations

from dataclasses import dataclass

from jobbot.branding import MARK, stamp_description
from jobbot.models.candidate import Candidate

PROFILE_EDIT_URL = "https://www.getonbrd.com/webpros/edit"
# Resumes live under the professional profile area (HITL: open edit, then "Tus CVs").
RESUMES_HINT_URL = "https://www.getonbrd.com/webpros/edit"


@dataclass(frozen=True)
class GetOnBoardSyncPackage:
    headline: str
    summary: str
    location: str
    linkedin: str
    github: str
    email: str
    phone: str
    skills: list[str]
    experience_blocks: list[str]
    education_blocks: list[str]
    profile_edit_url: str = PROFILE_EDIT_URL
    resumes_url: str = RESUMES_HINT_URL


def build_getonboard_sync_package(candidate: Candidate) -> GetOnBoardSyncPackage:
    personal = candidate.personal
    skills = list(candidate.skills.all_skills())[:10]  # GoB skills UI: up to 10
    exp_blocks: list[str] = []
    for exp in candidate.experience:
        lines = [f"{exp.title} — {exp.company}"]
        end = "actualidad" if exp.current else (exp.end_date or "")
        if exp.start_date:
            lines.append(f"{exp.start_date} – {end}" if end else exp.start_date)
        if exp.location:
            lines.append(exp.location)
        if exp.description:
            lines.append(exp.description.strip())
        for ach in exp.achievements[:4]:
            lines.append(f"• {ach.text.strip()}")
        exp_blocks.append("\n".join(lines))
    edu_blocks: list[str] = []
    for edu in candidate.education:
        line = f"{edu.degree} — {edu.institution}"
        dates = "–".join(d for d in (edu.start_date, edu.end_date) if d)
        if dates:
            line += f" ({dates})"
        if edu.details:
            line += f"\n{edu.details}"
        edu_blocks.append(line)
    return GetOnBoardSyncPackage(
        headline=personal.headline,
        summary=stamp_description(candidate.summary or ""),
        location=personal.location_line() or "",
        linkedin=personal.linkedin or "",
        github=personal.github or "",
        email=str(personal.email) if personal.email else "",
        phone=personal.phone or "",
        skills=skills,
        experience_blocks=exp_blocks,
        education_blocks=edu_blocks,
    )


def render_getonboard_sync_markdown(package: GetOnBoardSyncPackage) -> str:
    lines = [
        "# Get on Board — sync package (from profile.yaml)",
        "",
        "Orden HITL: 1) Editar perfil  2) Tus CVs  3) recién entonces postular.",
        f"No inventar. Pegar solo hechos. El resumen cierra con: {MARK}",
        "",
        f"- Perfil: {package.profile_edit_url}",
        f"- CVs (mismo área profesional → sección Tus CVs / Your resumes): {package.resumes_url}",
        "",
        "## Contacto / links",
        f"- Email: {package.email or '—'}",
        f"- Teléfono: {package.phone or '—'}",
        f"- Ubicación: {package.location or '—'}",
        f"- LinkedIn: {package.linkedin or '—'}",
        f"- GitHub: {package.github or '—'}",
        "",
        "## Headline",
        package.headline,
        "",
        "## Resumen / about",
        package.summary or "_(vacío)_",
        "",
        "## Skills (máx. 10 en GoB)",
        ", ".join(package.skills) if package.skills else "_(none)_",
        "",
        "## Experiencia (pegar por rol)",
    ]
    for i, block in enumerate(package.experience_blocks, start=1):
        lines.extend(["", f"### Rol {i}", "```", block, "```"])
    lines.extend(["", "## Educación"])
    for i, block in enumerate(package.education_blocks, start=1):
        lines.extend(["", f"### Estudio {i}", "```", block, "```"])
    lines.extend(
        [
            "",
            "## Tus CVs",
            "1. Genera el PDF: `jobbot cv build` → `output/base/cv.pdf`",
            "2. En Get on Board → Tus CVs: sube ese PDF (≤ 5 MB).",
            "3. Renombra (ej. `Leonardo-Jofre-DS-2026`) y márcalo como default.",
            "4. Luego postula con Quick Apply usando ese CV.",
            "",
        ]
    )
    return "\n".join(lines)
