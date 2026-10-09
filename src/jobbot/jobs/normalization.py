"""Skill / keyword normalization."""

from __future__ import annotations

import re
import unicodedata

# Canonical key → accepted aliases (lowercase, normalized).
#
# This table only records equivalences between names of the same thing, so an
# unknown skill is never dropped: normalize_skill falls back to the term itself.
# It must never hold an employer, a city or a person.
_ALIAS_TO_CANONICAL: dict[str, str] = {}

_GROUPS: dict[str, list[str]] = {
    "python": ["python", "py"],
    "sql": ["sql", "t-sql", "tsql"],
    "postgresql": ["postgresql", "postgres", "psql"],
    "r": ["r", "rlang"],
    "machine_learning": [
        "machine learning",
        "machine-learning",
        "ml",
        "aprendizaje automatico",
        "aprendizaje automático",
    ],
    "deep_learning": ["deep learning", "deep-learning", "dl"],
    "xgboost": ["xgboost", "xgb"],
    "pytorch": ["pytorch", "torch"],
    "tensorflow": ["tensorflow", "tf"],
    "scikit_learn": ["scikit-learn", "sklearn", "scikit learn"],
    "causal_inference": [
        "causal inference",
        "inferencia causal",
        "causalidad",
        "uplift",
        "uplift modeling",
    ],
    "experimentation": [
        "experimentation",
        "a/b testing",
        "ab testing",
        "a/b test",
        "experimentacion",
        "experimentación",
    ],
    "gcp": ["gcp", "google cloud", "google cloud platform", "bigquery"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure", "microsoft azure"],
    "mlops": ["mlops", "ml ops"],
    "apis": ["apis", "api", "rest", "rest api"],
    "bayesian": ["bayesian", "bayes", "estadistica bayesiana", "estadística bayesiana"],
    "survival_analysis": ["survival analysis", "analisis de supervivencia"],
    "statistics": ["statistics", "estadistica", "estadística"],
    "predictive_modeling": [
        "predictive modeling",
        "predictive modelling",
        "predictive model",
        "predictive models",
        "modelo predictivo",
        "modelos predictivos",
        "modelamiento predictivo",
        "modelado predictivo",
    ],
    "data_science": ["data science", "ciencia de datos", "ciencias de datos"],
    "customer_analytics": [
        "customer analytics",
        "customer lifetime value",
        "clv",
        "share of wallet",
    ],
    "fintech": ["fintech", "payments"],
    "retail": ["retail", "marketplace", "e-commerce", "ecommerce"],
    "genai": ["genai", "generative ai", "llm", "llms", "langchain"],
    "scala": ["scala"],
    "spark": ["spark", "pyspark", "databricks"],
}


def _build_alias_map() -> None:
    if _ALIAS_TO_CANONICAL:
        return
    for canonical, aliases in _GROUPS.items():
        for alias in aliases:
            _ALIAS_TO_CANONICAL[_normalize_key(alias)] = canonical
        _ALIAS_TO_CANONICAL[_normalize_key(canonical)] = canonical


def _normalize_key(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.strip().lower())
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def fold_text(text: str) -> str:
    """Accent- and case-insensitive text: 'Gestión Ágil' → 'gestion agil'."""
    return _normalize_key(text)


def normalize_skill(text: str) -> str:
    """Map a skill/keyword string to a canonical token when known."""
    _build_alias_map()
    key = _normalize_key(text)
    if not key:
        return ""
    if key in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[key]
    # Whole-token / phrase match only — never substring (sql ⊂ typescript).
    best: tuple[int, str] | None = None
    tokens = set(key.split())
    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        if not alias:
            continue
        alias_parts = alias.split()
        if len(alias_parts) == 1:
            if alias in tokens:
                score = len(alias)
                if best is None or score > best[0]:
                    best = (score, canonical)
        elif alias in key:
            # multi-word phrase as contiguous substring of normalized key
            score = len(alias)
            if best is None or score > best[0]:
                best = (score, canonical)
    if best:
        return best[1]
    return key.replace(" ", "_")


_MIN_PROSE_ALIAS = 4


def skills_in_text(text: str) -> set[str]:
    """Canonical skills a sentence names, e.g. 'modelos predictivos' → predictive_modeling.

    Whole phrases only. Aliases shorter than four letters ('r', 'ml', 'tf') are
    skipped because in prose they collide with ordinary words and initials.
    """
    _build_alias_map()
    folded = f" {_normalize_key(text)} "
    if not folded.strip():
        return set()
    return {
        canonical
        for alias, canonical in _ALIAS_TO_CANONICAL.items()
        if len(alias) >= _MIN_PROSE_ALIAS and f" {alias} " in folded
    }


def stem_word(word: str) -> str:
    """'geofísico' and 'geofísica' are the same claim; so are 'proyecto'/'proyectos'.

    A JD writes the masculine and the profile the feminine (or the reverse), and a
    requirement was reported as missing over a single vowel. Long words only, so
    short names ('sql', 'scrum') are never touched.
    """
    folded = fold_text(word)
    if len(folded) < 6:
        return folded
    for suffix in ("es", "s"):
        if folded.endswith(suffix) and len(folded) - len(suffix) >= 5:
            folded = folded[: -len(suffix)]
            break
    if folded[-1] in "aoe" and len(folded) >= 6:
        folded = folded[:-1]
    return folded


_COGNATE_PREFIX = 7
_COGNATE_SHARE = 0.7

# Spanish and English spell the same word with regular endings: -ción/-tion,
# -dad/-ty, -ía/-y, -ico/-ic. Longest ending first; the root must keep four letters.
_COGNATE_ENDINGS: tuple[tuple[str, str], ...] = (
    ("ciones", "tion"),
    ("tions", "tion"),
    ("cion", "tion"),
    ("tion", "tion"),
    ("siones", "sion"),
    ("sions", "sion"),
    ("dades", "ty"),
    ("ties", "ty"),
    ("dad", "ty"),
    ("icales", "ic"),
    ("icals", "ic"),
    ("ical", "ic"),
    ("icas", "ic"),
    ("icos", "ic"),
    ("ica", "ic"),
    ("ico", "ic"),
    ("ias", "y"),
    ("ies", "y"),
    ("ia", "y"),
    ("orios", "ory"),
    ("orias", "ory"),
    ("ories", "ory"),
    ("orio", "ory"),
    ("oria", "ory"),
    ("istas", "ist"),
    ("ists", "ist"),
    ("ista", "ist"),
    ("ivos", "ive"),
    ("ivas", "ive"),
    ("ives", "ive"),
    ("ivo", "ive"),
    ("iva", "ive"),
)
_COGNATE_ROOT = 4

# Words that name the same thing in Spanish and English but share no root, so no
# ending rule can pair them. Equivalence only: a word missing here falls through
# to its own spelling, and nothing is ever gated on this list.
_CROSS_LANGUAGE: tuple[tuple[str, ...], ...] = (
    ("vigilancia", "surveillance", "monitoring", "monitoreo"),
    ("brote", "brotes", "outbreak", "outbreaks"),
    ("enfermedad", "enfermedades", "disease", "diseases"),
    ("salud", "health"),
    ("red", "redes", "network", "networks"),
    ("sistema", "sistemas", "system", "systems"),
    ("datos", "data"),
    ("medicina", "medicine", "medico", "medica", "medical"),
    ("vacuna", "vacunas", "vaccine", "vaccines"),
    ("inmunizacion", "inmunizaciones", "immunization", "immunisation"),
    ("sarampion", "measles"),
    ("gestion", "management"),
    ("capacitacion", "training"),
    ("docente", "docentes", "teacher", "lecturer", "professor"),
    ("docencia", "teaching"),
    ("informe", "informes", "report", "reports"),
    ("encuesta", "encuestas", "survey", "surveys"),
    ("investigacion", "research"),
    ("ventas", "sales"),
    ("cliente", "clientes", "customer", "customers", "client", "clients"),
    ("cuenta", "cuentas", "account", "accounts"),
    ("calidad", "quality"),
    ("seguridad", "safety"),
    ("presupuesto", "budget"),
    ("compras", "procurement", "purchasing"),
    ("habilidades", "skills"),
    ("conocimiento", "conocimientos", "knowledge"),
    ("enfermera", "enfermero", "nurse"),
    ("cuidado", "cuidados", "care"),
    ("abogada", "abogado", "lawyer", "attorney"),
    ("derecho", "law"),
    ("ingenieria", "engineering"),
    ("ingeniera", "ingeniero", "engineer"),
)


def cognate_key(word: str) -> str:
    """'epidemiología' and 'epidemiology' share the key 'epidemiology'."""
    folded = fold_text(word)
    for ending, common in _COGNATE_ENDINGS:
        if folded.endswith(ending) and len(folded) - len(ending) >= _COGNATE_ROOT:
            return folded[: -len(ending)] + common
    return folded


def _build_concepts() -> dict[str, int]:
    concepts: dict[str, int] = {}
    for number, group in enumerate(_CROSS_LANGUAGE):
        for word in group:
            folded = fold_text(word)
            concepts[folded] = number
            concepts[stem_word(folded)] = number
    return concepts


_CONCEPTS = _build_concepts()


def concept_of(word: str) -> int | None:
    """The cross-language group a word belongs to ('surveillance' ↔ 'vigilancia'), if any."""
    folded = fold_text(word)
    found = _CONCEPTS.get(folded)
    return found if found is not None else _CONCEPTS.get(stem_word(folded))


class WordIndex:
    """The words of a text, looked up tolerant of gender, plural and cognates.

    'epidemiology' and 'epidemiología', 'zoonotic' and 'zoonóticas', 'consultant'
    and 'consultora' name the same thing across languages and genders. The evidence
    is a shared root (seven letters or more, covering most of the shorter word), a
    regular Spanish/English ending (`cognate_key`) or the small cross-language table
    for words with no shared root ('surveillance' ↔ 'vigilancia'). A short word only
    matches itself or its stem, so 'sql' never reads as 'sqlite'.
    """

    def __init__(self, words: set[str] | frozenset[str]) -> None:
        self.words = frozenset(words)
        self._stems = frozenset(stem_word(word) for word in self.words)
        self._cognates = frozenset(
            cognate_key(word) for word in self.words if len(word) > _COGNATE_ROOT
        )
        self._concepts = frozenset(
            concept for word in self.words if (concept := concept_of(word)) is not None
        )
        self._by_prefix: dict[str, list[str]] = {}
        for word in self.words:
            if len(word) >= _COGNATE_PREFIX:
                self._by_prefix.setdefault(word[:_COGNATE_PREFIX], []).append(word)

    def has(self, word: str) -> bool:
        if word in self.words or stem_word(word) in self._stems:
            return True
        concept = concept_of(word)
        if concept is not None and concept in self._concepts:
            return True
        if len(word) > _COGNATE_ROOT and cognate_key(word) in self._cognates:
            return True
        if len(word) < _COGNATE_PREFIX:
            return False
        return any(
            _shared_prefix(word, other) >= _COGNATE_SHARE * min(len(word), len(other))
            for other in self._by_prefix.get(word[:_COGNATE_PREFIX], ())
        )


def _shared_prefix(left: str, right: str) -> int:
    count = 0
    for a, b in zip(left, right, strict=False):
        if a != b:
            break
        count += 1
    return count


def normalize_many(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        canon = normalize_skill(value)
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out
