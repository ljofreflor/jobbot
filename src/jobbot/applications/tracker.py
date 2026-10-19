"""Local pipeline labels. A job with no application row is ``saved``.

``applied`` is written only by an explicit ``application status --set``. A
dry-run apply does not call this module.
"""

from __future__ import annotations

from jobbot.models.application import Application, ApplicationStatus

_KNOWN = frozenset({"saved", *(status.value for status in ApplicationStatus)})


class TrackerError(ValueError):
    """The status name is not one this pipeline stores."""


def status_label(application: Application | None) -> str:
    """``saved`` when the job has no application row yet."""
    if application is None:
        return "saved"
    return application.status.value


def parse_status(value: str) -> ApplicationStatus:
    """``saved`` is the stored equivalent ``discovered``. Unknown names fail."""
    key = value.strip().casefold()
    if key not in _KNOWN:
        known = ", ".join(sorted(_KNOWN))
        msg = f"unknown status {value!r}; expected one of: {known}"
        raise TrackerError(msg)
    if key == "saved":
        return ApplicationStatus.DISCOVERED
    return ApplicationStatus(key)


def known_status(value: str) -> bool:
    """True for ``saved`` and every stored application status."""
    return value.strip().casefold() in _KNOWN
