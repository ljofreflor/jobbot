"""Languages and certifications the profile already states."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

LEVELS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2", "native")
_YEAR_MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


class Language(BaseModel):
    """A language the candidate speaks, with a CEFR level or native."""

    name: str = Field(min_length=1)
    level: str
    evidence: str | None = None

    @field_validator("level", mode="before")
    @classmethod
    def known_level(cls, value: object) -> object:
        if value in LEVELS:
            return value
        msg = f"level must be one of: {', '.join(LEVELS)}"
        raise ValueError(msg)

    @field_validator("evidence", mode="before")
    @classmethod
    def empty_evidence(cls, value: object) -> object:
        if value == "":
            return None
        return value

    def line(self) -> str:
        return f"{self.name} ({self.level})"


class Certification(BaseModel):
    """A certificate the candidate holds. The id is unique inside the profile."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    issuer: str = Field(min_length=1)
    date: str = Field(pattern=_YEAR_MONTH)
    url: str | None = None
    expires: str | None = Field(default=None, pattern=_YEAR_MONTH)

    @field_validator("url", "expires", mode="before")
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    def line(self) -> str:
        return f"{self.name} — {self.issuer} ({self.date[:4]})"
