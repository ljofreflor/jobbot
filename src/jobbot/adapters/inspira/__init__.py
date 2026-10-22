"""UN Inspira (PeopleSoft) — account / Talent Pool signup helpers (HITL).

Job discovery for UN Careers stays in ``adapters/un_careers``. This package
covers **alta de cuenta**: registration URL, sheet, form recognition and local
account evidence. Never invents a password, never solves CAPTCHA/OAuth, never
clicks Subscribe/Create without HITL confirmation. See #437.
"""

from jobbot.adapters.inspira.signup import (
    UN_CAREERS,
    account_evidence,
    portal_for_id,
    recognize_signup_html,
    registration_url,
    render_inspira_sheet,
    signup_items,
)

__all__ = [
    "UN_CAREERS",
    "account_evidence",
    "portal_for_id",
    "recognize_signup_html",
    "registration_url",
    "render_inspira_sheet",
    "signup_items",
]
