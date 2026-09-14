"""Parse free-text job descriptions into JobPosting fields."""

from __future__ import annotations

import re
from typing import Any

from jobbot.models.job import JobPosting

_SKILL_HINTS = [
    "Python",
    "SQL",
    "R",
    "Machine Learning",
    "Deep Learning",
    "XGBoost",
    "PyTorch",
    "TensorFlow",
    "scikit-learn",
    "Causal Inference",
    "A/B Testing",
    "Experimentation",
    "GCP",
    "AWS",
    "Azure",
    "BigQuery",
    "Spark",
    "Databricks",
    "MLOps",
    "LLM",
    "LangChain",
    "Bayesian",
    "Survival Analysis",
]


def parse_job_text(
    text: str,
    *,
    job_id: str,
    source: str = "manual",
    url: str | None = None,
) -> JobPosting:
    """Best-effort parse of a pasted JD into a JobPosting."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    title = _field(lines, "title", "role", "cargo", "puesto") or (lines[0] if lines else "Untitled")
    company = _field(lines, "company", "empresa", "organization") or "Unknown"
    location = _field(lines, "location", "ubicacion", "ubicación", "city")
    seniority = _infer_seniority(text)
    remote_type = _infer_remote(text)
    skills = _extract_skills(text)
    requirements = _extract_requirements(text)
    languages = _extract_languages(text)

    description = text.strip()
    return JobPosting(
        id=job_id,
        source=source,
        url=url,
        title=title,
        company=company,
        location=location,
        description=description,
        raw_description=text,
        requirements=requirements,
        skills=skills,
        seniority=seniority,
        language_requirements=languages,
        remote_type=remote_type,
    )


def job_to_dict(job: JobPosting) -> dict[str, Any]:
    return job.model_dump(mode="json")


def _field(lines: list[str], *keys: str) -> str | None:
    for line in lines:
        for key in keys:
            match = re.match(rf"(?i)^{re.escape(key)}\s*[:\-]\s*(.+)$", line)
            if match:
                return match.group(1).strip()
    return None


def _infer_seniority(text: str) -> str | None:
    lower = text.lower()
    for label in ("staff", "principal", "senior", "semi-senior", "mid", "junior", "lead"):
        if re.search(rf"\b{re.escape(label)}\b", lower):
            return label
    return None


def _infer_remote(text: str) -> str | None:
    lower = text.lower()
    if "remote" in lower or "remoto" in lower:
        return "remote"
    if "hybrid" in lower or "híbrido" in lower or "hibrido" in lower:
        return "hybrid"
    if "on-site" in lower or "presencial" in lower:
        return "onsite"
    return None


def extract_skills_from_text(text: str) -> list[str]:
    """Public alias used by job sources that skip parse_job_text."""
    return _extract_skills(text)


def _extract_skills(text: str) -> list[str]:
    found: list[str] = []
    lower = text.lower()
    for hint in _SKILL_HINTS:
        hint_l = hint.lower()
        if len(hint_l) <= 2:
            if re.search(rf"(?<![a-z]){re.escape(hint_l)}(?![a-z])", lower):
                found.append(hint)
        elif hint_l in lower:
            found.append(hint)
    return found


def _extract_requirements(text: str) -> list[str]:
    reqs: list[str] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"(?i)^(requirements|requisitos|requirements:|what you.ll need)", stripped):
            in_block = True
            continue
        if in_block:
            if not stripped:
                if reqs:
                    break
                continue
            if re.match(r"(?i)^(benefits|beneficios|about us|sobre)", stripped):
                break
            bullet = re.sub(r"^[-*•\d.)\s]+", "", stripped)
            if bullet:
                reqs.append(bullet)
    return reqs


def _extract_languages(text: str) -> list[str]:
    langs: list[str] = []
    lower = text.lower()
    if re.search(r"\benglish\b|\bingl[eé]s\b", lower):
        langs.append("english")
    if re.search(r"\bspanish\b|\bespa[nñ]ol\b", lower):
        langs.append("spanish")
    return langs
