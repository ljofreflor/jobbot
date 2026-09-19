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


def normalize_many(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        canon = normalize_skill(value)
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out
