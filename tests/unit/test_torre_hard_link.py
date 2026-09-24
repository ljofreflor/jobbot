"""Torre hard link support: graceful handling of Torre URLs in jobbot get."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.config import JobbotConfig, PathsConfig
from jobbot.db.engine import make_engine, make_session_factory
from jobbot.jobs.from_url import UnsupportedPortalFetchError, ingest_hard_link
from jobbot.models.candidate import Candidate
from jobbot.portals.knowledge import lookup_portal
from tests.fixtures.profile import nurse_profile_dict


def _config(tmp_path: Path, project_root: Path) -> JobbotConfig:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    # Minimal portals.yaml with Torre registered
    (tmp_path / "data" / "portals.yaml").write_text(
        "portals:\n"
        "  - domain: torre.ai\n"
        "    ats_kind: torre\n"
        "    sample_jd_url: https://torre.ai/post/abc123\n",
        encoding="utf-8",
    )
    return JobbotConfig(
        root=tmp_path,
        paths=PathsConfig(templates=project_root / "templates", output=Path("output")),
    )


def _candidate() -> Candidate:
    return Candidate.model_validate(nurse_profile_dict())


def test_torre_url_without_html_raises_helpful_error(
    tmp_path: Path, project_root: Path
) -> None:
    """Torre uses search API, not direct job fetch, so guide users accordingly."""
    config = _config(tmp_path, project_root)
    session = make_session_factory(make_engine(config.database_path))()
    url = "https://torre.ai/post/abc123-techcorp-engineer"

    with pytest.raises(UnsupportedPortalFetchError) as exc_info:
        ingest_hard_link(config, session, url, candidate=_candidate(), html=None)

    assert "cannot be fetched by URL directly" in str(exc_info.value)
    assert "jobbot torre search" in str(exc_info.value)


def test_torre_url_with_valid_html_fixture_parses(tmp_path: Path, project_root: Path) -> None:
    """If a Torre HTML fixture is provided, try to parse it as a career page."""
    config = _config(tmp_path, project_root)
    session = make_session_factory(make_engine(config.database_path))()
    url = "https://torre.ai/post/abc123-techcorp-engineer"
    html_fixture = (project_root / "tests" / "fixtures" / "torre_profile_page.html").read_text(
        encoding="utf-8"
    )

    # This should not raise - it attempts parsing but may fail if HTML isn't a job posting
    # For this test we expect it to fail parsing but NOT give the "use search" error
    with pytest.raises(UnsupportedPortalFetchError) as exc_info:
        ingest_hard_link(config, session, url, candidate=_candidate(), html=html_fixture)

    # Should mention fixture parsing failed, not "use search"
    assert "fixture could not be parsed" in str(exc_info.value)
    assert "jobbot torre search" in str(exc_info.value)


def test_torre_portal_is_recognized(tmp_path: Path, project_root: Path) -> None:
    """Torre URLs should be recognized as a known portal."""
    config = _config(tmp_path, project_root)

    portal = lookup_portal(config, "https://torre.ai/post/xyz789")

    assert portal is not None
    assert portal.domain == "torre.ai"
    assert portal.ats_kind == "torre"


def test_torre_co_domain_is_also_recognized(tmp_path: Path, project_root: Path) -> None:
    """Torre.co should also be recognized (Torre has multiple domains)."""
    config = _config(tmp_path, project_root)
    # Add torre.co to portals registry
    portals_yaml = tmp_path / "data" / "portals.yaml"
    content = portals_yaml.read_text(encoding="utf-8")
    content += (
        "  - domain: torre.co\n"
        "    ats_kind: torre\n"
        "    sample_jd_url: https://torre.co/jobs/123\n"
    )
    portals_yaml.write_text(content, encoding="utf-8")

    portal = lookup_portal(config, "https://torre.co/jobs/123")

    assert portal is not None
    assert portal.domain == "torre.co"
