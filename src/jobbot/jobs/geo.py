"""Where the candidate wants to work: country detection from job text."""

from __future__ import annotations

import re
from collections.abc import Sequence

DEFAULT_COUNTRIES: tuple[str, ...] = ("CL",)

# Country names / codes accepted in config and CLI.
_COUNTRY_ALIASES: dict[str, str] = {
    "cl": "CL",
    "chile": "CL",
    "ar": "AR",
    "argentina": "AR",
    "pe": "PE",
    "peru": "PE",
    "perú": "PE",
    "mx": "MX",
    "mexico": "MX",
    "méxico": "MX",
    "co": "CO",
    "colombia": "CO",
    "br": "BR",
    "brasil": "BR",
    "brazil": "BR",
    "uy": "UY",
    "uruguay": "UY",
    "es": "ES",
    "espana": "ES",
    "españa": "ES",
    "spain": "ES",
    "us": "US",
    "usa": "US",
    "eeuu": "US",
}

# Markers that tie a posting to one country: cities, currencies, demonyms.
_COUNTRY_MARKERS: dict[str, tuple[str, ...]] = {
    "CL": (
        "chile",
        "chilena",
        "chileno",
        "santiago",
        "providencia",
        "las condes",
        "vitacura",
        "ñuñoa",
        "valparaíso",
        "concepción",
        "antofagasta",
        "clp",
    ),
    "MX": (
        "cdmx",
        "ciudad de méxico",
        "ciudad de mexico",
        "méxico",
        "mexico",
        "mexicana",
        "mexicano",
        "guadalajara",
        "monterrey",
        "querétaro",
        "mxn",
    ),
    "PE": ("perú", "peru", "peruana", "peruano", "lima", "arequipa", "pen "),
    "AR": (
        "argentina",
        "buenos aires",
        "caba",
        "córdoba capital",
        "rosario",
        "mendoza",
    ),
    "CO": ("colombia", "colombiana", "bogotá", "bogota", "medellín", "medellin", "cop "),
    "BR": ("brasil", "brazil", "são paulo", "sao paulo", "rio de janeiro", "brl"),
    "UY": ("uruguay", "montevideo"),
    "ES": ("españa", "espana", "madrid", "barcelona", "valencia, españa"),
    "US": ("united states", "estados unidos", "new york", "san francisco", "usd/yr"),
}

_REMOTE_MARKERS = (
    "remoto",
    "remota",
    "remote",
    "teletrabajo",
    "home office",
    "trabajo desde casa",
    "anywhere",
)

_WORD_RE = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)


def normalize_country(value: str | None) -> str | None:
    """Accept 'cl', 'CL', 'Chile' → 'CL'."""
    if not value:
        return None
    key = str(value).strip().casefold()
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    if len(key) == 2:
        return key.upper()
    return None


def normalize_countries(values: Sequence[str] | None) -> tuple[str, ...]:
    out: list[str] = []
    for value in values or ():
        code = normalize_country(value)
        if code and code not in out:
            out.append(code)
    return tuple(out)


def detect_country(text: str) -> str | None:
    """Best-effort country of a posting; None when the text does not say."""
    lowered = (text or "").casefold()
    best: tuple[int, str] | None = None
    for code, markers in _COUNTRY_MARKERS.items():
        hit = min(
            (lowered.find(marker) for marker in markers if marker in lowered),
            default=-1,
        )
        if hit >= 0 and (best is None or hit < best[0]):
            best = (hit, code)
    return best[1] if best else None


def mentions_remote(text: str) -> bool:
    lowered = (text or "").casefold()
    return any(marker in lowered for marker in _REMOTE_MARKERS)


def country_allows(
    text: str,
    *,
    wanted: Sequence[str] = DEFAULT_COUNTRIES,
    allow_remote: bool = True,
) -> bool:
    """
    True when the posting fits the countries we want to work in.

    Postings whose country cannot be detected are kept: a human decides, JobBot
    does not silently discard work it failed to classify.
    """
    codes = normalize_countries(wanted)
    if not codes:
        return True
    if allow_remote and mentions_remote(text):
        return True
    detected = detect_country(text)
    if detected is None:
        return True
    return detected in codes


def resolve_countries(
    configured: Sequence[str],
    override: Sequence[str] | None = None,
    *,
    any_country: bool = False,
) -> tuple[str, ...]:
    """CLI --country wins over config; --any-country lifts the filter."""
    if any_country:
        return ()
    if override:
        return normalize_countries(override)
    return normalize_countries(configured)
