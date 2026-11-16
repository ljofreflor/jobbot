"""Measure saved searches against title results before anything is stored.

The rules compare stems. They do not name a profession: a word is foreign when
it is absent from this candidate's own experience.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from jobbot.jobs.normalization import fold_text, stem_word
from jobbot.models.candidate import Candidate
from jobbot.profile.search_queries import (
    _CONNECTORS,
    _FUNCTION_WORDS,
    _GENERIC_STEMS,
    _GENERIC_WORDS,
)

TEXT_QUERY_SOURCES = ("getonboard", "indeed", "torre")
_MIN_WORD = 4
_WORD_RE = re.compile(r"[^\W\d_]+")
_NOISE_MIN = 5
_NOISE_RATIO = 0.2
_AMBIGUOUS_RATIO = 0.5
_SPLIT_MIN_STEMS = 3

NOISE_SUGGESTION = "Esta fuente busca en la descripción; filtrar por título"
EMPTY_SUGGESTION = "Sin resultados en ninguna fuente"


@dataclass(frozen=True)
class QueryCell:
    query: str
    source: str
    returned: int
    title_matches: int
    dominant: tuple[str, ...]
    error: str | None = None


@dataclass(frozen=True)
class QueryWarning:
    code: str
    query: str
    suggestion: str
    source: str | None = None


@dataclass(frozen=True)
class QueryCheck:
    cells: tuple[QueryCell, ...]
    warnings: tuple[QueryWarning, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "cells": [
                {
                    "query": cell.query,
                    "source": cell.source,
                    "returned": cell.returned,
                    "title_matches": cell.title_matches,
                    "dominant": list(cell.dominant),
                    "error": cell.error,
                }
                for cell in self.cells
            ],
            "warnings": [
                {
                    "code": warning.code,
                    "query": warning.query,
                    "source": warning.source,
                    "suggestion": warning.suggestion,
                }
                for warning in self.warnings
            ],
        }


TitleSearch = Callable[[str, str], list[str]]


def significant_stems(text: str) -> tuple[str, ...]:
    """Content roots of a query, in order, without connectors or generic work words."""
    stems: list[str] = []
    for word in _words(text):
        if word in _CONNECTORS or word in _FUNCTION_WORDS or word in _GENERIC_WORDS:
            continue
        stem = stem_word(word)
        if stem in _GENERIC_STEMS or stem in stems:
            continue
        stems.append(stem)
    return tuple(stems)


def title_covers(query: str, title: str) -> bool:
    """True when every significant root of the query is a root of the title."""
    needed = significant_stems(query)
    if not needed:
        return False
    have = {stem_word(word) for word in _words(title)}
    return all(stem in have for stem in needed)


def dominant_words(titles: Sequence[str], query: str, *, limit: int = 3) -> tuple[str, ...]:
    """The most common title words that are not the query and not generic."""
    query_stems = set(significant_stems(query))
    counts: Counter[str] = Counter()
    for title in titles:
        seen: set[str] = set()
        for word in _words(title):
            if word in seen or word in _CONNECTORS or word in _FUNCTION_WORDS:
                continue
            if word in _GENERIC_WORDS or stem_word(word) in _GENERIC_STEMS:
                continue
            if stem_word(word) in query_stems:
                continue
            seen.add(word)
            counts[word] += 1
    ranked = sorted(counts, key=lambda word: (-counts[word], word))
    return tuple(ranked[:limit])


def measure_queries(
    candidate: Candidate,
    queries: Sequence[str],
    sources: Sequence[str],
    search: TitleSearch,
) -> QueryCheck:
    """Run ``search(source, query)`` and score titles. Nothing is stored."""
    experience = _experience_stems(candidate)
    cells: list[QueryCell] = []
    warnings: list[QueryWarning] = []
    for query in queries:
        group: list[QueryCell] = []
        for source in sources:
            group.append(_cell(query, source, search))
        cells.extend(group)
        warnings.extend(_warnings(query, group, experience))
    return QueryCheck(cells=tuple(cells), warnings=tuple(warnings))


def format_cell(cell: QueryCell) -> str:
    if cell.error:
        return f"error: {cell.error}"
    dominant = ", ".join(cell.dominant) if cell.dominant else "—"
    return f"{cell.returned} devueltos, {cell.title_matches} en el título, dominantes: {dominant}"


def _cell(query: str, source: str, search: TitleSearch) -> QueryCell:
    try:
        titles = _unique(search(source, query))
    except Exception as exc:  # noqa: BLE001 — one source must not abort the rest
        reason = str(exc).strip() or exc.__class__.__name__
        return QueryCell(query, source, 0, 0, (), error=reason)
    matches = sum(1 for title in titles if title_covers(query, title))
    return QueryCell(
        query,
        source,
        len(titles),
        matches,
        dominant_words(titles, query),
    )


def _warnings(
    query: str,
    cells: Sequence[QueryCell],
    experience: set[str],
) -> list[QueryWarning]:
    measured = [cell for cell in cells if cell.error is None]
    if not measured:
        return []
    found: list[QueryWarning] = []
    if all(cell.returned == 0 for cell in measured):
        found.append(QueryWarning("vacía", query, EMPTY_SUGGESTION))
    elif len(significant_stems(query)) >= _SPLIT_MIN_STEMS and all(
        cell.title_matches == 0 for cell in measured
    ):
        quoted = ", ".join(f'"{stem}"' for stem in significant_stems(query))
        found.append(QueryWarning("sin calce", query, f"Dividir: probar {quoted}"))
    for cell in measured:
        if cell.returned < _NOISE_MIN:
            continue
        ratio = cell.title_matches / cell.returned
        if ratio < _NOISE_RATIO:
            found.append(QueryWarning("ruido", query, NOISE_SUGGESTION, cell.source))
        elif ratio >= _AMBIGUOUS_RATIO and _foreign(cell.dominant, experience):
            names = ", ".join(cell.dominant)
            found.append(
                QueryWarning("ambigua", query, f"Revisar exclusiones: {names}", cell.source)
            )
    return found


def _foreign(words: Sequence[str], experience: set[str]) -> bool:
    return bool(words) and all(stem_word(word) not in experience for word in words)


def _experience_stems(candidate: Candidate) -> set[str]:
    stems: set[str] = set()
    for exp in candidate.experience:
        parts = [exp.title, exp.company, exp.description or "", exp.location or ""]
        parts.extend(item.text for item in exp.achievements)
        for word in _words(" ".join(parts)):
            stems.add(stem_word(word))
    return stems


def _words(text: str) -> list[str]:
    return [word for word in _WORD_RE.findall(fold_text(text)) if len(word) >= _MIN_WORD]


def _unique(titles: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for title in titles:
        key = fold_text(title)
        if key in seen:
            continue
        seen.add(key)
        unique.append(title)
    return unique


def sources_or_reject(requested: Sequence[str] | None) -> tuple[str, ...] | str:
    """The text-search sources to measure, or an error naming the valid ones."""
    if not requested:
        return TEXT_QUERY_SOURCES
    unknown = [name for name in requested if name not in TEXT_QUERY_SOURCES]
    if unknown:
        valid = ", ".join(TEXT_QUERY_SOURCES)
        listed = ", ".join(unknown)
        return f"fuente desconocida o sin búsqueda por texto: {listed}. Fuentes: {valid}"
    return tuple(requested)


def search_source_titles(source: str, query: str, *, config: object) -> list[str]:
    """First-page titles from a text-search adapter. Tests replace this."""
    from jobbot.config import JobbotConfig
    from jobbot.jobs.sources import JobSearchQuery, get_job_source

    if not isinstance(config, JobbotConfig):
        msg = "query check needs a JobbotConfig"
        raise TypeError(msg)
    adapter = get_job_source(source, config)  # type: ignore[arg-type]
    postings = adapter.search_jobs(JobSearchQuery(query=query, limit=20))
    return [posting.title for posting in postings]
