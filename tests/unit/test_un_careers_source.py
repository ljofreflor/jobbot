"""UN Careers public feed: parsing, New York deadlines, home-based, robots, detail (#233)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from jobbot.adapters.un_careers.feed import (
    FEED_URL,
    UnCareersClient,
    UnCareersError,
    UnCareersShapeChanged,
    job_from_item,
    job_id_from_url,
    parse_feed,
    parse_meta,
    parse_stamp,
    with_detail,
)
from jobbot.adapters.un_careers.jobs import UnCareersDiscover, UnCareersJobSource
from jobbot.jobs.discover import JobFilters, SiteStatus, SiteTarget
from jobbot.jobs.sources import JobSearchQuery
from jobbot.models.job import JobPosting
from tests.fixtures.un_careers_http import FakeUnCareers, fixture_text, install
from tests.fixtures.workday_http import forbid_sockets

NEW_YORK = ZoneInfo("America/New_York")
TARGET = SiteTarget(url=FEED_URL)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_sockets(monkeypatch)


def _jobs() -> dict[str, JobPosting]:
    return {i.job_id: job_from_item(i) for i in parse_feed(fixture_text("jobfeed.xml"))}


def _discover(monkeypatch: pytest.MonkeyPatch, fake: FakeUnCareers) -> UnCareersDiscover:
    install(monkeypatch, fake)
    return UnCareersDiscover()


def test_feed_item_maps_title_entity_station_level_and_url() -> None:
    job = _jobs()["286122"]

    assert job.title == "Arabic editor individual contractor"
    assert job.company == "United Nations Environment Programme"
    assert job.location == "GENEVA"
    assert job.seniority == "CON"
    assert job.employment_type == "consultancy"
    assert job.source == "un_careers"
    assert job.source_job_id == "286122"
    assert job.url == "https://careers.un.org/jobSearchDescription/286122?language=en"
    assert job.ats_url == job.url
    assert "Job Family: Language" in job.description


def test_deadline_is_new_york_time_with_zone() -> None:
    job = _jobs()["286122"]

    assert job.closes_at == datetime(2026, 10, 20, 23, 59, 59, tzinfo=NEW_YORK)
    assert job.closes_at.astimezone(UTC) == datetime(2026, 10, 21, 3, 59, 59, tzinfo=UTC)
    assert job.closes_on == date(2026, 10, 20)
    assert job.closes_text == "Deadline: 10/20/2026 23:59:59 PM (New York time)"
    assert job.posted_at == datetime(2026, 10, 9, 0, 0, tzinfo=NEW_YORK)


def test_source_job_id_comes_from_the_guid() -> None:
    assert job_id_from_url("https://careers.un.org/jobSearchDescription/286047?language=en") == (
        "286047"
    )
    assert job_id_from_url("https://example.org/jobSearchDescription/286047") is None
    assert job_id_from_url("https://careers.un.org/") is None


def test_entity_is_the_first_segment_of_the_office() -> None:
    jobs = _jobs()

    assert jobs["285531"].company == "UNRWA"
    assert "UNRWA - Programme Relief & Social Services" in jobs["285531"].description


def test_home_based_is_remote_but_remote_sensing_is_not() -> None:
    jobs = _jobs()

    assert jobs["900001"].remote_type == "remote"
    assert jobs["900001"].location == "HOME BASED"
    assert jobs["285646"].title == "IMEO Remote Sensing Data Engineer"
    assert jobs["285646"].remote_type is None


def test_grades_map_to_employment_type() -> None:
    jobs = _jobs()

    assert (jobs["285569"].seniority, jobs["285569"].employment_type) == ("I-1", "internship")
    assert (jobs["283445"].seniority, jobs["283445"].employment_type) == ("NO-B", "staff")
    assert (jobs["285431"].seniority, jobs["285431"].employment_type) == ("P-3", "staff")
    assert (jobs["283080"].seniority, jobs["283080"].employment_type) == (None, None)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10/20/2026 23:59:59 PM (New York time)", datetime(2026, 10, 20, 23, 59, 59)),
        ("10/20/2026 11:59:59 PM (New York time)", datetime(2026, 10, 20, 23, 59, 59)),
        ("10/20/2026 12:00:00 AM (New York time)", datetime(2026, 10, 20, 0, 0, 0)),
        ("10/20/2026 09:30 (New York time)", datetime(2026, 10, 20, 9, 30, 0)),
    ],
)
def test_stamp_reads_24h_with_a_redundant_meridiem_and_true_12h(
    raw: str, expected: datetime
) -> None:
    parsed = parse_stamp(raw)

    assert parsed is not None
    assert parsed[1] == expected.replace(tzinfo=NEW_YORK)


def test_stamp_without_a_known_zone_keeps_only_the_date() -> None:
    assert parse_stamp("10/20/2026 23:59:59 PM (Central Time)") == (date(2026, 10, 20), None)
    assert parse_stamp("10/20/2026 23:59:59") == (date(2026, 10, 20), None)
    assert parse_stamp("13/40/2026 10:00:00 AM") is None
    assert parse_stamp("soon") is None


def test_query_matches_every_word_in_title_family_network_or_office() -> None:
    items = parse_feed(fixture_text("jobfeed.xml"))

    def ids(query: str) -> list[str]:
        return [i.job_id for i in items if i.matches(query)]

    assert ids("public health") == ["900001"]
    assert ids("HEALTH") == ["285431", "283080", "900001"]
    assert ids("humanitarian affairs") == ["285531", "900001"]
    assert ids("comisión económica") == []
    assert len(ids("")) == len(items)


def test_meta_tolerates_spacing_and_values_with_colons() -> None:
    meta = parse_meta("Level :  <br>Job ID : 1 <br/> Department/Office : A: B <br>")

    assert meta == {"Level": "", "Job ID": "1", "Department/Office": "A: B"}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (fixture_text("jobfeed_broken.xml"), "no <rss><channel>"),
        ("<html><body>maintenance", "not XML"),
        (
            "<rss><channel><item><title>X</title><description>Level : P-3</description>"
            "</item></channel></rss>",
            "no Job ID",
        ),
        (
            "<rss><channel><item><title>X</title><guid>https://careers.un.org/"
            "jobSearchDescription/1</guid><description>Level : P-3</description>"
            "</item></channel></rss>",
            "lack Duty Station/Deadline",
        ),
    ],
)
def test_a_feed_that_changed_shape_says_what_is_missing(text: str, message: str) -> None:
    with pytest.raises(UnCareersShapeChanged, match=message):
        parse_feed(text)


def test_an_empty_channel_is_no_postings() -> None:
    assert parse_feed(fixture_text("jobfeed_empty.xml")) == []


def test_html_robots_means_no_rules_and_the_feed_is_read_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeUnCareers()
    discover = _discover(monkeypatch, fake)

    first = discover.discover_site(TARGET, query="health", limit=50, details=False)
    second = discover.discover_site(TARGET, query="consultant", limit=50, details=False)

    assert first.status is SiteStatus.OK and len(first.jobs) == 3
    assert second.status is SiteStatus.OK
    assert fake.paths() == ["/robots.txt", "/jobfeed"]
    agent = fake.calls[1].headers["user-agent"]
    assert agent.startswith("jobbot/") and "github.com/ljofreflor/jobbot" in agent
    assert "3 de 3 coincidencias; feed: 8 avisos" in first.detail


def test_plain_text_robots_disallow_is_obeyed_before_any_feed_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeUnCareers(robots=fixture_text("robots_disallow.txt"), robots_type="text/plain")
    outcome = _discover(monkeypatch, fake).discover_site(TARGET, query="x", limit=5, details=False)

    assert outcome.status is SiteStatus.ROBOTS
    assert "/jobfeed" in outcome.detail
    assert fake.paths() == ["/robots.txt"]


@pytest.mark.parametrize(
    ("fake", "status", "detail"),
    [
        (FakeUnCareers(robots_status=503), SiteStatus.FAILED, "refused robots.txt"),
        (FakeUnCareers(feed_status=500), SiteStatus.FAILED, "HTTP 500"),
        (FakeUnCareers(feed=fixture_text("jobfeed_broken.xml")), SiteStatus.CHANGED, "channel"),
        (FakeUnCareers(feed=fixture_text("jobfeed_empty.xml")), SiteStatus.EMPTY, "feed: 0"),
    ],
)
def test_failures_are_reported_as_outcomes(
    monkeypatch: pytest.MonkeyPatch, fake: FakeUnCareers, status: SiteStatus, detail: str
) -> None:
    outcome = _discover(monkeypatch, fake).discover_site(TARGET, query="x", limit=5, details=False)

    assert outcome.status is status
    assert detail in outcome.detail


def test_network_error_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    import jobbot.adapters.un_careers.feed as feed

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    transport = httpx.MockTransport(broken)

    def client(**kw: object) -> httpx.Client:
        return httpx.Client(**{**kw, "transport": transport})  # type: ignore[arg-type]

    monkeypatch.setattr(feed, "_client", client)
    monkeypatch.setattr(feed, "pause", lambda _s: None)

    outcome = UnCareersDiscover().discover_site(TARGET, query="x", limit=5, details=False)

    assert outcome.status is SiteStatus.FAILED
    assert "refused robots.txt" in outcome.detail


def test_requests_to_the_host_are_spaced_one_second_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, FakeUnCareers())
    waits: list[float] = []
    client = UnCareersClient(sleep=waits.append, clock=lambda: 100.0)

    client.feed()

    assert waits == [1.0]


def test_filters_apply_before_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    discover = _discover(monkeypatch, FakeUnCareers())

    santiago = discover.discover_site(
        TARGET, query="", limit=1, details=False, filters=JobFilters(location="Santiago")
    )
    graded = discover.discover_site(
        TARGET, query="", limit=50, details=False, filters=JobFilters(levels=("con", "P-3"))
    )

    assert [j.source_job_id for j in santiago.jobs] == ["285569"]
    assert "7 fuera de --location/--level" in santiago.detail
    assert sorted(j.source_job_id or "" for j in graded.jobs) == [
        "285431",
        "285531",
        "285646",
        "286122",
        "900001",
    ]


def test_remote_location_filter_keeps_home_based() -> None:
    jobs = _jobs()
    remote = JobFilters(location="home-based")

    assert remote.keeps(jobs["900001"])
    assert JobFilters(location="remote").keeps(jobs["900001"])
    assert not remote.keeps(jobs["285646"])
    assert not JobFilters().active


def test_detail_adds_the_posting_text_and_agrees_on_the_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeUnCareers(details={"285431": (200, fixture_text("detail_285431.json"))})
    outcome = _discover(monkeypatch, fake).discover_site(
        TARGET, query="mental health", limit=5, details=True
    )

    [job] = outcome.jobs
    assert fake.detail_calls == ["/api/public/opening/jo/285431/en"]
    assert "Org. Setting and Reporting" in job.description
    assert "<div" in job.raw_description
    assert job.closes_at == datetime(2026, 10, 9, 23, 59, 59, tzinfo=NEW_YORK)
    assert job.note is None


def test_a_detail_that_disagrees_wins_and_says_so() -> None:
    job = _jobs()["285431"]
    data = json.loads(fixture_text("detail_285431.json"))["data"]
    data["endDate"] = "2026-10-12T03:59:59.000Z"

    full = with_detail(job, data)

    assert full.closes_at is not None
    assert full.closes_at.astimezone(UTC) == datetime(2026, 10, 12, 3, 59, 59, tzinfo=UTC)
    assert full.closes_on == date(2026, 10, 11)
    assert full.note is not None and "se usa el detalle" in full.note
    assert full.closes_text is not None and "endDate" in full.closes_text


def test_detail_fills_closing_and_posting_when_the_feed_had_none() -> None:
    job = _jobs()["285431"].model_copy(update={"closes_at": None, "posted_at": None})
    data = json.loads(fixture_text("detail_285431.json"))["data"]

    full = with_detail(job, data)

    assert full.closes_at == datetime(2026, 10, 10, 3, 59, 59, tzinfo=UTC)
    assert full.posted_at == datetime(2026, 9, 25, 4, 0, tzinfo=UTC)
    assert full.note is None


@pytest.mark.parametrize(
    ("answer", "note"),
    [
        ((500, "{}"), "detalle 285431: HTTP 500"),
        ((200, "<html>"), "answer is not JSON"),
        ((200, json.dumps({"data": {"jobTitle": ""}})), "lacks data.jobTitle"),
    ],
)
def test_a_failing_detail_keeps_the_feed_row(
    monkeypatch: pytest.MonkeyPatch, answer: tuple[int, str], note: str
) -> None:
    fake = FakeUnCareers(details={"285431": answer})
    outcome = _discover(monkeypatch, fake).discover_site(
        TARGET, query="mental health", limit=5, details=True
    )

    assert outcome.status is SiteStatus.OK
    assert outcome.jobs[0].closes_at is not None
    assert note in outcome.detail


def test_site_target_accepts_only_careers_un_org() -> None:
    discover = UnCareersDiscover()

    assert discover.site_target("careers.un.org").url == FEED_URL
    assert discover.site_target("https://careers.un.org/jobfeed").url == FEED_URL
    with pytest.raises(ValueError, match="one public feed"):
        discover.site_target("https://jobs.unicef.org/en-us/listing/")


def test_job_source_search_and_get_by_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from jobbot.config import JobbotConfig
    from jobbot.jobs.sources import get_job_source

    fake = install(
        monkeypatch, FakeUnCareers(details={"285431": (200, fixture_text("detail_285431.json"))})
    )
    source = get_job_source("un_careers", JobbotConfig())
    assert isinstance(source, UnCareersJobSource)

    found = source.search_jobs(JobSearchQuery(query="", location="Santiago"))
    one = source.get_job("https://careers.un.org/jobSearchDescription/285431?language=en")

    assert [j.source_job_id for j in found] == ["285569"]
    assert "Org. Setting and Reporting" in one.description
    assert fake.paths().count("/jobfeed") == 1
    with pytest.raises(ValueError):
        source.get_job("J0001")
    with pytest.raises(UnCareersError, match="not in the UN Careers feed"):
        source.get_job("https://careers.un.org/jobSearchDescription/1?language=en")


def test_job_source_search_raises_when_the_feed_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeUnCareers(feed_status=503))

    with pytest.raises(UnCareersError, match="HTTP 503"):
        UnCareersJobSource().search_jobs(JobSearchQuery(query="x"))


def test_careers_un_org_is_a_board_so_no_entity_claims_it_as_its_portal() -> None:
    from jobbot.portals.detect import JOB_BOARD_KINDS, AtsKind, detect_ats

    job = _jobs()["285569"]

    assert detect_ats(job.url or "") is AtsKind.UN_CAREERS
    assert AtsKind.UN_CAREERS in JOB_BOARD_KINDS
    assert job.ats_kind == "un_careers"
