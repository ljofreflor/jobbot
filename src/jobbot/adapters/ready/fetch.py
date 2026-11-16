"""Fetch one Ready careers JSON document. Tests replace `fetch_public`."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from jobbot.adapters.ready.parse import api_url, career_slug, job_from_payload
from jobbot.jobs.from_url import (
    InvalidPostingUrlError,
    PortalShapeChangedError,
    UnsupportedPortalFetchError,
)
from jobbot.models.job import JobPosting


def fetch_public(url: str) -> tuple[int, str]:
    """GET one public JSON URL. Tests replace this."""
    request = urllib.request.Request(url, headers={"User-Agent": "jobbot/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            status = int(getattr(response, "status", 200))
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        # 4xx/5xx is an answer: keep the code so the caller names it.
        return int(exc.code), exc.read(20_000).decode("utf-8", errors="replace")
    except OSError as exc:
        raise UnsupportedPortalFetchError(
            "Ready ATS did not answer. Pass --fixture with the careers JSON. "
            "The posting was not invented."
        ) from exc
    return status, body


def fetch_ready_posting(page_url: str, *, body: str | None = None) -> JobPosting:
    """JSON fixture, or the public careers API. Never a title guessed from the slug."""
    slug = career_slug(page_url)
    if slug is None:
        raise InvalidPostingUrlError(f"{page_url} is not a Ready /careers/{{slug}} link")
    if body is None:
        status, body = fetch_public(api_url(slug))
        if status != 200:
            raise UnsupportedPortalFetchError(
                f"Ready ATS answered HTTP {status}. Pass --fixture with the careers JSON. "
                "The posting was not invented."
            )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise UnsupportedPortalFetchError(
            "Ready ATS needs the careers JSON. The page shell has no posting, "
            "and nothing was invented."
        ) from exc
    job = job_from_payload(payload, page_url=page_url)
    if job is None:
        raise PortalShapeChangedError(
            f"Ready careers JSON for {slug} has no title and description. Nothing was invented."
        )
    return job
