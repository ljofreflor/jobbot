"""Cumulative text refinement for portal profile blurbs.

Previous drafts are computational capital: each iteration should improve them
using profile.yaml as the fact base — not discard and regenerate from scratch.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from jobbot.adapters.getonboard.draft import (
    EDUCATION_MAX,
    EXPERIENCE_MAX,
    PermanentProfileFields,
    build_permanent_profile_fields,
)
from jobbot.models.candidate import Candidate

logger = logging.getLogger("jobbot.nlp.refine")


class ProfileTextRefiner(Protocol):
    def refine(
        self,
        candidate: Candidate,
        previous: PermanentProfileFields | None,
    ) -> PermanentProfileFields: ...


@dataclass(frozen=True)
class RefineResult:
    fields: PermanentProfileFields
    mode: str  # cold | cumulative | llm
    kept_paragraphs: int
    added_paragraphs: int
    dropped_paragraphs: int


def refine_permanent_profile(
    candidate: Candidate,
    previous: PermanentProfileFields | None,
    *,
    use_llm: bool = False,
) -> RefineResult:
    """Prefer cumulative refine; optional LangChain when use_llm=True.

    NL work lives here (not in chat): heuristics by default, LLM only if requested.
    """
    from jobbot.nlp.gateway import run_optional_llm

    def _deterministic() -> RefineResult:
        if previous is None:
            cold = build_permanent_profile_fields(candidate)
            return RefineResult(
                fields=cold,
                mode="cold",
                kept_paragraphs=0,
                added_paragraphs=0,
                dropped_paragraphs=0,
            )
        return CumulativeProfileRefiner().refine_with_stats(candidate, previous)

    def _llm() -> RefineResult:
        from jobbot.nlp.langchain_refine import LangChainProfileRefiner

        fields = LangChainProfileRefiner().refine(candidate, previous)
        return RefineResult(
            fields=fields,
            mode="llm",
            kept_paragraphs=0,
            added_paragraphs=0,
            dropped_paragraphs=0,
        )

    outcome = run_optional_llm(
        deterministic=_deterministic,
        llm=_llm,
        use_llm=use_llm,
        task_name="permanent_profile_refine",
    )
    if outcome.mode == "llm_fallback":
        logger.warning("LLM refine fell back: %s", outcome.detail)
    return outcome.value


class CumulativeProfileRefiner:
    """Improve previous GoB texts using Candidate facts — keep what still holds."""

    def refine(
        self,
        candidate: Candidate,
        previous: PermanentProfileFields | None,
    ) -> PermanentProfileFields:
        return self.refine_with_stats(candidate, previous).fields

    def refine_with_stats(
        self,
        candidate: Candidate,
        previous: PermanentProfileFields | None,
    ) -> RefineResult:
        if previous is None:
            cold = build_permanent_profile_fields(candidate)
            return RefineResult(
                fields=cold,
                mode="cold",
                kept_paragraphs=0,
                added_paragraphs=0,
                dropped_paragraphs=0,
            )

        cold = build_permanent_profile_fields(candidate)
        companies = _company_tokens(candidate)
        exp_text, kept, added, dropped = _merge_experience(
            previous.experiencia_y_perfil,
            cold.experiencia_y_perfil,
            companies,
            EXPERIENCE_MAX,
        )
        edu_text, _, _, _ = _merge_experience(
            previous.formacion_academica,
            cold.formacion_academica,
            _education_tokens(candidate),
            EDUCATION_MAX,
        )
        fields = PermanentProfileFields(
            experiencia_y_perfil=exp_text,
            formacion_academica=edu_text,
            headline=candidate.personal.headline or previous.headline,
            skills=list(candidate.skills.all_skills())[:10] or previous.skills,
            signature=previous.signature,
        )
        return RefineResult(
            fields=fields,
            mode="cumulative",
            kept_paragraphs=kept,
            added_paragraphs=added,
            dropped_paragraphs=dropped,
        )


def _company_tokens(candidate: Candidate) -> set[str]:
    tokens: set[str] = set()
    for exp in candidate.experience:
        for part in re.split(r"[/|,]", exp.company):
            t = part.strip().casefold()
            if len(t) >= 3:
                tokens.add(t)
        tokens.add(exp.title.casefold())
    if candidate.summary:
        tokens.add(candidate.summary.casefold())
    return tokens


def _education_tokens(candidate: Candidate) -> set[str]:
    tokens: set[str] = set()
    for edu in candidate.education:
        tokens.add(edu.institution.casefold())
        tokens.add(edu.degree.casefold())
    for pub in candidate.publications:
        if pub.journal:
            tokens.add(pub.journal.casefold())
        tokens.add(pub.title.casefold())
    for exp in candidate.experience:
        title_l = exp.title.casefold()
        if any(k in title_l for k in ("profesor", "docente", "ayudante", "investigador")):
            tokens.add(exp.company.casefold())
            tokens.add(title_l)
    return tokens


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _paragraph_supported(paragraph: str, anchors: set[str]) -> bool:
    """Keep paragraph if it overlaps known anchors, or looks like a summary lead."""
    lower = paragraph.casefold()
    if any(a in lower for a in anchors if len(a) >= 4):
        return True
    # Short generic lead without obsolete company names still useful
    obsolete = (
        "ceamos",
        "matlab",
        "mayavi",
        "adexus",
        "adacom",
        "mmgeo",
        "back-caving",
        "vtk",
        "qt-python",
    )
    if any(o in lower for o in obsolete):
        return False
    # Keep if it mentions senior data / consultor without obsolete stack
    return bool(
        re.search(
            r"data scientist|estadística|inferencia causal|thoughtworks|mercado",
            lower,
        )
    )


def _merge_experience(
    previous: str,
    cold: str,
    anchors: set[str],
    maximum: int,
) -> tuple[str, int, int, int]:
    prev_parts = _paragraphs(previous)
    cold_parts = _paragraphs(cold)
    kept: list[str] = []
    dropped = 0
    for part in prev_parts:
        if _paragraph_supported(part, anchors):
            kept.append(part)
        else:
            dropped += 1

    # Ensure cold facts for recent companies appear if missing
    added = 0
    cold_missing: list[str] = []
    kept_blob = "\n".join(kept).casefold()
    for part in cold_parts:
        # If cold paragraph introduces a company/title not covered, append
        tokens = re.findall(r"[a-záéíóúñ]{4,}", part.casefold())
        if not tokens:
            continue
        # Prefer appending role paragraphs that mention companies in anchors
        if (
            any(a in part.casefold() for a in anchors)
            and part.casefold() not in kept_blob
            and not any(_similar(part, k) for k in kept)
        ):
            cold_missing.append(part)
            added += 1

    merged = kept + cold_missing
    # Prefer order: summary-like first (from kept or cold), then roles
    text = "\n\n".join(merged).strip()
    if len(text) > maximum:
        # Drop from the end of cold additions first, then oldest kept
        while merged and len("\n\n".join(merged)) > maximum:
            merged.pop()
        text = "\n\n".join(merged).strip()
    if not text:
        text = cold[:maximum]
        added = len(cold_parts)
        kept = []
        dropped = len(prev_parts)
    return text, len(kept), added, dropped


def _similar(a: str, b: str, *, threshold: float = 0.55) -> bool:
    ta = set(re.findall(r"[a-záéíóúñ0-9]{4,}", a.casefold()))
    tb = set(re.findall(r"[a-záéíóúñ0-9]{4,}", b.casefold()))
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold
