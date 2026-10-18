"""Alta Dirección Pública (Servicio Civil) — a known board whose robots.txt says Disallow: /.

#191 asked for an ADP adapter. The site forbids every automated agent, so JobBot
recognises its links (a board, never one employer's career site) and refuses to read
them: the human opens the ficha and may hand the saved HTML over with ``--fixture``.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest
import yaml

from jobbot.companies.discovery import classify_url
from jobbot.companies.models import CareerSiteType
from jobbot.config import JobbotConfig, PathsConfig
from jobbot.db.engine import make_engine, make_session_factory
from jobbot.exit_codes import VALIDATION_FAILURE
from jobbot.jobs.closure import fetch_posting_text
from jobbot.jobs.from_url import (
    PortalDisallowedError,
    UnsupportedPortalFetchError,
    ingest_hard_link,
)
from jobbot.models.candidate import Candidate
from jobbot.portals.detect import (
    JOB_BOARD_KINDS,
    ROBOTS_DISALLOWED_KINDS,
    AtsKind,
    detect_ats,
)
from jobbot.portals.knowledge import lookup_portal
from tests.fixtures.profile import public_health_profile_dict

FICHA_URL = "https://adp.serviciocivil.cl/concursos-spl/opencms/convocatoria/ADP-29895"


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Any attempt to open a URL is recorded and fails the test's expectations."""
    opened: list[str] = []

    def refuse(request: object, *args: object, **kwargs: object) -> object:
        opened.append(getattr(request, "full_url", str(request)))
        raise AssertionError("ADP must never be fetched")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    return opened


def _config(tmp_path: Path, project_root: Path) -> JobbotConfig:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    return JobbotConfig(
        root=tmp_path,
        paths=PathsConfig(templates=project_root / "templates", output=Path("output")),
    )


@pytest.mark.parametrize(
    "url",
    [
        FICHA_URL,
        "https://adp.serviciocivil.cl/concursos-spl/opencms/",
        "https://antares.serviciocivil.cl/concursos-spl/opencms/portada.html",
    ],
)
def test_adp_hosts_are_recognised(url: str) -> None:
    assert detect_ats(url) == AtsKind.ALTA_DIRECCION_PUBLICA


@pytest.mark.parametrize(
    "url",
    ["https://www.adp.cl/", "https://adp.com/careers", "https://www.serviciocivil.cl/"],
)
def test_adp_payroll_firm_and_institutional_site_are_not_the_board(url: str) -> None:
    assert detect_ats(url) != AtsKind.ALTA_DIRECCION_PUBLICA


def test_adp_is_a_board_not_an_employer_site() -> None:
    assert AtsKind.ALTA_DIRECCION_PUBLICA in JOB_BOARD_KINDS
    found = classify_url(FICHA_URL)
    assert found.site_type == CareerSiteType.JOB_BOARD
    assert not found.is_company_specific


def test_seed_records_the_robots_decision(project_root: Path) -> None:
    for relpath in ("data/portals.example.yaml", "src/jobbot/resources/portals.example.yaml"):
        raw = yaml.safe_load((project_root / relpath).read_text(encoding="utf-8"))
        entry = next(p for p in raw["portals"] if p["domain"] == "adp.serviciocivil.cl")
        assert entry["ats_kind"] == AtsKind.ALTA_DIRECCION_PUBLICA.value
        assert "Disallow: /" in entry["notes"]
        assert "adp.cl" in entry["notes"]
        assert detect_ats(entry["example_url"]) == AtsKind.ALTA_DIRECCION_PUBLICA


def test_hard_link_without_fixture_is_refused_without_fetching(
    tmp_path: Path, project_root: Path, no_network: list[str]
) -> None:
    assert AtsKind.ALTA_DIRECCION_PUBLICA in ROBOTS_DISALLOWED_KINDS
    config = _config(tmp_path, project_root)
    session = make_session_factory(make_engine(config.database_path))()
    portal = lookup_portal(config, FICHA_URL)
    assert portal.known and portal.ats_kind == AtsKind.ALTA_DIRECCION_PUBLICA

    with pytest.raises(PortalDisallowedError, match="robots.txt"):
        ingest_hard_link(
            config,
            session,
            FICHA_URL,
            candidate=Candidate.model_validate(public_health_profile_dict()),
            html=None,
            build=False,
            prepare=False,
        )
    assert no_network == []


SAVED_FICHA = """<html><head><title>Convocatoria ADP-29895</title></head><body>
<h1>Jefe(a) División Jurídica</h1>
<p>Servicio Neutro de Vivienda</p>
<h2>Descripción del cargo</h2>
<p>Dirigir la asesoría jurídica del servicio y coordinar los equipos regionales.</p>
<h2>Requisitos</h2>
<ul><li>Título profesional de abogado(a)</li><li>Cinco años de experiencia</li></ul>
<p>Región Metropolitana de Santiago</p>
</body></html>"""


def test_a_saved_ficha_without_job_markup_points_to_jobs_add(
    tmp_path: Path, project_root: Path, no_network: list[str]
) -> None:
    """No ADP parser yet (#228): the saved page is read offline and the way out is named."""
    config = _config(tmp_path, project_root)
    session = make_session_factory(make_engine(config.database_path))()

    with pytest.raises(UnsupportedPortalFetchError) as caught:
        ingest_hard_link(
            config,
            session,
            FICHA_URL,
            candidate=Candidate.model_validate(public_health_profile_dict()),
            html=SAVED_FICHA,
            build=False,
            prepare=False,
        )

    assert no_network == []
    assert f"jobbot jobs add --file ficha.txt --url {FICHA_URL}" in str(caught.value)


def test_jobs_add_keeps_the_adp_link_as_evidence_without_fetching(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_network: list[str],
) -> None:
    from jobbot.cli import run_cli
    from jobbot.config import load_config
    from jobbot.exit_codes import SUCCESS
    from jobbot.jobs.repository import JobRepository

    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ficha = tmp_path / "ficha.txt"
    ficha.write_text(
        "Jefe(a) División Jurídica\nServicio Neutro de Vivienda\n"
        "Dirigir la asesoría jurídica del servicio.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    args = ["jobs", "add", "--file", str(ficha), "--url", FICHA_URL]
    assert run_cli(args, standalone_mode=False) == SUCCESS

    assert no_network == []
    session = make_session_factory(make_engine(load_config().database_path))()
    try:
        [job] = JobRepository(session).list_all()
    finally:
        session.close()
    assert job.url == FICHA_URL


def test_posting_status_check_never_reads_adp(no_network: list[str]) -> None:
    with pytest.raises(OSError, match="robots.txt"):
        fetch_posting_text(FICHA_URL)
    assert no_network == []


def test_get_refuses_quietly_and_records_no_ops_failure(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_network: list[str],
) -> None:
    """Being asked not to read a site is a decision, not a missing fetcher to file."""
    from jobbot.cli import run_cli

    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    assert run_cli(["get", FICHA_URL], standalone_mode=False) == VALIDATION_FAILURE

    err = capsys.readouterr().err
    assert "robots.txt" in err
    assert no_network == []
    failures_dir = tmp_path / "output" / "ops" / "failures"
    assert not failures_dir.exists() or not any(failures_dir.iterdir())
