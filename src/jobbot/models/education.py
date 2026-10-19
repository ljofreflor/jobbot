"""Education model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

EducationStatus = Literal["completed", "in_progress", "candidate", "abandoned"]
EDUCATION_STATUSES: tuple[str, ...] = ("completed", "in_progress", "candidate", "abandoned")


class Education(BaseModel):
    id: str = Field(min_length=1)
    institution: str = Field(min_length=1)
    degree: str = Field(min_length=1)
    start_date: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    duration_semesters: int | None = Field(default=None, ge=1)
    details: str | None = None
    status: EducationStatus | None = None
    expected_end: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")

    @field_validator("status", mode="before")
    @classmethod
    def _known_status(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if value not in EDUCATION_STATUSES:
            allowed = ", ".join(EDUCATION_STATUSES)
            raise ValueError(f"status must be one of: {allowed}")
        return value

    @model_validator(mode="after")
    def check_dates(self) -> Education:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            msg = f"{self.id}: end_date is before start_date"
            raise ValueError(msg)
        if self.start_date and self.expected_end and self.expected_end < self.start_date:
            msg = f"{self.id}: expected_end is before start_date"
            raise ValueError(msg)
        if self.resolved_status() == "abandoned" and self.expected_end:
            msg = f"{self.id}: abandoned cannot set expected_end"
            raise ValueError(msg)
        return self

    def resolved_status(self) -> EducationStatus:
        """Explicit status, or completed when an end exists and in progress otherwise."""
        if self.status is not None:
            return self.status
        return "completed" if self.end_date else "in_progress"
