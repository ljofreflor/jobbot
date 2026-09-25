"""Matching package facade."""

from jobbot.matching.analyzer import JobAnalyzer, RuleBasedJobAnalyzer
from jobbot.matching.similarity import (
    AdaptationFit,
    TextEmbedder,
    bag_cosine,
    bert_available,
    build_local_bert_embedder,
    compare_adaptation_fit,
    document_similarity,
    is_spanish_text,
    resolve_bert_model_name,
    text_similarity,
)

__all__ = [
    "AdaptationFit",
    "JobAnalyzer",
    "RuleBasedJobAnalyzer",
    "TextEmbedder",
    "bag_cosine",
    "bert_available",
    "build_local_bert_embedder",
    "compare_adaptation_fit",
    "document_similarity",
    "is_spanish_text",
    "resolve_bert_model_name",
    "text_similarity",
]
