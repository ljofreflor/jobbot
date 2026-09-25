"""Matching package facade."""

from jobbot.matching.analyzer import JobAnalyzer, RuleBasedJobAnalyzer
from jobbot.matching.similarity import (
    TextEmbedder,
    bag_cosine,
    build_openai_embedder,
    document_similarity,
    embeddings_available,
)

__all__ = [
    "JobAnalyzer",
    "RuleBasedJobAnalyzer",
    "TextEmbedder",
    "bag_cosine",
    "build_openai_embedder",
    "document_similarity",
    "embeddings_available",
]
