"""Alta Dirección Pública — offline ficha parse + identity_bound account sheet.

robots.txt forbids fetching the site; discovery stays fixture-first.
"""

from jobbot.adapters.alta_direccion.signup import (
    ADP,
    account_evidence,
    portal_for_id,
    recognize_signup_html,
    registration_url,
    render_adp_sheet,
    signup_items,
)

__all__ = [
    "ADP",
    "account_evidence",
    "portal_for_id",
    "recognize_signup_html",
    "registration_url",
    "render_adp_sheet",
    "signup_items",
]
