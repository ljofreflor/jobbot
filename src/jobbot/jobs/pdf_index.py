"""List PDF links on one public page. Same host only; nothing is downloaded."""

from __future__ import annotations

from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from jobbot.jobs.pdf_posting import fetch_public


def fetch_page(url: str) -> str:
    """HTML of a transparency index. Tests replace this."""
    body = fetch_public(url)
    return body.body.decode("utf-8", errors="replace")


def matching_pdfs(html: str, page_url: str, *, match: str = "concurso") -> list[str]:
    """PDF links on `page_url`'s host whose filename contains `match`."""
    page = urlsplit(page_url)
    needle = match.casefold()
    found: list[str] = []
    for anchor in BeautifulSoup(html or "", "html.parser").find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(page_url, href)
        parts = urlsplit(absolute)
        if parts.netloc.casefold() != page.netloc.casefold():
            continue
        name = unquote(parts.path.rsplit("/", 1)[-1])
        if not name.casefold().endswith(".pdf"):
            continue
        if needle and needle not in name.casefold():
            continue
        clean = urlunsplit((parts.scheme or page.scheme, parts.netloc, parts.path, "", ""))
        if clean not in found:
            found.append(clean)
    return found
