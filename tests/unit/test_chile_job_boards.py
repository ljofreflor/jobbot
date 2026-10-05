"""Chilean job boards are bolsas, not a company's career portal (#183)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from jobbot.companies.discovery import classify_url
from jobbot.companies.learn import learn_from_job, learn_from_url
from jobbot.companies.models import CareerSiteType, DiscoverySource
from jobbot.companies.registry import (
    CompanyRegistry,
    default_companies_path,
    load_companies,
    save_companies,
)
from jobbot.config import JobbotConfig
from jobbot.exit_codes import SUCCESS
from jobbot.models.job import JobPosting
from jobbot.portals.detect import (
    JOB_BOARD_KINDS,
    AtsKind,
    detect_ats,
    first_external_ats_url,
    is_white_label_tenant,
    job_board_host_review,
)

# Fictional postings only — never a real vacancy or employer.
_TRABAJANDO_BOARD = "https://www.trabajando.cl/trabajo-empleo/oferta/1234567-cargo-ficticio"
_LABORUM_BOARD = "https://www.laborum.cl/empleos/cargo-ficticio-1234.html"
_COMPUTRABAJO_BOARD = "https://cl.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-x-ABC123"
_EMPLEOS_PUBLICOS_BOARD = (
    "https://www.empleospublicos.cl/pub/convocatorias/convpostularavisoTrabajo.aspx?i=99999"
)
_BUMERAN_BOARD = "https://www.bumeran.cl/empleos/cargo-ficticio-1234.html"
_CHILETRABAJOS_BOARD = "https://www.chiletrabajos.cl/trabajo/cargo-ficticio-1234"
_WHITE_LABEL = "https://acme.trabajando.cl/ofertas/cargo-ficticio"


def _job(**kwargs: object) -> JobPosting:
    base: dict[str, object] = {
        "id": "J0001",
        "source": "manual",
        "title": "Cargo ficticio",
        "company": "Consultora Ficticia",
    }
    base.update(kwargs)
    return JobPosting.model_validate(base)


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        (_TRABAJANDO_BOARD, AtsKind.TRABAJANDO),
        ("https://trabajando.cl/", AtsKind.TRABAJANDO),
        (_LABORUM_BOARD, AtsKind.LABORUM),
        (_COMPUTRABAJO_BOARD, AtsKind.COMPUTRABAJO),
        (_EMPLEOS_PUBLICOS_BOARD, AtsKind.EMPLEOS_PUBLICOS),
        (_BUMERAN_BOARD, AtsKind.BUMERAN),
        ("https://www.bumeran.com/empleos/cargo-ficticio", AtsKind.BUMERAN),
        (_CHILETRABAJOS_BOARD, AtsKind.CHILETRABAJOS),
        (_WHITE_LABEL, AtsKind.TRABAJANDO),
    ],
)
def test_chilean_board_hosts_are_detected(url: str, kind: AtsKind) -> None:
    assert detect_ats(url) == kind
    assert kind in JOB_BOARD_KINDS


def test_apex_and_www_trabajando_are_shared_boards_not_tenants() -> None:
    assert not is_white_label_tenant(_TRABAJANDO_BOARD)
    assert not is_white_label_tenant("https://trabajando.cl/")
    assert is_white_label_tenant(_WHITE_LABEL)
    assert not is_white_label_tenant(_LABORUM_BOARD)
    assert not is_white_label_tenant(_COMPUTRABAJO_BOARD)


@pytest.mark.parametrize(
    "url",
    [_TRABAJANDO_BOARD, _LABORUM_BOARD, _COMPUTRABAJO_BOARD, _EMPLEOS_PUBLICOS_BOARD],
)
def test_learn_from_job_skips_chilean_board_postings(tmp_path: Path, url: str) -> None:
    config = JobbotConfig(root=tmp_path)
    assert learn_from_job(config, _job(url=url, company="Consultora Ficticia")) is None
    path = default_companies_path(tmp_path)
    assert not path.exists() or load_companies(path).companies == []


def test_learn_from_url_skips_www_trabajando() -> None:
    registry = CompanyRegistry()
    assert (
        learn_from_url(
            registry,
            company="Consultora Ficticia",
            url=_TRABAJANDO_BOARD,
            source=DiscoverySource.JOB_SOURCE,
        )
        is None
    )
    assert registry.companies == []


def test_trabajando_white_label_is_learned_as_the_company_ats(tmp_path: Path) -> None:
    config = JobbotConfig(root=tmp_path)
    result = learn_from_job(config, _job(company="Acme", url=_WHITE_LABEL))
    assert result is not None
    assert result.ats == AtsKind.TRABAJANDO.value
    assert result.company_id == "acme"
    assert "acme.trabajando.cl" in result.url
    found = classify_url(_WHITE_LABEL)
    assert found.is_company_specific
    assert found.site_type in {CareerSiteType.ATS_INSTANCE, CareerSiteType.JOB_POSTING}
    assert found.ats == AtsKind.TRABAJANDO
    registry = load_companies(default_companies_path(tmp_path))
    assert registry.companies[0].domains == []


def test_indeed_and_getonboard_still_are_not_company_knowledge(tmp_path: Path) -> None:
    config = JobbotConfig(root=tmp_path)
    assert learn_from_job(config, _job(url="https://cl.indeed.com/viewjob?jk=abc123")) is None
    assert learn_from_job(config, _job(url="https://www.getonbrd.com/jobs/ds-empresa")) is None
    path = default_companies_path(tmp_path)
    assert not path.exists() or load_companies(path).companies == []


def test_a_chilean_board_loses_to_the_employer_page() -> None:
    urls = [_TRABAJANDO_BOARD, "https://careers.acme.example/jobs/42"]
    assert first_external_ats_url(urls) == (
        "https://careers.acme.example/jobs/42",
        AtsKind.UNKNOWN,
    )


def test_white_label_trabajando_is_a_real_apply_route() -> None:
    assert first_external_ats_url([_WHITE_LABEL]) == (_WHITE_LABEL, AtsKind.TRABAJANDO)
    assert first_external_ats_url([_TRABAJANDO_BOARD, _WHITE_LABEL]) == (
        _WHITE_LABEL,
        AtsKind.TRABAJANDO,
    )


def test_job_board_host_review_flags_shared_hosts_only() -> None:
    assert job_board_host_review(_TRABAJANDO_BOARD) == "host de bolsa: revisar"
    assert job_board_host_review(_LABORUM_BOARD) == "host de bolsa: revisar"
    assert job_board_host_review(_WHITE_LABEL) is None
    assert job_board_host_review("https://careers.empresa-demo.cl/jobs") is None
    assert job_board_host_review("https://boards.greenhouse.io/acme") is None


def test_companies_list_flags_a_stored_trabajando_board_host(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    registry = CompanyRegistry()
    registry.observe(
        company="Consultora Ficticia",
        url="https://www.trabajando.cl/",
        source=DiscoverySource.JOB_SOURCE,
        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
    )
    save_companies(registry, default_companies_path(tmp_path))

    import jobbot.cli as cli

    buffer = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=buffer, width=160, color_system=None))
    assert cli.run_cli(["companies", "list"], standalone_mode=False) == SUCCESS
    out = buffer.getvalue()
    assert "host de bolsa: revisar" in out
    assert "companies reject" in out
