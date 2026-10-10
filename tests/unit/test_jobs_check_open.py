"""#207: classify a stored posting as open / closed / unknown from its live source."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from jobbot.adapters.workday.cxs import HttpResponse
from jobbot.jobs.check_open import (
    OpenChecker,
    OpenStatus,
    PoliteHttp,
    due_for_check,
    request_url,
    verification_label,
)
from jobbot.jobs.open_signals import read_chiletrabajos, read_trabajando, trabajando_offer_id
from jobbot.models.job import JobPosting
from tests.fixtures.check_open_http import (
    CHILETRABAJOS_URL,
    PAGE_URL,
    TRABAJANDO_API_URL,
    TRABAJANDO_URL,
    WORKDAY_API,
    WORKDAY_HOST,
    WORKDAY_URL,
    FakeWeb,
    page,
    workday,
)
from tests.fixtures.workday_http import forbid_sockets

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    forbid_sockets(monkeypatch)


def _job(url: str | None = PAGE_URL, **extra: object) -> JobPosting:
    return JobPosting(
        id="J0001", source="manual", title="Analista", company="Acme", url=url, **extra
    )


def _check(
    web: FakeWeb, job: JobPosting, *, now: datetime = NOW, sleeps: list[float] | None = None
) -> tuple[OpenStatus, str]:
    pauses = sleeps if sleeps is not None else []
    http = PoliteHttp(runner=web, sleep=pauses.append)
    result = OpenChecker(http=http, now=lambda: now).check(job)
    return result.status, result.evidence


# --- Workday (CXS) ---------------------------------------------------------------


def test_workday_can_apply_is_open_and_cites_can_apply() -> None:
    web = FakeWeb().route(WORKDAY_API, 200, workday("detail_open.json"))
    http = PoliteHttp(runner=web, sleep=lambda _s: None)

    result = OpenChecker(http=http, now=lambda: NOW).check(_job(WORKDAY_URL))

    assert result.status is OpenStatus.OPEN
    assert "canApply: true" in result.evidence
    assert result.method == "workday"
    assert result.closes_on == date(2026, 10, 11)
    assert result.closes is not None


@pytest.mark.parametrize(
    ("status", "fixture", "evidence"),
    [
        (404, "error_404.json", "HTTP 404"),
        (403, "error_403_s22.json", "S22"),
    ],
)
def test_workday_gone_posting_is_closed_with_the_http_code(
    status: int, fixture: str, evidence: str
) -> None:
    web = FakeWeb().route(WORKDAY_API, status, workday(fixture))

    got, why = _check(web, _job(WORKDAY_URL))

    assert got is OpenStatus.CLOSED
    assert evidence in why


def test_workday_posted_without_can_apply_is_closed() -> None:
    web = FakeWeb().route(WORKDAY_API, 200, page("workday_cant_apply.json"))

    assert _check(web, _job(WORKDAY_URL)) == (OpenStatus.CLOSED, "canApply: false")


def test_workday_unposted_is_closed() -> None:
    payload = json.loads(workday("detail_open.json"))
    payload["jobPostingInfo"]["posted"] = False
    web = FakeWeb().route(WORKDAY_API, 200, json.dumps(payload))

    assert _check(web, _job(WORKDAY_URL)) == (OpenStatus.CLOSED, "posted: false")


def test_workday_closing_already_past_is_closed() -> None:
    web = FakeWeb().route(WORKDAY_API, 200, workday("detail_open.json"))

    got, why = _check(web, _job(WORKDAY_URL), now=datetime(2026, 10, 13, 12, 0, tzinfo=UTC))

    assert got is OpenStatus.CLOSED
    assert why.startswith("cierre vencido") and "Eastern Time" in why


def test_workday_closing_day_at_22h_in_the_tenant_zone_is_still_open() -> None:
    """22:00 in New York is already the next day in UTC; the posting closes at 23:59 ET."""
    late = datetime(2026, 10, 11, 22, 0, tzinfo=ZoneInfo("America/New_York"))
    web = FakeWeb().route(WORKDAY_API, 200, workday("detail_open.json"))

    got, _ = _check(web, _job(WORKDAY_URL), now=late.astimezone(UTC))

    assert got is OpenStatus.OPEN


def test_workday_persistent_406_is_retried_once_then_unknown() -> None:
    web = FakeWeb().route(WORKDAY_API, 406, "")

    got, _ = _check(web, _job(WORKDAY_URL))

    assert got is OpenStatus.UNKNOWN
    assert web.urls().count(WORKDAY_API) == 2


def test_workday_robots_disallow_reads_no_detail() -> None:
    web = FakeWeb().route(f"{WORKDAY_HOST}/robots.txt", 200, workday("robots_disallow.txt"))

    got, why = _check(web, _job(WORKDAY_URL))

    assert got is OpenStatus.UNKNOWN and "robots.txt" in why
    assert web.urls() == []


def test_workday_generic_403_is_unknown_not_closed() -> None:
    web = FakeWeb().route(WORKDAY_API, 403, '{"errorCode": "S10"}')

    got, why = _check(web, _job(WORKDAY_URL))

    assert got is OpenStatus.UNKNOWN and "403" in why


def test_workday_ats_link_wins_over_the_stored_post_url() -> None:
    web = FakeWeb().route(WORKDAY_API, 200, workday("detail_open.json"))
    job = _job("https://www.linkedin.com/posts/someone_activity-1", ats_url=WORKDAY_URL)

    got, _ = _check(web, job)

    assert got is OpenStatus.OPEN


# --- Generic HTTP ----------------------------------------------------------------


@pytest.mark.parametrize("status", [404, 410])
def test_gone_page_is_closed(status: int) -> None:
    web = FakeWeb().route(PAGE_URL, status, "<html>Not found</html>")

    assert _check(web, _job()) == (OpenStatus.CLOSED, f"HTTP {status}")


@pytest.mark.parametrize(
    ("fixture", "phrase"),
    [
        ("page_closed_es.html", "oferta finalizada"),
        ("page_closed_en.html", "this job is no longer available"),
        ("indeed_caducado.html", "este empleo caducó"),
    ],
)
def test_closing_phrase_on_the_page_is_closed(fixture: str, phrase: str) -> None:
    web = FakeWeb().route(PAGE_URL, 200, page(fixture))

    got, why = _check(web, _job())

    assert got is OpenStatus.CLOSED
    assert phrase in why


def test_page_without_a_signal_is_unknown_not_open() -> None:
    """A hidden 'expired' template does not count; no phrase is not 'open' either."""
    web = FakeWeb().route(PAGE_URL, 200, page("page_open.html"))

    got, why = _check(web, _job())

    assert got is OpenStatus.UNKNOWN
    assert "no implica abierto" in why


def test_published_closing_in_the_past_is_closed() -> None:
    web = FakeWeb().route(PAGE_URL, 200, page("page_expired_date.html"))

    got, why = _check(web, _job())

    assert got is OpenStatus.CLOSED and "January 15, 2026" in why


@pytest.mark.parametrize(("status", "text"), [(403, "Forbidden"), (429, ""), (0, "timed out")])
def test_refusal_or_network_error_is_unknown(status: int, text: str) -> None:
    web = FakeWeb().route(PAGE_URL, status, text)

    got, _ = _check(web, _job())

    assert got is OpenStatus.UNKNOWN


def test_robots_disallow_skips_the_page() -> None:
    web = FakeWeb().route(
        "https://careers.acme.test/robots.txt", 200, "User-agent: *\nDisallow: /jobs/\n"
    )

    got, why = _check(web, _job())

    assert got is OpenStatus.UNKNOWN and "robots.txt" in why
    assert web.urls() == []


def test_robots_refused_by_host_is_unknown() -> None:
    web = FakeWeb().route("https://careers.acme.test/robots.txt", 503, "")

    got, _ = _check(web, _job())

    assert got is OpenStatus.UNKNOWN
    assert web.urls() == []


@pytest.mark.parametrize(
    ("url", "evidence"),
    [
        ("https://www.linkedin.com/jobs/view/123", "LinkedIn"),
        ("https://municipio.example.test/bases/concurso.pdf", "PDF"),
        ("mailto:jobs@acme.test", "no es una página web"),
        (None, "sin URL"),
    ],
)
def test_unreadable_sources_are_unknown_without_any_request(url: str | None, evidence: str) -> None:
    web = FakeWeb()

    got, why = _check(web, _job(url))

    assert got is OpenStatus.UNKNOWN and evidence in why
    assert web.calls == []


def test_stored_closing_in_the_past_closes_an_unknown() -> None:
    job = _job("https://www.linkedin.com/jobs/view/123", closes_on=date(2026, 9, 1))

    got, why = _check(FakeWeb(), job)

    assert got is OpenStatus.CLOSED
    assert why.startswith("cierre guardado vencido: 2026-09-01")


def test_two_pages_on_one_host_wait_their_turn() -> None:
    other = "https://careers.acme.test/jobs/9999-otro"
    web = FakeWeb().route(PAGE_URL, 404).route(other, 404)
    pauses: list[float] = []
    http = PoliteHttp(runner=web, sleep=pauses.append, delay=1.0, clock=lambda: 100.0)
    checker = OpenChecker(http=http, now=lambda: NOW)

    checker.check(_job())
    checker.check(_job(other))

    assert pauses and all(p == pytest.approx(1.0) for p in pauses)
    assert all("jobbot" in headers["User-Agent"] for _, headers in web.calls)


# --- URLs urllib cannot send, and errors that must not stop a run ----------------


class AsciiWire(FakeWeb):
    """Like ``http.client``: a non-ASCII request line raises ``UnicodeEncodeError``."""

    def __call__(self, method: str, url: str, **kwargs: Any) -> HttpResponse:
        url.encode("ascii")
        return super().__call__(method, url, **kwargs)


ACCENTED = "https://careers.acme.test/en-us/job/593485/readvertised-consultoría-actualización"
ACCENTED_WIRE = (
    "https://careers.acme.test/en-us/job/593485/readvertised-consultor%C3%ADa-actualizaci%C3%B3n"
)


def test_non_ascii_path_is_percent_encoded_before_the_request() -> None:
    web = AsciiWire().route(ACCENTED_WIRE, 404)
    http = PoliteHttp(runner=web, sleep=lambda _s: None)

    result = OpenChecker(http=http, now=lambda: NOW).check(_job(ACCENTED))

    assert (result.status, result.evidence) == (OpenStatus.CLOSED, "HTTP 404")
    assert result.url == ACCENTED
    assert web.urls() == [ACCENTED_WIRE]


def test_non_ascii_host_is_sent_as_idna_also_for_robots() -> None:
    web = AsciiWire()

    got, _ = _check(web, _job("https://empleos.ñandú.test/aviso/1?cargo=técnico#postular"))

    assert got is OpenStatus.UNKNOWN
    sent = [url for url, _ in web.calls]
    assert sent[0] == "https://empleos.xn--and-6ma2c.test/robots.txt"
    assert sent[1] == "https://empleos.xn--and-6ma2c.test/aviso/1?cargo=t%C3%A9cnico"


def test_already_encoded_url_is_not_encoded_twice() -> None:
    assert request_url(ACCENTED_WIRE) == ACCENTED_WIRE


def test_invalid_url_is_unknown_without_requests() -> None:
    web = FakeWeb()

    got, why = _check(web, _job("http://[::1"))

    assert got is OpenStatus.UNKNOWN and why.startswith("URL inválida")
    assert web.calls == []


def test_an_error_while_checking_is_unknown_with_the_error() -> None:
    def broken(*_args: object, **_kwargs: object) -> HttpResponse:
        raise RuntimeError("socket exploded")

    http = PoliteHttp(runner=broken, sleep=lambda _s: None)

    result = OpenChecker(http=http, now=lambda: NOW).check(_job())

    assert result.status is OpenStatus.UNKNOWN
    assert result.evidence == "error al verificar: RuntimeError: socket exploded"
    assert result.url == PAGE_URL


# --- Trabajando (public offer API) -----------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "now", "expected", "evidence"),
    [
        (200, "trabajando_publicada.json", NOW, OpenStatus.OPEN, "PUBLICADA, expira 2026-11-07"),
        (
            200,
            "trabajando_publicada.json",
            datetime(2026, 11, 9, 12, 0, tzinfo=UTC),
            OpenStatus.CLOSED,
            "PUBLICADA, expiró 2026-11-07",
        ),
        (200, "trabajando_desactivada.json", NOW, OpenStatus.CLOSED, "estadoOferta: DESACTIVADA"),
        (404, None, NOW, OpenStatus.CLOSED, "HTTP 404"),
        (500, None, NOW, OpenStatus.UNKNOWN, "Trabajando: HTTP 500"),
        (200, "<html>no</html>", NOW, OpenStatus.UNKNOWN, "no es JSON"),
    ],
)
def test_trabajando_reads_the_offer_api(
    status: int, body: str | None, now: datetime, expected: OpenStatus, evidence: str
) -> None:
    text = page(body) if body and body.endswith(".json") else (body or "")
    web = FakeWeb().route(TRABAJANDO_API_URL, status, text)

    got, why = _check(web, _job(TRABAJANDO_URL), now=now)

    assert got is expected
    assert evidence in why
    assert web.urls() == [TRABAJANDO_API_URL]


def test_trabajando_open_offer_keeps_its_expiry_as_closing() -> None:
    web = FakeWeb().route(TRABAJANDO_API_URL, 200, page("trabajando_publicada.json"))
    http = PoliteHttp(runner=web, sleep=lambda _s: None)

    result = OpenChecker(http=http, now=lambda: NOW).check(_job(TRABAJANDO_URL))

    assert result.method == "trabajando"
    assert result.closes_on == date(2026, 11, 7)
    assert result.url == TRABAJANDO_URL


@pytest.mark.parametrize(
    ("payload", "evidence"),
    [
        ([], "sin forma de oferta"),
        ({"idOferta": 1}, "no informa estadoOferta"),
        ({"estadoOferta": "PUBLICADA"}, "sin fecha de expiración"),
    ],
)
def test_trabajando_payload_without_the_fields_is_unknown(payload: object, evidence: str) -> None:
    signal = read_trabajando(payload, now=NOW)

    assert signal.status is OpenStatus.UNKNOWN and evidence in signal.evidence


def test_trabajando_offer_id_only_for_its_posting_paths() -> None:
    assert trabajando_offer_id(TRABAJANDO_URL) == "6135043"
    assert trabajando_offer_id("https://www.trabajando.cl/trabajo-empleo") is None
    assert trabajando_offer_id("https://www.otro.test/trabajo/123-x") is None


# --- Chiletrabajos (detail page) -------------------------------------------------


def test_chiletrabajos_expira_row_in_the_future_is_open() -> None:
    web = FakeWeb().route(CHILETRABAJOS_URL, 200, page("chiletrabajos_open.html"))
    http = PoliteHttp(runner=web, sleep=lambda _s: None)

    result = OpenChecker(http=http, now=lambda: NOW).check(_job(CHILETRABAJOS_URL))

    assert (result.status, result.evidence) == (OpenStatus.OPEN, "Expira: 2026-12-23")
    assert result.closes_on == date(2026, 12, 23)


def test_chiletrabajos_expira_row_in_the_past_is_closed() -> None:
    web = FakeWeb().route(CHILETRABAJOS_URL, 200, page("chiletrabajos_open.html"))

    got, why = _check(web, _job(CHILETRABAJOS_URL), now=datetime(2027, 1, 2, tzinfo=UTC))

    assert got is OpenStatus.CLOSED and why == "Expira: 2026-12-23 (vencido)"


def test_chiletrabajos_expired_banner_is_closed() -> None:
    web = FakeWeb().route(CHILETRABAJOS_URL, 200, page("chiletrabajos_expired.html"))

    got, why = _check(web, _job(CHILETRABAJOS_URL))

    assert got is OpenStatus.CLOSED and "este anuncio ha expirado" in why


def test_chiletrabajos_without_a_readable_expira_row_says_nothing() -> None:
    assert (
        read_chiletrabajos("<table><tr><td>Expira</td><td>pronto</td></tr></table>", now=NOW)
        is None
    )
    assert read_chiletrabajos("<p>sin tabla</p>", now=NOW) is None


# --- Bookkeeping -----------------------------------------------------------------


def test_recently_closed_is_not_due_but_older_or_open_is() -> None:
    fresh = _job(open_status="closed", checked_at=NOW - timedelta(hours=2))
    stale = _job(open_status="closed", checked_at=NOW - timedelta(days=2))
    still = _job(open_status="open", checked_at=NOW - timedelta(hours=2))

    assert not due_for_check(fresh, now=NOW)
    assert due_for_check(stale, now=NOW)
    assert due_for_check(still, now=NOW)
    assert due_for_check(_job(), now=NOW)


def test_verification_label_names_state_day_and_evidence() -> None:
    job = _job(open_status="closed", checked_at=NOW, open_evidence="HTTP 404")

    assert verification_label(job) == "cerrado, verificado 2026-10-05: HTTP 404"
    assert verification_label(_job()) == ""
    assert verification_label(_job(open_status="unknown", checked_at=NOW)).startswith(
        "vigencia desconocida"
    )
