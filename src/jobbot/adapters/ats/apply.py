"""Generic ATS open / prefill helpers (HITL; no CAPTCHA bypass)."""

from __future__ import annotations

import logging
import webbrowser
from dataclasses import dataclass, field

from jobbot.adapters.base import ApplyMethod, PrefillResult
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind, detect_ats

logger = logging.getLogger("jobbot.ats")


@dataclass
class AtsApplyPlan:
    job_id: str
    ats_url: str
    ats_kind: AtsKind
    method: ApplyMethod
    fields_to_fill: list[str] = field(default_factory=list)
    needs_review: list[str] = field(default_factory=list)
    message: str = ""


def resolve_ats_url(job: JobPosting) -> tuple[str | None, AtsKind]:
    if job.ats_url:
        if job.ats_url.lower().startswith("mailto:") or job.ats_kind == "email":
            return job.ats_url, AtsKind.EMAIL
        return job.ats_url, detect_ats(job.ats_url)
    if job.url:
        kind = detect_ats(job.url)
        if kind != AtsKind.LINKEDIN:
            return job.url, kind
    return None, AtsKind.UNKNOWN


def build_apply_plan(candidate: Candidate, job: JobPosting) -> AtsApplyPlan:
    url, kind = resolve_ats_url(job)
    fields = _known_fields(candidate)
    review = [
        "salary_expectation",
        "work_authorization",
        "english_level",
        "CAPTCHA / 2FA if shown",
    ]
    if not url:
        return AtsApplyPlan(
            job_id=job.id,
            ats_url="",
            ats_kind=AtsKind.UNKNOWN,
            method=ApplyMethod.UNKNOWN,
            fields_to_fill=fields,
            needs_review=review,
            message="No ATS URL on job; open LinkedIn post manually or set ats_url.",
        )
    if kind == AtsKind.EMAIL or url.lower().startswith("mailto:"):
        return AtsApplyPlan(
            job_id=job.id,
            ats_url=url,
            ats_kind=AtsKind.EMAIL,
            method=ApplyMethod.EMAIL,
            fields_to_fill=fields,
            needs_review=[
                "Attach CV in Gmail UI",
                "Review subject/body then press Send",
                "Gmail login if prompted",
            ],
            message=(
                "HITL email apply: review draft, open Gmail compose, "
                "attach CV, press Send yourself."
            ),
        )
    return AtsApplyPlan(
        job_id=job.id,
        ats_url=url,
        ats_kind=kind,
        method=ApplyMethod.EXTERNAL_ATS,
        fields_to_fill=fields,
        needs_review=review,
        message=f"Open {kind.value} and prefill known Candidate fields only.",
    )


def open_ats_in_browser(url: str) -> None:
    webbrowser.open(url)


# Written into ats_prefill.yaml next to the package. Contact stays in profile.yaml.
SHEET_OMITTED_CONTACT = frozenset({"email", "phone"})


def split_personal_name(name: str) -> tuple[str, str]:
    """Given names and surnames. Four or more tokens: the last two are the surnames.

    Splitting on the first space puts a second given name into the surname
    ("Ada María López Soto" → surname "María López Soto"). Two or three tokens
    stay first-token / the rest: three is ambiguous (one given + two surnames,
    or two given + one surname) and is not guessed.
    """
    parts = name.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    if len(parts) >= 4:
        return " ".join(parts[:-2]), " ".join(parts[-2:])
    return parts[0], " ".join(parts[1:])


def prefill_field_map(candidate: Candidate) -> dict[str, str]:
    """Map common ATS labels → values from Candidate (facts only)."""
    personal = candidate.personal
    out: dict[str, str] = {}
    if personal.name:
        given, surnames = split_personal_name(personal.name)
        out["full_name"] = personal.name
        out["first_name"] = given
        if surnames:
            out["last_name"] = surnames
    if personal.email:
        out["email"] = str(personal.email)
    if personal.phone:
        out["phone"] = personal.phone
    if personal.linkedin:
        out["linkedin"] = personal.linkedin
    if personal.city:
        out["city"] = personal.city
    if personal.country:
        out["country"] = personal.country
    if personal.headline:
        out["headline"] = personal.headline
    loc = personal.location_line()
    if loc:
        out["location"] = loc
    return out


def prefill_sheet_fields(candidate: Candidate) -> dict[str, str]:
    """Fields written to ats_prefill.yaml. Email and phone are not copied."""
    return {
        key: value
        for key, value in prefill_field_map(candidate).items()
        if key not in SHEET_OMITTED_CONTACT
    }


def describe_prefill(candidate: Candidate, job: JobPosting) -> PrefillResult:
    plan = build_apply_plan(candidate, job)
    filled = list(prefill_field_map(candidate).keys())
    return PrefillResult(filled=filled, needs_review=plan.needs_review)


def _known_fields(candidate: Candidate) -> list[str]:
    return sorted(prefill_field_map(candidate).keys())
