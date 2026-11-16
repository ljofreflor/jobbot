"""Technical evidence can promote a candidate site. HTTP 200 cannot."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.companies.auto_promote import auto_promote_eligible, auto_promote_plan
from jobbot.companies.models import (
    CareerSite,
    CareerSiteType,
    CompanyRecord,
    DiscoverySource,
    KnowledgeStatus,
    Observation,
)
from jobbot.companies.registry import CompanyRegistry, save_companies
from jobbot.exit_codes import SUCCESS
from jobbot.portals.detect import AtsKind


def _site(
    *,
    url: str,
    ats: AtsKind,
    status: KnowledgeStatus = KnowledgeStatus.CANDIDATE,
    site_type: CareerSiteType = CareerSiteType.ATS_INSTANCE,
    evidence: str = "host rule",
    conflicts: list[str] | None = None,
) -> CareerSite:
    return CareerSite(
        url=url,
        domain=url.split("/")[2],
        site_type=site_type,
        ats=ats,
        status=status,
        observations=[Observation(source=DiscoverySource.WEB_DISCOVERY, evidence=evidence)],
        conflicts=conflicts or [],
    )


def test_known_ats_qualifies_and_http_200_rejected_and_boards_do_not() -> None:
    greenhouse = _site(url="https://boards.greenhouse.io/servicio", ats=AtsKind.GREENHOUSE)
    http_only = _site(
        url="https://carreras.servicio-neutro.test/jobs",
        ats=AtsKind.UNKNOWN,
        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
        evidence="HTTP 200",
    )
    rejected = _site(
        url="https://jobs.lever.co/servicio",
        ats=AtsKind.LEVER,
        status=KnowledgeStatus.REJECTED,
    )
    stale = _site(
        url="https://servicio.wd1.myworkdayjobs.com/careers",
        ats=AtsKind.WORKDAY,
        status=KnowledgeStatus.STALE,
    )
    board = _site(
        url="https://www.indeed.com/jobs",
        ats=AtsKind.INDEED,
        site_type=CareerSiteType.JOB_BOARD,
    )
    conflicted = _site(
        url="https://jobs.ashbyhq.com/servicio",
        ats=AtsKind.ASHBY,
        conflicts=["ats changed"],
    )

    assert auto_promote_eligible(greenhouse) is True
    assert auto_promote_eligible(http_only) is False
    assert auto_promote_eligible(rejected) is False
    assert auto_promote_eligible(stale) is False
    assert auto_promote_eligible(board) is False
    assert auto_promote_eligible(conflicted) is False


def test_dry_run_lists_the_site_and_apply_marks_it_active(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli
    from jobbot.companies.registry import default_companies_path, load_companies

    registry = CompanyRegistry(
        companies=[
            CompanyRecord(
                id="servicio",
                name="Servicio Neutro",
                career_sites=[
                    _site(url="https://boards.greenhouse.io/servicio", ats=AtsKind.GREENHOUSE),
                    _site(
                        url="https://carreras.servicio-neutro.test/jobs",
                        ats=AtsKind.UNKNOWN,
                        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
                        evidence="HTTP 200",
                    ),
                ],
            )
        ]
    )
    path = default_companies_path(tmp_path)
    save_companies(registry, path)

    dry = run_cli(["companies", "auto-promote"], standalone_mode=False)
    assert dry == SUCCESS
    output = capsys.readouterr().out
    assert "boards.greenhouse.io/servicio" in output
    assert "carreras.servicio-neutro.test" not in output
    assert "Dry-run" in output
    stored = load_companies(path)
    assert stored.companies[0].career_sites[0].status is KnowledgeStatus.CANDIDATE

    applied = run_cli(["companies", "auto-promote", "--apply"], standalone_mode=False)
    assert applied == SUCCESS
    stored = load_companies(path)
    by_url = {site.url: site.status for site in stored.companies[0].career_sites}
    assert by_url["https://boards.greenhouse.io/servicio"] is KnowledgeStatus.ACTIVE
    assert by_url["https://carreras.servicio-neutro.test/jobs"] is KnowledgeStatus.CANDIDATE
    assert auto_promote_plan(stored) == ()


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
