"""Empleos Públicos account signup — identity_bound sheet (no browser).

The portal binds the account to RUN / ClaveÚnica. JobBot never attaches to the
login, never invents a password, never starts ClaveÚnica/OAuth, and never clicks
Crear. See #435 / #434.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from jobbot.companies.signup import SignupItem
from jobbot.models.candidate import Candidate
from jobbot.portals.field_homologation import answer_for_label
from jobbot.portals.form_learn import FormKnowledge, learn_form_html
from jobbot.portals.profile_state import AccountState

NEEDS_HUMAN = "needs_human"

# Public registration entry (ASP.NET). Fixtures use example-careers.example.org.
REGISTRATION_URL = (
    "https://www.empleospublicos.cl/pub/usuarios/usrPostulanteAgregar.aspx"
)
LOGIN_URL = "https://www.empleospublicos.cl/pub/usuarios/usrLogin.aspx"

# Inventory of usrPostulanteAgregar. RUN / password / terms / create stay HITL.
_FIELDS: tuple[str, ...] = (
    "Nombres",
    "Apellido Paterno",
    "Apellido Materno",
    "Correo electrónico",
    "Celular",
    "RUN",
    "Contraseña",
    "Confirmación de contraseña",
    "Condiciones de uso",
    "ClaveÚnica",
    "Crear cuenta",
)

_ALWAYS_HITL: frozenset[str] = frozenset(
    {
        "RUN",
        "Contraseña",
        "Confirmación de contraseña",
        "Condiciones de uso",
        "ClaveÚnica",
        "Crear cuenta",
    }
)

_CLAVEUNICA_MARKERS: tuple[str, ...] = (
    "claveunica",
    "clave única",
    "clave unica",
    "accounts.claveunica.gob.cl",
)
_CAPTCHA_MARKERS: tuple[str, ...] = (
    "g-recaptcha",
    "h-captcha",
    "data-sitekey",
    "recaptcha",
    "hcaptcha",
)
_EVIDENCE_MARKERS: tuple[str, ...] = (
    "mi currículum",
    "mi curriculum",
    "mis postulaciones",
    "cerrar sesión",
    "cerrar sesion",
    "número de registro",
    "numero de registro",
)


class SignupRecognize(StrEnum):
    """Result of inspecting a saved registration HTML fixture."""

    OK = "ok"
    UI_CHANGED = "ui_changed"
    MANUAL_CHALLENGE = "manual_challenge"


@dataclass(frozen=True)
class EmpleosPublicosPortal:
    """Fill-catalog identity for Empleos Públicos (Servicio Civil)."""

    portal_id: str
    name: str
    signup_url: str
    login_url: str


EMPLEOS_PUBLICOS = EmpleosPublicosPortal(
    portal_id="empleos_publicos",
    name="Empleos Públicos",
    signup_url=REGISTRATION_URL,
    login_url=LOGIN_URL,
)


def portal_for_id(portal_id: str) -> EmpleosPublicosPortal | None:
    if portal_id.strip() == EMPLEOS_PUBLICOS.portal_id:
        return EMPLEOS_PUBLICOS
    return None


def registration_url(url: str = "") -> str:
    """Canonical registration entry for Empleos Públicos career sites.

    Any board/home/login URL maps to ``usrPostulanteAgregar``. An already-open
    registration URL is returned unchanged (query preserved).
    """
    text = (url or "").strip()
    if not text:
        return REGISTRATION_URL
    lowered = text.casefold()
    if "usrpostulanteagregar" in lowered:
        return text
    return REGISTRATION_URL


def _has_claveunica(html: str) -> bool:
    lowered = (html or "").casefold()
    return any(marker in lowered for marker in _CLAVEUNICA_MARKERS)


def _has_captcha(html: str) -> bool:
    lowered = (html or "").casefold()
    return any(marker in lowered for marker in _CAPTCHA_MARKERS)


def recognize_signup_html(
    html: str,
    *,
    url: str = "",
) -> tuple[SignupRecognize, FormKnowledge | None]:
    """Offline recognition of the Empleos Públicos registration form.

    ClaveÚnica / CAPTCHA walls are ``MANUAL_CHALLENGE`` — JobBot never starts them.
    """
    if _has_captcha(html):
        return SignupRecognize.MANUAL_CHALLENGE, None
    # A dedicated ClaveÚnica *gate* (login with only the state IdP) is HITL.
    # The registration form itself may *mention* ClaveÚnica as an alternative;
    # that mention alone is not a wall if name/email fields are present.
    form = learn_form_html(
        html,
        url=url or "https://example-careers.example.org/pub/usuarios/usrPostulanteAgregar.aspx",
    )
    if not form.readable:
        if _has_claveunica(html):
            return SignupRecognize.MANUAL_CHALLENGE, None
        return SignupRecognize.UI_CHANGED, None
    labels = {field.label.casefold() for field in form.fields}
    nameish = any(
        token in label
        for label in labels
        for token in ("nombre", "apellido", "name")
    )
    emailish = any("email" in label or "correo" in label for label in labels)
    if not (nameish or emailish):
        if _has_claveunica(html):
            return SignupRecognize.MANUAL_CHALLENGE, None
        return SignupRecognize.UI_CHANGED, form
    return SignupRecognize.OK, form


def account_evidence(html: str) -> AccountState:
    """Local evidence from saved HTML only — never invents a session.

    Without Candidate Home markers the portal stays ``identity_bound`` (sheet
    only; JobBot does not attach).
    """
    if _has_captcha(html):
        return AccountState.needs_human
    lowered = (html or "").casefold()
    if any(marker in lowered for marker in _EVIDENCE_MARKERS):
        return AccountState.evidenced
    if _has_claveunica(html) and "usrpostulanteagregar" not in lowered:
        return AccountState.needs_human
    return AccountState.identity_bound


def _family_parts(candidate: Candidate) -> tuple[str, str]:
    """Paterno / materno from ``personal.name`` when SST has two family tokens."""
    parts = (candidate.personal.name or "").split()
    if len(parts) >= 4:
        family = parts[2:]
    elif len(parts) >= 2:
        family = parts[1:]
    else:
        family = []
    if not family:
        return ("", "")
    if len(family) == 1:
        return (family[0], "")
    return (family[0], " ".join(family[1:]))


def signup_items(candidate: Candidate) -> list[SignupItem]:
    """Sheet rows. RUN / password / ClaveÚnica / create stay empty (HITL)."""
    items: list[SignupItem] = []
    paterno, materno = _family_parts(candidate)
    for label in _FIELDS:
        if label in _ALWAYS_HITL:
            items.append(
                SignupItem(
                    label=label,
                    value="",
                    source=(
                        "HITL — JobBot never fills RUN, password, ClaveÚnica, "
                        "terms or create"
                    ),
                )
            )
            continue
        if label == "Apellido Paterno":
            items.append(
                SignupItem(
                    label=label,
                    value=paterno,
                    source="personal.name" if paterno else "you decide: not a fact in the profile",
                )
            )
            continue
        if label == "Apellido Materno":
            items.append(
                SignupItem(
                    label=label,
                    value=materno,
                    source="personal.name" if materno else "you decide: not a fact in the profile",
                )
            )
            continue
        value, source = answer_for_label(candidate, label)
        items.append(SignupItem(label=label, value=value, source=source))
    return items


def render_empleos_publicos_sheet(
    candidate: Candidate,
    aliases: dict[str, str],
    *,
    email_alias: str | None = None,
    portal: EmpleosPublicosPortal = EMPLEOS_PUBLICOS,
) -> str:
    """Markdown the person copies by hand. JobBot does not open the browser."""
    lines = [
        f"# {portal.name}",
        "",
        f"Portal: `{portal.portal_id}` · adapter: `identity_bound`",
        "",
        f"Registro: `{portal.signup_url}`",
        "",
        "Este portal pide identidad estatal (RUN / ClaveÚnica). jobbot no abre el "
        "navegador ni escribe. Copiar esta hoja a mano. Password, términos, "
        "ClaveÚnica y Crear quedan en HITL.",
        "",
    ]
    for item in signup_items(candidate):
        if item.label.casefold() in {"correo electrónico", "correo electronico"} and email_alias:
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
