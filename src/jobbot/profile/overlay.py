"""English texts keyed by the profile's own ids. Nothing here is written back."""

from __future__ import annotations

import re
from typing import Any

import yaml

from jobbot.models.candidate import Candidate

_NUMBER_GAP = re.compile(r"(?<=\d)[\s.,](?=\d)")
_DIGITS = re.compile(r"\d+")


def base_texts(candidate: Candidate) -> dict[str, str]:
    """Id → the text the base profile already stores."""
    texts: dict[str, str] = {"headline": candidate.personal.headline}
    if candidate.summary:
        texts["summary"] = candidate.summary
    for exp in candidate.experience:
        texts[exp.id] = exp.title
        for achievement in exp.achievements:
            texts[achievement.id] = achievement.text
    for edu in candidate.education:
        texts[edu.id] = edu.degree
    return texts


def read_overlay(path_text: str) -> dict[str, str]:
    """``texts: {id: phrase}``. Any other shape is an error string, not a guess."""
    loaded: Any = yaml.safe_load(path_text) or {}
    if not isinstance(loaded, dict) or not isinstance(loaded.get("texts"), dict):
        msg = "overlay needs a texts map of id to phrase"
        raise ValueError(msg)
    texts: dict[str, str] = {}
    for key, value in loaded["texts"].items():
        if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
            msg = f"overlay text for {key} is not a phrase"
            raise ValueError(msg)
        texts[key] = value.strip()
    return texts


def _numbers(text: str) -> list[str]:
    folded = _NUMBER_GAP.sub("", text)
    return _DIGITS.findall(folded)


def overlay_problems(candidate: Candidate, texts: dict[str, str]) -> list[str]:
    """Unknown ids, and phrases whose numbers are not the base phrase's numbers."""
    base = base_texts(candidate)
    problems: list[str] = []
    for key, phrase in texts.items():
        original = base.get(key)
        if original is None:
            problems.append(f"unknown id: {key}")
            continue
        if sorted(_numbers(original)) != sorted(_numbers(phrase)):
            problems.append(f"{key}: number mismatch")
    return problems
