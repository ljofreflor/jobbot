"""Catalog seed → companies candidates (#265/#269), never a parallel registry."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.companies.catalog_seed import (
    candidates_from_seed,
    import_catalog_seed,
    load_catalog_seed,
)
from jobbot.companies.models import KnowledgeStatus
from jobbot.companies.registry import CompanyRegistry, load_companies, save_companies
from jobbot.companies.urls import semantic_key


def _mini_seed(tmp_path: Path, *, channels: list[dict], expected: dict | None = None) -> Path:
    doc = {
        "catalog_version": "0.1.0",
        "country": "CL",
        "researched_at": "2026-10-12",
        "expected": expected
        or {
            "employers": len({c["employer"] for c in channels}),
            "channels": len(channels),
            "sectors": len({c["sector"] for c in channels if c.get("sector")}),
            "by_type": {},
            "by_read": {},
        },
        "channels": channels,
    }
    path = tmp_path / "seed.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return path


def test_seed_keeps_tenant_query_and_stays_candidate(tmp_path: Path) -> None:
    path = _mini_seed(
        tmp_path,
        channels=[
            {
                "employer": "Cencosud",
                "sector": "retail",
                "url": "https://cencosud.csod.com/ux/ats/careersite/5/home?c=cencosud&utm_source=x",
                "type": "listing",
                "ats": "cornerstone",
                "read": "fetched",
            }
        ],
        expected={"employers": 1, "channels": 1, "sectors": 1},
    )
    doc = load_catalog_seed(path)
    candidates, report = candidates_from_seed(doc)
    assert report.ok
    assert len(candidates) == 1
    assert "c=cencosud" in candidates[0].career_url
    assert "utm_" not in candidates[0].career_url
    assert candidates[0].status is KnowledgeStatus.CANDIDATE

    registry = CompanyRegistry()
    applied = import_catalog_seed(registry, doc, apply=True)
    assert applied.ok
    save_companies(registry, tmp_path / "companies.yaml")
    loaded = load_companies(tmp_path / "companies.yaml")
    site = loaded.find_company("Cencosud").career_sites[0]
    assert site.status is KnowledgeStatus.CANDIDATE
    assert "c=cencosud" in site.url
    assert site.key == semantic_key(site.url)


def test_count_mismatch_refuses_apply(tmp_path: Path) -> None:
    path = _mini_seed(
        tmp_path,
        channels=[
            {
                "employer": "Acme",
                "sector": "tech",
                "url": "https://jobs.acme-demo.cl/acme",
                "type": "listing",
                "ats": "unknown",
                "read": "fetched",
            }
        ],
        expected={"employers": 99, "channels": 1, "sectors": 1},
    )
    doc = load_catalog_seed(path)
    registry = CompanyRegistry()
    report = import_catalog_seed(registry, doc, apply=True)
    assert not report.ok
    assert registry.companies == []


def test_enabled_row_is_an_error(tmp_path: Path) -> None:
    path = _mini_seed(
        tmp_path,
        channels=[
            {
                "employer": "Acme",
                "sector": "tech",
                "url": "https://careers.acme-demo.cl/acme",
                "type": "listing",
                "ats": "unknown",
                "read": "fetched",
                "enabled": True,
            }
        ],
        expected={"employers": 1, "channels": 1, "sectors": 1},
    )
    _candidates, report = candidates_from_seed(load_catalog_seed(path))
    assert not report.ok
    assert any("enabled" in i.reason for i in report.errors)


def test_imported_catalog_rows_are_not_auto_promote_eligible(tmp_path: Path) -> None:
    from jobbot.companies.auto_promote import auto_promote_eligible, auto_promote_plan

    path = _mini_seed(
        tmp_path,
        channels=[
            {
                "employer": "Cencosud",
                "sector": "retail",
                "url": "https://cencosud.csod.com/ux/ats/careersite/5/home?c=cencosud",
                "type": "listing",
                "ats": "unknown",
                "read": "fetched",
            }
        ],
        expected={"employers": 1, "channels": 1, "sectors": 1},
    )
    doc = load_catalog_seed(path)
    registry = CompanyRegistry()
    assert import_catalog_seed(registry, doc, apply=True).ok
    site = registry.find_company("Cencosud").career_sites[0]
    assert auto_promote_eligible(site) is False
    assert auto_promote_plan(registry) == ()


def test_full_chile_seed_counts_match() -> None:
    root = Path("data/sources-cl.example.yaml")
    if not root.is_file():
        pytest.skip("seed not in checkout")
    doc = load_catalog_seed(root)
    _candidates, report = candidates_from_seed(doc)
    assert report.ok, [f"{i.subject}: {i.reason}" for i in report.errors]
    assert report.channels == 249
    assert report.employers == 194
