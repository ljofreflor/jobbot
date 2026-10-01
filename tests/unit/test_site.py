"""The advisory page published on GitHub Pages: static, private, honest. Offline."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from jobbot.ops import pii_guard

LINKEDIN = "https://www.linkedin.com/in/leonardojofre"
REPO = "https://github.com/ljofreflor/jobbot"

_TRACKING_MARKERS = (
    "googletagmanager",
    "gtag(",
    "google-analytics",
    "analytics",
    "connect.facebook.net",
    "fbq(",
    "hotjar",
    "plausible",
    "matomo",
    "clarity.ms",
)
_ANY_EMAIL = re.compile(r"[\w.%+\-]+@[\w\-]+\.[\w.\-]+")
_PHONE_LIKE = re.compile(r"\+?\d[\d\s().\-]{7,}\d")
_EXTERNAL = re.compile(r"^(https?:)?//", re.I)


@pytest.fixture
def site_dir(project_root: Path) -> Path:
    return project_root / "asesoria"


@pytest.fixture
def html(site_dir: Path) -> str:
    return (site_dir / "index.html").read_text(encoding="utf-8")


@pytest.fixture
def soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


@pytest.fixture
def css(site_dir: Path) -> str:
    return (site_dir / "styles.css").read_text(encoding="utf-8")


def test_page_is_spanish(soup: BeautifulSoup) -> None:
    root = soup.find("html")
    assert root is not None
    assert root.get("lang") == "es"


def test_headings_start_at_one_h1(soup: BeautifulSoup) -> None:
    assert len(soup.find_all("h1")) == 1
    assert soup.find_all("h2"), "sections need their own headings"


def test_no_scripts_at_all(soup: BeautifulSoup) -> None:
    """Plain HTML: nothing runs in the visitor's browser, so nothing can track."""
    assert soup.find_all("script") == []


@pytest.mark.parametrize("marker", _TRACKING_MARKERS)
def test_no_tracking_markers(html: str, css: str, marker: str) -> None:
    assert marker not in html.casefold()
    assert marker not in css.casefold()


def test_no_external_assets(soup: BeautifulSoup, css: str) -> None:
    """No fonts, CDNs or pixels: a visit reaches nobody but GitHub Pages."""
    for tag, attr in (("link", "href"), ("img", "src"), ("iframe", "src"), ("source", "src")):
        for node in soup.find_all(tag):
            if tag == "link" and "stylesheet" not in (node.get("rel") or []):
                continue
            assert not _EXTERNAL.match(str(node.get(attr, ""))), f"external <{tag}>"
    assert "@import" not in css
    for target in re.findall(r"url\(\s*['\"]?([^'\")]+)", css):
        assert not _EXTERNAL.match(target), f"external url() in CSS: {target}"


def test_no_contact_data_besides_linkedin(html: str, css: str) -> None:
    for name, text in (("asesoria/index.html", html), ("asesoria/styles.css", css)):
        assert pii_guard.scan_text(text, name) == []
        assert not _ANY_EMAIL.search(text), "contact is LinkedIn only"
        assert not _PHONE_LIKE.search(text), "contact is LinkedIn only"
    assert "mailto:" not in html
    assert "tel:" not in html


def test_links_to_linkedin_and_the_repo(soup: BeautifulSoup) -> None:
    hrefs = {str(a.get("href", "")).rstrip("/") for a in soup.find_all("a")}
    assert LINKEDIN in hrefs
    assert REPO in hrefs


def test_external_links_do_not_leak_the_referrer(soup: BeautifulSoup) -> None:
    for a in soup.find_all("a"):
        if _EXTERNAL.match(str(a.get("href", ""))):
            rel = a.get("rel") or []
            assert "noopener" in rel and "noreferrer" in rel, a.get("href")


def test_local_stylesheet_resolves(soup: BeautifulSoup, site_dir: Path) -> None:
    sheets = [
        str(link.get("href"))
        for link in soup.find_all("link")
        if "stylesheet" in (link.get("rel") or [])
    ]
    assert sheets, "the page must reference its stylesheet"
    for href in sheets:
        assert (site_dir / href).is_file(), href


def test_no_prices_and_no_promised_outcomes(soup: BeautifulSoup) -> None:
    text = soup.get_text(" ").casefold()
    assert not re.search(r"[$€]\s*\d|\d\s*(clp|usd|uf)\b", text), "fee is agreed, never listed"
    for promise in ("garantiza", "aseguramos", "consigue trabajo"):
        assert promise not in text


def test_pages_has_one_workflow_that_ships_the_page(project_root: Path) -> None:
    """A repo has one Pages site: two deploying workflows overwrite each other."""
    workflows = project_root / ".github" / "workflows"
    deployers = [p.name for p in workflows.glob("*.yml") if "deploy-pages" in p.read_text()]
    assert deployers == ["pages.yml"]

    pages = (workflows / "pages.yml").read_text(encoding="utf-8")
    assert "asesoria/**" in pages, "editing the page must redeploy it"
    assert "site/asesoria" in pages, "the page must land inside the published artefact"


def test_pages_pins_setup_uv_to_a_published_tag(project_root: Path) -> None:
    """setup-uv publishes no floating major tag (``@v10`` does not resolve)."""
    pages = (project_root / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    pins = re.findall(r"astral-sh/setup-uv@(\S+)", pages)
    assert pins
    for pin in pins:
        assert re.fullmatch(r"v\d+\.\d+\.\d+", pin), pin
