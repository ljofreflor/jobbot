"""LinkedIn recruiter-post job source (MVP: posts → ATS URL)."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from jobbot.adapters.linkedin.sweep import (
    is_data_relevant,
    parse_post_blob,
    parse_posts_fixture,
    post_to_job,
)
from jobbot.browser.session import BrowserSession
from jobbot.config import JobbotConfig, load_config
from jobbot.jobs.sources import JobSearchQuery
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind
from jobbot.portals.redirect import expand_urls

logger = logging.getLogger("jobbot.linkedin.sweep")


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

    def search_from_fixture(self, path: Path, *, query: str | None = None) -> list[JobPosting]:
        text = path.read_text(encoding="utf-8")
        posts = parse_posts_fixture(text)
        jobs: list[JobPosting] = []
        q = (query or "").casefold()
        for post in posts:
            if not is_data_relevant(post.text):
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
        jobs: list[JobPosting] = []
        with BrowserSession(
            profile_dir=self.profile_dir,
            headless=False,
            slow_mo=100,
            cdp_url=self.cdp_url,
            debug_root=self.config.output_dir / "debug",
        ) as browser:
            page = browser.page
            page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
            if "login" in page.url.lower() or "authwall" in page.url.lower():
                browser.pause_for_manual(
                    "Log in to LinkedIn, run the content search if needed, "
                    "then continue so JobBot can read visible posts."
                )
            browser.pause_for_manual(
                "Scroll the LinkedIn content results so relevant hiring posts are visible, "
                "then continue."
            )
            cards = page.locator("div.feed-shared-update-v2")
            if cards.count() == 0:
                cards = page.locator(
                    "div.update-components-text, div.feed-shared-text, span.break-words"
                )
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
                q = query.query.casefold()
                if q not in text.casefold() and (
                    "hiring" not in text.casefold()
                    and "buscamos" not in text.casefold()
                    and "postula" not in text.casefold()
                    and "vacante" not in text.casefold()
                ):
                    continue
                hrefs = expand_urls(_hrefs_from_locator(card, base_url=page.url))
                unresolved = [h for h in hrefs if "lnkd.in" in h or "linkedin.com" in h]
                if unresolved:
                    hrefs = expand_urls(hrefs + _click_resolve_hrefs(card, unresolved))
                blob = text if not hrefs else text + "\n" + "\n".join(hrefs)
                post = parse_post_blob(blob)
                jobs.append(post_to_job(post))
        return jobs

    def get_job(self, job_id: str) -> JobPosting:
        msg = "LinkedInPostJobSource.get_job is not supported; use JobRepository"
        raise NotImplementedError(msg)


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
