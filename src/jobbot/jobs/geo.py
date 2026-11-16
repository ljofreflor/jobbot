"""Where the candidate wants to work: country detection from job text."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from functools import lru_cache

from babel import Locale

from jobbot.resources import resource_text

DEFAULT_COUNTRIES: tuple[str, ...] = ("CL",)

# Local shorthands CLDR does not carry.
_EXTRA_ALIASES: dict[str, str] = {
    "usa": "US",
    "eeuu": "US",
    "ee uu": "US",
    "uk": "GB",
}


def _fold(text: str) -> str:
    """Case- and accent-insensitive key: 'México' and 'mexico' must match."""
    stripped = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in stripped if not unicodedata.combining(ch)).casefold().strip()


@lru_cache(maxsize=1)
def _country_aliases() -> dict[str, str]:
    """Country names in Spanish and English come from CLDR, not from a literal here."""
    aliases: dict[str, str] = {}
    for locale in ("es", "en"):
        for code, name in Locale(locale).territories.items():
            if len(code) != 2 or not code.isalpha():
                continue  # numeric CLDR regions ('419' = Latin America) are not countries
            aliases.setdefault(_fold(name), code)
            aliases.setdefault(code.casefold(), code)
    aliases.update(_EXTRA_ALIASES)
    return aliases

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
        # Chile's personal-data law — posts cite it without naming the country.
        "ley 21.719",
        "ley 21719",
        "21.719",
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

# Wording that ties a "remote" posting to a place: then it is a local job.
_LOCATION_ANCHORS = (
    "visita",
    "presencial",
    "híbrid",
    "hibrid",
    "onsite",
    "on-site",
    "on site",
    "acudir",
    "asistir a la oficina",
)

_WORD_RE = re.compile(r"[a-záéíóúñü]+", re.IGNORECASE)

# A city is evidence only next to a location frame. "split the team" is not Split, Croatia.
_CITY_FRAME_RE = re.compile(
    r"(?:[,;:]|\b(?:ubicacion|location|sede|oficina|en|in|at|de)\b)\W*$",
    re.IGNORECASE,
)
_POPULATION_LEAD = 8
_MAX_CITY_WORDS = 6


def normalize_country(value: str | None) -> str | None:
    """Accept 'cl', 'CL', 'Chile', 'México', 'Ecuador' → ISO code."""
    if not value:
        return None
    key = _fold(str(value))
    code = _country_aliases().get(key)
    if code:
        return code
    if len(key) == 2 and key.isalpha():
        return key.upper()
    return None


def country_name(code: str | None, *, locale: str = "es") -> str | None:
    """'CL' → 'Chile'; the display name comes from CLDR, not from a literal here."""
    if not code:
        return None
    name = Locale(locale).territories.get(code.upper())
    return str(name) if name else None


def normalize_countries(values: Sequence[str] | None) -> tuple[str, ...]:
    out: list[str] = []
    for value in values or ():
        code = normalize_country(value)
        if code and code not in out:
            out.append(code)
    return tuple(out)


_US_SHORT = re.compile(r"(?<![A-Za-z])U\.?S\.?(?![A-Za-z])|(?<![a-z])ee\.?\s?uu\.?(?![a-z])", re.I)
_MIN_NAME = 4


def countries_in_text(text: str) -> tuple[str, ...]:
    """Every country a clause names, in order of appearance ('Peru and Colombia' → PE, CO).

    Names come from CLDR in Spanish and English; bare two-letter codes are not read
    ('in', 'es' are words), except the usual shorthands for the US and the UK.
    A name inside a longer one ('Sudan' in 'South Sudan') counts once, as the longer.
    """
    clause = (text or "").strip()
    folded = _fold(clause)
    if not folded:
        return ()
    hits: list[tuple[int, int, str]] = []
    for alias, code in _country_aliases().items():
        if len(alias) < _MIN_NAME and alias not in _EXTRA_ALIASES:
            continue
        for match in re.finditer(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", folded):
            hits.append((match.start(), match.end(), code))
    for match in _US_SHORT.finditer(clause):
        if match.group(0).isupper() or "." in match.group(0) or match.group(0)[0] in "eE":
            hits.append((match.start(), match.end(), "US"))
    hits.sort(key=lambda hit: (hit[0], -(hit[1] - hit[0])))
    out: list[str] = []
    covered_until = -1
    for start, end, code in hits:
        if start < covered_until:
            continue
        covered_until = end
        if code not in out:
            out.append(code)
    return tuple(out)


def leading_country(
    rows: Sequence[tuple[str, int]],
    *,
    named: Sequence[str] = (),
) -> str | None:
    """Pick a country from one city name, or None when the guess could drop a job.

    A country the text already names wins. Otherwise a single country, or the
    most populated one when it has at least eight times the next, is enough.
    A closer race stays undetectable.
    """
    totals: dict[str, int] = {}
    for code, population in rows:
        totals[code] = max(totals.get(code, 0), population)
    if not totals:
        return None
    named_hit: list[str] = []
    for code in named:
        if code in totals and code not in named_hit:
            named_hit.append(code)
    if len(named_hit) == 1:
        return named_hit[0]
    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    if len(ordered) == 1:
        return ordered[0][0]
    runner_up = ordered[1][1]
    if runner_up > 0 and ordered[0][1] >= _POPULATION_LEAD * runner_up:
        return ordered[0][0]
    return None


@lru_cache(maxsize=1)
def _city_index() -> dict[str, tuple[tuple[str, int], ...]]:
    """Primary geonames of cities at or above 100k inhabitants, folded.

    The geonamescache package is 33 MB, mostly alternate names, so the wheel
    ships this snapshot instead. Credit: GeoNames (https://www.geonames.org/),
    CC-BY 4.0. Alternate names are omitted on purpose.
    """
    raw = json.loads(resource_text("cities_100k.json"))
    index: dict[str, tuple[tuple[str, int], ...]] = {}
    if not isinstance(raw, dict):
        return index
    for name, rows in raw.items():
        if not isinstance(name, str) or not isinstance(rows, list):
            continue
        parsed: list[tuple[str, int]] = []
        for row in rows:
            if isinstance(row, list) and len(row) == 2 and isinstance(row[0], str):
                parsed.append((row[0], int(row[1])))
        if parsed:
            index[name] = tuple(parsed)
    return index


def _has_location_frame(folded: str, start: int) -> bool:
    window = folded[max(0, start - 24) : start]
    return _CITY_FRAME_RE.search(window) is not None


def _country_from_cities(text: str) -> str | None:
    folded = _fold(text)
    words = list(re.finditer(r"[a-z0-9]+", folded))
    if not words:
        return None
    named = countries_in_text(text)
    index = _city_index()
    cursor = 0
    while cursor < len(words):
        consumed = 1
        for size in range(min(_MAX_CITY_WORDS, len(words) - cursor), 0, -1):
            phrase = " ".join(match.group(0) for match in words[cursor : cursor + size])
            rows = index.get(phrase)
            if rows is None:
                continue
            consumed = size
            if _has_location_frame(folded, words[cursor].start()):
                code = leading_country(rows, named=named)
                if code:
                    return code
            break
        cursor += consumed
    return None


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
    if best:
        return best[1]
    return _country_from_cities(text or "")


def mentions_remote(text: str) -> bool:
    lowered = (text or "").casefold()
    return any(marker in lowered for marker in _REMOTE_MARKERS)


def remote_is_location_free(text: str) -> bool:
    """
    Remote you can take from another country, as opposed to remote-with-visits.

    "Remota, con visitas ocasionales a Monterrey" is a job in Mexico; "100% remoto
    para LATAM" is not.
    """
    if not mentions_remote(text):
        return False
    lowered = (text or "").casefold()
    return not any(anchor in lowered for anchor in _LOCATION_ANCHORS)


def country_allows(
    text: str,
    *,
    wanted: Sequence[str] = DEFAULT_COUNTRIES,
    allow_remote: bool = True,
) -> bool:
    """
    True when the posting fits the countries we want to work in.

    An explicit foreign country wins over remote wording; remote only rescues a
    foreign posting when it is not tied to a place. Postings whose country cannot
    be detected are kept: a human decides, JobBot does not silently discard work
    it failed to classify.
    """
    codes = normalize_countries(wanted)
    if not codes:
        return True
    detected = detect_country(text)
    if detected is None or detected in codes:
        return True
    return allow_remote and remote_is_location_free(text)


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
