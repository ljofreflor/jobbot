"""Quantified bullets already in the profile, surfaced as highlights.

The text is copied from the achievement. A job posting only breaks ties. It
never adds a word that the bullet did not already contain.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting

_DIGIT = re.compile(r"\d")
_WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
_STOP = frozenset(
    {
        "para",
        "como",
        "sobre",
        "entre",
        "desde",
        "hasta",
        "with",
        "from",
        "that",
        "this",
        "into",
        "your",
        "their",
    }
)


@dataclass(frozen=True)
class HighlightPlan:
    """Bullets to print, in rank order, each equal to a source achievement."""

    lines: tuple[str, ...]
    warning: str = ""


def select_highlights(candidate: Candidate, job: JobPosting | None = None) -> HighlightPlan:
    """Quantified achievements, job overlap first, then profile order."""
    job_words = _job_words(job) if job is not None else frozenset()
    ranked: list[tuple[int, int, str]] = []
    for index, text in enumerate(_bullets(candidate)):
        if _DIGIT.search(text) is None:
            continue
        overlap = len(_words(text) & job_words)
        ranked.append((-overlap, index, text))
    ranked.sort()
    lines = tuple(text for _overlap, _index, text in ranked)
    warning = ""
    if not lines:
        warning = "no quantified bullet; highlights omitted"
    return HighlightPlan(lines=lines, warning=warning)


def _bullets(candidate: Candidate) -> list[str]:
    return [ach.text for exp in candidate.experience for ach in exp.achievements]


def _job_words(job: JobPosting) -> frozenset[str]:
    parts = [job.title, job.description, job.raw_description, *job.requirements, *job.skills]
    return _words(" ".join(part for part in parts if part))


def _words(text: str) -> frozenset[str]:
    folded = _fold(text)
    return frozenset(word for word in _WORD.findall(folded) if word not in _STOP)


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in nfkd if not unicodedata.combining(char))
