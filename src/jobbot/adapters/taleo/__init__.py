"""Oracle Taleo Enterprise careersection — account signup helpers (HITL).

Job discovery for Taleo stays in ``jobs discover --source taleo`` (#245).
This package covers **alta de cuenta**: registration URL, sheet, form
recognition and local account evidence. Never invents a password, never
solves CAPTCHA/OAuth, never clicks create/submit.
"""

from jobbot.adapters.taleo.signup import (
    FAO,
    OMS_WHO,
    TaleoPortal,
    account_evidence,
    portal_for_id,
    portal_registration_url,
    recognize_signup_html,
    registration_url,
    render_taleo_sheet,
    signup_items,
)

__all__ = [
    "FAO",
    "OMS_WHO",
    "TaleoPortal",
    "account_evidence",
    "portal_for_id",
    "portal_registration_url",
    "recognize_signup_html",
    "registration_url",
    "render_taleo_sheet",
    "signup_items",
]
