"""LinkedIn recruiter-post job source (MVP: posts → ATS URL / email)."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin

from jobbot.adapters.linkedin.sweep import (
    is_data_relevant,
    parse_post_blob,
    parse_posts_fixture,
    post_to_job,
)
from jobbot.browser.session import BrowserSession
from jobbot.config import JobbotConfig, load_config
from jobbot.jobs.geo import country_allows
from jobbot.jobs.sources import JobSearchQuery
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind
from jobbot.portals.redirect import expand_urls

logger = logging.getLogger("jobbot.linkedin.sweep")

# LinkedIn 2026 search results: hashed class names, stable `componentkey` hook.
MODERN_POST_CARD = 'div[componentkey^="update-card-focus"]'
LEGACY_POST_CARD = "div.feed-shared-update-v2"
TEXT_ONLY_CARD = "div.update-components-text, div.feed-shared-text, span.break-words"

SEE_MORE_TOGGLE = (
    "button.feed-shared-inline-show-more-text__see-more-less-toggle, "
    'button[aria-label*="see more"], '
    'button[aria-label*="ver más"], '
    'button:has-text("… más"), '
    'button:has-text("…more"), '
    'button:has-text("see more")'
)

_PERMALINK_RE = re.compile(r"linkedin\.com/(?:feed/update|posts)/", re.IGNORECASE)
_URN_RE = re.compile(r"urn:li:(?:activity|share|ugcPost):\d+")
_PROFILE_RE = re.compile(r"linkedin\.com/in/[^/?#]+", re.IGNORECASE)


def permalink_from_html(html: str) -> str | None:
    """Search cards rarely link themselves, but their HTML still carries the urn."""
    match = _URN_RE.search(html or "")
    if match is None:
        return None
    return f"https://www.linkedin.com/feed/update/{match.group(0)}/"


def first_post_permalink(hrefs: Sequence[str]) -> str | None:
    """The post's own URL, ignoring author profiles and hashtag searches."""
    for href in hrefs:
        if _PERMALINK_RE.search(href):
            return href
    return None


def author_profile_url(hrefs: Sequence[str]) -> str | None:
    """
    Fallback when the card exposes no permalink.

    Modern LinkedIn cards carry no urn:li:activity, so the recruiter's profile is
    the only durable handle: it leaves the post one click away instead of nothing.
    """
    for href in hrefs:
        if _PROFILE_RE.search(href):
            return href
    return None


def wait_for_post_cards(page: Any, *, timeout_ms: int = 20_000) -> bool:
    """Search results render async; scrolling too early yields an empty sweep."""
    selector = f"{MODERN_POST_CARD}, {LEGACY_POST_CARD}"
    try:
        page.wait_for_selector(selector, timeout=timeout_ms)
    except Exception as exc:  # noqa: BLE001 — Playwright timeout types vary
        logger.warning("No post cards rendered within %dms: %s", timeout_ms, exc)
        return False
    return True


def autoscroll_feed(page: Any, *, rounds: int = 6, pause_ms: int = 800) -> None:
    """Load lazy feed posts without a human scrolling (read-only discovery)."""
    for _ in range(rounds):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        page.wait_for_timeout(pause_ms)


def expand_truncated_posts(page: Any, *, limit: int = 40) -> int:
    """Click '…see more' toggles: the apply email is often inside the hidden tail."""
    toggles = page.locator(SEE_MORE_TOGGLE)
    try:
        total = min(int(toggles.count()), limit)
    except Exception:  # noqa: BLE001 — locator may vanish mid-scroll
        return 0
    expanded = 0
    for i in range(total):
        try:
            toggles.nth(i).click(timeout=1500)
            expanded += 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("see-more toggle %d not clickable: %s", i, exc)
    return expanded


class LinkedInPostJobSource:
    """Discover jobs from LinkedIn recruiter posts (fixture or live HITL)."""

    def __init__(
        self,
        config: JobbotConfig | None = None,
        *,
        cdp_url: str | None = None,
    ) -> None:
        self.config = config or load_config()
        from jobbot.browser.cdp import resolve_cdp_url

        self.cdp_url = resolve_cdp_url(cdp_url)
        self.profile_dir = self.config.root / "browser-data" / "linkedin"

    def search_jobs(self, query: JobSearchQuery) -> list[JobPosting]:
        """Live LinkedIn content search for posts (HITL / CDP)."""
        return self.search_live(query)

    def search_from_fixture(
        self,
        path: Path,
        *,
        query: str | None = None,
        countries: Sequence[str] = (),
        allow_remote: bool = True,
    ) -> list[JobPosting]:
        text = path.read_text(encoding="utf-8")
        posts = parse_posts_fixture(text)
        jobs: list[JobPosting] = []
        q = (query or "").casefold()
        for post in posts:
            if not is_data_relevant(post.text):
                continue
            if not country_allows(post.text, wanted=countries, allow_remote=allow_remote):
                continue
            if (
                q
                and q not in post.text.casefold()
                and q not in (post.author or "").casefold()
                and post.ats_kind == AtsKind.UNKNOWN
            ):
                continue
            jobs.append(post_to_job(post))
        return jobs

    def search_live(self, query: JobSearchQuery) -> list[JobPosting]:
        """Open LinkedIn content search; user assists; scrape visible post texts."""
        search_url = (
            "https://www.linkedin.com/search/results/content/"
            f"?keywords={quote_plus(query.query)}&origin=GLOBAL_SEARCH_HEADER"
        )
        with BrowserSession(
            profile_dir=self.profile_dir,
            headless=False,
            slow_mo=100,
            cdp_url=self.cdp_url,
            debug_root=self.config.output_dir / "debug",
        ) as browser:
            # Attached to the user's own Chrome: do not take over a tab in use.
            page = browser.context.new_page() if self.cdp_url else browser.page
            page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
            if "login" in page.url.lower() or "authwall" in page.url.lower():
                browser.pause_for_manual(
                    "Log in to LinkedIn, run the content search if needed, "
                    "then continue so JobBot can read visible posts."
                )
            wait_for_post_cards(page)
            autoscroll_feed(page)
            wait_for_post_cards(page, timeout_ms=10_000)
            expanded = expand_truncated_posts(page)
            logger.info("Expanded %d truncated posts", expanded)
            browser.pause_for_manual(
                "Scroll further if you want more LinkedIn posts included, then continue "
                "(JobBot already auto-scrolled and expanded '…see more')."
            )
            autoscroll_feed(page, rounds=2)
            expand_truncated_posts(page)
            return collect_jobs_from_feed_page(page, query)

    def get_job(self, job_id: str) -> JobPosting:
        msg = "LinkedInPostJobSource.get_job is not supported; use JobRepository"
        raise NotImplementedError(msg)


def collect_jobs_from_feed_page(
    page: Any,
    query: JobSearchQuery,
    *,
    resolve_short_links: bool = True,
) -> list[JobPosting]:
    """
    Scrape visible LinkedIn-like feed cards from an already-open page.

    Same path used by live sweep after HITL scroll — suitable for game-condition
    browser tests with a local DOM fixture.
    """
    jobs: list[JobPosting] = []
    cards = page.locator(MODERN_POST_CARD)
    if cards.count() == 0:
        cards = page.locator(LEGACY_POST_CARD)
    if cards.count() == 0:
        cards = page.locator(TEXT_ONLY_CARD)
    seen: set[str] = set()
    limit = query.limit
    for i in range(min(cards.count(), 80)):
        if len(jobs) >= limit:
            break
        card = cards.nth(i)
        try:
            text = card.inner_text(timeout=1000).strip()
        except Exception:  # noqa: BLE001
            continue
        if len(text) < 40 or text in seen:
            continue
        seen.add(text)
        if not is_data_relevant(text):
            continue
        if not country_allows(
            text,
            wanted=query.countries,
            allow_remote=query.allow_remote,
        ):
            logger.info("Skipped post outside %s", ", ".join(query.countries))
            continue
        q = query.query.casefold()
        if q not in text.casefold() and (
            "hiring" not in text.casefold()
            and "buscamos" not in text.casefold()
            and "postula" not in text.casefold()
            and "vacante" not in text.casefold()
            and "enviar cv" not in text.casefold()
        ):
            continue
        raw_hrefs = _hrefs_from_locator(card, base_url=page.url)
        mailtos = _mailto_from_locator(card)
        permalink = first_post_permalink(raw_hrefs) or _permalink_from_card(card)
        post_url = permalink or author_profile_url(raw_hrefs)
        hrefs = expand_urls([h for h in raw_hrefs if h != permalink])
        if resolve_short_links:
            unresolved = [h for h in hrefs if "lnkd.in" in h or "linkedin.com" in h]
            if unresolved:
                hrefs = expand_urls(hrefs + _click_resolve_hrefs(card, unresolved))
        blob = text if not hrefs else text + "\n" + "\n".join(hrefs)
        post = parse_post_blob(blob, post_url=post_url, mailto_urls=mailtos)
        jobs.append(post_to_job(post))
    return jobs


def _permalink_from_card(card: Any) -> str | None:
    try:
        return permalink_from_html(card.inner_html(timeout=1000))
    except Exception:  # noqa: BLE001 — card may detach while scrolling
        return None


def _mailto_from_locator(card: object) -> list[str]:
    """Collect mailto: links: some posts only expose the address as a link."""
    out: list[str] = []
    try:
        anchors = card.locator('a[href^="mailto:"]')  # type: ignore[attr-defined]
        count = min(int(anchors.count()), 20)
    except Exception:  # noqa: BLE001
        return out
    for j in range(count):
        try:
            href = (anchors.nth(j).get_attribute("href") or "").strip()
        except Exception:  # noqa: BLE001
            continue
        if href and href not in out:
            out.append(href)
    return out


def _click_resolve_hrefs(card: object, hrefs: list[str]) -> list[str]:
    """Click short links in-card (HITL browser) and capture navigation targets."""
    resolved: list[str] = []
    try:
        anchors = card.locator("a[href]")  # type: ignore[attr-defined]
        count = min(int(anchors.count()), 50)
    except Exception:  # noqa: BLE001
        return resolved
    targets = set(hrefs)
    for j in range(count):
        try:
            anchor = anchors.nth(j)
            href = (anchor.get_attribute("href") or "").strip()
        except Exception:  # noqa: BLE001
            continue
        if href not in targets:
            continue
        try:
            with anchor.page.expect_navigation(timeout=8000):
                anchor.click(timeout=3000)
            final = anchor.page.url
            if final.startswith("http") and final not in resolved:
                resolved.append(final)
            anchor.page.go_back(timeout=8000)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Click-resolve failed for %s: %s", href, exc)
    return resolved


def _hrefs_from_locator(card: object, *, base_url: str) -> list[str]:
    """Collect absolute http(s) links from a post card (for ATS / board detection)."""
    out: list[str] = []
    seen: set[str] = set()
    try:
        anchors = card.locator("a[href]")  # type: ignore[attr-defined]
        count = min(int(anchors.count()), 50)
    except Exception:  # noqa: BLE001
        return out
    for j in range(count):
        try:
            href = anchors.nth(j).get_attribute("href") or ""
        except Exception:  # noqa: BLE001
            continue
        href = href.strip()
        if not href or href.startswith("#"):
            continue
        abs_url = urljoin(base_url, href)
        if not abs_url.startswith("http"):
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        out.append(abs_url)
    return out
