"""Each stored requirement is backed by the profile, or left for the person.

Nothing here is written back into ``profile.yaml``. A gap is ``[por confirmar]``,
never a claim that the candidate meets it.
"""

from __future__ import annotations

from jobbot.applications.cover_letter import fact_blob
from jobbot.jobs.normalization import fold_text
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting


def requirement_checklist(candidate: Candidate, job: JobPosting) -> list[tuple[str, str]]:
    """``(requirement, evidence)``. Evidence is empty when the profile does not say it."""
    blob = fold_text(fact_blob(candidate, job))
    skills = [skill for skill in candidate.skills.all_skills() if len(fold_text(skill)) >= 4]
    rows: list[tuple[str, str]] = []
    for requirement in job.requirements:
        text = requirement.strip()
        if not text:
            continue
        folded = fold_text(text)
        if folded and folded in blob:
            rows.append((text, text))
            continue
        cited = next((skill for skill in skills if fold_text(skill) in folded), "")
        rows.append((text, cited))
    return rows


def render_requirement_checklist(candidate: Candidate, job: JobPosting) -> str:
    """One markdown list. A gap stays marked and is not filled in."""
    lines = [f"# Requisitos — {job.id}", ""]
    rows = requirement_checklist(candidate, job)
    if not rows:
        lines.append("El aviso guardado no trae requisitos.")
        return "\n".join(lines) + "\n"
    for requirement, evidence in rows:
        if evidence:
            lines.append(f"- cumple: {requirement} — el perfil dice «{evidence}»")
        else:
            lines.append(f"- [por confirmar]: {requirement}")
    return "\n".join(lines) + "\n"
