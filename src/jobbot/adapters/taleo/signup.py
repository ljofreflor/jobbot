"""Taleo careersection account signup — sheet + recognition (no browser driver).

Each portal in the coverage epic (#434) gets its own PR. This module holds the
shared careersection mechanics; ``OMS_WHO`` is the first wired portal (#438).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse, urlunparse

from jobbot.companies.signup import SignupItem
from jobbot.models.candidate import Candidate
from jobbot.portals.field_homologation import answer_for_label
from jobbot.portals.form_learn import FormKnowledge, learn_form_html
from jobbot.portals.profile_state import AccountState

NEEDS_HUMAN = "needs_human"

# Public careersection path segments we rewrite to the access-control entry.
_JOBSEARCH = re.compile(
    r"^(?P<prefix>.*/careersection/(?P<section>[^/]+))/(?:jobsearch|jobdetail)\.ftl(?:$|\?)",
    re.I,
)
_ACCESS = re.compile(
    r".*/careersection/[^/]+/accesscontrol\.ftl",
    re.I,
)

# Markers seen on Candidate Home / My Jobpage after a successful login (offline).
_EVIDENCE_MARKERS: tuple[str, ...] = (
    "candidate home",
    "my submissions",
    "my jobpage",
    "my profile",
    "sign out",
    "cerrar sesión",
    "cerrar sesion",
)

# Blocking challenges — not ordinary Terms/Privacy *checkboxes* on the form.
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

# Inventory of the new-user / access-control form. Password and terms stay HITL.
_FIELDS_EN: tuple[tuple[str, str | None], ...] = (
    ("First Name", "personal.name"),
    ("Last Name", "personal.name"),
    ("Email Address", "personal.email"),
    ("Phone Number", "personal.phone"),
    ("Country", "personal.country"),
    ("City", "personal.city"),
    ("Password", None),
    ("Confirm Password", None),
    ("Terms and Conditions", None),
    ("Privacy Agreement", None),
    ("CAPTCHA", None),
    ("Create Account", None),
)

# FAO careersection often serves the registration UI in Spanish (#447).
_FIELDS_ES: tuple[tuple[str, str | None], ...] = (
    ("Nombre", "personal.name"),
    ("Apellido", "personal.name"),
    ("Correo Electrónico Personal", "personal.email"),
    ("Teléfono", "personal.phone"),
    ("País", "personal.country"),
    ("Ciudad", "personal.city"),
    ("Contraseña", None),
    ("Vuelva a introducir contraseña", None),
    ("Términos y condiciones", None),
    ("Acuerdo de privacidad", None),
    ("CAPTCHA", None),
    ("Registrar", None),
)

_ALWAYS_HITL: frozenset[str] = frozenset(
    {
        "Password",
        "Confirm Password",
        "Terms and Conditions",
        "Privacy Agreement",
        "CAPTCHA",
        "Create Account",
        "Contraseña",
        "Vuelva a introducir contraseña",
        "Términos y condiciones",
        "Acuerdo de privacidad",
        "Registrar",
    }
)

# Path tokens on the Privacy Agreement *gate* (before the form). Not checkbox labels.
_PRIVACY_WALL_PATHS: tuple[str, ...] = (
    "statementbeforeauthentification",
    "/privacyagreement/",
)


class SignupRecognize(StrEnum):
    """Result of inspecting a saved registration HTML fixture."""

    OK = "ok"
    UI_CHANGED = "ui_changed"
    MANUAL_CHALLENGE = "manual_challenge"


@dataclass(frozen=True)
class TaleoPortal:
    """One employer careersection that uses Taleo for candidate accounts."""

    portal_id: str
    name: str
    section: str
    # Public jobsearch URL (host is the real careers host; fixtures use example.org).
    jobsearch_url: str
    lang: str = "en"
    # When set, used as the sheet registration URL instead of deriving accesscontrol.
    signup_url: str | None = None


OMS_WHO = TaleoPortal(
    portal_id="oms_who",
    name="WHO Careers (Taleo)",
    section="ex",
    jobsearch_url="https://careers.who.int/careersection/ex/jobsearch.ftl",
    lang="en",
)

FAO = TaleoPortal(
    portal_id="fao",
    name="FAO Jobs (Taleo)",
    section="fao_external",
    jobsearch_url=(
        "https://jobs.fao.org/careersection/fao_external/jobsearch.ftl?lang=es"
    ),
    lang="es",
    signup_url=(
        "https://jobs.fao.org/careersection/fao_external/accesscontrol.ftl?lang=es"
    ),
)

_BY_ID: dict[str, TaleoPortal] = {
    OMS_WHO.portal_id: OMS_WHO,
    FAO.portal_id: FAO,
}


def portal_for_id(portal_id: str) -> TaleoPortal | None:
    return _BY_ID.get(portal_id.strip())


def registration_url(url: str, *, lang: str | None = None) -> str:
    """Map a careersection jobsearch/jobdetail URL to accesscontrol (new user entry).

    Already-accesscontrol URLs are returned unchanged (query preserved). Unknown
    shapes are returned unchanged so callers can still open the page.
    """
    text = (url or "").strip()
    if not text:
        return text
    if _ACCESS.search(text):
        return text
    match = _JOBSEARCH.match(text)
    if match is None:
        return text
    prefix = match.group("prefix")
    query_lang = lang
    if query_lang is None:
        parsed = urlparse(text)
        for part in parsed.query.split("&"):
            if part.lower().startswith("lang="):
                query_lang = part.split("=", 1)[1] or "en"
                break
    query_lang = query_lang or "en"
    target = f"{prefix}/accesscontrol.ftl?lang={query_lang}"
    # Preserve scheme/host from the input when prefix is relative (should not happen).
    if target.startswith("http"):
        return target
    parsed = urlparse(text)
    return urlunparse((parsed.scheme, parsed.netloc, target, "", f"lang={query_lang}", ""))


def _has_captcha(html: str) -> bool:
    lowered = (html or "").casefold()
    return any(marker in lowered for marker in _CAPTCHA_MARKERS)


def _has_code_challenge(html: str) -> bool:
    lowered = (html or "").casefold()
    return any(marker in lowered for marker in _CODE_CHALLENGE_MARKERS)


def _is_privacy_wall(html: str, url: str) -> bool:
    """True for the FAO/Taleo privacy gate page, not a privacy checkbox on the form."""
    haystack = f"{url}\n{html}".casefold()
    return any(marker in haystack for marker in _PRIVACY_WALL_PATHS)


def recognize_signup_html(
    html: str,
    *,
    url: str = "",
) -> tuple[SignupRecognize, FormKnowledge | None]:
    """Offline recognition of a Taleo-like registration form.

    Returns ``MANUAL_CHALLENGE`` when CAPTCHA, a verification-code wall, or a
    Privacy Agreement gate blocks, ``UI_CHANGED`` when no readable signup fields
    are found, otherwise ``OK`` with a learned form (password/terms stay
    unfilled by ``signup_fill``). Terms/Privacy *checkboxes* on the form are
    HITL fields, not a challenge wall — unless the page itself is the privacy
    gate (FAO ``privacyagreement`` path).
    """
    if _has_captcha(html) or _has_code_challenge(html):
        return SignupRecognize.MANUAL_CHALLENGE, None
    if _is_privacy_wall(html, url):
        # Gate before the form: human must accept; JobBot never clicks I Accept.
        return SignupRecognize.MANUAL_CHALLENGE, None
    form = learn_form_html(
        html,
        url=url or "https://careers.example.org/careersection/ex/accesscontrol.ftl",
    )
    if not form.readable:
        return SignupRecognize.UI_CHANGED, None
    labels = {field.label.casefold() for field in form.fields}
    # Need at least an email-like field or a name field to call it a signup form.
    emailish = any("email" in label or "correo" in label for label in labels)
    nameish = any(
        token in label
        for label in labels
        for token in ("name", "nombre", "first", "last", "apellido")
    )
    if not (emailish or nameish):
        return SignupRecognize.UI_CHANGED, form
    return SignupRecognize.OK, form


def account_evidence(html: str, *, url: str = "") -> AccountState:
    """Local evidence from saved HTML only — never invents a session."""
    if _has_captcha(html) or _has_code_challenge(html):
        return AccountState.needs_human
    if _is_privacy_wall(html, url):
        return AccountState.needs_human
    lowered = (html or "").casefold()
    if any(marker in lowered for marker in _EVIDENCE_MARKERS):
        return AccountState.evidenced
    return AccountState.unknown


def _fields_for(portal: TaleoPortal | None) -> tuple[tuple[str, str | None], ...]:
    if portal is not None and portal.lang.startswith("es"):
        return _FIELDS_ES
    return _FIELDS_EN


def signup_items(
    candidate: Candidate,
    *,
    portal: TaleoPortal | None = None,
) -> list[SignupItem]:
    """Sheet rows for Taleo registration. Password / terms / create stay empty."""
    items: list[SignupItem] = []
    for label, _home in _fields_for(portal):
        if label in _ALWAYS_HITL:
            items.append(
                SignupItem(
                    label=label,
                    value="",
                    source="HITL — JobBot never fills password, terms, CAPTCHA or create",
                )
            )
            continue
        value, source = answer_for_label(candidate, label)
        items.append(SignupItem(label=label, value=value, source=source))
    return items


def portal_registration_url(portal: TaleoPortal) -> str:
    """Public registration entry for the sheet and companies signup."""
    if portal.signup_url:
        return portal.signup_url
    return registration_url(portal.jobsearch_url, lang=portal.lang)


def render_taleo_sheet(
    portal: TaleoPortal,
    candidate: Candidate,
    aliases: dict[str, str],
    *,
    email_alias: str | None = None,
) -> str:
    """Markdown the person can copy. Contact email uses the portal alias when set."""
    email_labels = {"Email Address", "Correo Electrónico Personal"}
    lines = [
        f"# {portal.name}",
        "",
        f"Portal: `{portal.portal_id}` · adapter: `taleo` · section: `{portal.section}`",
        "",
        f"Registro: `{portal_registration_url(portal)}`",
        "",
        "Hoja de alta. JobBot rellena solo campos que el SST ya responde (`companies signup "
        "--apply`); password, términos, CAPTCHA y Create quedan en HITL.",
        "",
    ]
    for item in signup_items(candidate, portal=portal):
        if item.label in email_labels and email_alias:
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
