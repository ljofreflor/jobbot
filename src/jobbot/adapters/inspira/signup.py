"""UN Careers / Inspira Talent Pool signup — sheet + recognition (no auto-submit).

``companies signup --apply`` may fill fields the SST already answers via
``signup_fill``. Password (if present), CAPTCHA, OAuth and Subscribe/Create stay
HITL. See #437 / #434.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse, urlunparse

from jobbot.companies.signup import SignupItem
from jobbot.models.candidate import Candidate
from jobbot.portals.field_homologation import answer_for_label
from jobbot.portals.form_learn import FormKnowledge, learn_form_html
from jobbot.portals.profile_state import AccountState

NEEDS_HUMAN = "needs_human"

# Public Inspira REGISTER entry (PeopleSoft). Fixtures use inspira.example.org.
REGISTRATION_URL = (
    "https://inspira.un.org/psc/REGISTER/EMPLOYEE/HRMS/c/"
    "UN_SKILL_REG.UN_SKILL_REG.GBL&languagecd=ENG"
)
CAREERS_HOME = "https://careers.un.org/"

_FIELDS: tuple[str, ...] = (
    "First Name",
    "Last Name",
    "Email Address",
    "LinkedIn",
    "Date of Birth",
    "Gender",
    "Nationality",
    "Highest Education",
    "Work Experience",
    "Languages",
    "Job Network",
    "Password",
    "CAPTCHA",
    "Subscribe",
)

_ALWAYS_HITL: frozenset[str] = frozenset(
    {
        "Date of Birth",
        "Gender",
        "Nationality",
        "Highest Education",
        "Work Experience",
        "Languages",
        "Job Network",
        "Password",
        "CAPTCHA",
        "Subscribe",
    }
)

_CAPTCHA_MARKERS: tuple[str, ...] = (
    "g-recaptcha",
    "h-captcha",
    "data-sitekey",
    "recaptcha",
    "hcaptcha",
)
_CODE_CHALLENGE_MARKERS: tuple[str, ...] = (
    "verification code",
    "one-time password",
    "enter the code",
    "otp",
)
_EVIDENCE_MARKERS: tuple[str, ...] = (
    "candidate home",
    "my applications",
    "my profile",
    "sign out",
    "welcome,",
    "personal history profile",
)


class SignupRecognize(StrEnum):
    """Result of inspecting a saved registration HTML fixture."""

    OK = "ok"
    UI_CHANGED = "ui_changed"
    MANUAL_CHALLENGE = "manual_challenge"


@dataclass(frozen=True)
class InspiraPortal:
    """Fill-catalog identity for UN Careers / Inspira."""

    portal_id: str
    name: str
    signup_url: str
    careers_url: str


UN_CAREERS = InspiraPortal(
    portal_id="un_careers",
    name="UN Careers / Inspira",
    signup_url=REGISTRATION_URL,
    careers_url=CAREERS_HOME,
)


def portal_for_id(portal_id: str) -> InspiraPortal | None:
    if portal_id.strip() == UN_CAREERS.portal_id:
        return UN_CAREERS
    return None


def registration_url(url: str = "") -> str:
    """Map careers.un.org / Inspira URLs to the Talent Pool REGISTER entry."""
    text = (url or "").strip()
    if not text:
        return REGISTRATION_URL
    lowered = text.casefold()
    if "un_skill_reg" in lowered or "/psc/register/" in lowered:
        return text
    host = urlparse(text).netloc.casefold()
    if host.endswith("inspira.un.org") or host.endswith("careers.un.org") or host.endswith(
        "example.org"
    ):
        # Preserve scheme/host for offline fixtures on example.org.
        if host.endswith("example.org"):
            parsed = urlparse(text)
            path = (
                "/psc/REGISTER/EMPLOYEE/HRMS/c/UN_SKILL_REG.UN_SKILL_REG.GBL"
            )
            return urlunparse(
                (parsed.scheme or "https", parsed.netloc, path, "", "languagecd=ENG", "")
            )
        return REGISTRATION_URL
    return REGISTRATION_URL


def _has_captcha(html: str) -> bool:
    lowered = (html or "").casefold()
    return any(marker in lowered for marker in _CAPTCHA_MARKERS)


def _has_code_challenge(html: str) -> bool:
    lowered = (html or "").casefold()
    return any(marker in lowered for marker in _CODE_CHALLENGE_MARKERS)


def recognize_signup_html(
    html: str,
    *,
    url: str = "",
) -> tuple[SignupRecognize, FormKnowledge | None]:
    """Offline recognition of an Inspira / Talent Pool registration form."""
    if _has_captcha(html) or _has_code_challenge(html):
        return SignupRecognize.MANUAL_CHALLENGE, None
    form = learn_form_html(
        html,
        url=url
        or "https://inspira.example.org/psc/REGISTER/EMPLOYEE/HRMS/c/UN_SKILL_REG.UN_SKILL_REG.GBL",
    )
    if not form.readable:
        return SignupRecognize.UI_CHANGED, None
    labels = {field.label.casefold() for field in form.fields}
    emailish = any("email" in label or "correo" in label for label in labels)
    nameish = any(
        token in label
        for label in labels
        for token in ("name", "nombre", "first", "last", "apellido")
    )
    if not (emailish or nameish):
        return SignupRecognize.UI_CHANGED, form
    return SignupRecognize.OK, form


def account_evidence(html: str) -> AccountState:
    """Local evidence from saved HTML only — never invents a session."""
    if _has_captcha(html) or _has_code_challenge(html):
        return AccountState.needs_human
    lowered = (html or "").casefold()
    if any(marker in lowered for marker in _EVIDENCE_MARKERS):
        return AccountState.evidenced
    return AccountState.unknown


def signup_items(candidate: Candidate) -> list[SignupItem]:
    """Sheet rows for Talent Pool. DOB / gender / Subscribe stay empty."""
    items: list[SignupItem] = []
    for label in _FIELDS:
        if label in _ALWAYS_HITL:
            items.append(
                SignupItem(
                    label=label,
                    value="",
                    source=(
                        "HITL — JobBot never fills password, CAPTCHA, "
                        "demographics gaps or Subscribe"
                    ),
                )
            )
            continue
        value, source = answer_for_label(candidate, label)
        items.append(SignupItem(label=label, value=value, source=source))
    return items


def render_inspira_sheet(
    candidate: Candidate,
    aliases: dict[str, str],
    *,
    email_alias: str | None = None,
    portal: InspiraPortal = UN_CAREERS,
) -> str:
    """Markdown the person can copy. Contact email uses the portal alias when set."""
    lines = [
        f"# {portal.name}",
        "",
        f"Portal: `{portal.portal_id}` · adapter: `inspira`",
        "",
        f"Registro: `{portal.signup_url}`",
        "",
        "Hoja de alta (UN Global Talent Pool / Inspira). JobBot rellena solo campos "
        "que el SST ya responde (`companies signup --apply`); DOB, género, "
        "nacionalidad, Job Network, password, CAPTCHA y Subscribe quedan en HITL.",
        "",
    ]
    for item in signup_items(candidate):
        if item.label == "Email Address" and email_alias:
            resolved = aliases.get(email_alias)
            shown = (
                f"{email_alias} → {resolved}"
                if resolved
                else f"[falta alias: {email_alias}]"
            )
            lines.append(f"- {item.label}: {shown}")
            continue
        if item.label in _ALWAYS_HITL:
            lines.append(f"- {item.label}: {NEEDS_HUMAN}")
            continue
        shown = item.value.strip() if item.value else f"[falta en el SST: {item.label}]"
        lines.append(f"- {item.label}: {shown}")
    lines.append("")
    return "\n".join(lines)
