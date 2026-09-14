"""Candidate domain model — single source of truth representation."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, HttpUrl, TypeAdapter, field_validator

from jobbot.models.education import Education
from jobbot.models.experience import Experience
from jobbot.models.skill import Publication, SkillGroups

_HTTP_URL = TypeAdapter(HttpUrl)


class PersonalInfo(BaseModel):
    name: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    city: str | None = None
    country: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None

    @field_validator("linkedin", "github", mode="before")
    @classmethod
    def strip_empty(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("linkedin", "github")
    @classmethod
    def validate_url_like(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not (value.startswith("http://") or value.startswith("https://")):
            msg = "URL must start with http:// or https://"
            raise ValueError(msg)
        _HTTP_URL.validate_python(value)
        return value

    def location_line(self) -> str | None:
        parts = [p for p in (self.city, self.country) if p]
        return ", ".join(parts) if parts else None


class Candidate(BaseModel):
    personal: PersonalInfo
    summary: str | None = None
    specialties: list[str] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: SkillGroups = Field(default_factory=SkillGroups)
    publications: list[Publication] = Field(default_factory=list)

    def achievement_count(self) -> int:
        return sum(len(exp.achievements) for exp in self.experience)
