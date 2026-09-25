"""Matching package facade."""

from jobbot.matching.analyzer import JobAnalyzer, RuleBasedJobAnalyzer
from jobbot.matching.similarity import (
    TextEmbedder,
    bag_cosine,
    bert_available,
    build_local_bert_embedder,
    document_similarity,
)

__all__ = [
    "JobAnalyzer",
    "RuleBasedJobAnalyzer",
    "TextEmbedder",
    "bag_cosine",
    "bert_available",
    "build_local_bert_embedder",
    "document_similarity",
]
