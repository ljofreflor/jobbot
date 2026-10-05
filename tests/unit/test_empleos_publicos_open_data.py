"""Empleos Públicos search from the Servicio Civil open data (#191, #153).

The portal answers 403 to any client that names itself, and JobBot does not dress up
as a browser. The publisher releases the same convocatorias as an open-data CSV with
closing date and gross pay; these tests replay an anonymised slice of it, offline.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from jobbot.adapters.empleospublicos import open_data
from jobbot.adapters.empleospublicos.jobs import EmpleosPublicosJobSource
from jobbot.adapters.empleospublicos.open_data import (
    OPEN_DATA_URL,
    SANTIAGO,
    USER_AGENT,
    OpenDataCache,
    OpenDataError,
    download_open_data,
    job_from_convocatoria,
    parse_open_data_csv,
    search_convocatorias,
)
from jobbot.companies.oneshot import FetchResult
from jobbot.exit_codes import GENERIC_FAILURE, SUCCESS
from jobbot.jobs.conditions import ConditionKind, posting_conditions
from jobbot.jobs.sources import JobSearchQuery
from jobbot.portals.detect import AtsKind

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "empleospublicos"
    / "open_data_convocatorias.csv"
)
NOW = datetime(2026, 10, 5, 16, 0, tzinfo=SANTIAGO)
ROBOTS_URL = "https://reporte.serviciocivil.cl/robots.txt"
ROBOTS_OK = "User-agent: *\nDisallow: /wp-admin/\nAllow: /wp-admin/admin-ajax.php\n"


class FakeFetcher:
    """Serves robots.txt and the CSV from memory; records every URL asked for."""

    def __init__(
        self,
        *,
        robots: FetchResult | None = None,
        csv: FetchResult | None = None,
    ) -> None:
        self.robots = robots or FetchResult(url=ROBOTS_URL, status=200, html=ROBOTS_OK)
        self.csv = csv or FetchResult(
            url=OPEN_DATA_URL, status=200, html=FIXTURE.read_text(encoding="utf-8-sig")
        )
        self.asked: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.asked.append(url)
        if url.endswith("/robots.txt"):
            return self.robots
        assert url == OPEN_DATA_URL
        return self.csv


def _items() -> list[open_data.Convocatoria]:
    return parse_open_data_csv(FIXTURE.read_text(encoding="utf-8-sig"))


def test_every_row_is_read_and_applicant_counts_never_reach_a_posting() -> None:
    items = _items()
    assert [item.id for item in items] == [
        "990101",
        "990102",
        "990103",
        "990104",
        "990105",
        "990106",
    ]
    for item in items:
        job = job_from_convocatoria(item)
        assert "4242" not in job.description
        assert "2121" not in job.description
        assert "seleccionad" not in job.description.casefold()


def test_only_open_convocatorias_pass_newest_first() -> None:
    hits = search_convocatorias(_items(), "", now=NOW)
    # 990103 closed on 2026-09-10; 990104 is open by date but declared "sin efecto".
    assert [item.id for item in hits] == ["990106", "990105", "990101", "990102"]


def test_closed_ones_come_back_only_when_asked() -> None:
    hits = search_convocatorias(_items(), "división jurídica", now=NOW, include_closed=True)
    assert [item.id for item in hits] == ["990103"]
    assert search_convocatorias(_items(), "división jurídica", now=NOW) == []


def test_query_words_match_across_gender_and_accents() -> None:
    """'jefe jurídico' is the candidate's wording; the cargo says 'Jefe(a) … Jurídica'."""
    hits = search_convocatorias(_items(), "jefe jurídico", now=NOW)
    assert [item.id for item in hits] == ["990101"]


def test_every_query_word_must_be_present() -> None:
    assert search_convocatorias(_items(), "abogado litigante", now=NOW)[0].id == "990102"
    assert search_convocatorias(_items(), "abogado enfermera", now=NOW) == []


def test_region_filter_is_accent_and_case_free() -> None:
    hits = search_convocatorias(_items(), "", now=NOW, region="biobio")
    assert [item.id for item in hits] == ["990101"]


def test_a_convocatoria_becomes_a_lead_with_deadline_and_pay() -> None:
    item = next(i for i in _items() if i.id == "990101")
    job = job_from_convocatoria(item)

    assert job.source == "empleos_publicos"
    assert job.source_job_id == "990101"
    assert job.ats_kind == AtsKind.EMPLEOS_PUBLICOS.value
    assert job.title.startswith("Jefe(a) Departamento Asesoría Jurídica")
    assert job.company == "Servicio Neutro de Salud Norte"
    assert job.location == "Región del Biobío"
    assert job.employment_type == "Planta"
    assert job.url == (
        "https://www.empleospublicos.cl/pub/convocatorias/avisotrabajoficha.aspx?i=990101"
    )
    assert job.posted_at is not None and job.posted_at.date().isoformat() == "2026-10-01"
    assert "Fecha límite: 2026-10-20 23:59" in job.description
    assert "Renta: $3.816.217 bruta mensual" in job.description
    assert "Ministerio: Ministerio Neutro de Salud" in job.description


def test_jobs_conditions_reads_the_deadline_and_the_pay_offline() -> None:
    item = next(i for i in _items() if i.id == "990101")
    found = {c.kind: c for c in posting_conditions(job_from_convocatoria(item))}

    assert found[ConditionKind.DEADLINE].when is not None
    assert found[ConditionKind.DEADLINE].when.isoformat() == "2026-10-20"
    assert found[ConditionKind.SALARY].shown is True


def test_a_row_without_portal_url_falls_back_to_the_plain_ficha() -> None:
    item = next(i for i in _items() if i.id == "990106")
    assert item.url == (
        "https://www.empleospublicos.cl/pub/convocatorias/avisotrabajoficha.aspx?i=990106"
    )
    assert "Renta:" not in job_from_convocatoria(item).description


def test_aviso_rows_say_how_to_apply() -> None:
    item = next(i for i in _items() if i.id == "990105")
    assert not item.online
    assert "Postulación: aviso" in job_from_convocatoria(item).description


def test_job_notice_url_is_the_same_one_get_canonicalises_to() -> None:
    """convFicha only frames avisotrabajoficha; both routes must store one posting."""
    from jobbot.adapters.empleospublicos.jobs import canonical_ficha_url

    item = next(i for i in _items() if i.id == "990102")
    assert canonical_ficha_url(item.url) == item.url


def test_other_notice_kinds_keep_the_published_link() -> None:
    item = next(i for i in _items() if i.id == "990105")
    assert item.url == (
        "https://www.empleospublicos.cl/pub/convocatorias/convFicha.aspx"
        "?i=990105&tipo=avisopizarronficha"
    )


def test_a_changed_file_format_is_reported_not_guessed() -> None:
    text = "ID Convocatoria,Cargo\n1,Analista\n"
    with pytest.raises(OpenDataError, match="format changed"):
        parse_open_data_csv(text)


def test_download_reads_robots_first_then_the_file_politely() -> None:
    fetcher = FakeFetcher()
    pauses: list[float] = []

    text = download_open_data(fetcher, sleep_fn=pauses.append)

    assert fetcher.asked == [ROBOTS_URL, OPEN_DATA_URL]
    assert pauses == [1.0]
    assert "ID Convocatoria" in text


def test_a_refused_download_is_reported_not_worked_around() -> None:
    fetcher = FakeFetcher(csv=FetchResult(url=OPEN_DATA_URL, status=403))
    with pytest.raises(OpenDataError, match="HTTP 403"):
        download_open_data(fetcher, sleep_fn=lambda _: None)
    assert fetcher.asked == [ROBOTS_URL, OPEN_DATA_URL]


def test_robots_disallow_stops_before_the_file() -> None:
    fetcher = FakeFetcher(
        robots=FetchResult(url=ROBOTS_URL, status=200, html="User-agent: *\nDisallow: /\n")
    )
    with pytest.raises(OpenDataError, match="robots.txt"):
        download_open_data(fetcher, sleep_fn=lambda _: None)
    assert fetcher.asked == [ROBOTS_URL]


def test_a_host_that_refuses_its_robots_is_left_alone() -> None:
    fetcher = FakeFetcher(robots=FetchResult(url=ROBOTS_URL, status=403))
    with pytest.raises(OpenDataError, match="refused"):
        download_open_data(fetcher, sleep_fn=lambda _: None)
    assert fetcher.asked == [ROBOTS_URL]


def test_the_identifiable_user_agent_is_jobbot() -> None:
    assert USER_AGENT.startswith("jobbot/")
    assert "Mozilla" not in USER_AGENT


def test_cache_downloads_once_and_remembers_a_failure() -> None:
    good = FakeFetcher()
    cache = OpenDataCache(fetcher=good, sleep_fn=lambda _: None)
    assert cache.items() is cache.items()
    assert good.asked.count(OPEN_DATA_URL) == 1

    bad = FakeFetcher(csv=FetchResult(url=OPEN_DATA_URL, status=503))
    failing = OpenDataCache(fetcher=bad, sleep_fn=lambda _: None)
    for _ in range(3):
        with pytest.raises(OpenDataError):
            failing.items()
    assert bad.asked.count(OPEN_DATA_URL) == 1


def test_source_without_fixture_reads_open_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(open_data, "_now", lambda: NOW)
    fetcher = FakeFetcher()
    source = EmpleosPublicosJobSource(
        fixture=None, open_data=OpenDataCache(fetcher=fetcher, sleep_fn=lambda _: None)
    )

    jobs = source.search_jobs(JobSearchQuery(query="jurídica", limit=10))

    assert [job.source_job_id for job in jobs] == ["990101", "990102"]
    assert set(source.seen) == {"990101", "990102"}
    assert source.seen["990101"].gross_salary == 3816217


def test_source_replays_a_saved_csv_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(open_data, "_now", lambda: NOW)
    source = EmpleosPublicosJobSource(fixture=FIXTURE)
    jobs = source.search_jobs(JobSearchQuery(query="enfermera", location="Valparaíso", limit=5))
    assert [job.source_job_id for job in jobs] == ["990105"]


@pytest.fixture
def workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(open_data, "_now", lambda: NOW)
    monkeypatch.setattr(open_data, "_POLITE_DELAY", 0.0)
    return tmp_path


def _install(monkeypatch: pytest.MonkeyPatch, fetcher: FakeFetcher) -> None:
    monkeypatch.setattr(open_data, "OpenDataFetcher", lambda: fetcher)


def test_cli_search_stores_open_leads_with_deadline_and_pay(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from jobbot.cli import run_cli
    from jobbot.config import load_config
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    fetcher = FakeFetcher()
    _install(monkeypatch, fetcher)

    args = ["empleospublicos", "search", "jurídica", "--limit", "10"]
    assert run_cli(args, standalone_mode=False) == SUCCESS

    out = capsys.readouterr().out
    assert "Empleos Públicos (leads)" in out
    assert "2026-10-20" in out
    assert "$3.816.217" in out
    assert "Stored 2 leads" in out
    assert fetcher.asked == [ROBOTS_URL, OPEN_DATA_URL]
    assert (workspace / "data" / "portals.yaml").is_file()

    session = make_session_factory(make_engine(load_config().database_path))()
    try:
        stored = {job.source_job_id: job for job in JobRepository(session).list_all()}
    finally:
        session.close()
    assert set(stored) == {"990101", "990102"}
    assert "Fecha límite: 2026-10-20" in stored["990101"].description


def test_cli_one_failing_query_does_not_cancel_the_others(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import jobbot.cli as cli

    _install(monkeypatch, FakeFetcher())
    original = EmpleosPublicosJobSource.search_jobs

    def flaky(self: EmpleosPublicosJobSource, query: JobSearchQuery) -> list:  # type: ignore[type-arg]
        if query.query == "falla":
            raise OpenDataError("simulated failure")
        return original(self, query)

    monkeypatch.setattr(EmpleosPublicosJobSource, "search_jobs", flaky)
    monkeypatch.setattr(cli, "_search_queries", lambda *_: ["falla", "enfermera"])

    assert cli.run_cli(["empleospublicos", "search"], standalone_mode=False) == SUCCESS
    captured = capsys.readouterr()
    assert "simulated failure" in captured.err
    assert "Stored 1 leads" in captured.out


def test_cli_refused_download_fails_once_for_every_query(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import jobbot.cli as cli

    fetcher = FakeFetcher(csv=FetchResult(url=OPEN_DATA_URL, status=403))
    _install(monkeypatch, fetcher)
    monkeypatch.setattr(cli, "_search_queries", lambda *_: ["uno", "dos", "tres"])

    assert cli.run_cli(["empleospublicos", "search"], standalone_mode=False) == GENERIC_FAILURE
    assert "HTTP 403" in capsys.readouterr().err
    assert fetcher.asked.count(OPEN_DATA_URL) == 1
