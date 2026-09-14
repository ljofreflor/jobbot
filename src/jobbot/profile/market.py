"""Market-language suggestions for baseline CV (no invention; no deletions)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from jobbot.jobs.normalization import normalize_skill
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting

# Tokens often requested in DS/data JDs (canonical via normalize when possible)
_MARKET_TERMS = [
    "python",
    "sql",
    "pytorch",
    "xgboost",
    "scikit-learn",
    "machine learning",
    "deep learning",
    "causal inference",
    "experimentation",
    "a/b testing",
    "bayesian",
    "statistics",
    "spark",
    "airflow",
    "dbt",
    "bigquery",
    "snowflake",
    "aws",
    "gcp",
    "azure",
    "mlops",
    "llm",
    "nlp",
    "computer vision",
    "feature store",
    "kafka",
    "docker",
    "kubernetes",
]


@dataclass
class MarketGapQuestion:
    term: str
    reason: str
    evidence_jobs: list[str] = field(default_factory=list)


@dataclass
class MarketSuggestion:
    """Proposed baseline wording changes + questions (never auto-applied)."""

    market_terms: list[tuple[str, int]]  # term, count
    present: list[str]
    missing_suspected: list[MarketGapQuestion]
    rephrase_hints: list[str]
    summary_suggestion: str | None = None


def suggest_from_market(
    candidate: Candidate,
    jobs: list[JobPosting],
    *,
    min_count: int = 2,
) -> MarketSuggestion:
    """Extract frequent JD terms; suggest rephrases; flag gaps as questions only."""
    corpus = "\n".join((j.description or "") + "\n" + (j.raw_description or "") for j in jobs)
    counts = _count_market_terms(corpus)
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    frequent = [(t, c) for t, c in ranked if c >= min_count]

    cand_tokens = _candidate_token_set(candidate)
    present: list[str] = []
    missing: list[MarketGapQuestion] = []
    for term, count in frequent:
        if _term_present_in_profile(term, cand_tokens):
            present.append(term)
        else:
            job_ids = [
                j.id
                for j in jobs
                if term.casefold() in ((j.description or "") + (j.raw_description or "")).casefold()
            ][:5]
            missing.append(
                MarketGapQuestion(
                    term=term,
                    reason=(
                        f"Appears in {count} job description(s). "
                        "Confirm only if you have used it; otherwise leave out."
                    ),
                    evidence_jobs=job_ids,
                )
            )

    rephrase_hints = _rephrase_hints(candidate, present)
    summary_suggestion = None
    if present:
        top = ", ".join(present[:8])
        base = (candidate.summary or "").strip()
        if base and top:
            summary_suggestion = (
                f"{base}\n\n# Suggested market-aligned emphasis (review before promote):\n"
                f"# Highlight where already true: {top}."
            )
        elif top:
            summary_suggestion = (
                f"# Suggested emphasis (only keep facts you already have):\n# {top}."
            )

    return MarketSuggestion(
        market_terms=frequent,
        present=present,
        missing_suspected=missing,
        rephrase_hints=rephrase_hints,
        summary_suggestion=summary_suggestion,
    )


def render_suggestion_markdown(suggestion: MarketSuggestion) -> str:
    lines = [
        "# Market feedback (from stored job descriptions)",
        "",
        "Rules: do not invent experience; do not delete baseline facts;",
        "confirm gaps interactively before adding anything to profile.yaml.",
        "",
        "## Frequent market terms",
    ]
    if not suggestion.market_terms:
        lines.append("(none above threshold)")
    else:
        for term, count in suggestion.market_terms:
            lines.append(f"- {term} ({count})")
    lines += ["", "## Already reflected in profile"]
    lines += [f"- {t}" for t in suggestion.present] or ["- (none)"]
    lines += ["", "## Ask before adding (suspected gaps)"]
    if not suggestion.missing_suspected:
        lines.append("- (none)")
    else:
        for gap in suggestion.missing_suspected:
            jobs = ", ".join(gap.evidence_jobs) or "—"
            lines.append(f"- **{gap.term}**: {gap.reason} (jobs: {jobs})")
    lines += ["", "## Rephrase hints (presentation only)"]
    lines += [f"- {h}" for h in suggestion.rephrase_hints] or ["- (none)"]
    if suggestion.summary_suggestion:
        lines += [
            "",
            "## Summary draft (commented / review)",
            "```",
            suggestion.summary_suggestion,
            "```",
        ]
    lines.append("")
    return "\n".join(lines)


def apply_confirmed_skills(
    candidate: Candidate,
    confirmed: list[str],
    *,
    group: str = "machine_learning",
) -> Candidate:
    """Add user-confirmed skills only; never remove existing ones."""
    data = candidate.model_dump()
    skills = data.get("skills") or {}
    bucket = list(skills.get(group) or [])
    existing = {s.casefold() for s in bucket}
    for term in confirmed:
        if term.casefold() not in existing:
            bucket.append(term)
            existing.add(term.casefold())
    skills[group] = bucket
    data["skills"] = skills
    return Candidate.model_validate(data)


def merge_confirmed_skills_into_raw(
    raw: dict,
    confirmed: list[str],
    *,
    group: str = "machine_learning",
) -> dict:
    """Merge confirmed skills into a raw profile mapping (no deletions)."""
    import copy

    out = copy.deepcopy(raw)
    skills = out.setdefault("skills", {})
    if not isinstance(skills, dict):
        skills = {}
        out["skills"] = skills
    bucket = list(skills.get(group) or [])
    existing = {str(s).casefold() for s in bucket}
    for term in confirmed:
        if term.casefold() not in existing:
            bucket.append(term)
            existing.add(term.casefold())
    skills[group] = bucket
    return out


def _count_market_terms(corpus: str) -> Counter[str]:
    lowered = corpus.casefold()
    counts: Counter[str] = Counter()
    for term in _MARKET_TERMS:
        # word-ish boundary for short tokens
        if len(term) <= 3:
            pat = rf"(?<![a-z]){re.escape(term)}(?![a-z])"
            n = len(re.findall(pat, lowered))
        else:
            n = lowered.count(term.casefold())
        if n:
            counts[term] = n
    return counts


def _candidate_token_set(candidate: Candidate) -> set[str]:
    tokens: set[str] = set()
    for skill in candidate.skills.all_skills():
        tokens.add(normalize_skill(skill))
        tokens.add(skill.casefold())
    for specialty in candidate.specialties:
        tokens.add(normalize_skill(specialty))
        tokens.add(specialty.casefold())
    if candidate.summary:
        tokens.add(candidate.summary.casefold())
    for exp in candidate.experience:
        if exp.description:
            tokens.add(exp.description.casefold())
        for ach in exp.achievements:
            tokens.add(ach.text.casefold())
    return tokens


_IMPLIED_BY_STACK: dict[str, set[str]] = {
    "machine_learning": {
        "machine_learning",
        "pytorch",
        "xgboost",
        "scikit_learn",
        "tensorflow",
        "deep_learning",
        "lightgbm",
    },
    "statistics": {
        "statistics",
        "bayesian",
        "causal_inference",
        "experimentation",
        "survival_analysis",
        "ab_testing",
    },
}


def _term_present_in_profile(term: str, cand_tokens: set[str]) -> bool:
    canon = normalize_skill(term)
    if canon in cand_tokens or term.casefold() in cand_tokens:
        return True
    implied = _IMPLIED_BY_STACK.get(canon, set())
    return bool(implied & cand_tokens)


def _rephrase_hints(candidate: Candidate, present_market_terms: list[str]) -> list[str]:
    hints: list[str] = []
    if not present_market_terms:
        return hints
    # Suggest weaving known market terms into existing bullets when already present
    for exp in candidate.experience[:3]:
        for ach in exp.achievements[:2]:
            text = ach.text.casefold()
            hits = [t for t in present_market_terms if t.casefold() in text]
            if hits:
                hints.append(
                    f"Keep fact at {exp.company}: emphasize wording around {', '.join(hits[:3])} "
                    f"(bullet already contains the concept)."
                )
    if candidate.summary:
        hints.append(
            "Keep summary facts; optionally lead with market-aligned terms you already cover: "
            + ", ".join(present_market_terms[:5])
        )
    return hints[:10]
