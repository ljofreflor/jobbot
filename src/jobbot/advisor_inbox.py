"""Inbound client messages (WhatsApp): questions and CV HITL, never submit, never secrets.

The OSS CLI has no WhatsApp daemon. Enrolled clients of the advisory service
still write to JobBot there; this module is the policy that transport must call.
A yes confirms a fact. It never sends an application. Passwords, OTP and 2FA
are refused and not stored. Anything that needs a human judgment is queued for
the advisor. The same never-invent rules as the rest of JobBot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class InboundKind(StrEnum):
    """What the message is asking JobBot to do."""

    IGNORE = "ignore"
    QUESTION = "question"
    FACT_CONFIRM = "fact_confirm"
    FACT_DECLINE = "fact_decline"
    FACT_OFFER = "fact_offer"
    SECRET = "secret"
    SUBMIT = "submit"
    ADVISOR = "advisor"


@dataclass(frozen=True)
class PendingPrompt:
    """A CV question already asked, waiting for a yes, a no, or a fact."""

    summary: str


@dataclass(frozen=True)
class InboundDecision:
    """How the gateway may act. ``may_submit`` is always false."""

    kind: InboundKind
    writes_profile: bool
    may_submit: bool
    store_body: bool
    needs_human: bool
    reply: str


_SECRET_RE = re.compile(
    r"\b("
    r"contrase[nñ]a|password|passwd|passcode|"
    r"clave\s+de\s+(acceso|paso)|"
    r"c[oó]digo\s+de\s+verificaci[oó]n|"
    r"verification\s+code|one[-\s]?time|"
    r"\botp\b|\b2fa\b|two[-\s]?factor|autenticador|"
    r"authenticator|token\s+de\s+acceso"
    r")\b",
    re.I,
)
_SUBMIT_RE = re.compile(
    r"\b("
    r"postula(?:r|me|lo|la)?|postul[áa]|"
    r"env[ií]a(?:lo|la|me)?|m[aá]ndalo|m[aá]ndala|"
    r"aplic(?:a|ar|ame)|submit|"
    r"dale\s+enviar|aprieta\s+enviar"
    r")\b",
    re.I,
)
_YES_RE = re.compile(
    r"^(s[ií]|ok|okay|dale|de\s+acuerdo|confirmo|yes|yep|yeah)\.?$",
    re.I,
)
_NO_RE = re.compile(
    r"^(no|nop|nope|cancel[aeá]|descarta|nah)\.?$",
    re.I,
)
_QUESTION_RE = re.compile(
    r"[¿?]|\bpreguntas?\b|\bquestions?\b|"
    r"^\s*(qu[eé]|c[oó]mo|por\s+qu[eé]|cu[aá]ndo|cu[aá]l(?:es)?|"
    r"cu[aá]nto|d[oó]nde|who|what|when|where|why|how)\b",
    re.I,
)
_FIRST_PERSON_RE = re.compile(
    r"\b("
    r"tengo|tuve|hice|trabaj[eé]|soy|fui|estuve|estudi[eé]|"
    r"me\s+llamo|en\s+realidad|de\s+verdad|fueron|"
    r"i\s+(have|had|did|worked|am|was|studied)|actually\s+it\s+was"
    r")\b",
    re.I,
)

_REPLY_SECRET = "No envíes contraseñas, códigos ni 2FA por este chat. Escríbelos tú en el portal."
_REPLY_SUBMIT = "JobBot no envía postulaciones por WhatsApp. Revisa el paquete y aprieta enviar tú."
_REPLY_CONFIRM = "Quedó confirmado. Entra a tu perfil solo eso, nada más."
_REPLY_DECLINE = "No entra. Lo dejamos como está."
_REPLY_OFFER = (
    "Eso sería un hecho nuevo en tu perfil. ¿Lo confirmo? Hasta que digas que sí, no se escribe."
)
_REPLY_QUESTION = ""
_REPLY_ADVISOR = "Eso lo mira el asesor. Te responde aquí; JobBot no inventa la respuesta."
_REPLY_IGNORE = ""


def classify_inbound(
    text: str,
    pending: PendingPrompt | None = None,
) -> InboundDecision:
    """Decide what an inbound WhatsApp (or any chat) message may do.

    Order is a safety gate: secrets and submit intents win over a question
    mark. A yes only writes when a pending CV prompt exists.
    """
    body = " ".join((text or "").split())
    if not body:
        return _decision(InboundKind.IGNORE, reply=_REPLY_IGNORE, store_body=False)

    if _SECRET_RE.search(body):
        return _decision(
            InboundKind.SECRET,
            reply=_REPLY_SECRET,
            store_body=False,
        )
    if _SUBMIT_RE.search(body):
        return _decision(InboundKind.SUBMIT, reply=_REPLY_SUBMIT)

    folded = body.strip()
    if pending is not None and _YES_RE.match(folded):
        return _decision(
            InboundKind.FACT_CONFIRM,
            reply=_REPLY_CONFIRM,
            writes_profile=True,
        )
    if pending is not None and _NO_RE.match(folded):
        return _decision(InboundKind.FACT_DECLINE, reply=_REPLY_DECLINE)

    if _QUESTION_RE.search(body):
        return _decision(
            InboundKind.QUESTION,
            reply=_REPLY_QUESTION,
        )
    if _FIRST_PERSON_RE.search(body):
        return _decision(InboundKind.FACT_OFFER, reply=_REPLY_OFFER)

    return _decision(
        InboundKind.ADVISOR,
        reply=_REPLY_ADVISOR,
        needs_human=True,
    )


def _decision(
    kind: InboundKind,
    *,
    reply: str,
    writes_profile: bool = False,
    store_body: bool = True,
    needs_human: bool = False,
) -> InboundDecision:
    return InboundDecision(
        kind=kind,
        writes_profile=writes_profile,
        may_submit=False,
        store_body=store_body,
        needs_human=needs_human,
        reply=reply,
    )
