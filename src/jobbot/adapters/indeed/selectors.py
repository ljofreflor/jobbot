"""Indeed selector hints (prefer role/label over obfuscated CSS)."""

INDEED_HOME = "https://www.indeed.com/"
INDEED_PROFILE = "https://profile.indeed.com/"
INDEED_RESUME = "https://profile.indeed.com/resume"
INDEED_LOGIN = "https://secure.indeed.com/auth"

_COUNTRY_HOSTS = {
    "cl": "https://cl.indeed.com",
    "us": "https://www.indeed.com",
    "mx": "https://mx.indeed.com",
    "ar": "https://ar.indeed.com",
    "es": "https://es.indeed.com",
}


def indeed_jobs_base(country: str = "cl") -> str:
    return _COUNTRY_HOSTS.get(country.lower(), f"https://{country.lower()}.indeed.com")


# Learned once from the Indeed resume editor (profile.indeed.com). Next candidates
# reuse these test ids; they do not rediscover the control by hand.
HEADLINE_INPUT = "headline-input"
CONTACT_SAVE = "contact-info-save"


def select_list_testid(control_testid: str) -> str:
    """Menu that opens from an Indeed select button.

    The date control is ``work-experience-date-range-to-year``; its options live
    in ``container-work-experience-date-range-to-year-list`` as ``role=option``.
    Clicking the year text anywhere on the page hits the wrong node.
    """
    return f"container-{control_testid}-list"
