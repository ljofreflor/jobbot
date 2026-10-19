"""Achievement / content selection for CV builds."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from jobbot.jobs.normalization import fold_text, normalize_skill
from jobbot.jobs.parsing import extract_skills_from_text
from jobbot.matching.analyzer import achievement_echo_hits, posting_word_index
from jobbot.models.candidate import Candidate
from jobbot.models.experience import Achievement, Experience
from jobbot.models.job import JobPosting
from jobbot.models.match import JobMatch

# A terse LinkedIn / email-apply post is not enough signal to shrink the CV.
_SHORT_JD_CHARS = 400
_MIN_EXPERIENCES = 4
_MIN_ACHIEVEMENTS = 4
_FLOOR_REASON = "floor: short JD — kept recent evidence so the CV stays usable"
_FLOOR_FEW_REASON = "floor: few experiences matched the posting"
_FALLBACK_REASON = "fallback: no strong keyword overlap; kept recent evidence"
_FULL_REASON = "full: kept from profile, no overlap with the posting"
_FEW_TOKENS = 3


@dataclass
class SelectedAchievement:
    id: str
    reason: list[str] = field(default_factory=list)


@dataclass
class SelectionResult:
    """Which profile facts to include in a derived CV."""

    experience_ids: list[str]
    selected_achievements: list[SelectedAchievement]
    skill_names: list[str]
    include_publications: bool = True
    job_id: str | None = None
    # Achievements render in selection order (by relevance) instead of profile order.
    full: bool = False
    # Terms the posting names that the profile does not. Never copied onto the CV.
    gaps: list[str] = field(default_factory=list)
    # False when the posting had no extracted terms and none selected an achievement.
    used_posting_terms: bool = True

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "experience_ids": self.experience_ids,
            "selected_achievements": [
                {"id": a.id, "reason": a.reason} for a in self.selected_achievements
            ],
            "skill_names": self.skill_names,
            "include_publications": self.include_publications,
        }
        if self.job_id:
            payload["job_id"] = self.job_id
        if self.full:
            payload["full"] = True
        if self.gaps:
            payload["gaps"] = self.gaps
        return payload


def select_for_base_cv(candidate: Candidate) -> SelectionResult:
    """Select all profile content for the base (non-job-specific) CV."""
    achievements: list[SelectedAchievement] = []
    for exp in candidate.experience:
        for ach in exp.achievements:
            achievements.append(SelectedAchievement(id=ach.id, reason=["included in base CV"]))
    return SelectionResult(
        experience_ids=[e.id for e in candidate.experience],
        selected_achievements=achievements,
        skill_names=candidate.skills.all_skills(),
        include_publications=True,
    )


def select_for_job(
    candidate: Candidate,
    job: JobPosting,
    match: JobMatch | None = None,
    *,
    full: bool = False,
) -> SelectionResult:
    """Select achievements/skills overlapping the job — never invent.

    ``full`` keeps every role and achievement; inside each role the ones the posting
    names come first (most overlap first, ties in profile order).
    """
    job_tokens = _job_tokens(job)
    if full:
        return _select_full(candidate, job, job_tokens)
    selected: list[SelectedAchievement] = []
    exp_ids: list[str] = []

    for exp in candidate.experience:
        exp_selected = False
        for ach in exp.achievements:
            reasons = _achievement_reasons(ach, exp, job_tokens, job)
            if reasons:
                selected.append(SelectedAchievement(id=ach.id, reason=reasons))
                exp_selected = True
        if exp_selected or _experience_relevant(exp, job_tokens):
            exp_ids.append(exp.id)

    few_tokens = len(job_tokens) < _FEW_TOKENS
    used_terms = bool(selected)
    if not selected and few_tokens:
        echoed = _echoed_achievements(candidate, job, match)
        if echoed:
            for exp, ach, reason in echoed:
                selected.append(SelectedAchievement(id=ach.id, reason=[reason]))
                exp_ids.append(exp.id)
        else:
            for exp in _by_recency(candidate)[:3]:
                exp_ids.append(exp.id)
                for ach in exp.achievements[:2]:
                    selected.append(SelectedAchievement(id=ach.id, reason=[_FALLBACK_REASON]))
    elif not selected:
        for exp in _by_recency(candidate)[:3]:
            exp_ids.append(exp.id)
            for ach in exp.achievements[:2]:
                selected.append(SelectedAchievement(id=ach.id, reason=[_FALLBACK_REASON]))

    jd_blob = " ".join(
        part
        for part in (job.description, job.title, "\n".join(job.requirements))
        if part
    )
    short_jd = len(jd_blob) < _SHORT_JD_CHARS
    if short_jd or len({e for e in exp_ids}) < _MIN_EXPERIENCES:
        _pad_selection_floor(
            candidate,
            exp_ids,
            selected,
            reason=_FLOOR_REASON if short_jd else _FLOOR_FEW_REASON,
        )

    # Skills: intersection only
    skill_names = [
        s for s in candidate.skills.all_skills() if normalize_skill(s) in job_tokens
    ]
    if not skill_names:
        skill_names = candidate.skills.all_skills()[:8]

    # Dedupe experience ids preserving order
    seen: set[str] = set()
    ordered_exp: list[str] = []
    for eid in exp_ids:
        if eid not in seen:
            seen.add(eid)
            ordered_exp.append(eid)

    return SelectionResult(
        experience_ids=ordered_exp,
        selected_achievements=selected,
        skill_names=skill_names,
        include_publications=True,
        job_id=job.id,
        gaps=_gaps(candidate, job),
        used_posting_terms=used_terms or not few_tokens,
    )


def _select_full(
    candidate: Candidate,
    job: JobPosting,
    job_tokens: set[str],
) -> SelectionResult:
    selected: list[SelectedAchievement] = []
    for exp in candidate.experience:
        scored = [
            SelectedAchievement(
                id=ach.id,
                reason=_achievement_reasons(ach, exp, job_tokens, job) or [_FULL_REASON],
            )
            for ach in exp.achievements
        ]
        selected += sorted(scored, key=lambda item: -_overlap(item))
    related = [s for s in candidate.skills.all_skills() if normalize_skill(s) in job_tokens]
    return SelectionResult(
        experience_ids=[exp.id for exp in candidate.experience],
        selected_achievements=selected,
        skill_names=related + [s for s in candidate.skills.all_skills() if s not in related],
        include_publications=True,
        job_id=job.id,
        full=True,
        gaps=_gaps(candidate, job),
    )


def _by_recency(candidate: Candidate) -> list[Experience]:
    """Most recent role first. A tie keeps profile order."""
    indexed = list(enumerate(candidate.experience))
    indexed.sort(key=lambda pair: (pair[1].start_date or "", -pair[0]), reverse=True)
    return [exp for _, exp in indexed]


def _echoed_achievements(
    candidate: Candidate,
    job: JobPosting,
    match: JobMatch | None,
) -> list[tuple[Experience, Achievement, str]]:
    """Achievements the posting repeats, most overlap first, then the more recent role."""
    index = posting_word_index(job)
    found: dict[str, tuple[int, str]] = {}
    owners: dict[str, tuple[Experience, Achievement, int]] = {}
    for position, exp in enumerate(candidate.experience):
        for ach in exp.achievements:
            owners[ach.id] = (exp, ach, position)
            hits = achievement_echo_hits(ach.text, index)
            if hits:
                found[ach.id] = (len(hits), f"posting echoes: {', '.join(hits[:5])}")
    if match is not None:
        for item in match.items:
            prefix = "achievement:"
            if not item.label.startswith(prefix):
                continue
            ach_id = item.label[len(prefix) :]
            if ach_id in found or ach_id not in owners:
                continue
            detail = item.detail or ""
            if "echo" not in detail.casefold():
                continue
            shown = detail.split(":", 1)[-1].strip()
            count = len([part for part in shown.split(",") if part.strip()])
            found[ach_id] = (count, f"posting echoes: {shown}")
    ranked: list[tuple[int, str, int, Experience, Achievement, str]] = []
    for ach_id, (hit_count, reason) in found.items():
        exp, ach, position = owners[ach_id]
        ranked.append((hit_count, exp.start_date or "", -position, exp, ach, reason))
    ranked.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    return [(exp, ach, reason) for _, _, _, exp, ach, reason in ranked]


def _overlap(item: SelectedAchievement) -> int:
    return sum(1 for reason in item.reason if reason != _FULL_REASON)


def _pad_selection_floor(
    candidate: Candidate,
    exp_ids: list[str],
    selected: list[SelectedAchievement],
    *,
    reason: str = _FLOOR_REASON,
) -> None:
    """Keep enough recent evidence when the posting did not fill the CV."""
    selected_ids = {item.id for item in selected}
    for exp in candidate.experience:
        if len({eid for eid in exp_ids}) >= _MIN_EXPERIENCES and len(selected) >= _MIN_ACHIEVEMENTS:
            return
        if exp.id not in exp_ids:
            exp_ids.append(exp.id)
        for ach in exp.achievements:
            if ach.id in selected_ids:
                continue
            selected.append(SelectedAchievement(id=ach.id, reason=[reason]))
            selected_ids.add(ach.id)
            if (
                len(selected) >= _MIN_ACHIEVEMENTS
                and len({eid for eid in exp_ids}) >= _MIN_EXPERIENCES
            ):
                return


def write_selection_json(selection: SelectionResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(selection.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def filter_experiences(
    candidate: Candidate,
    selection: SelectionResult,
) -> list[tuple[Experience, list[Achievement]]]:
    """Return experiences with only selected achievements.

    Roles keep profile order. Achievements keep profile order too, unless the selection
    is ``full``: then they follow the selection's relevance order.
    """
    rank = {a.id: i for i, a in enumerate(selection.selected_achievements)}
    allowed_exp = set(selection.experience_ids)
    result: list[tuple[Experience, list[Achievement]]] = []
    for exp in candidate.experience:
        if exp.id not in allowed_exp:
            continue
        achs = [a for a in exp.achievements if a.id in rank]
        if selection.full:
            achs.sort(key=lambda a: rank[a.id])
        result.append((exp, achs))
    return result


def _gaps(candidate: Candidate, job: JobPosting) -> list[str]:
    """Posting skills the profile never states. They stay off the CV."""
    haystack = fold_text(
        "\n".join(
            [
                candidate.summary or "",
                *candidate.specialties,
                *candidate.skills.all_skills(),
                *(exp.title for exp in candidate.experience),
                *(exp.description or "" for exp in candidate.experience),
                *(ach.text for exp in candidate.experience for ach in exp.achievements),
                *(edu.degree for edu in candidate.education),
            ]
        )
    )
    gaps: list[str] = []
    for skill in job.skills:
        needle = fold_text(skill)
        if len(needle) < 3:
            continue
        if re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is None:
            gaps.append(skill)
    return gaps


def _job_tokens(job: JobPosting) -> set[str]:
    """What the job asks for, in its own words: skills it names plus its title."""
    named = [*job.skills, *extract_skills_from_text(job.title)]
    if len(named) < 3:
        # Short or prose-only postings: read the requirement lines as well.
        named += extract_skills_from_text("\n".join(job.requirements))
    tokens = {normalize_skill(skill) for skill in named}
    return {token for token in tokens if token}


def _achievement_reasons(
    ach: Achievement,
    exp: Experience,
    job_tokens: set[str],
    job: JobPosting,
) -> list[str]:
    reasons: list[str] = []
    for tag in ach.tags:
        token = normalize_skill(tag)
        if token in job_tokens:
            reasons.append(f"tag overlap: {tag}")
    folded = fold_text(ach.text)
    for token in job_tokens:
        phrase = fold_text(token.replace("_", " "))
        if phrase and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", folded):
            reasons.append(f"achievement mentions {phrase}")
    if reasons and ach.metrics:
        # A quantified bullet is stronger evidence, whatever the unit measures.
        units = ", ".join(sorted(ach.metrics)[:3])
        reasons.append(f"quantified result ({units})")
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _experience_relevant(exp: Experience, job_tokens: set[str]) -> bool:
    blob = fold_text(f"{exp.title} {exp.company} {exp.description or ''}")
    return any(
        re.search(rf"(?<!\w){re.escape(fold_text(token.replace('_', ' ')))}(?!\w)", blob)
        for token in job_tokens
        if token
    )
