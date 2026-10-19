"""HiringRoom host detection and a saved vacancy. No listing crawl."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from jobbot.adapters.hiringroom.parse import (
    HiringRoomParseError,
    listing_links,
    parse_vacancy,
)
from jobbot.companies.signup import AccountNeed, account_need
from jobbot.portals.detect import JOB_BOARD_KINDS, AtsKind, detect_ats, detect_ats_in_html

VACANCY = (
    "https://acme.hiringroom.com/jobs/get_vacancy/0123456789abcdef01234567"
)
FICHA = """<html><body>
<h1 class="vacancy-name">Analista de operaciones</h1>
<p class="hero__information-vacancy">Comuna Neutra, Región Neutra, Chile</p>
<p class="hero__time-vacancy">Hace 1 día</p>
<div class="job-description-content">Coordinar los equipos regionales del servicio.</div>
<img src="/img/HiringRoom-logo_footer.png" alt="">
</body></html>"""


def test_a_tenant_vacancy_is_hiringroom() -> None:
    assert detect_ats(VACANCY) == AtsKind.HIRINGROOM
    assert detect_ats("https://www.hiringroom.com/") == AtsKind.HIRINGROOM
    assert AtsKind.HIRINGROOM not in JOB_BOARD_KINDS
    assert account_need(AtsKind.HIRINGROOM) == AccountNeed.NEEDED


def test_an_unrelated_host_is_not_hiringroom() -> None:
    assert detect_ats("https://example.com/jobs") != AtsKind.HIRINGROOM


def test_the_footer_logo_is_a_hiringroom_page() -> None:
    kind, evidence = detect_ats_in_html("<img src='HiringRoom-logo_footer.png'>")
    assert kind == AtsKind.HIRINGROOM
    assert "hiringroom footer logo" in evidence


def test_a_saved_vacancy_keeps_title_place_and_relative_day() -> None:
    job = parse_vacancy(FICHA, url=VACANCY + "?utm=1", today=date(2026, 10, 8))

    assert job.title == "Analista de operaciones"
    assert job.company == "acme"
    assert job.location == "Comuna Neutra, Región Neutra, Chile"
    assert job.description == "Coordinar los equipos regionales del servicio."
    assert job.source_job_id == "acme:0123456789abcdef01234567"
    assert job.url == VACANCY
    assert job.posted_at == datetime(2026, 10, 7, tzinfo=UTC)
    assert job.ats_kind == AtsKind.HIRINGROOM.value


def test_another_trade_uses_the_same_selectors() -> None:
    html = FICHA.replace("Analista de operaciones", "Enfermera de turno")
    job = parse_vacancy(html, url=VACANCY, today=date(2026, 10, 8))
    assert job.title == "Enfermera de turno"
    assert job.company == "acme"


def test_a_page_without_a_title_is_refused() -> None:
    with pytest.raises(HiringRoomParseError):
        parse_vacancy(
            "<html><body><p>sin cargo</p></body></html>",
            url=VACANCY,
            today=date(2026, 10, 8),
        )


def test_listing_links_are_canonical_and_deduped() -> None:
    html = """
    <a href="/jobs/get_vacancy/0123456789abcdef01234567?x=1">Uno</a>
    <a href="/jobs/get_vacancy/0123456789abcdef01234567">Uno otra vez</a>
    <a href="/jobs/get_vacancy/abcdef0123456789abcdef01">Dos</a>
    <a href="/empleos/otro">No</a>
    """
    links = listing_links(html, base="https://acme.hiringroom.com/jobs")
    assert links == [
        "https://acme.hiringroom.com/jobs/get_vacancy/0123456789abcdef01234567",
        "https://acme.hiringroom.com/jobs/get_vacancy/abcdef0123456789abcdef01",
    ]
