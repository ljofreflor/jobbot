"""Rule-based job matching — never invents candidate skills.

When the JD has a rich description, the final % blends lexical skill/requirement
hits with a document-level CV↔JD cosine (bag-of-words offline, or optional local
BERT via ``jobbot[bert]`` — no paid API). Noisy/incomplete ``job.skills`` from a
paste no longer own the score alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from jobbot.jobs.normalization import fold_text, normalize_skill
from jobbot.jobs.parsing import extract_skills_from_text
from jobbot.matching.similarity import (
    TextEmbedder,
    description_is_rich,
    document_similarity,
)
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.models.match import JobMatch, MatchItem, MatchStrength

# A job whose posting names almost nothing cannot be a perfect fit, whatever it asks.
_THIN_EVIDENCE_ITEMS = 3
_THIN_EVIDENCE_CAP = 80.0
# Weight on document cosine when blending with lexical skill hits.
_DOCUMENT_FIT_WEIGHT = 0.55

# Requirement sentences are prose: only content words carry evidence.
_STOPWORDS = frozenset(
    {
        "años",
        "anos",
        "para",
        "con",
        "como",
        "experiencia",
        "experience",
        "conocimiento",
        "conocimientos",
        "manejo",
        "titulo",
        "deseable",
        "excluyente",
        "trabajo",
        "equipo",
        "equipos",
        "afin",
        "otros",
        "otras",
        "sobre",
        "strong",
        "comfortable",
        "preferred",
        "nice",
        "have",
        "with",
        "and",
        "the",
        "role",
        "senior",
        "junior",
        "semi",
    }
)

_MAX_REQUIREMENT_CHARS = 140


@dataclass(frozen=True)
class _Vocabulary:
    """What the profile actually claims: skill phrases plus their content words."""

    phrases: dict[str, str]  # folded phrase → original wording
    words: frozenset[str]
    stems: frozenset[str]


def _stem(word: str) -> str:
    """'geofísico' and 'geofísica' are the same claim; so are 'proyecto'/'proyectos'.

    A JD writes the masculine and the profile the feminine (or the reverse), and a
    requirement was reported as missing over a single vowel. Long words only, so
    short names ('sql', 'scrum') are never touched.
    """
    folded = fold_text(word)
    if len(folded) < 6:
        return folded
    for suffix in ("es", "s"):
        if folded.endswith(suffix) and len(folded) - len(suffix) >= 5:
            folded = folded[: -len(suffix)]
            break
    if folded[-1] in "aoe" and len(folded) >= 6:
        folded = folded[:-1]
    return folded


class JobAnalyzer(Protocol):
    def analyze(self, candidate: Candidate, job: JobPosting) -> JobMatch: ...


class RuleBasedJobAnalyzer:
    """Deterministic matcher using skills, tags, keywords, seniority, role family.

    ``document_fit`` (default True) blends in CV↔JD document cosine when the
    posting has a rich description — bag-of-words offline, or a local BERT
    ``embedder`` when ``--bert`` / ``build_local_bert_embedder()`` is used.
    """

    def __init__(
        self,
        *,
        document_fit: bool = True,
        embedder: TextEmbedder | None = None,
        document_weight: float = _DOCUMENT_FIT_WEIGHT,
    ) -> None:
        self.document_fit = document_fit
        self.embedder = embedder
        self.document_weight = document_weight

    def analyze(self, candidate: Candidate, job: JobPosting) -> JobMatch:
        candidate_tokens = _candidate_tokens(candidate)
        vocabulary = _candidate_vocabulary(candidate)
        items: list[MatchItem] = []

        required = _job_requirements(job)
        for token, label, text in required:
            evidence = _requirement_evidence(text, vocabulary)
            if token in candidate_tokens:
                items.append(
                    MatchItem(
                        label=label,
                        strength=MatchStrength.STRONG,
                        detail="present in profile",
                    )
                )
            elif evidence is not None:
                strength, detail = evidence
                items.append(MatchItem(label=label, strength=strength, detail=detail))
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

        lexical = _score(items, role_cap=None, required_tokens={t for t, _, _ in required})
        document_score: float | None = None
        fit_mode = "rules"
        score = lexical

        if self.document_fit and description_is_rich(job):
            document_score, mode = document_similarity(candidate, job, embedder=self.embedder)
            fit_mode = mode
            items.append(_document_fit_item(document_score, mode))
            w = min(0.85, max(0.15, self.document_weight))
            # Noisy/incomplete skill lists (bad paste parse) → trust the JD text more.
            skill_like = [
                i
                for i in items
                if i.strength != MatchStrength.UNKNOWN
                and not i.label.startswith("document:")
                and not i.label.startswith("role:")
                and not i.label.startswith("seniority:")
            ]
            if skill_like:
                missing_n = sum(1 for i in skill_like if i.strength == MatchStrength.MISSING)
                if missing_n / len(skill_like) >= 0.6:
                    w = max(w, 0.72)
            blended = (1.0 - w) * lexical + w * document_score
            # Document fit rescues noisy parses; it must not dilute a clean lexical hit
            # (nurse/journalist JDs share little bag vocabulary with synonym tables).
            score = max(lexical, blended)

        score = _apply_caps(
            score,
            role_cap=role_cap,
            required_tokens={t for t, _, _ in required},
            description_rich=description_is_rich(job) and self.document_fit,
        )
        return JobMatch(
            job_id=job.id,
            score=score,
            items=items,
            document_score=document_score,
            lexical_score=lexical if document_score is not None else None,
            fit_mode=fit_mode,
        )


def _document_fit_item(score: float, mode: str) -> MatchItem:
    label = f"document:{mode}"
    if score >= 55:
        strength = MatchStrength.STRONG
        detail = f"CV↔JD {mode} cosine {score:.0f}%"
    elif score >= 30:
        strength = MatchStrength.PARTIAL
        detail = f"CV↔JD {mode} cosine {score:.0f}%"
    else:
        strength = MatchStrength.MISSING
        detail = f"CV↔JD {mode} cosine {score:.0f}% — weak overlap"
    return MatchItem(label=label, strength=strength, detail=detail)


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


def _job_requirements(job: JobPosting) -> list[tuple[str, str, str]]:
    """(token, label, full text) per requirement; long Spanish lines stay in."""
    pairs: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for skill in job.skills:
        token = normalize_skill(skill)
        if token and token not in seen:
            seen.add(token)
            pairs.append((token, skill, skill))
    for req in job.requirements:
        if re.search(r"(?i)\b(english|spanish|idioma|language|proficiency)\b", req):
            continue
        token = normalize_skill(req)
        if token and token not in seen and len(req) <= _MAX_REQUIREMENT_CHARS:
            seen.add(token)
            pairs.append((token, req[:80], req))
    blob = f"{job.title}\n{job.description}\n{job.raw_description}"
    if len(pairs) < 3:
        for hint in extract_skills_from_text(blob):
            token = normalize_skill(hint)
            if token and token not in seen:
                seen.add(token)
                pairs.append((token, hint, hint))
    return pairs


def _candidate_vocabulary(candidate: Candidate) -> _Vocabulary:
    """Skills, specialties, titles and degrees: what the profile literally claims."""
    phrases: dict[str, str] = {}
    for claim in (
        *candidate.skills.all_skills(),
        *candidate.specialties,
        *(exp.title for exp in candidate.experience),
        *(edu.degree for edu in candidate.education),
    ):
        folded = fold_text(claim)
        if len(folded) >= 3:
            phrases.setdefault(folded, claim)

    words = {
        word
        for folded in phrases
        for word in folded.split()
        if len(word) >= 4 and word not in _STOPWORDS
    }
    return _Vocabulary(
        phrases=phrases,
        words=frozenset(words),
        stems=frozenset(_stem(word) for word in words),
    )


def _requirement_evidence(
    requirement: str,
    vocabulary: _Vocabulary,
) -> tuple[MatchStrength, str] | None:
    """Match a requirement sentence against the profile's own wording."""
    folded = fold_text(requirement)
    if not folded:
        return None

    for phrase, original in vocabulary.phrases.items():
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", folded):
            return MatchStrength.STRONG, f"profile claims {original}"

    content = [word for word in folded.split() if len(word) >= 4 and word not in _STOPWORDS]
    hits = sorted({word for word in content if word in vocabulary.words})
    variants = sorted(
        {word for word in content if word not in hits and _stem(word) in vocabulary.stems}
    )

    if len(hits) >= 2:
        return MatchStrength.STRONG, f"profile wording: {', '.join(hits)}"
    if hits and variants:
        return MatchStrength.STRONG, f"profile wording: {', '.join([*hits, *variants])}"
    if hits:
        return MatchStrength.PARTIAL, f"profile wording: {hits[0]}"
    if variants:
        return MatchStrength.PARTIAL, f"profile wording (variant): {variants[0]}"
    return None


def _keyword_candidates(text: str) -> set[str]:
    """Content words of the candidate's own prose — no vocabulary to belong to."""
    return {word for word in fold_text(text).split() if len(word) >= 4 and word not in _STOPWORDS}


def _partial_token(token: str, candidate_tokens: set[str]) -> bool:
    """A requirement is partially met when the profile names part of that phrase."""
    words = [word for word in token.split("_") if len(word) >= 4 and word not in _STOPWORDS]
    if not words:
        return False
    return any(word in candidate_tokens for word in words)


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


def _role_family_item(candidate: Candidate, job: JobPosting) -> tuple[MatchItem, float | None]:
    """Compare the job title with the titles the candidate has actually held.

    A table of role families only knows the families someone wrote down, and a
    candidate whose field is missing from it gets judged by a family they never
    claimed. The titles in the profile are the only evidence there is.
    """
    label = f"role:{job.title}"
    held = _title_words(
        *(exp.title for exp in candidate.experience),
        candidate.personal.headline or "",
    )
    wanted = _title_words(job.title)
    shared = sorted(held & wanted)

    if len(shared) >= 2:
        return (
            MatchItem(
                label=label,
                strength=MatchStrength.STRONG,
                detail=f"held titles share: {', '.join(shared)}",
            ),
            None,
        )
    if len(shared) == 1:
        return (
            MatchItem(
                label=label,
                strength=MatchStrength.PARTIAL,
                detail=f"held titles share: {shared[0]}",
            ),
            70.0,
        )
    if not wanted:
        return (
            MatchItem(
                label=label,
                strength=MatchStrength.UNKNOWN,
                detail="job title carries no comparable words",
            ),
            None,
        )
    return (
        MatchItem(
            label=label,
            strength=MatchStrength.MISSING,
            detail="job title does not match any title in the profile",
        ),
        40.0,
    )


def _title_words(*titles: str) -> set[str]:
    return {
        word
        for title in titles
        for word in fold_text(title).split()
        if len(word) >= 4 and word not in _STOPWORDS
    }


def _score(
    items: list[MatchItem],
    *,
    role_cap: float | None,
    required_tokens: set[str],
) -> float:
    """Score only on strong/partial/missing skill-like items; unknowns excluded."""
    relevant = [
        i
        for i in items
        if i.strength != MatchStrength.UNKNOWN and not i.label.startswith("document:")
    ]
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
    return _apply_caps(
        score,
        role_cap=role_cap,
        required_tokens=required_tokens,
        description_rich=False,
    )


def _apply_caps(
    score: float,
    *,
    role_cap: float | None,
    required_tokens: set[str],
    description_rich: bool,
) -> float:
    # Thin structured skills: cap unless a rich JD description already backed the blend.
    if not description_rich and len(required_tokens - {""}) < _THIN_EVIDENCE_ITEMS:
        score = min(score, _THIN_EVIDENCE_CAP)
    if role_cap is not None:
        score = min(score, role_cap)
    return round(score, 1)
