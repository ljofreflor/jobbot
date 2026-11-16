"""Offline admissibility of a public contest against the local profile.

Rules come only from the posting's exclusive-requirements block. A degree
matches a closed list by the whole phrase, never by a loose word, and an open
area is always a question. Missing semesters or leadership stay doubtful.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Literal

from jobbot.jobs.normalization import fold_text
from jobbot.models.candidate import Candidate
from jobbot.models.experience import Experience

RuleKind = Literal[
    "degree_list",
    "degree_area",
    "min_semesters",
    "min_years",
    "min_years_leadership",
    "other",
]
VerdictStatus = Literal["admisible", "no_admisible", "dudoso"]

_TAG = re.compile(r"<[^>]+>")
_EXCLUSIVE = re.compile(
    r"requisitos\s+(espec[ií]ficos|legales|excluyentes)\s*(.*)",
    re.IGNORECASE | re.DOTALL,
)
_STOP = re.compile(r"perfil de la funci[oó]n|competencias", re.IGNORECASE)
_ALTERNATIVE = re.compile(
    r"(?:^|\n)\s*(?:[a-zA-Z]\)|o bien|alternativamente)\s*",
    re.IGNORECASE,
)
_GENDER = re.compile(r"\([oaOA]\)")
_CODE = re.compile(r"c[oó]digo\s*:\s*([A-Za-z0-9-]+)", re.IGNORECASE)
_AREA = re.compile(r"[áa]rea de\s+([^.\n]+)", re.IGNORECASE)
_SEMESTERS = re.compile(r"(\d+)\s+semestres")
_YEARS = re.compile(r"(\d+)\s+anos")

UNREADABLE = "ficha sin requisitos excluyentes legibles"


@dataclass(frozen=True)
class AdmissibilityRule:
    kind: RuleKind
    alternatives_group: int
    accepted_degrees: tuple[str, ...] = ()
    area: str | None = None
    value: int | None = None
    source_text: str = ""


@dataclass(frozen=True)
class AdmissibilityVerdict:
    status: VerdictStatus
    rule: str
    evidence: str
    question: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "status": self.status,
            "rule": self.rule,
            "evidence": self.evidence,
            "question": self.question,
        }


def contest_code(text: str, fallback: str) -> str:
    """Contest code printed on the sheet, or the stored job id."""
    match = _CODE.search(_plain(text))
    return match.group(1) if match else fallback


def extract_rules(text: str) -> list[AdmissibilityRule]:
    """Rules inside the exclusive block. A later function profile is ignored."""
    section = _exclusive_section(_plain(text))
    if not section:
        return []
    rules: list[AdmissibilityRule] = []
    for index, chunk in enumerate(part for part in _ALTERNATIVE.split(section) if part.strip()):
        rules.extend(_rules_in_chunk(chunk.strip(), index))
    return rules


def assess(
    rules: list[AdmissibilityRule],
    candidate: Candidate,
    *,
    contest_code: str = "",
    today: date | None = None,
) -> AdmissibilityVerdict:
    """One verdict. A fully evidenced group wins; a missing fact stays doubtful."""
    if not rules:
        return AdmissibilityVerdict("dudoso", "", UNREADABLE, UNREADABLE)
    when = today or date.today()
    groups: dict[int, list[AdmissibilityRule]] = {}
    for rule in rules:
        groups.setdefault(rule.alternatives_group, []).append(rule)
    met: tuple[str, str] | None = None
    missing: tuple[str, str] | None = None
    failed: tuple[str, str] | None = None
    for group in groups.values():
        source = group[0].source_text
        blocked = False
        notes: list[str] = []
        for rule in group:
            state, detail = _eval_rule(rule, candidate, contest_code=contest_code, today=when)
            if state == "fail":
                failed = failed or (source, detail)
                blocked = True
                break
            if state == "missing":
                missing = missing or (source, detail)
                blocked = True
                break
            notes.append(detail)
        if not blocked and met is None:
            met = (source, "; ".join(notes))
    if met is not None:
        return AdmissibilityVerdict("admisible", met[0], met[1])
    if missing is not None:
        return AdmissibilityVerdict("dudoso", missing[0], missing[1], missing[1])
    assert failed is not None
    return AdmissibilityVerdict("no_admisible", failed[0], failed[1])


def shortlist_mark(path: object) -> str:
    """Mark already stored for this job. Absent file or an admissible verdict adds nothing."""
    from pathlib import Path

    file = Path(str(path))
    if not file.is_file():
        return ""
    status = json.loads(file.read_text(encoding="utf-8")).get("status")
    if status == "no_admisible":
        return "  [no admisible]"
    if status == "dudoso":
        return "  [dudoso]"
    return ""


def _plain(text: str) -> str:
    return _TAG.sub("\n", text)


def _exclusive_section(text: str) -> str:
    match = _EXCLUSIVE.search(text)
    if match is None:
        return ""
    rest = match.group(2)
    stop = _STOP.search(rest)
    if stop is not None:
        rest = rest[: stop.start()]
    return rest.strip()


def _rules_in_chunk(chunk: str, group: int) -> list[AdmissibilityRule]:
    folded = fold_text(chunk)
    rules: list[AdmissibilityRule] = []
    area = _AREA.search(chunk)
    if "titulo" in folded and area is not None:
        rules.append(
            AdmissibilityRule(
                "degree_area",
                group,
                area=area.group(1).strip(),
                source_text=chunk,
            )
        )
    else:
        degrees = _degree_phrases(chunk)
        if degrees:
            rules.append(
                AdmissibilityRule(
                    "degree_list",
                    group,
                    accepted_degrees=degrees,
                    source_text=chunk,
                )
            )
    semesters = _SEMESTERS.search(folded)
    if semesters is not None:
        rules.append(
            AdmissibilityRule(
                "min_semesters",
                group,
                value=int(semesters.group(1)),
                source_text=chunk,
            )
        )
    years = _YEARS.search(folded)
    if "jefatura" in folded:
        rules.append(
            AdmissibilityRule(
                "min_years_leadership",
                group,
                value=int(years.group(1)) if years else None,
                source_text=chunk,
            )
        )
    elif years is not None:
        rules.append(
            AdmissibilityRule(
                "min_years",
                group,
                value=int(years.group(1)),
                source_text=chunk,
            )
        )
    if not rules and folded:
        rules.append(AdmissibilityRule("other", group, source_text=chunk))
    return rules


def _degree_phrases(chunk: str) -> tuple[str, ...]:
    folded = fold_text(_GENDER.sub("", chunk))
    if "titulo" not in folded or "area de" in folded:
        return ()
    body = re.sub(r"^.*?titulo(?: profesional)? de ", "", folded)
    if re.search(r"\d+\s+semestres|\d+\s+anos", body):
        return ()
    phrases = tuple(part.strip() for part in body.split(" o ") if re.search(r"[a-z]", part))
    return phrases


def _same_phrase(phrase: str, degree: str) -> bool:
    return fold_text(_GENDER.sub("", degree)) == phrase


def _eval_rule(
    rule: AdmissibilityRule,
    candidate: Candidate,
    *,
    contest_code: str,
    today: date,
) -> tuple[Literal["met", "fail", "missing"], str]:
    if rule.kind == "degree_list":
        for education in candidate.education:
            if any(_same_phrase(phrase, education.degree) for phrase in rule.accepted_degrees):
                return "met", education.id
        return "fail", "el título del perfil no está en la lista"
    if rule.kind == "degree_area":
        return "missing", _area_question(candidate, rule.area or "", contest_code)
    if rule.kind == "min_semesters":
        return _semesters(candidate, rule.value or 0)
    if rule.kind == "min_years":
        years = _years(candidate.experience, today)
        if years + 1e-9 >= (rule.value or 0):
            return "met", f"{years:.0f} años de experiencia"
        return "fail", "los años de experiencia no alcanzan el mínimo"
    if rule.kind == "min_years_leadership":
        return _leadership(candidate, rule.value or 0, today)
    return "missing", UNREADABLE


def _area_question(candidate: Candidate, area: str, code: str) -> str:
    degree = candidate.education[0].degree if candidate.education else "el perfil"
    semesters = candidate.education[0].duration_semesters if candidate.education else None
    span = f" ({semesters} semestres)" if semesters else ""
    return (
        f"¿El título de {degree}{span} se considera del área de {area} "
        f"para el requisito específico del concurso {code}?"
    )


def _semesters(candidate: Candidate, minimum: int) -> tuple[Literal["met", "fail", "missing"], str]:
    known = [item for item in candidate.education if item.duration_semesters is not None]
    matched = next((item for item in known if (item.duration_semesters or 0) >= minimum), None)
    if matched is not None:
        return "met", f"{matched.id}: {matched.duration_semesters} semestres"
    if not known:
        degree = candidate.education[0].degree if candidate.education else "el título"
        return "missing", f"¿Cuántos semestres dura el título de {degree}?"
    return "fail", "los semestres del título no alcanzan el mínimo"


def _leadership(
    candidate: Candidate,
    minimum: int,
    today: date,
) -> tuple[Literal["met", "fail", "missing"], str]:
    marked = [item for item in candidate.experience if item.leadership is True]
    years = _years(marked, today)
    if years + 1e-9 >= minimum:
        return "met", f"{years:.0f} años en jefatura"
    if any(item.leadership is None for item in candidate.experience) or not candidate.experience:
        return "missing", "¿Alguno de los cargos fue de jefatura con personas a cargo?"
    return "fail", "ningún cargo está marcado como jefatura"


def _years(roles: list[Experience], today: date) -> float:
    spans: list[tuple[int, int]] = []
    for role in roles:
        if role.end_date:
            end = _month_index(role.end_date)
        elif role.current:
            end = today.year * 12 + today.month
        else:
            continue
        start = _month_index(role.start_date)
        if end >= start:
            spans.append((start, end))
    return _merged_years(spans)


def _month_index(value: str) -> int:
    year, month = value.split("-")
    return int(year) * 12 + int(month)


def _merged_years(spans: list[tuple[int, int]]) -> float:
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
