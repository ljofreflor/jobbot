"""Skills, seniority and English on the Get on Board profile, from the local profile.

The portal accepts at most ten skills. A skill with no level, or a CEFR level the
dropdown does not list, stays needs_human. Nothing here invents a level.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from jobbot.adapters.getonboard.profile_edit import PageLike, set_chosen_select
from jobbot.jobs.conditions import language_mentions
from jobbot.jobs.eligibility import ApplicationAnswers
from jobbot.jobs.normalization import fold_text
from jobbot.models.candidate import Candidate
from jobbot.models.experience import Experience

SKILL_LIMIT = 10
NEEDS_HUMAN = "needs_human"
SKILLS_SELECTOR = "select#skills"
SKILLS_MISSING = "campo no encontrado: skills (¿cambió el portal?)"
SECTIONS = frozenset({"skills", "seniority", "english"})

# Last observed dropdowns. Tests keep the fixture HTML equal to these pairs.
OBSERVED_ENGLISH: tuple[tuple[str, str], ...] = (("4", "B2"), ("5", "C1"))
OBSERVED_SENIORITY: tuple[tuple[str, str], ...] = (
    ("1", "Junior"),
    ("2", "Semi Senior"),
    ("3", "Senior"),
)

_LEVELS = frozenset({"beginner", "intermediate", "advanced", "proficient"})
_OPTION = re.compile(
    r'<option[^>]*value="([^"]*)"[^>]*>\s*([^<]*?)\s*</option>',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SkillRow:
    name: str
    level: str | None
    status: str


@dataclass(frozen=True)
class SkillPlan:
    rows: tuple[SkillRow, ...]
    trimmed: tuple[str, ...]
    note: str


def parse_sections(text: str) -> set[str]:
    """Comma-separated section names, or an error string the CLI can print."""
    parts = [part.strip().casefold() for part in text.split(",") if part.strip()]
    unknown = [part for part in parts if part not in SECTIONS]
    if not parts or unknown:
        msg = "secciones: skills, seniority, english"
        raise ValueError(msg)
    return set(parts)


def skill_level_map(candidate: Candidate) -> dict[str, str]:
    """Optional levels beside the skill lists. A missing name has no level."""
    extra = candidate.skills.model_extra or {}
    raw = extra.get("levels")
    if not isinstance(raw, dict):
        return {}
    return {str(name): str(level) for name, level in raw.items() if str(name).strip()}


def plan_skills(names: list[str], levels: dict[str, str], *, limit: int = SKILL_LIMIT) -> SkillPlan:
    """First ``limit`` skills in the given order. The rest are named in the note."""
    folded = {name.casefold(): level for name, level in levels.items()}
    rows: list[SkillRow] = []
    for name in names[:limit]:
        level = folded.get(name.casefold())
        if level is None or level.casefold() not in _LEVELS:
            rows.append(SkillRow(name, None, NEEDS_HUMAN))
        else:
            rows.append(SkillRow(name, level.casefold(), "planned"))
    trimmed = tuple(names[limit:])
    note = ""
    if trimmed:
        note = f"recorte: {len(trimmed)} skills quedan fuera del máximo de {limit}"
    return SkillPlan(tuple(rows), trimmed, note)


def options_for(html: str, select_name: str) -> list[tuple[str, str]]:
    """(value, label) pairs inside the named select. Empty when the control is absent."""
    pattern = re.compile(
        rf'<select[^>]*name="{re.escape(select_name)}"[^>]*>(.*?)</select>',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(html)
    if match is None:
        return []
    return [
        (value, label.strip())
        for value, label in _OPTION.findall(match.group(1))
        if value and label.strip()
    ]


def project_english(level: str, options: list[tuple[str, str]]) -> str | None:
    """Option value whose label contains the CEFR token. None when there is no single match."""
    token = level.strip().upper()
    if not token:
        return None
    hits = [value for value, label in options if token in label.upper()]
    if len(hits) == 1:
        return hits[0]
    return None


def project_seniority(years: float, options: list[tuple[str, str]]) -> str | None:
    """One dropdown value for the years, or None when the options do not decide."""
    if years < 3:
        needle, blocked = "junior", "semi"
    elif years < 6:
        needle, blocked = "semi", ""
    else:
        needle, blocked = "senior", "semi"
    hits: list[str] = []
    for value, label in options:
        folded = fold_text(label)
        if needle in folded and (not blocked or blocked not in folded):
            hits.append(value)
    if len(hits) == 1:
        return hits[0]
    return None


def english_level(candidate: Candidate, answers: ApplicationAnswers | None) -> str | None:
    """CEFR for English from the answers file, else from a line in the profile."""
    if answers is not None:
        stated = answers.language_level("en")
        if stated:
            return stated
    texts = [*candidate.specialties, *candidate.skills.all_skills()]
    for text in texts:
        for code, level in language_mentions(text):
            if code == "en" and level:
                return level
    return None


def _month_index(value: str) -> int:
    year, month = value.split("-")
    return int(year) * 12 + int(month)


def experience_years(roles: list[Experience], *, today: date | None = None) -> float:
    """Years covered by the dated roles, merging overlaps. Undated roles add nothing."""
    when = today or date.today()
    spans: list[tuple[int, int]] = []
    for role in roles:
        start = _month_index(role.start_date)
        if role.end_date:
            end = _month_index(role.end_date)
        elif role.current:
            end = when.year * 12 + when.month
        else:
            continue
        if end >= start:
            spans.append((start, end))
    if not spans:
        return 0.0
    ordered = sorted(spans)
    total = 0
    start, end = ordered[0]
    for next_start, next_end in ordered[1:]:
        if next_start <= end:
            end = max(end, next_end)
            continue
        total += end - start
        start, end = next_start, next_end
    total += end - start
    return total / 12


def render_section_plan(
    candidate: Candidate,
    answers: ApplicationAnswers | None,
    sections: set[str],
) -> list[str]:
    """Lines for ``getonboard sync --section``. No browser and no write."""
    lines: list[str] = []
    if "skills" in sections:
        plan = plan_skills(candidate.skills.all_skills(), skill_level_map(candidate))
        for row in plan.rows:
            shown = row.level if row.level else NEEDS_HUMAN
            lines.append(f"skill  {row.name}  {shown}")
        if plan.note:
            lines.append(plan.note)
    if "english" in sections:
        level = english_level(candidate, answers)
        picked = project_english(level, list(OBSERVED_ENGLISH)) if level else None
        if picked is None:
            lines.append(f"english  {NEEDS_HUMAN}")
        else:
            lines.append(f"english  {level}  {picked}")
    if "seniority" in sections:
        years = experience_years(candidate.experience)
        picked = project_seniority(years, list(OBSERVED_SENIORITY))
        if picked is None:
            lines.append(f"seniority  {NEEDS_HUMAN}")
        else:
            lines.append(f"seniority  {picked}")
    return lines


def set_skills_select(page: PageLike, value: str) -> None:
    """Choose one skill on the hidden Chosen select. Does not open the level modal."""
    set_chosen_select(page, SKILLS_SELECTOR, value, missing=SKILLS_MISSING)
