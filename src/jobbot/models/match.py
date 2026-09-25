"""Job match result models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class MatchStrength(StrEnum):
    STRONG = "strong_match"
    PARTIAL = "partial_match"
    MISSING = "missing"
    UNKNOWN = "unknown"


class MatchItem(BaseModel):
    label: str
    strength: MatchStrength
    detail: str | None = None


class JobMatch(BaseModel):
    job_id: str
    score: float = Field(ge=0, le=100)
    items: list[MatchItem] = Field(default_factory=list)
    # Optional document-level CV↔JD fit (bag or embedding); None = rules-only.
    document_score: float | None = Field(default=None, ge=0, le=100)
    lexical_score: float | None = Field(default=None, ge=0, le=100)
    fit_mode: str = "rules"  # rules | bag | embedding

    def by_strength(self, strength: MatchStrength) -> list[MatchItem]:
        return [i for i in self.items if i.strength == strength]

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "job_id": self.job_id,
            "score": self.score,
            "fit_mode": self.fit_mode,
            "strong_match": [i.label for i in self.by_strength(MatchStrength.STRONG)],
            "partial_match": [i.label for i in self.by_strength(MatchStrength.PARTIAL)],
            "missing": [i.label for i in self.by_strength(MatchStrength.MISSING)],
            "unknown": [i.label for i in self.by_strength(MatchStrength.UNKNOWN)],
            "items": [i.model_dump() for i in self.items],
        }
        if self.document_score is not None:
            data["document_score"] = self.document_score
        if self.lexical_score is not None:
            data["lexical_score"] = self.lexical_score
        return data
