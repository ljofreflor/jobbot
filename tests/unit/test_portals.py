"""Portal detect + registry tests."""

from pathlib import Path

from jobbot.portals.detect import AtsKind, detect_ats, extract_http_urls, first_external_ats_url
from jobbot.portals.registry import PortalRegistry, domain_from_url, load_registry, save_registry


def test_detect_ats_kinds() -> None:
    assert detect_ats("https://boards.greenhouse.io/acme/jobs/1") == AtsKind.GREENHOUSE
    assert detect_ats("https://jobs.lever.co/x/y") == AtsKind.LEVER
    assert detect_ats("https://company.wd1.myworkdayjobs.com/en-US/careers") == AtsKind.WORKDAY
    assert detect_ats("https://jobs.ashbyhq.com/c/r") == AtsKind.ASHBY
    assert detect_ats("https://www.getonbrd.com/jobs/x") == AtsKind.GETONBOARD
    assert detect_ats("https://www.linkedin.com/posts/x") == AtsKind.LINKEDIN
    assert detect_ats("https://example.com/jobs/1") == AtsKind.UNKNOWN


def test_first_external_ats_prefers_greenhouse() -> None:
    urls = extract_http_urls(
        "see https://www.linkedin.com/feed/update/1 and "
        "https://boards.greenhouse.io/acme/jobs/9"
    )
    url, kind = first_external_ats_url(urls)
    assert kind == AtsKind.GREENHOUSE
    assert url is not None and "greenhouse" in url


def test_first_external_skips_lnkd_and_keeps_unknown_career() -> None:
    urls = [
        "https://lnkd.in/abc",
        "https://www.linkedin.com/jobs/view/1",
        "https://careers.acme.example/jobs/42",
    ]
    url, kind = first_external_ats_url(urls)
    assert url == "https://careers.acme.example/jobs/42"
    assert kind == AtsKind.UNKNOWN


def test_registry_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "portals.yaml"
    reg = PortalRegistry()
    reg.upsert(
        domain=domain_from_url("https://boards.greenhouse.io/acme/jobs/1"),
        ats_kind=AtsKind.GREENHOUSE,
        registered=True,
        example_url="https://boards.greenhouse.io/acme/jobs/1",
    )
    save_registry(reg, path)
    loaded = load_registry(path)
    assert len(loaded.portals) == 1
    assert loaded.portals[0].domain == "boards.greenhouse.io"
    assert loaded.portals[0].registered is True
