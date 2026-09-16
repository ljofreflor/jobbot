"""LinkedIn post sweep parsing tests."""

from pathlib import Path

from jobbot.adapters.linkedin.posts_source import LinkedInPostJobSource
from jobbot.adapters.linkedin.sweep import is_data_relevant, parse_posts_fixture, post_to_job
from jobbot.portals.detect import AtsKind


def test_parse_posts_fixture_filters_and_detects_ats(project_root: Path) -> None:
    text = (project_root / "tests/fixtures/linkedin_posts.txt").read_text(encoding="utf-8")
    posts = parse_posts_fixture(text)
    assert len(posts) == 7
    relevant = [p for p in posts if is_data_relevant(p.text)]
    assert len(relevant) == 6  # hiking post excluded
    greenhouse = next(p for p in relevant if p.ats_kind == AtsKind.GREENHOUSE)
    assert greenhouse.ats_url and "greenhouse" in greenhouse.ats_url
    gob = next(p for p in relevant if p.ats_kind == AtsKind.GETONBOARD)
    assert gob.ats_url and "getonbrd.com" in gob.ats_url
    email = next(p for p in relevant if p.ats_kind == AtsKind.EMAIL)
    assert email.ats_url == "mailto:seleccion@empresa.cl"
    job = post_to_job(greenhouse, job_id="J0001")
    assert job.source == "linkedin_post"
    assert job.ats_kind == "greenhouse"
    assert "Data Scientist" in job.title or "data scientist" in job.title.casefold()


def test_parse_post_expands_short_links(monkeypatch: object) -> None:
    from jobbot.adapters.linkedin.sweep import parse_post_blob

    def fake_expand(urls: list[str]) -> list[str]:
        return urls + ["https://boards.greenhouse.io/acme/jobs/99"]

    import jobbot.adapters.linkedin.sweep as sweep_mod

    monkeypatch.setattr(sweep_mod, "expand_urls", fake_expand)
    post = parse_post_blob(
        "Hiring DS! Apply: https://lnkd.in/short\n",
    )
    assert post.ats_kind.value == "greenhouse"
    assert post.ats_url and "greenhouse" in post.ats_url


def test_source_from_fixture(project_root: Path, tmp_path: Path) -> None:
    from jobbot.config import JobbotConfig, PathsConfig

    config = JobbotConfig(paths=PathsConfig(output=tmp_path / "out"), root=project_root)
    source = LinkedInPostJobSource(config)
    jobs = source.search_from_fixture(
        project_root / "tests/fixtures/linkedin_posts.txt",
        query="data scientist",
    )
    assert len(jobs) >= 2
    kinds = {j.ats_kind for j in jobs}
    assert "greenhouse" in kinds
    assert "lever" in kinds


class _FakeButtons:
    def __init__(self, count: int, fail_on: set[int] | None = None) -> None:
        self._count = count
        self._fail_on = fail_on or set()
        self.clicked: list[int] = []

    def count(self) -> int:
        return self._count

    def nth(self, index: int) -> "_FakeButtons":
        self._index = index
        return self

    def click(self, **_: object) -> None:
        if self._index in self._fail_on:
            msg = "not clickable"
            raise TimeoutError(msg)
        self.clicked.append(self._index)


class _FakeFeedPage:
    def __init__(self, see_more: int = 0, fail_on: set[int] | None = None) -> None:
        self.scripts: list[str] = []
        self.waits: list[int] = []
        self.buttons = _FakeButtons(see_more, fail_on)

    def evaluate(self, script: str) -> None:
        self.scripts.append(script)

    def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(ms)

    def locator(self, _selector: str) -> _FakeButtons:
        return self.buttons


def test_autoscroll_feed_scrolls_and_waits() -> None:
    """Agent runs have no human to scroll; lazy posts must load anyway."""
    from jobbot.adapters.linkedin.posts_source import autoscroll_feed

    page = _FakeFeedPage()
    autoscroll_feed(page, rounds=4, pause_ms=500)

    assert len(page.scripts) == 4
    assert all("scrollBy" in script for script in page.scripts)
    assert page.waits == [500, 500, 500, 500]


def test_expand_truncated_posts_clicks_see_more() -> None:
    """The apply email often lives behind LinkedIn's '…see more' toggle."""
    from jobbot.adapters.linkedin.posts_source import expand_truncated_posts

    page = _FakeFeedPage(see_more=3)
    assert expand_truncated_posts(page) == 3
    assert page.buttons.clicked == [0, 1, 2]


def test_expand_truncated_posts_survives_unclickable_toggle() -> None:
    from jobbot.adapters.linkedin.posts_source import expand_truncated_posts

    page = _FakeFeedPage(see_more=3, fail_on={1})
    assert expand_truncated_posts(page) == 2
    assert page.buttons.clicked == [0, 2]


class _FakeCards:
    """Cards for one selector: text plus anchor hrefs."""

    def __init__(self, cards: list[tuple[str, list[str]]]) -> None:
        self._cards = cards

    def count(self) -> int:
        return len(self._cards)

    def nth(self, index: int) -> "_FakeCard":
        text, hrefs = self._cards[index]
        return _FakeCard(text, hrefs)


class _FakeCard:
    def __init__(self, text: str, hrefs: list[str]) -> None:
        self._text = text
        self._hrefs = hrefs

    def inner_text(self, **_: object) -> str:
        return self._text

    def locator(self, _selector: str) -> "_FakeAnchors":
        return _FakeAnchors(self._hrefs)


class _FakeAnchors:
    def __init__(self, hrefs: list[str]) -> None:
        self._hrefs = hrefs

    def count(self) -> int:
        return len(self._hrefs)

    def nth(self, index: int) -> "_FakeAnchor":
        return _FakeAnchor(self._hrefs[index])


class _FakeAnchor:
    def __init__(self, href: str) -> None:
        self._href = href

    def get_attribute(self, _name: str) -> str:
        return self._href


class _FakeSearchPage:
    """Only the modern componentkey cards exist, like LinkedIn today."""

    def __init__(self, cards: list[tuple[str, list[str]]], *, selector: str) -> None:
        self._cards = cards
        self._selector = selector
        self.url = "https://www.linkedin.com/search/results/content/?keywords=enviar+CV"
        self.queried: list[str] = []

    def locator(self, selector: str) -> _FakeCards:
        self.queried.append(selector)
        return _FakeCards(self._cards if selector == self._selector else [])


_MODERN_POST = (
    "Publicación en el feed\nDiego Recruiter\nExpert Analyst @ NTT Data\n"
    "Buscamos Data Scientist con Python y SQL para proyecto de analytics.\n"
    "Interesados enviar CV a seleccion@nttdata.com"
)


def test_collect_jobs_reads_modern_componentkey_cards() -> None:
    """Regression: LinkedIn dropped div.feed-shared-update-v2 for componentkey cards."""
    from jobbot.adapters.linkedin.posts_source import (
        MODERN_POST_CARD,
        collect_jobs_from_feed_page,
    )
    from jobbot.jobs.sources import JobSearchQuery

    permalink = "https://www.linkedin.com/feed/update/urn:li:share:7438557958579417088/"
    page = _FakeSearchPage(
        [(_MODERN_POST, ["https://www.linkedin.com/in/diego/", permalink])],
        selector=MODERN_POST_CARD,
    )
    jobs = collect_jobs_from_feed_page(
        page,
        JobSearchQuery(query="enviar CV", limit=10),
        resolve_short_links=False,
    )

    assert len(jobs) == 1
    assert jobs[0].ats_kind == "email"
    assert jobs[0].ats_url == "mailto:seleccion@nttdata.com"
    assert jobs[0].url == permalink


def test_parse_post_blob_uses_mailto_anchor_when_text_has_no_email() -> None:
    """Recruiters often hide the address behind a 'escríbeme' mailto link."""
    from jobbot.adapters.linkedin.sweep import parse_post_blob

    post = parse_post_blob(
        "Buscamos Data Scientist para analytics. Postulaciones por correo.",
        mailto_urls=["mailto:irina@bcp.com.pe"],
    )
    assert post.ats_kind == AtsKind.EMAIL
    assert post.ats_url == "mailto:irina@bcp.com.pe"


def test_first_post_permalink_ignores_profiles_and_hashtags() -> None:
    from jobbot.adapters.linkedin.posts_source import first_post_permalink

    hrefs = [
        "https://www.linkedin.com/in/someone/",
        "https://www.linkedin.com/search/results/all/?keywords=%23hiring",
        "https://www.linkedin.com/feed/update/urn:li:activity:7438557958579417088/",
    ]
    assert first_post_permalink(hrefs) == hrefs[-1]
    assert first_post_permalink(hrefs[:2]) is None


_FEED_CARD_TEXT = """Publicación en el feed
Diego Carreño M.
Expert Analyst @ NTT Data
• 1er
10 meses • Editado •
Buscamos Data Scientist Senior para Airport Operations.
• Python y SQL
• Inferencia causal
Interesados enviar CV a seleccion@nttdata.com"""


def test_strip_feed_chrome_takes_author_and_drops_ui_lines() -> None:
    """Regression: company came out as 'el feed' from LinkedIn's own header."""
    from jobbot.adapters.linkedin.sweep import strip_feed_chrome

    author, body = strip_feed_chrome(_FEED_CARD_TEXT)

    assert author == "Diego Carreño M."
    assert "Publicación en el feed" not in body
    assert "• 1er" not in body
    assert "10 meses" not in body
    # Real bullet content from the post body must survive.
    assert "• Python y SQL" in body
    assert "• Inferencia causal" in body


def test_post_to_job_company_is_the_author_not_the_feed() -> None:
    from jobbot.adapters.linkedin.sweep import parse_post_blob

    job = post_to_job(parse_post_blob(_FEED_CARD_TEXT), job_id="J0042")

    assert job.company == "Diego Carreño M."
    assert "el feed" not in job.company
    assert job.ats_url == "mailto:seleccion@nttdata.com"


def test_strip_feed_chrome_leaves_fixture_posts_untouched() -> None:
    from jobbot.adapters.linkedin.sweep import strip_feed_chrome

    text = "We're hiring a Data Scientist.\nApply: https://boards.greenhouse.io/x/1"
    author, body = strip_feed_chrome(text)
    assert author is None
    assert body == text


def test_permalink_falls_back_to_urn_in_card_html() -> None:
    """Most search cards hide the permalink; the urn is still in their HTML."""
    from jobbot.adapters.linkedin.posts_source import permalink_from_html

    html = '<div data-x="urn:li:activity:7438557958579417088"><p>hiring</p></div>'
    assert (
        permalink_from_html(html)
        == "https://www.linkedin.com/feed/update/urn:li:activity:7438557958579417088/"
    )
    assert permalink_from_html("<div>no urn here</div>") is None


class _FakeWaitPage:
    def __init__(self, *, raises: bool = False) -> None:
        self._raises = raises
        self.waited: list[str] = []

    def wait_for_selector(self, selector: str, **_: object) -> None:
        if self._raises:
            msg = "timeout"
            raise TimeoutError(msg)
        self.waited.append(selector)


def test_wait_for_post_cards_waits_before_scrolling() -> None:
    """Regression: sweep scrolled an empty page and reported 'no relevant posts'."""
    from jobbot.adapters.linkedin.posts_source import (
        MODERN_POST_CARD,
        wait_for_post_cards,
    )

    page = _FakeWaitPage()
    assert wait_for_post_cards(page, timeout_ms=1000) is True
    assert MODERN_POST_CARD in page.waited[0]


def test_wait_for_post_cards_returns_false_on_timeout() -> None:
    from jobbot.adapters.linkedin.posts_source import wait_for_post_cards

    assert wait_for_post_cards(_FakeWaitPage(raises=True), timeout_ms=10) is False


def test_collect_jobs_drops_posts_outside_the_wanted_country() -> None:
    """Setting the country keeps CDMX adverts out of a Chile-only search."""
    from jobbot.adapters.linkedin.posts_source import (
        MODERN_POST_CARD,
        collect_jobs_from_feed_page,
    )
    from jobbot.jobs.sources import JobSearchQuery

    mexico = (
        "Publicación en el feed\nZayd Recruiter\n"
        "Vacantes exclusivas en TI para CDMX. Data Scientist con Python y SQL.\n"
        "Enviar CV a seleccion@empresa.mx"
    )
    chile = (
        "Publicación en el feed\nAna Recruiter\n"
        "Buscamos Data Scientist en Santiago, Chile. Python y SQL.\n"
        "Enviar CV a seleccion@empresa.cl"
    )
    page = _FakeSearchPage([(mexico, []), (chile, [])], selector=MODERN_POST_CARD)
    jobs = collect_jobs_from_feed_page(
        page,
        JobSearchQuery(query="enviar CV", limit=10, countries=("CL",)),
        resolve_short_links=False,
    )

    assert [j.ats_url for j in jobs] == ["mailto:seleccion@empresa.cl"]


def test_collect_jobs_without_country_preference_keeps_both() -> None:
    from jobbot.adapters.linkedin.posts_source import (
        MODERN_POST_CARD,
        collect_jobs_from_feed_page,
    )
    from jobbot.jobs.sources import JobSearchQuery

    mexico = (
        "Publicación en el feed\nZayd Recruiter\n"
        "Data Scientist para CDMX con Python.\nEnviar CV a seleccion@empresa.mx"
    )
    page = _FakeSearchPage([(mexico, [])], selector=MODERN_POST_CARD)
    jobs = collect_jobs_from_feed_page(
        page, JobSearchQuery(query="enviar CV", limit=10), resolve_short_links=False
    )
    assert len(jobs) == 1
