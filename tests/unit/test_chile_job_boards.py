"""Chilean job boards are not an employer's career portal. A tenant subdomain is."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.companies.discovery import classify_url
from jobbot.companies.learn import learn_from_job, learn_from_url
from jobbot.companies.models import CareerSiteType, DiscoverySource
from jobbot.companies.recheck import REVIEW_NOTE, apply_recheck, plan_recheck
from jobbot.companies.registry import CompanyRegistry, default_companies_path, load_companies
from jobbot.config import JobbotConfig
from jobbot.exit_codes import SUCCESS
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind, detect_ats, is_white_label_tenant, job_board_host_review

BOARD_URLS = (
    "https://www.trabajando.cl/trabajo-empleo/oferta/1234567-cargo-ficticio",
    "https://trabajando.cl/trabajo/1234567-cargo-ficticio",
    "https://www.laborum.cl/empleos/cargo-ficticio-1234.html",
    "https://cl.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-x-ABC123",
    "https://www.bumeran.cl/empleos/cargo-ficticio.html",
    "https://www.chiletrabajos.cl/cargo-ficticio",
    "https://www.empleospublicos.cl/pub/convocatorias/convpostularavisoTrabajo.aspx?i=99999",
)
TENANT = "https://acme.trabajando.cl/ofertas/cargo-ficticio"


def _job(url: str, company: str = "Consultora Ficticia") -> JobPosting:
    return JobPosting(id="J0001", source="manual", title="Cargo ficticio", company=company, url=url)


def test_shared_board_hosts_are_boards_and_a_tenant_is_not() -> None:
    for url in BOARD_URLS:
        assert classify_url(url, resolve=False).site_type is CareerSiteType.JOB_BOARD
        assert not is_white_label_tenant(url)
    for shared in ("www", "www2", "m", "mobile", "empleo", "empleos", "jobs", "trabajo"):
        assert not is_white_label_tenant(f"https://{shared}.trabajando.cl/ofertas")
    classified = classify_url(TENANT, resolve=False)
    assert is_white_label_tenant(TENANT)
    assert classified.ats is AtsKind.TRABAJANDO
    assert classified.site_type is CareerSiteType.JOB_POSTING


def test_learn_from_job_ignores_shared_boards(tmp_path: Path) -> None:
    config = JobbotConfig(root=tmp_path)
    for url in BOARD_URLS:
        assert learn_from_job(config, _job(url)) is None
    assert load_companies(default_companies_path(tmp_path)).companies == []


def test_known_boards_stay_ignored(tmp_path: Path) -> None:
    config = JobbotConfig(root=tmp_path)
    indeed = "https://cl.indeed.com/viewjob?jk=abc1234567890abc"
    gob = "https://www.getonbrd.com/empleos/programacion/cargo-ficticio"
    assert learn_from_job(config, _job(indeed, company="Empresa Demo")) is None
    assert learn_from_job(config, _job(gob, company="Empresa Demo")) is None
    assert detect_ats(indeed) is AtsKind.INDEED
    assert detect_ats(gob) is AtsKind.GETONBOARD


def test_white_label_tenant_is_stored_as_the_companys_ats(tmp_path: Path) -> None:
    registry = CompanyRegistry()
    outcome = learn_from_url(
        registry,
        company="Acme",
        url=TENANT,
        source=DiscoverySource.USER_OBSERVATION,
        resolve=False,
    )
    assert outcome is not None and outcome.site is not None
    assert outcome.site.url == "https://acme.trabajando.cl"
    assert outcome.site.ats is AtsKind.TRABAJANDO
    assert outcome.site.site_type is CareerSiteType.ATS_INSTANCE
    assert outcome.company.name == "Acme"


def test_board_host_review_names_the_shared_board_only() -> None:
    assert job_board_host_review(BOARD_URLS[0]) == "host de bolsa: revisar"
    assert job_board_host_review(TENANT) == ""


def test_companies_list_marks_a_board_host(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = project_root / "tests/fixtures/companies/registry_with_board_host.yaml"
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "data" / "companies.yaml").write_text(
        fixture.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli

    assert run_cli(["companies", "list"], standalone_mode=False) == SUCCESS
    out = capsys.readouterr().out
    assert "host de bolsa: revisar" in out
    assert (
        "jobbot companies reject consultora-ficticia "
        "--site https://www.trabajando.cl/trabajo-empleo/oferta/1234567-cargo-ficticio"
    ) in out


def test_recheck_keeps_a_tenant_as_the_companys_ats() -> None:
    registry = CompanyRegistry()
    registry.observe(
        company="Acme",
        url="https://acme.trabajando.cl",
        source=DiscoverySource.USER_OBSERVATION,
        site_type=CareerSiteType.ATS_INSTANCE,
        ats=AtsKind.TRABAJANDO,
        evidence="stored earlier",
    )

    apply_recheck(registry, plan_recheck(registry))
    site = registry.companies[0].career_sites[0]

    assert site.site_type is CareerSiteType.ATS_INSTANCE
    assert REVIEW_NOTE not in (site.notes or "")
    assert all(obs.site_type is not CareerSiteType.JOB_BOARD for obs in site.observations)


def test_jobs_add_does_not_replace_a_white_label_with_the_board(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import socket

    fixture = project_root / "tests/fixtures/companies/registry_with_white_label.yaml"
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    before = fixture.read_text(encoding="utf-8")
    (tmp_path / "data" / "companies.yaml").write_text(before, encoding="utf-8")
    posting = tmp_path / "aviso.txt"
    posting.write_text(
        "Title: Cargo ficticio\nCompany: Acme\nLocation: Santiago\n\nDescripcion del aviso.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "jobbot.jobs.closure.fetch_posting_text",
        lambda _url: (_ for _ in ()).throw(OSError("offline")),
    )

    def _refuse_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network")

    monkeypatch.setattr(socket, "create_connection", _refuse_network)
    from jobbot.cli import run_cli

    url = "https://trabajando.cl/trabajo/1234567-cargo-ficticio"
    code = run_cli(["jobs", "add", "--url", url, "--file", str(posting)], standalone_mode=False)
    assert code == SUCCESS
    captured = capsys.readouterr()
    assert "learned" not in captured.out.casefold()
    saved = (tmp_path / "data" / "companies.yaml").read_text(encoding="utf-8")
    assert "https://acme.trabajando.cl" in saved
    assert "trabajando.cl/trabajo/" not in saved
