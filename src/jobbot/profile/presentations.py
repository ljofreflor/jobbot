"""Presentation variants may rephrase. They may not change the headline or add a figure."""

from __future__ import annotations

import re
from typing import Any

from jobbot.models.candidate import Candidate

_NUMBER_GAP = re.compile(r"(?<=\d)[\s.,](?=\d)")
_DIGITS = re.compile(r"\d+")


def presentation_problems(candidate: Candidate, block: object) -> list[str]:
    """Headline key, a fixed sentence that is not the summary's prefix, or a new number."""
    if not isinstance(block, dict):
        return ["presentations is not a map"]
    summary = candidate.summary or ""
    fixed = block.get("fixed_sentence")
    problems: list[str] = []
    if not isinstance(fixed, str) or not summary.startswith(fixed):
        problems.append("fixed_sentence is not a prefix of summary")
    variants = block.get("variants")
    if not isinstance(variants, list):
        problems.append("variants is not a list")
        return problems
    known = set(_numbers(_fact_blob(candidate)))
    for item in variants:
        problems.extend(_variant_problems(item, known))
    return problems


def _variant_problems(item: object, known: set[str]) -> list[str]:
    if not isinstance(item, dict):
        return ["variant is not a map"]
    name = item.get("name")
    label = name.strip() if isinstance(name, str) and name.strip() else "?"
    problems: list[str] = []
    if label == "?":
        problems.append("variant missing name")
    if "headline" in item:
        problems.append(f"{label}: headline is not a variant")
    tail = item.get("summary_tail")
    if tail is None:
        return problems
    if not isinstance(tail, str):
        problems.append(f"{label}: summary_tail is not a phrase")
        return problems
    extra = set(_numbers(tail)) - known
    if extra:
        problems.append(f"{label}: number mismatch")
    return problems


def _fact_blob(candidate: Candidate) -> str:
    parts = [candidate.personal.headline, candidate.summary or ""]
    for exp in candidate.experience:
        parts.append(exp.title)
        parts.extend(item.text for item in exp.achievements)
    for edu in candidate.education:
        parts.append(edu.degree)
    return "\n".join(parts)


def _numbers(text: str) -> list[str]:
    return _DIGITS.findall(_NUMBER_GAP.sub("", text))


def presentations_block(raw: dict[str, Any]) -> Any:
    """The raw presentations map, when the file has one."""
    if "presentations" not in raw:
        return None
    return raw["presentations"]
