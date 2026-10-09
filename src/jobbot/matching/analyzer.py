"""Rule-based job matching — never invents candidate skills."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from jobbot.jobs.normalization import WordIndex, fold_text, normalize_skill, skills_in_text
from jobbot.jobs.parsing import degree_fields, extract_skills_from_text, looks_like_page_metadata
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.models.match import JobMatch, MatchItem, MatchStrength

# A job whose posting names almost nothing cannot be a perfect fit, whatever it asks.
_THIN_EVIDENCE_ITEMS = 3
_THIN_EVIDENCE_CAP = 80.0

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

# An achievement echoes a posting when most of its own content words are there.
_ECHO_MIN_WORD = 5
_ECHO_MIN_HITS = 4
_ECHO_SHARE = 0.5
_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)")

# An acronym is two to eight capitals, digits allowed after the first letter.
_ACRONYM_RE = re.compile(r"[A-Z][A-Z0-9]{1,7}")
_ACRONYM_PIECE_RE = re.compile(r"[A-Za-z0-9]+")
# Degree words say how high, not in what: two degrees sharing only 'ingeniería' or
# 'magíster' are degrees in different fields.
_DEGREE_LEVELS = frozenset(
    {
        "ingenieria",
        "ingeniero",
        "ingeniera",
        "licenciatura",
        "licenciado",
        "licenciada",
        "magister",
        "master",
        "masters",
        "maestria",
        "doctorado",
        "doctor",
        "doctora",
        "phd",
        "bachelor",
        "bachelors",
        "tecnico",
        "tecnica",
        "diplomado",
        "postitulo",
        "civil",
    }
)
_HEADLINE_ONLY_CAP = 40.0
_HEADLINE_NO_HISTORY_CAP = 70.0


@dataclass(frozen=True)
class _Claim:
    """One thing the profile states: a skill, a specialty, a title held, a degree."""

    original: str
    folded: str
    words: frozenset[str]
    index: WordIndex


@dataclass(frozen=True)
class _Vocabulary:
    """What the profile actually claims, kept claim by claim."""

    claims: tuple[_Claim, ...]
    degrees: tuple[_Claim, ...]
    acronyms: frozenset[str]


@dataclass(frozen=True)
class _Evidence:
    strength: MatchStrength
    detail: str
    claims: tuple[str, ...] = ()
    final: bool = False  # a degree verdict: no looser rule may overturn it


class JobAnalyzer(Protocol):
    def analyze(self, candidate: Candidate, job: JobPosting) -> JobMatch: ...


class RuleBasedJobAnalyzer:
    """Deterministic matcher using skills, tags, keywords, seniority, role family."""

    def analyze(self, candidate: Candidate, job: JobPosting) -> JobMatch:
        candidate_tokens = _candidate_tokens(candidate)
        vocabulary = _candidate_vocabulary(candidate)
        items: list[MatchItem] = []

        required = _job_requirements(job)
        cited: set[str] = set()
        for token, label, text in required:
            evidence = _requirement_evidence(text, vocabulary)
            if evidence is not None and evidence.final:
                items.append(
                    MatchItem(label=label, strength=evidence.strength, detail=evidence.detail)
                )
                if evidence.strength == MatchStrength.STRONG:
                    cited.update(evidence.claims)
            elif token in candidate_tokens:
                items.append(
                    MatchItem(
                        label=label,
                        strength=MatchStrength.STRONG,
                        detail="present in profile",
                    )
                )
            elif evidence is not None:
                items.append(
                    MatchItem(label=label, strength=evidence.strength, detail=evidence.detail)
                )
                if evidence.strength == MatchStrength.STRONG:
                    cited.update(evidence.claims)
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

        items.extend(_profile_evidence(candidate, job, items, cited))

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

        score = _score(items, role_cap=role_cap, required_tokens={t for t, _, _ in required})
        return JobMatch(job_id=job.id, score=score, items=items)


def requirement_evidence(
    candidate: Candidate, requirement: str
) -> tuple[MatchStrength, str] | None:
    """The profile's own wording behind one requirement sentence, or None."""
    evidence = _requirement_evidence(requirement, _candidate_vocabulary(candidate))
    return None if evidence is None else (evidence.strength, evidence.detail)


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
            tokens |= _keyword_candidates(exp.description)
            tokens |= skills_in_text(exp.description)
        for ach in exp.achievements:
            for tag in ach.tags:
                tokens.add(normalize_skill(tag))
            tokens |= _keyword_candidates(ach.text)
            tokens |= skills_in_text(ach.text)
    for edu in candidate.education:
        tokens |= skills_in_text(edu.degree)
    if candidate.summary:
        tokens |= _keyword_candidates(candidate.summary)
        tokens |= skills_in_text(candidate.summary)
    return {t for t in tokens if t}


def _job_requirements(job: JobPosting) -> list[tuple[str, str, str]]:
    """(token, label, full text) per requirement; long Spanish lines stay in."""
    pairs: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for skill in job.skills:
        token = normalize_skill(skill)
        if token and token not in seen and not looks_like_page_metadata(skill):
            seen.add(token)
            pairs.append((token, skill, skill))
    long_skills = [fold_text(label) for _, label, _ in pairs if len(label.split()) >= 3]
    for req in job.requirements:
        if re.search(r"(?i)\b(english|spanish|idioma|language|proficiency)\b", req):
            continue
        if looks_like_page_metadata(req):
            continue
        if any(fold_text(req).startswith(skill) for skill in long_skills):
            # The same line already counted as a skill, trimmed of its trailing noise.
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


def _claim(original: str) -> _Claim | None:
    folded = fold_text(original)
    if len(folded) < 3:
        return None
    words = frozenset(
        word for word in folded.split() if len(word) >= 4 and word not in _STOPWORDS
    )
    return _Claim(original=original, folded=folded, words=words, index=WordIndex(words))


def _candidate_vocabulary(candidate: Candidate) -> _Vocabulary:
    """Skills, specialties, titles held and degrees: what the profile literally claims."""
    claims: dict[str, _Claim] = {}
    for original in (
        *candidate.skills.all_skills(),
        *candidate.specialties,
        *(exp.title for exp in candidate.experience),
        *(edu.degree for edu in candidate.education),
    ):
        claim = _claim(original)
        if claim is not None:
            claims.setdefault(claim.folded, claim)
    degrees = tuple(
        claim for edu in candidate.education if (claim := _claim(edu.degree)) is not None
    )
    return _Vocabulary(
        claims=tuple(claims.values()),
        degrees=degrees,
        acronyms=_profile_acronyms(candidate),
    )


def _profile_acronyms(candidate: Candidate) -> frozenset[str]:
    """Acronyms the profile writes anywhere, including inside 'SIVI-SMART' or '(PIZ)'."""
    texts: list[str] = [
        *candidate.skills.all_skills(),
        *candidate.specialties,
        candidate.summary or "",
    ]
    for exp in candidate.experience:
        texts += [exp.title, exp.company, exp.description or ""]
        texts += [ach.text for ach in exp.achievements]
    for edu in candidate.education:
        texts += [edu.degree, edu.institution, edu.details or ""]
    return frozenset(
        piece
        for text in texts
        for piece in _ACRONYM_PIECE_RE.findall(text)
        if _ACRONYM_RE.fullmatch(piece) and not piece.isdigit()
    )


def _degree_evidence(requirement: str, degrees: tuple[_Claim, ...]) -> _Evidence | None:
    """A degree requirement is met by a degree in that field, never by loose words."""
    fields = degree_fields(requirement)
    if fields is None:
        return None
    related: tuple[str, _Claim] | None = None
    for field in fields:
        words = field.split()
        subject = [word for word in words if word not in _DEGREE_LEVELS]
        for degree in degrees:
            if all(degree.index.has(word) for word in words):
                return _Evidence(
                    MatchStrength.STRONG,
                    f"degree in profile: {degree.original}",
                    claims=(degree.folded,),
                    final=True,
                )
            if related is None and subject:
                shared = [word for word in subject if degree.index.has(word)]
                if shared:
                    related = (", ".join(shared), degree)
    if related is not None:
        shared_words, closest = related
        return _Evidence(
            MatchStrength.PARTIAL,
            f"related degree in profile: {closest.original} ({shared_words})",
            claims=(closest.folded,),
            final=True,
        )
    return _Evidence(MatchStrength.MISSING, "degree not in profile", final=True)


def _requirement_evidence(requirement: str, vocabulary: _Vocabulary) -> _Evidence | None:
    """Match a requirement sentence against the profile's own wording.

    Strong evidence comes from one claim: its whole phrase, or two content words of
    the same skill, title or degree. Words found in different claims ('ingeniería'
    in a degree, 'comercial' in a job title) only make a partial match, and the
    detail says which claim gave each word.
    """
    degree = _degree_evidence(requirement, vocabulary.degrees)
    if degree is not None:
        return degree
    folded = fold_text(requirement)
    if not folded:
        return None

    bare = requirement.strip(" .,:;()")
    if _ACRONYM_RE.fullmatch(bare) and bare in vocabulary.acronyms:
        return _Evidence(MatchStrength.STRONG, f"profile names {bare}")

    for claim in vocabulary.claims:
        if re.search(rf"(?<!\w){re.escape(claim.folded)}(?!\w)", folded):
            return _Evidence(
                MatchStrength.STRONG, f"profile claims {claim.original}", (claim.folded,)
            )

    content = list(
        dict.fromkeys(word for word in folded.split() if len(word) >= 4 and word not in _STOPWORDS)
    )
    best: tuple[list[str], _Claim] | None = None
    sources: dict[str, _Claim] = {}
    for claim in vocabulary.claims:
        hits = [word for word in content if claim.index.has(word)]
        for word in hits:
            sources.setdefault(word, claim)
        if hits and (best is None or len(hits) > len(best[0])):
            best = (hits, claim)

    if best is not None and len(best[0]) >= 2:
        hits, claim = best
        return _Evidence(
            MatchStrength.STRONG,
            f"profile claims {claim.original}: {', '.join(hits)}",
            (claim.folded,),
        )
    if sources:
        detail = "; ".join(f"{word} ({claim.original})" for word, claim in sources.items())
        return _Evidence(MatchStrength.PARTIAL, f"profile wording: {detail}")
    return None


def _profile_evidence(
    candidate: Candidate,
    job: JobPosting,
    matched: list[MatchItem],
    cited: set[str],
) -> list[MatchItem]:
    """What the profile claims and the posting talks about, read from the profile's side.

    Requirements are read from the posting, and a career page full of chrome yields
    few real ones. The candidate's own skills, specialties, titles held, degrees and
    achievements found in the posting's text are evidence of fit in any field. Only
    what is found is added: a claim the posting does not mention is not a gap, so it
    costs nothing. A claim already cited for a requirement is not counted twice.
    """
    posting = WordIndex(
        frozenset(_keyword_candidates(f"{job.title}\n{job.description}\n{job.raw_description}"))
    )
    if not posting.words:
        return []
    already = [
        fold_text(item.label)
        for item in matched
        if item.strength in {MatchStrength.STRONG, MatchStrength.PARTIAL}
    ]
    items: list[MatchItem] = []
    seen: set[str] = set(cited)
    claims = [
        *((claim, "profile") for claim in candidate.skills.all_skills()),
        *((claim, "profile") for claim in candidate.specialties),
        *((edu.degree, "profile") for edu in candidate.education),
        *((exp.title, "held") for exp in candidate.experience),
    ]
    for claim, kind in claims:
        bare = _PARENTHETICAL_RE.sub("", claim).strip()
        folded = fold_text(bare)
        words = _keyword_candidates(bare)
        if not words or folded in seen or fold_text(claim) in seen:
            continue
        if any(folded in done or done in folded for done in already):
            continue
        seen.add(folded)
        if all(posting.has(word) for word in words):
            items.append(
                MatchItem(
                    label=f"{kind}:{bare}",
                    strength=MatchStrength.STRONG,
                    detail="the posting mentions it",
                )
            )
    for exp in candidate.experience:
        for ach in exp.achievements:
            words = {word for word in _keyword_candidates(ach.text) if len(word) >= _ECHO_MIN_WORD}
            hits = sorted(word for word in words if posting.has(word))
            if len(hits) >= _ECHO_MIN_HITS and len(hits) >= _ECHO_SHARE * len(words):
                items.append(
                    MatchItem(
                        label=f"achievement:{ach.id}",
                        strength=MatchStrength.STRONG,
                        detail=f"the posting echoes: {', '.join(hits[:5])}",
                    )
                )
    return items


def _keyword_candidates(text: str) -> set[str]:
    """Content words of the candidate's own prose — no vocabulary to belong to."""
    return {
        word
        for word in fold_text(text).split()
        if len(word) >= 4 and word not in _STOPWORDS
    }


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
    claimed. The titles in the profile are the only evidence there is. The headline
    is not one of them: made of degrees, it shares words with every teaching post.
    It can only make a partial match, and the score keeps the cap of a role never
    held unless the profile lists no experience at all.
    """
    label = f"role:{job.title}"
    wanted = _title_words(job.title)
    best: list[str] = []
    best_title = ""
    for exp in candidate.experience:
        index = WordIndex(frozenset(_title_words(exp.title)))
        shared = sorted(word for word in wanted if index.has(word))
        if len(shared) > len(best):
            best, best_title = shared, exp.title

    if len(best) >= 2:
        return (
            MatchItem(
                label=label,
                strength=MatchStrength.STRONG,
                detail=f"held title {best_title} shares: {', '.join(best)}",
            ),
            None,
        )
    if len(best) == 1:
        return (
            MatchItem(
                label=label,
                strength=MatchStrength.PARTIAL,
                detail=f"held title {best_title} shares: {best[0]}",
            ),
            70.0,
        )
    headline = WordIndex(frozenset(_title_words(candidate.personal.headline or "")))
    from_headline = sorted(word for word in wanted if headline.has(word))
    if from_headline:
        return (
            MatchItem(
                label=label,
                strength=MatchStrength.PARTIAL,
                detail=f"only the headline shares: {', '.join(from_headline)} (not a title held)",
            ),
            _HEADLINE_ONLY_CAP if candidate.experience else _HEADLINE_NO_HISTORY_CAP,
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
    # A posting that names almost nothing is thin evidence, not a perfect fit.
    if len(required_tokens - {""}) < _THIN_EVIDENCE_ITEMS:
        score = min(score, _THIN_EVIDENCE_CAP)
    if role_cap is not None:
        score = min(score, role_cap)
    return round(score, 1)
