"""Each posting condition against the candidate: meets, ask the candidate, or dealbreaker.

Facts come from profile.yaml. What the profile does not hold — language level, where
the candidate may work, whether a contractor contract is acceptable, notice period,
salary expectation — comes from ``data/application_answers.yaml``: a preference the
candidate edits, not a professional fact. A blank answer becomes the exact question
to ask, never a guess. A mandatory requirement the profile does not back is a
question too, not a dealbreaker: the profile may simply not mention it, and only the
candidate can say whether it is true.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from babel import Locale
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from jobbot.jobs.conditions import (
    Condition,
    ConditionKind,
    cefr_rank,
    language_code,
    language_mentions,
    level_from_text,
)
from jobbot.jobs.geo import normalize_countries, normalize_country
from jobbot.matching.analyzer import requirement_evidence
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.models.match import MatchStrength

ANSWERS_FILE = "data/application_answers.yaml"


class VerdictStatus(StrEnum):
    MEETS = "meets"
    ASK = "ask"
    DEALBREAKER = "dealbreaker"
    NOTE = "note"


MARKS: dict[VerdictStatus, str] = {
    VerdictStatus.DEALBREAKER: "❌",
    VerdictStatus.ASK: "⚠️",
    VerdictStatus.MEETS: "✅",
    VerdictStatus.NOTE: "ℹ️",
}
_SEVERITY = {status: index for index, status in enumerate(MARKS)}


@dataclass(frozen=True)
class Verdict:
    condition: Condition
    status: VerdictStatus
    reason: str
    question: str | None = None

    def to_dict(self) -> dict[str, object]:
        data = self.condition.to_dict()
        data["status"] = self.status.value
        data["reason"] = self.reason
        if self.question:
            data["question"] = self.question
        return data


_YES = frozenset({"true", "yes", "si", "sí", "y", "1"})
_NO = frozenset({"false", "no", "n", "0"})


def _to_bool(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if not text:
        return None
    if text in _YES:
        return True
    if text in _NO:
        return False
    return value


def _modality_preference(value: str) -> str:
    folded = value.casefold()
    if "hibrid" in folded or "hybrid" in folded:
        return "hybrid"
    if re.search(r"presencial|on ?-?site|office|oficina", folded):
        return "onsite"
    if "remot" in folded:
        return "remote"
    return value.strip()


_CURRENCIES = frozenset({"CLP", "USD", "EUR", "GBP", "ARS", "BRL", "MXN", "COP", "PEN", "UYU"})
_JOB_TYPES = frozenset({"full_time", "contract", "consultancy"})
_GENDERS = frozenset({"female", "male", "non_binary", "prefer_not_to_say"})
_RELOCATION_SCOPES = frozenset({"within_country", "international"})
REFUSED_ANSWER_KEYS = frozenset({"rut", "run", "national_id"})
_KNOWN_BLOCKS = (
    "identity",
    "salary",
    "availability",
    "relocation",
    "job_types",
    "desired_titles",
    "residence_country",
    "work_authorization",
    "languages",
    "accepts_contractor",
    "remote_preference",
    "notice_period",
    "salary_expectation",
)


def _blank(value: object) -> object:
    if value == "":
        return None
    return value


def _country_list(value: object) -> object:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = re.split(r"[,;/]", value)
    if isinstance(value, list):
        return list(normalize_countries([str(item) for item in value if str(item).strip()]))
    return value


class IdentityAnswers(BaseModel):
    """Declared identity a form may ask. A national id is not a field here."""

    model_config = ConfigDict(extra="forbid")

    birth_date: date | None = None
    nationality: list[str] = Field(default_factory=list)
    gender_to_declare: Literal["female", "male", "non_binary", "prefer_not_to_say"] | None = None
    comuna: str | None = None
    region: str | None = None

    @field_validator("birth_date", "comuna", "region", "gender_to_declare", mode="before")
    @classmethod
    def _empty(cls, value: object) -> object:
        return _blank(value)

    @field_validator("nationality", mode="before")
    @classmethod
    def _codes(cls, value: object) -> object:
        return _country_list(value)

    @field_validator("gender_to_declare", mode="before")
    @classmethod
    def _gender(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        text = value.strip().casefold().replace("-", "_").replace(" ", "_")
        if not text:
            return None
        if text not in _GENDERS:
            msg = f"gender_to_declare: {value}"
            raise ValueError(msg)
        return text


class SalaryAnswers(BaseModel):
    """Pay the candidate states. Net and gross are never converted."""

    model_config = ConfigDict(extra="forbid")

    amount: int | None = None
    currency: str | None = None
    period: Literal["month", "year", "hour", "day"] | None = None
    basis: Literal["net", "gross"] | None = None

    @field_validator("amount", "currency", "period", "basis", mode="before")
    @classmethod
    def _empty(cls, value: object) -> object:
        return _blank(value)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = value.strip().upper()
        if code not in _CURRENCIES:
            msg = f"currency: {value}"
            raise ValueError(msg)
        return code

    @field_validator("period", "basis", mode="before")
    @classmethod
    def _token(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip().casefold() or None


class AvailabilityAnswers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_date: date | None = None

    @field_validator("from_date", mode="before")
    @classmethod
    def _empty(cls, value: object) -> object:
        return _blank(value)


class ApplicationAnswers(BaseModel):
    """Answers the profile does not hold. Blank means unknown, and unknown is asked."""

    model_config = ConfigDict(extra="forbid")

    residence_country: str | None = None
    work_authorization: list[str] = Field(default_factory=list)
    languages: dict[str, str] = Field(default_factory=dict)
    accepts_contractor: bool | None = None
    relocation: bool | Literal["within_country", "international"] | None = None
    remote_preference: str | None = None
    notice_period: str | None = None
    salary_expectation: str | None = None
    identity: IdentityAnswers = Field(default_factory=IdentityAnswers)
    salary: SalaryAnswers | None = None
    availability: AvailabilityAnswers | None = None
    job_types: list[str] = Field(default_factory=list)
    desired_titles: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("work_authorization", mode="before")
    @classmethod
    def _countries(cls, value: object) -> object:
        return _country_list(value)

    @field_validator("identity", mode="before")
    @classmethod
    def _identity_block(cls, value: object) -> object:
        if value in (None, ""):
            return {}
        return value

    @field_validator("salary", "availability", mode="before")
    @classmethod
    def _optional_block(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("job_types", "desired_titles", mode="before")
    @classmethod
    def _lists(cls, value: object) -> object:
        if value in (None, ""):
            return []
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("job_types")
    @classmethod
    def _known_job_types(cls, value: list[str]) -> list[str]:
        unknown = [item for item in value if item not in _JOB_TYPES]
        if unknown:
            msg = f"job_types: {unknown[0]}"
            raise ValueError(msg)
        return value

    @field_validator("languages", mode="before")
    @classmethod
    def _levels(cls, value: object) -> object:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {
                str(key): str(level)
                for key, level in value.items()
                if level is not None and str(level).strip()
            }
        return value

    @field_validator("accepts_contractor", mode="before")
    @classmethod
    def _yes_no(cls, value: object) -> object:
        return _to_bool(value)

    @field_validator("relocation", mode="before")
    @classmethod
    def _relocation(cls, value: object) -> object:
        if value is None or isinstance(value, bool):
            return value
        text = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
        if text in _RELOCATION_SCOPES:
            return text
        if text == "":
            return None
        return _to_bool(value)

    @field_validator(
        "residence_country", "remote_preference", "notice_period", "salary_expectation",
        mode="before",
    )  # fmt: skip
    @classmethod
    def _text(cls, value: object) -> object:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("remote_preference")
    @classmethod
    def _preference(cls, value: str | None) -> str | None:
        return _modality_preference(value) if value else None

    def language_level(self, code: str) -> str | None:
        """CEFR level stated for a language ('english: B1', 'inglés: conversacional')."""
        for key, value in self.languages.items():
            if language_code(key) == code:
                return level_from_text(value)
        return None

    def residence(self) -> str | None:
        return normalize_country(self.residence_country)


def default_answers_path(root: Path) -> Path:
    """Local, gitignored: the candidate's answers to what profile.yaml does not hold."""
    return root / "data" / "application_answers.yaml"


def job_answers_path(output_dir: Path, job_id: str) -> Path:
    """Per-posting answers written by `application prepare`; they win for that posting."""
    return output_dir / "jobs" / job_id / "application" / "answers.yaml"


_JOB_KEYS = (
    "salary_expectation",
    "notice_period",
    "work_authorization",
    "relocation",
    "remote_preference",
    "job_types",
    "desired_titles",
)
_JOB_BLOCKS = ("identity", "salary", "availability")


def _answered(value: object) -> bool:
    """A posting's own file only overrides where it actually holds an answer."""
    return value not in (None, "", [], {})


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"{path}: not valid YAML ({exc})"
        raise ValueError(msg) from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = f"{path}: expected a mapping of answers"
        raise ValueError(msg)
    return raw


def load_application_answers(path: Path, *, job_answers: Path | None = None) -> ApplicationAnswers:
    """Read the answers file; a posting's own answers.yaml overrides what it fills in."""
    data = _read_yaml(path)
    if job_answers is not None:
        job = _read_yaml(job_answers)
        for key in _JOB_KEYS:
            value = job.get(key)
            if _answered(value):
                data[key] = value
        for block in _JOB_BLOCKS:
            own = job.get(block)
            if not isinstance(own, dict):
                if _answered(own):
                    data[block] = own
                continue
            answered = {key: value for key, value in own.items() if _answered(value)}
            if answered:
                base = data.get(block)
                data[block] = {**base, **answered} if isinstance(base, dict) else answered
        english = job.get("english_level")
        if english not in (None, ""):
            languages = {
                key: level
                for key, level in (data.get("languages") or {}).items()
                if language_code(str(key)) != "en"
            }
            languages["english"] = str(english)
            data["languages"] = languages
    try:
        return ApplicationAnswers.model_validate(data)
    except ValidationError as exc:
        msg = f"{path}: {exc}"
        raise ValueError(msg) from exc


def read_answers_mapping(path: Path) -> dict[str, Any]:
    """Raw answers mapping. Missing file is an empty mapping."""
    return _read_yaml(path)


def answer_key_refused(key: str) -> bool:
    """A national identifier is typed on the portal. It is never stored."""
    return any(part.casefold() in REFUSED_ANSWER_KEYS for part in key.split("."))


def filled_blocks(answers: ApplicationAnswers) -> list[str]:
    """Block names that hold something. Values stay out of this list."""
    filled: list[str] = []
    identity = answers.identity
    if any(
        (
            identity.birth_date,
            identity.nationality,
            identity.gender_to_declare,
            identity.comuna,
            identity.region,
        )
    ):
        filled.append("identity")
    salary = answers.salary
    if salary is not None and any((salary.amount, salary.currency, salary.period, salary.basis)):
        filled.append("salary")
    if answers.availability is not None and answers.availability.from_date is not None:
        filled.append("availability")
    if answers.relocation is not None:
        filled.append("relocation")
    if answers.job_types:
        filled.append("job_types")
    if answers.desired_titles:
        filled.append("desired_titles")
    for name in (
        "residence_country",
        "work_authorization",
        "languages",
        "accepts_contractor",
        "remote_preference",
        "notice_period",
        "salary_expectation",
    ):
        value = getattr(answers, name)
        if value not in (None, "", [], {}):
            filled.append(name)
    return filled


def format_answers_show(answers: ApplicationAnswers) -> str:
    """Which blocks are filled. Never the values."""
    filled = filled_blocks(answers)
    empty = [name for name in _KNOWN_BLOCKS if name not in filled]
    filled_line = ", ".join(filled) if filled else "ninguno"
    empty_line = ", ".join(empty) if empty else "ninguno"
    return f"con datos: {filled_line}\nvacíos: {empty_line}"


def salary_migration_hint(answers: ApplicationAnswers) -> str | None:
    """Suggest a structured salary when the legacy sentence is unambiguous. Writes nothing."""
    salary = answers.salary
    if salary is not None and any((salary.amount, salary.currency, salary.period, salary.basis)):
        return None
    parsed = _parse_legacy_salary(answers.salary_expectation or "")
    if parsed is None:
        return None
    return (
        "sugerencia: migrar salary_expectation a "
        f"salary.amount: {parsed.amount}, salary.currency: {parsed.currency}, "
        f"salary.period: {parsed.period}, salary.basis: {parsed.basis} "
        "(no se escribió)"
    )


def assign_answer(data: dict[str, Any], key: str, raw: str) -> None:
    """Put one dotted key into the raw mapping. The caller validates before writing."""
    parts = [part for part in key.split(".") if part]
    if len(parts) != len(key.split(".")):
        msg = f"clave desconocida: {key}"
        raise ValueError(msg)
    cursor = data
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            child = {}
            cursor[part] = child
        cursor = child
    cursor[parts[-1]] = _coerce_leaf(parts[-1], raw)


def _coerce_leaf(leaf: str, raw: str) -> object:
    if leaf == "amount":
        return int(raw)
    if leaf in {"nationality", "job_types", "desired_titles", "work_authorization"}:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return raw


def _parse_legacy_salary(text: str) -> SalaryAnswers | None:
    if not text.strip():
        return None
    folded = text.casefold()
    if re.search(r"liquid|l[ií]quid|\bnet\b", folded):
        basis: Literal["net", "gross"] = "net"
    elif re.search(r"brut|bruta|bruto|\bgross\b", folded):
        basis = "gross"
    else:
        return None
    if re.search(r"mensual|al mes|\bmonth", folded):
        period: Literal["month", "year", "hour", "day"] = "month"
    elif re.search(r"anual|al a[nñ]o|\byear", folded):
        period = "year"
    elif re.search(r"hora|\bhour", folded):
        period = "hour"
    elif re.search(r"\bd[ií]a\b|\bday\b", folded):
        period = "day"
    else:
        return None
    currency = next((code for code in _CURRENCIES if code.casefold() in folded), None)
    match = re.search(r"\d{1,3}(?:\.\d{3})+|\d+", text)
    if match is None:
        return None
    token = match.group(0)
    if "." in token:
        amount = int(token.replace(".", ""))
        currency = currency or "CLP"
    else:
        amount = int(token)
    if currency is None:
        return None
    return SalaryAnswers(amount=amount, currency=currency, period=period, basis=basis)


def _language_name(code: str) -> str:
    return str(Locale("en").languages.get(code, code))


def _candidate_language(
    candidate: Candidate, answers: ApplicationAnswers, code: str
) -> tuple[str | None, str]:
    """Level stated in profile.yaml (skills, specialties), else in the answers file."""
    for claim in (*candidate.skills.all_skills(), *candidate.specialties):
        for mentioned, level in language_mentions(claim):
            if mentioned == code and level is not None:
                return level, f"profile.yaml: '{claim}'"
    return answers.language_level(code), ANSWERS_FILE


def _residence(candidate: Candidate, answers: ApplicationAnswers) -> tuple[str | None, str]:
    own = answers.residence()
    if own is not None:
        return own, f"{ANSWERS_FILE} residence_country: {answers.residence_country}"
    country = candidate.personal.country
    own = normalize_country(country)
    return own, f"profile.yaml personal.country: {country}"


def _names(codes: tuple[str, ...] | list[str]) -> str:
    return ", ".join(codes)


def _closed(c: Condition) -> Verdict:
    return Verdict(c, VerdictStatus.DEALBREAKER, "the posting no longer accepts applications")


def _deadline(c: Condition, today: date) -> Verdict:
    if c.when is not None and c.when < today:
        return Verdict(c, VerdictStatus.DEALBREAKER, f"the deadline {c.when} has passed")
    return Verdict(c, VerdictStatus.NOTE, f"apply before {c.when}")


def _residency(c: Condition, candidate: Candidate, answers: ApplicationAnswers) -> Verdict:
    if c.anywhere:
        return Verdict(c, VerdictStatus.MEETS, "the posting accepts residence anywhere")
    if not c.countries:
        return Verdict(
            c,
            VerdictStatus.ASK,
            f"the posting limits residence to '{c.detail}'",
            f"Do you reside in {c.detail}? The posting requires it.",
        )
    own, origin = _residence(candidate, answers)
    wanted = _names(c.countries)
    if own is None:
        return Verdict(
            c,
            VerdictStatus.ASK,
            f"the posting requires residence in {wanted}",
            f"Which country do you reside in? The posting requires {wanted}. Set "
            f"personal.country in profile.yaml or residence_country in {ANSWERS_FILE}.",
        )
    if own in c.countries:
        return Verdict(
            c, VerdictStatus.MEETS, f"you reside in {own} ({origin}); it accepts {wanted}"
        )
    return Verdict(
        c,
        VerdictStatus.DEALBREAKER,
        f"the posting requires residence in {wanted}; you reside in {own} ({origin})",
    )


def _work_authorization(c: Condition, answers: ApplicationAnswers) -> Verdict:
    allowed = answers.work_authorization
    if not c.countries:
        return Verdict(
            c,
            VerdictStatus.ASK,
            "the posting sets a work-authorization condition",
            f"The posting asks: “{c.source}”. Does your work authorization meet it? "
            f"List the countries where you may work in work_authorization in {ANSWERS_FILE}.",
        )
    wanted = _names(c.countries)
    if not allowed:
        return Verdict(
            c,
            VerdictStatus.ASK,
            f"the posting requires work authorization in {wanted}",
            f"Are you authorized to work in {wanted}? Set work_authorization in {ANSWERS_FILE}.",
        )
    if any(code in allowed for code in c.countries):
        return Verdict(
            c, VerdictStatus.MEETS, f"you may work in {_names(allowed)} ({ANSWERS_FILE})"
        )
    return Verdict(
        c,
        VerdictStatus.DEALBREAKER,
        f"the posting requires work authorization in {wanted}; you listed "
        f"{_names(allowed)} ({ANSWERS_FILE})",
    )


def _language(c: Condition, candidate: Candidate, answers: ApplicationAnswers) -> Verdict:
    code = c.language or ""
    name = _language_name(code)
    own, origin = _candidate_language(candidate, answers, code)
    asked = f" The posting asks for {c.level}." if c.level else ""
    if own is None:
        return Verdict(
            c,
            VerdictStatus.ASK,
            f"{name} {c.level or 'required'}; your level is not recorded",
            f"What is your {name} level (CEFR A1–C2)?{asked} Set "
            f"languages.{name.casefold()} in {ANSWERS_FILE}.",
        )
    needed, have = cefr_rank(c.level), cefr_rank(own)
    if needed is None or (have is not None and have >= needed):
        return Verdict(
            c, VerdictStatus.MEETS, f"you have {name} {own} ({origin}); it asks {c.level or name}"
        )
    if c.mandatory is False:
        return Verdict(
            c, VerdictStatus.NOTE, f"desirable {name} {c.level}; you have {own} ({origin})"
        )
    return Verdict(
        c,
        VerdictStatus.DEALBREAKER,
        f"the posting requires {name} {c.level} or higher; you have {own} ({origin})",
    )


def _requirement(c: Condition, candidate: Candidate) -> Verdict:
    detail = c.detail or c.source
    evidence = requirement_evidence(candidate, detail)
    if c.mandatory is False:
        backed = f" — {evidence[1]}" if evidence else ""
        return Verdict(c, VerdictStatus.NOTE, f"desirable: {detail}{backed}")
    if evidence is not None and evidence[0] is MatchStrength.STRONG:
        return Verdict(c, VerdictStatus.MEETS, f"{evidence[1]} (profile.yaml)")
    partial = f" (closest: {evidence[1]})" if evidence else ""
    return Verdict(
        c,
        VerdictStatus.ASK,
        f"mandatory, not found in profile.yaml{partial}",
        f"The posting requires “{detail}” (mandatory). Does your experience cover it? "
        "If it does, add it to profile.yaml; never claim what you have not done.",
    )


def _contract(c: Condition, answers: ApplicationAnswers) -> Verdict:
    if c.contract != "contractor":
        return Verdict(c, VerdictStatus.NOTE, f"contract: {(c.contract or '').replace('_', ' ')}")
    if answers.accepts_contractor is True:
        return Verdict(c, VerdictStatus.MEETS, f"you accept contractor work ({ANSWERS_FILE})")
    if answers.accepts_contractor is False:
        return Verdict(
            c,
            VerdictStatus.DEALBREAKER,
            f"contractor contract; you do not accept contractor work ({ANSWERS_FILE})",
        )
    return Verdict(
        c,
        VerdictStatus.ASK,
        "contractor / service contract, not an employment contract",
        "This role is a contractor (service) contract, not an employment contract. "
        f"Do you accept that? Set accepts_contractor in {ANSWERS_FILE}.",
    )


def _salary(c: Condition, answers: ApplicationAnswers) -> Verdict:
    expectation = answers.salary_expectation
    yours = f"; your expectation: {expectation} ({ANSWERS_FILE})" if expectation else ""
    if c.shown:
        return Verdict(c, VerdictStatus.NOTE, f"published: {c.detail}{yours}")
    if expectation:
        return Verdict(c, VerdictStatus.NOTE, f"pay not published{yours}")
    asks = " and asks for your expectation" if c.shown is None else ""
    return Verdict(
        c,
        VerdictStatus.ASK,
        f"pay not published{asks}",
        "What is your salary expectation (currency, gross or net, period)? "
        f"Set salary_expectation in {ANSWERS_FILE}.",
    )


def _modality(c: Condition, candidate: Candidate, answers: ApplicationAnswers) -> Verdict:
    modality = c.modality or ""
    own, _ = _residence(candidate, answers)
    if modality != "remote" and c.countries and own is not None and own not in c.countries:
        place = c.detail or _names(c.countries)
        if answers.relocation is True:
            return Verdict(
                c, VerdictStatus.MEETS, f"{modality} in {place}; you accept relocating"
            )
        if answers.relocation is False:
            return Verdict(
                c,
                VerdictStatus.DEALBREAKER,
                f"{modality} in {place}; you reside in {own} and do not relocate "
                f"({ANSWERS_FILE})",
            )
        return Verdict(
            c,
            VerdictStatus.ASK,
            f"{modality} in {place}; you reside in {own}",
            f"This role is {modality} in {place} and you reside in {own}. Would you "
            f"relocate? Set relocation in {ANSWERS_FILE}.",
        )
    preference = answers.remote_preference
    if preference in {"remote", "hybrid", "onsite"} and preference != modality:
        return Verdict(
            c,
            VerdictStatus.ASK,
            f"{modality}; your preference is {preference}",
            f"This role is {modality} and you prefer {preference}. Apply anyway?",
        )
    where = f" ({c.detail})" if c.detail else ""
    return Verdict(c, VerdictStatus.NOTE, f"modality: {modality}{where}")


def _availability(c: Condition, answers: ApplicationAnswers) -> Verdict:
    if answers.notice_period:
        return Verdict(
            c, VerdictStatus.NOTE, f"your notice period: {answers.notice_period} ({ANSWERS_FILE})"
        )
    return Verdict(
        c,
        VerdictStatus.ASK,
        "the posting asks about your availability",
        f"When can you start? Set notice_period in {ANSWERS_FILE}.",
    )


def _instruction(c: Condition) -> Verdict:
    language = f" (write it in {_language_name(c.language)})" if c.language else ""
    return Verdict(c, VerdictStatus.NOTE, f"follow the posting's instruction{language}")


def _assess(
    c: Condition, candidate: Candidate, answers: ApplicationAnswers, today: date
) -> Verdict:
    kind = c.kind
    if kind is ConditionKind.CLOSED:
        return _closed(c)
    if kind is ConditionKind.DEADLINE:
        return _deadline(c, today)
    if kind is ConditionKind.RESIDENCY:
        return _residency(c, candidate, answers)
    if kind is ConditionKind.WORK_AUTHORIZATION:
        return _work_authorization(c, answers)
    if kind is ConditionKind.LANGUAGE:
        return _language(c, candidate, answers)
    if kind is ConditionKind.REQUIREMENT:
        return _requirement(c, candidate)
    if kind is ConditionKind.CONTRACT:
        return _contract(c, answers)
    if kind is ConditionKind.SALARY:
        return _salary(c, answers)
    if kind is ConditionKind.MODALITY:
        return _modality(c, candidate, answers)
    if kind is ConditionKind.AVAILABILITY:
        return _availability(c, answers)
    if kind is ConditionKind.SENIORITY:
        return Verdict(c, VerdictStatus.NOTE, f"seniority: {c.detail} (see jobs match)")
    return _instruction(c)


def assess_conditions(
    conditions: list[Condition],
    candidate: Candidate,
    answers: ApplicationAnswers,
    *,
    today: date | None = None,
) -> list[Verdict]:
    """One verdict per condition. Never guesses an answer the candidate has not given."""
    day = today or date.today()
    return [_assess(c, candidate, answers, day) for c in conditions]


def has_dealbreaker(verdicts: list[Verdict]) -> bool:
    return any(v.status is VerdictStatus.DEALBREAKER for v in verdicts)


def format_conditions_report(job: JobPosting, verdicts: list[Verdict]) -> str:
    """Plain text, worst first: dealbreakers, questions, what is met, notes."""
    lines = [f"{job.id}  {job.title} — {job.company}"]
    if not verdicts:
        lines.append("  no special conditions found in the stored posting")
    for verdict in sorted(verdicts, key=lambda v: _SEVERITY[v.status]):
        mark = MARKS[verdict.status]
        lines.append(
            f"  {mark} {verdict.status.value:<11} {verdict.condition.kind.value:<18} "
            f"“{verdict.condition.source}”"
        )
        lines.append(f"      → {verdict.reason}")
        if verdict.question:
            lines.append(f"      ? {verdict.question}")
    blockers = [v.condition.kind.value for v in verdicts if v.status is VerdictStatus.DEALBREAKER]
    if blockers:
        lines.append(f"  DEALBREAKER — {job.id}: {', '.join(dict.fromkeys(blockers))}")
    return "\n".join(lines)
