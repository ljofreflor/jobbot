"""Workday CXS client and mapping, offline against recorded fixtures (#225, #215)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from jobbot.adapters.workday.cxs import (
    USER_AGENT,
    CxsClient,
    WorkdayPostingClosed,
    WorkdayRef,
    WorkdayRefused,
    WorkdayRobotsDisallowed,
    WorkdayShapeChanged,
    WorkdaySite,
    fetch_workday_job,
    job_from_detail,
    job_from_search_item,
    parse_site_url,
    parse_workday_url,
    posted_on_date,
)
from tests.fixtures.workday_http import (
    API,
    OPEN_PATH,
    FakeWorkday,
    fixture_text,
    forbid_sockets,
    load_json,
    paged_search,
)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_sockets(monkeypatch)


def _client(fake: FakeWorkday) -> CxsClient:
    return CxsClient(runner=fake, sleep=lambda _s: None)


@pytest.mark.parametrize(
    ("url", "tenant", "site", "path"),
    [
        (
            "https://acme.wd3.myworkdayjobs.com/en-US/External/job/Remote/Analyst_R-0001",
            "acme",
            "External",
            "/job/Remote/Analyst_R-0001",
        ),
        (
            "https://acme.wd1.myworkdayjobs.com/External/job/Remote/Analyst_R-0001?source=x",
            "acme",
            "External",
            "/job/Remote/Analyst_R-0001",
        ),
        (
            "https://acme.wd103.myworkdayjobs.com/es/Careers/details/Analyst_R-0001",
            "acme",
            "Careers",
            "/job/Analyst_R-0001",
        ),
        (
            "https://paho.wd5.myworkdayjobs.com/pahocareers" + OPEN_PATH,
            "paho",
            "pahocareers",
            OPEN_PATH,
        ),
    ],
)
def test_parse_workday_url(url: str, tenant: str, site: str, path: str) -> None:
    ref = parse_workday_url(url)

    assert ref is not None
    assert (ref.site.tenant, ref.site.site, ref.external_path) == (tenant, site, path)
    assert ref.req_id == path.rsplit("_", 1)[1]
    assert "/en-US/" not in ref.url and "?" not in ref.url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.getonbrd.com/empleos/x",
        "https://acme.wd3.myworkdayjobs.com/en-US/External",
        "https://acme.wd3.myworkdayjobs.com/",
    ],
)
def test_non_posting_urls_are_not_postings(url: str) -> None:
    assert parse_workday_url(url) is None


def test_site_url_drops_locale_and_keeps_tenant() -> None:
    site = parse_site_url("https://paho.wd5.myworkdayjobs.com/en-US/pahocareers")

    assert site is not None
    assert site.url == "https://paho.wd5.myworkdayjobs.com/pahocareers"
    assert site.api == API
    assert parse_site_url("https://example.org/careers") is None


def test_posted_on_relative_texts() -> None:
    today = date(2026, 10, 9)

    assert posted_on_date("Posted Today", today=today) == today
    assert posted_on_date("Posted Yesterday", today=today) == date(2026, 10, 8)
    assert posted_on_date("Posted 3 Days Ago", today=today) == date(2026, 10, 6)
    assert posted_on_date("Posted 30+ Days Ago", today=today) is None


def test_search_row_maps_to_a_job_with_canonical_url_and_dedupe_key() -> None:
    site = parse_site_url("https://paho.wd5.myworkdayjobs.com/en-US/pahocareers")
    assert site is not None
    rows = load_json("search_page1.json")["jobPostings"]

    job = job_from_search_item(site, rows[1], company="Org", today=date(2026, 10, 9))
    old = job_from_search_item(site, rows[3], today=date(2026, 10, 9))

    assert job.url == "https://paho.wd5.myworkdayjobs.com/pahocareers" + OPEN_PATH
    assert job.source == "workday"
    assert job.source_job_id == "paho/pahocareers:Req-06070"
    assert job.location == "Off Site"
    assert job.posted_at == datetime(2026, 10, 7, tzinfo=UTC)
    assert job.ats_kind == "workday"
    assert old.posted_at is None
    assert old.note == "workday: Posted 30+ Days Ago"
    assert old.company == "paho"


def test_detail_maps_description_closing_and_signals() -> None:
    ref = parse_workday_url("https://paho.wd5.myworkdayjobs.com/en-US/pahocareers" + OPEN_PATH)
    assert ref is not None

    job = job_from_detail(ref, load_json("detail_open.json"))

    assert job.title == "National PAHO Consultant - Comunicaciones"
    assert job.company == "Pan American Sanitary Bureau"
    assert job.source_job_id == "paho/pahocareers:Req-06070"
    assert job.url == ref.url
    assert "<p" not in job.description and "Closing Date" in job.description
    assert job.employment_type == "Full time"
    assert job.posted_at == datetime(2026, 10, 7, tzinfo=UTC)
    # The text's closing wins over endDate (2026-10-12, when the posting leaves the site).
    assert job.closes_on == date(2026, 10, 11)
    assert job.closes_at == datetime(2026, 10, 11, 23, 59, tzinfo=ZoneInfo("America/New_York"))
    assert job.ats_signals == {"can_apply": True, "resume_parsing": False, "questionnaire": True}


def test_ambiguous_zone_detail_keeps_date_without_inventing_time() -> None:
    payload = load_json("detail_ambiguous_zone.json")
    ref = parse_workday_url(payload["jobPostingInfo"]["externalUrl"])
    assert ref is not None

    job = job_from_detail(ref, payload)

    assert job.closes_on == date(2026, 10, 12)
    assert job.closes_at is None
    assert job.closes_text is not None and "Central Time" in job.closes_text


def test_detail_without_closing_line_falls_back_to_end_date_labelled() -> None:
    payload = load_json("detail_open.json")
    info = payload["jobPostingInfo"]
    info["jobDescription"] = "<p>No closing line</p>"
    ref = parse_workday_url(info["externalUrl"])
    assert ref is not None

    job = job_from_detail(ref, payload)

    assert job.closes_on == date(2026, 10, 12)
    assert job.closes_at is None
    assert job.closes_text is not None and "endDate" in job.closes_text


def test_cannot_apply_is_closed() -> None:
    payload = load_json("detail_open.json")
    payload["jobPostingInfo"]["canApply"] = False
    ref = parse_workday_url(payload["jobPostingInfo"]["externalUrl"])
    assert ref is not None

    with pytest.raises(WorkdayPostingClosed):
        job_from_detail(ref, payload)


def _site() -> WorkdaySite:
    site = parse_site_url("https://paho.wd5.myworkdayjobs.com/pahocareers")
    assert site is not None
    return site


def test_search_pages_by_offset_until_total() -> None:
    fake = FakeWorkday(pages=paged_search(45))

    result = _client(fake).search(_site(), "x", limit=50)

    offsets = [c.body["offset"] for c in fake.cxs_calls if c.body is not None]
    assert offsets == [0, 20, 40]
    assert len(result.postings) == 45
    assert result.total == 45
    assert result.pages == 3


def test_search_stops_when_an_offset_wraps_to_the_first_page() -> None:
    """Workday answers an offset past the end with page one again; no endless loop."""
    first = paged_search(20)[0]
    first["total"] = 60
    fake = FakeWorkday(pages=[first])

    result = _client(fake).search(_site(), "x", limit=200)

    assert len(result.postings) == 20
    assert len(fake.cxs_calls) == 2


def test_search_respects_limit_and_sends_the_documented_body() -> None:
    fake = FakeWorkday(pages=paged_search(45))

    result = _client(fake).search(_site(), "health", limit=5)

    assert len(result.postings) == 5
    first = fake.cxs_calls[0]
    assert first.body == {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "health"}
    assert first.headers["User-Agent"] == USER_AGENT
    assert first.headers["Content-Type"] == "application/json"


def test_empty_search_is_no_results_not_an_error() -> None:
    fake = FakeWorkday(pages=[load_json("search_empty.json")])

    result = _client(fake).search(_site(), "Req-99999", limit=20)

    assert result.postings == [] and result.total == 0


def test_search_shape_change_is_reported() -> None:
    fake = FakeWorkday(pages=[{"unexpected": True}])

    with pytest.raises(WorkdayShapeChanged):
        _client(fake).search(_site(), "x", limit=20)


def test_robots_disallow_means_no_cxs_request() -> None:
    fake = FakeWorkday(robots=fixture_text("robots_disallow.txt"), pages=paged_search(5))

    with pytest.raises(WorkdayRobotsDisallowed):
        _client(fake).search(_site(), "x", limit=20)

    assert fake.cxs_calls == []
    assert len(fake.calls) == 1


def test_detail_404_and_403_s22_are_closure_evidence() -> None:
    ref = WorkdayRef(site=_site(), external_path=OPEN_PATH)
    gone = FakeWorkday()
    denied = FakeWorkday()
    denied.details[OPEN_PATH] = (403, fixture_text("error_403_s22.json"))

    with pytest.raises(WorkdayPostingClosed, match="HTTP 404 errorCode S21"):
        _client(gone).job(ref)
    with pytest.raises(WorkdayPostingClosed, match="S22"):
        _client(denied).job(ref)


def test_other_403_is_a_refusal_not_a_closure() -> None:
    ref = WorkdayRef(site=_site(), external_path=OPEN_PATH)
    fake = FakeWorkday()
    fake.details[OPEN_PATH] = (403, "<html>blocked</html>")

    with pytest.raises(WorkdayRefused, match="HTTP 403"):
        _client(fake).job(ref)


def test_406_is_retried_once_with_a_wider_accept() -> None:
    ref = WorkdayRef(site=_site(), external_path=OPEN_PATH)
    fake = FakeWorkday()
    fake.details[OPEN_PATH] = (406, '{"errorCode":"HTTP_406"}')

    with pytest.raises(WorkdayRefused, match="406"):
        _client(fake).job(ref)

    tries = fake.cxs_calls
    assert len(tries) == 2
    assert tries[0].headers["Accept"] == "application/json"
    assert "*/*" in tries[1].headers["Accept"]


def test_detail_without_title_is_a_shape_change() -> None:
    ref = WorkdayRef(site=_site(), external_path=OPEN_PATH)
    fake = FakeWorkday()
    fake.detail(OPEN_PATH, {"jobPostingInfo": {}})

    with pytest.raises(WorkdayShapeChanged):
        _client(fake).job(ref)


def test_requests_to_one_host_are_paced() -> None:
    fake = FakeWorkday(pages=paged_search(45))
    waits: list[float] = []
    ticks = iter(float(n) * 0.1 for n in range(100))
    client = CxsClient(runner=fake, sleep=waits.append, clock=lambda: next(ticks), delay=1.0)

    client.search(_site(), "x", limit=45)

    assert len(fake.calls) == 4  # robots + 3 pages
    assert len(waits) == 3 and all(0 < w <= 1.0 for w in waits)


def test_fetch_workday_job_by_url() -> None:
    fake = FakeWorkday()
    fake.detail(OPEN_PATH, load_json("detail_open.json"))

    job = fetch_workday_job(
        "https://paho.wd5.myworkdayjobs.com/en-US/pahocareers" + OPEN_PATH, client=_client(fake)
    )

    assert job.title == "National PAHO Consultant - Comunicaciones"
    with pytest.raises(ValueError, match="Not a Workday posting URL"):
        fetch_workday_job("https://paho.wd5.myworkdayjobs.com/pahocareers", client=_client(fake))


def test_no_path_tries_to_log_in() -> None:
    fake = FakeWorkday(pages=paged_search(3))
    fake.detail(OPEN_PATH, load_json("detail_open.json"))
    client = _client(fake)

    client.search(_site(), "x", limit=3)
    client.job(WorkdayRef(site=_site(), external_path=OPEN_PATH))

    assert all("login" not in c.url.casefold() and "auth" not in c.url for c in fake.calls)
    assert all(c.headers["User-Agent"] == USER_AGENT for c in fake.calls)
