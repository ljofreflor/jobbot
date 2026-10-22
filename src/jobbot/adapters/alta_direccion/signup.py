"""Alta Dirección Pública (ADP) account signup — identity_bound sheet (no browser).

The portal binds the account to RUN. JobBot never attaches, never invents a
password, never clicks Registrar. robots.txt forbids live fetch; fixtures only.
See #436 / #434.
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

REGISTRATION_URL = (
    "https://adp.serviciocivil.cl/concursos-spl/opencms/registro.html"
)
LOGIN_URL = "https://adp.serviciocivil.cl/concursos-spl/opencms/login.html"

_FIELDS: tuple[str, ...] = (
    "Nombre",
    "Apellido Paterno",
    "Apellido Materno",
    "Correo electrónico",
    "RUN",
    "Contraseña",
    "Confirmación de contraseña",
    "Registrar",
)

_ALWAYS_HITL: frozenset[str] = frozenset(
    {
        "RUN",
        "Contraseña",
        "Confirmación de contraseña",
        "Registrar",
    }
)

_CAPTCHA_MARKERS: tuple[str, ...] = (
    "g-recaptcha",
    "h-captcha",
    "data-sitekey",
    "recaptcha",
    "hcaptcha",
)
_EVIDENCE_MARKERS: tuple[str, ...] = (
    "mis concursos",
    "mi postulación",
    "mi postulacion",
    "cerrar sesión",
    "cerrar sesion",
    "salir",
    "bienvenido",
)


class SignupRecognize(StrEnum):
    """Result of inspecting a saved registration HTML fixture."""

    OK = "ok"
    UI_CHANGED = "ui_changed"
    MANUAL_CHALLENGE = "manual_challenge"


@dataclass(frozen=True)
class AdpPortal:
    """Fill-catalog identity for Alta Dirección Pública."""

    portal_id: str
    name: str
    signup_url: str
    login_url: str


ADP = AdpPortal(
    portal_id="adp",
    name="Alta Dirección Pública",
    signup_url=REGISTRATION_URL,
    login_url=LOGIN_URL,
)


def portal_for_id(portal_id: str) -> AdpPortal | None:
    if portal_id.strip() == ADP.portal_id:
        return ADP
    return None


def registration_url(url: str = "") -> str:
    """Canonical ADP registro entry for career-site URLs."""
    text = (url or "").strip()
    if not text:
        return REGISTRATION_URL
    lowered = text.casefold()
    if "registro.html" in lowered:
        return text
    return REGISTRATION_URL


def _has_captcha(html: str) -> bool:
    lowered = (html or "").casefold()
    return any(marker in lowered for marker in _CAPTCHA_MARKERS)


def recognize_signup_html(
    html: str,
    *,
    url: str = "",
) -> tuple[SignupRecognize, FormKnowledge | None]:
    """Offline recognition of the ADP registro form."""
    if _has_captcha(html):
        return SignupRecognize.MANUAL_CHALLENGE, None
    form = learn_form_html(
        html,
        url=url or "https://adp.example.org/concursos-spl/opencms/registro.html",
    )
    if not form.readable:
        return SignupRecognize.UI_CHANGED, None
    labels = {field.label.casefold() for field in form.fields}
    nameish = any(
        token in label
        for label in labels
        for token in ("nombre", "apellido", "name")
    )
    emailish = any("email" in label or "correo" in label for label in labels)
    if not (nameish or emailish):
        return SignupRecognize.UI_CHANGED, form
    return SignupRecognize.OK, form


def account_evidence(html: str) -> AccountState:
    """Local evidence from saved HTML only — never invents a session."""
    if _has_captcha(html):
        return AccountState.needs_human
    lowered = (html or "").casefold()
    if any(marker in lowered for marker in _EVIDENCE_MARKERS):
        return AccountState.evidenced
    return AccountState.identity_bound


def _family_parts(candidate: Candidate) -> tuple[str, str]:
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
    """Sheet rows. RUN / password / Registrar stay empty (HITL)."""
    items: list[SignupItem] = []
    paterno, materno = _family_parts(candidate)
    for label in _FIELDS:
        if label in _ALWAYS_HITL:
            items.append(
                SignupItem(
                    label=label,
                    value="",
                    source="HITL — JobBot never fills RUN, password or Registrar",
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


def render_adp_sheet(
    candidate: Candidate,
    aliases: dict[str, str],
    *,
    email_alias: str | None = None,
    portal: AdpPortal = ADP,
) -> str:
    """Markdown the person copies by hand. JobBot does not open the browser."""
    lines = [
        f"# {portal.name}",
        "",
        f"Portal: `{portal.portal_id}` · adapter: `identity_bound`",
        "",
        f"Registro: `{portal.signup_url}`",
        "",
        "Este portal pide identidad estatal (RUN). jobbot no abre el navegador "
        "ni escribe. Copiar esta hoja a mano. Password y Registrar quedan en HITL. "
        "El sitio prohíbe fetch automático (robots); la evidencia es local.",
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
