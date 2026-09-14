"""Rule-based job matching — never invents candidate skills."""

from __future__ import annotations

import re
from typing import Protocol

from jobbot.jobs.normalization import normalize_skill
from jobbot.jobs.parsing import extract_skills_from_text
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.models.match import JobMatch, MatchItem, MatchStrength

# Role family adjacency: same family = 1.0 cap, adjacent = 70, mismatch = 40.
_ROLE_FAMILY_CAP: dict[tuple[str, str], float] = {
    ("data_science", "data_eng"): 70.0,
    ("data_eng", "data_science"): 70.0,
    ("data_science", "ml_eng"): 85.0,
    ("ml_eng", "data_science"): 85.0,
    ("data_eng", "ml_eng"): 70.0,
    ("ml_eng", "data_eng"): 70.0,
}

_GENERIC_ONLY = {"python", "sql", "machine_learning"}


class JobAnalyzer(Protocol):
    def analyze(self, candidate: Candidate, job: JobPosting) -> JobMatch: ...


class RuleBasedJobAnalyzer:
    """Deterministic matcher using skills, tags, keywords, seniority, role family."""

    def analyze(self, candidate: Candidate, job: JobPosting) -> JobMatch:
        candidate_tokens = _candidate_tokens(candidate)
        items: list[MatchItem] = []

        required = _job_requirement_tokens(job)
        for token, label in required:
            if token in candidate_tokens:
                items.append(
                    MatchItem(
                        label=label,
                        strength=MatchStrength.STRONG,
                        detail="present in profile",
                    )
                )
            elif _partial_token(token, candidate_tokens):
                items.append(
                    MatchItem(
                        label=label,
                        strength=MatchStrength.PARTIAL,
                        detail="related skill/tag in profile",
                    )
                )
            else:
                items.append(
                    MatchItem(
                        label=label,
                        strength=MatchStrength.MISSING,
                        detail="not found in profile",
                    )
                )

        role_item, role_cap = _role_family_item(candidate, job)
        items.append(role_item)

        for lang in job.language_requirements:
            # Languages are often not structured in profile → unknown, never missing
            items.append(
                MatchItem(
                    label=f"{lang} proficiency",
                    strength=MatchStrength.UNKNOWN,
                    detail="not modeled in profile.yaml",
                )
            )

        if job.seniority:
            items.append(_seniority_item(candidate, job.seniority))

        score = _score(items, role_cap=role_cap, required_tokens={t for t, _ in required})
        return JobMatch(job_id=job.id, score=score, items=items)


def _candidate_tokens(candidate: Candidate) -> set[str]:
    tokens: set[str] = set()
    for skill in candidate.skills.all_skills():
        tokens.add(normalize_skill(skill))
    for specialty in candidate.specialties:
        tokens.add(normalize_skill(specialty))
    for exp in candidate.experience:
        tokens.add(normalize_skill(exp.title))
        tokens.add(normalize_skill(exp.company))
        if exp.description:
            for word in _keyword_candidates(exp.description):
                tokens.add(word)
        for ach in exp.achievements:
            for tag in ach.tags:
                tokens.add(normalize_skill(tag))
            for word in _keyword_candidates(ach.text):
                tokens.add(word)
    if candidate.summary:
        for word in _keyword_candidates(candidate.summary):
            tokens.add(word)
    return {t for t in tokens if t}


def _job_requirement_tokens(job: JobPosting) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for skill in job.skills:
        token = normalize_skill(skill)
        if token and token not in seen:
            seen.add(token)
            pairs.append((token, skill))
    for req in job.requirements:
        if re.search(r"(?i)\b(english|spanish|idioma|language|proficiency)\b", req):
            continue
        token = normalize_skill(req)
        if token and token not in seen and _looks_like_skill_token(token, req):
            seen.add(token)
            pairs.append((token, req[:80]))
    blob = f"{job.title}\n{job.description}\n{job.raw_description}"
    if len(pairs) < 3:
        for hint in extract_skills_from_text(blob):
            token = normalize_skill(hint)
            if token and token not in seen:
                seen.add(token)
                pairs.append((token, hint))
    return pairs


def _looks_like_skill_token(token: str, original: str) -> bool:
    if len(original) > 60:
        return False
    # Known canonicals contain underscore or are short
    return "_" in token or len(token) <= 20


def _keyword_candidates(text: str) -> set[str]:
    words = set()
    lower = text.lower()
    for phrase in (
        "machine learning",
        "causal inference",
        "share of wallet",
        "customer analytics",
        "a/b testing",
        "experimentation",
        "bigquery",
        "feature store",
        "genai",
        "llm",
        "fintech",
        "retail",
        "marketplace",
        "bayesian",
        "mlops",
        "python",
        "pytorch",
        "xgboost",
    ):
        if phrase in lower:
            words.add(normalize_skill(phrase))
    return words


def _partial_token(token: str, candidate_tokens: set[str]) -> bool:
    related = {
        "gcp": {"aws", "azure", "cloud"},
        "aws": {"gcp", "azure", "cloud"},
        "azure": {"gcp", "aws", "cloud"},
        "pytorch": {"tensorflow", "deep_learning", "machine_learning"},
        "tensorflow": {"pytorch", "deep_learning", "machine_learning"},
        "xgboost": {"machine_learning", "scikit_learn"},
    }
    return any(alt in candidate_tokens for alt in related.get(token, set()))


def _seniority_item(candidate: Candidate, required: str) -> MatchItem:
    titles = " ".join(e.title.lower() for e in candidate.experience)
    req = required.lower()
    if req in titles or (req == "senior" and "senior" in titles):
        return MatchItem(
            label=f"seniority:{required}",
            strength=MatchStrength.STRONG,
            detail="title history includes seniority signal",
        )
    if req in {"senior", "staff", "lead"} and any(
        x in titles for x in ("senior", "lead", "staff", "principal")
    ):
        return MatchItem(
            label=f"seniority:{required}",
            strength=MatchStrength.PARTIAL,
            detail="adjacent seniority in profile",
        )
    return MatchItem(
        label=f"seniority:{required}",
        strength=MatchStrength.UNKNOWN,
        detail="cannot verify years/level precisely from profile",
    )


def _role_family(title: str) -> str:
    t = title.casefold()
    if any(k in t for k in ("product manager", "product owner", " project manager")):
        return "product"
    if any(k in t for k in ("frontend", "react", "typescript", "backend", "software engineer")):
        return "software"
    if any(k in t for k in ("data engineer", "analytics engineer", "ingeniero de datos")):
        return "data_eng"
    if any(
        k in t
        for k in (
            "ml engineer",
            "machine learning engineer",
            "mle",
            "ingeniero ml",
        )
    ):
        return "ml_eng"
    if any(
        k in t
        for k in (
            "data scientist",
            "applied scientist",
            "research scientist",
            "científico de datos",
            "cientifico de datos",
            "ia engineer",
            "ai engineer",
        )
    ):
        return "data_science"
    if any(k in t for k in ("head of", "director", "vp ")):
        return "leadership"
    return "other"


def _candidate_role_family(candidate: Candidate) -> str:
    titles = " ".join(e.title for e in candidate.experience)
    if candidate.personal.headline:
        titles = f"{candidate.personal.headline} {titles}"
    fam = _role_family(titles)
    return fam if fam != "other" else "data_science"


def _role_family_item(candidate: Candidate, job: JobPosting) -> tuple[MatchItem, float | None]:
    cand_fam = _candidate_role_family(candidate)
    job_fam = _role_family(job.title)
    label = f"role:{job.title}"
    if job_fam == cand_fam:
        return (
            MatchItem(label=label, strength=MatchStrength.STRONG, detail=f"family={job_fam}"),
            None,
        )
    if job_fam == "other":
        return (
            MatchItem(
                label=label,
                strength=MatchStrength.UNKNOWN,
                detail="could not classify job title family",
            ),
            None,
        )
    cap = _ROLE_FAMILY_CAP.get((cand_fam, job_fam), 40.0)
    strength = MatchStrength.PARTIAL if cap >= 70 else MatchStrength.MISSING
    return (
        MatchItem(
            label=label,
            strength=strength,
            detail=f"candidate={cand_fam} job={job_fam}",
        ),
        cap,
    )


def _score(
    items: list[MatchItem],
    *,
    role_cap: float | None,
    required_tokens: set[str],
) -> float:
    """Score only on strong/partial/missing skill-like items; unknowns excluded."""
    relevant = [i for i in items if i.strength != MatchStrength.UNKNOWN]
    if not relevant:
        return 0.0
    points = 0.0
    for item in relevant:
        if item.strength == MatchStrength.STRONG:
            points += 1.0
        elif item.strength == MatchStrength.PARTIAL:
            points += 0.5
        # missing contributes 0
    score = 100.0 * points / len(relevant)
    # Generic-only JD (Python/SQL/ML) must not look like a perfect fit.
    skill_tokens = required_tokens - {""}
    if skill_tokens and skill_tokens <= _GENERIC_ONLY and score > 80:
        score = 80.0
    if role_cap is not None:
        score = min(score, role_cap)
    return round(score, 1)
