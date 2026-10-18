"""Saved Buk list HTML into postings. The live site stays unread."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from jobbot.models.job import JobPosting

_CODE = re.compile(r"/s/([A-Za-z0-9_-]+)")


class BukShapeError(ValueError):
    """The saved page is not a Buk list of job cards."""


def tenant_from_url(url: str) -> str:
    """`acme.buk.cl` → `acme`. The subdomain is the employer key on a white-label host."""
    host = (urlparse(url).hostname or "").lower()
    labels = host.split(".")
    if len(labels) >= 3 and labels[-2] == "buk":
        return labels[0]
    return host or "buk"


def jobs_from_list_html(html: str, *, page_url: str) -> list[JobPosting]:
    """One posting per `jobs__card`. A page without that card is a shape change."""
    soup = BeautifulSoup(html or "", "html.parser")
    cards = [node for node in soup.select(".jobs__card") if isinstance(node, Tag)]
    if not cards:
        msg = "el listado Buk no tiene tarjetas jobs__card"
        raise BukShapeError(msg)
    tenant = tenant_from_url(page_url)
    host = urlparse(page_url).hostname or ""
    found: list[JobPosting] = []
    for card in cards:
        anchor = card.find("a", href=True)
        href = str(anchor.get("href")) if isinstance(anchor, Tag) else ""
        match = _CODE.search(href)
        name = card.select_one(".job__card-name")
        title = " ".join(name.get_text(" ", strip=True).split()) if isinstance(name, Tag) else ""
        if match is None or not title:
            continue
        code = match.group(1)
        info = card.select_one(".jobs__card-info")
        location = (
            " ".join(info.get_text(" ", strip=True).split()) if isinstance(info, Tag) else ""
        )
        absolute = urljoin(f"https://{host}/", href) if host else href
        posting_url = absolute.split("?", 1)[0]
        if not posting_url.endswith(f"/s/{code}"):
            posting_url = f"https://{host}/s/{code}" if host else posting_url
        found.append(
            JobPosting(
                id="PENDING",
                source="buk",
                source_job_id=f"{tenant}:{code}",
                url=posting_url,
                ats_url=posting_url,
                ats_kind="buk",
                title=title,
                company=tenant,
                location=location or None,
                description=title,
            )
        )
    if not found:
        msg = "el listado Buk no tiene tarjetas jobs__card con título y /s/{código}"
        raise BukShapeError(msg)
    return found
