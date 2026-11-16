"""LinkedIn selector hints. The Easy Apply submit control is named and never clicked."""

LINKEDIN_FEED = "https://www.linkedin.com/feed/"
LINKEDIN_LOGIN = "https://www.linkedin.com/login"
LINKEDIN_ME = "https://www.linkedin.com/in/me/"

# Post card control menu ("…"): the only place LinkedIn still hands over a
# post's own URL, via "Copy link to post" → clipboard.
POST_CONTROL_MENU = (
    '[aria-label^="Abrir el menú de controles"], '
    '[aria-label^="Open control menu"], '
    '[aria-label*="control menu for"]'
)
POST_MENU_ITEM = '[role="menuitem"], [role="menu"] [role="button"]'
COPY_LINK_LABELS = ("copiar enlace", "copy link")

# Last step of Easy Apply. Present so a writer can refuse it; this module never clicks.
EASY_APPLY_SUBMIT = (
    '[aria-label="Submit application"], [aria-label="Enviar solicitud"]'
)
_EASY_APPLY_SUBMIT_LABELS = frozenset({"submit application", "enviar solicitud"})


def is_easy_apply_submit(label: str) -> bool:
    """True only for the control that sends the application."""
    return " ".join(label.casefold().split()) in _EASY_APPLY_SUBMIT_LABELS
