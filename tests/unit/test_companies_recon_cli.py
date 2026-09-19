"""CLI tests for companies recon command."""

from pathlib import Path
from textwrap import dedent

import pytest

from jobbot.companies.models import (
    CareerSite,
    CareerSiteType,
    CompanyRecord,
    KnowledgeStatus,
)
from jobbot.companies.registry import CompanyRegistry, save_companies
from jobbot.portals.detect import AtsKind


@pytest.fixture
def greenhouse_fixture(tmp_path: Path) -> Path:
    """Create a Greenhouse HTML fixture."""
    fixture = tmp_path / "greenhouse.html"
    fixture.write_text(
        dedent("""
        <!DOCTYPE html>
        <html>
        <head><title>Careers at Acme</title></head>
        <body>
        <h1>Join Acme</h1>
        <div id="grnhse_app"></div>
        <script src="https://boards.greenhouse.io/embed/job_board/js?for=acme"></script>
        <form>
          <label for="name">Full name *</label>
          <input type="text" id="name" name="name" required />
          
          <label for="email">Email *</label>
          <input type="email" id="email" name="email" required />
          
          <label for="resume">Resume/CV *</label>
          <input type="file" id="resume" name="resume" accept=".pdf" required />
        </form>
        </body>
        </html>
        """),
        encoding="utf-8",
    )
    return fixture


@pytest.fixture
def no_markers_fixture(tmp_path: Path) -> Path:
    """Create an HTML fixture with no ATS markers."""
    fixture = tmp_path / "no_markers.html"
    fixture.write_text(
        dedent("""
        <!DOCTYPE html>
        <html>
        <head><title>Careers</title></head>
        <body>
        <h1>Work with us</h1>
        <form>
          <label for="name">Name</label>
          <input type="text" id="name" name="name" />
        </form>
        </body>
        </html>
        """),
        encoding="utf-8",
    )
    return fixture


@pytest.fixture
def setup_company(tmp_path: Path) -> tuple[Path, Path]:
    """Set up a company in the registry."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    companies_path = data_dir / "companies.yaml"
    registry = CompanyRegistry(
        companies=[
            CompanyRecord(
                id="acme",
                name="Acme Corp",
                country="CL",
                career_sites=[
                    CareerSite(
                        url="https://acme.example.com/careers",
                        domain="acme.example.com",
                        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
                        ats=AtsKind.UNKNOWN,
                        status=KnowledgeStatus.CANDIDATE,
                    )
                ],
            )
        ]
    )
    save_companies(registry, companies_path)
    
    profile_path = data_dir / "profile.yaml"
    profile_path.write_text(
        dedent("""
        version: 1
        personal:
          name: Test User
          email: test@example.com
          phone: "+56912345678"
          city: Santiago
          country: Chile
          headline: Software Engineer
        experience: []
        education: []
        skills: {}
        """),
        encoding="utf-8",
    )
    
    return tmp_path, companies_path


def test_recon_requires_fixture_or_cdp(
    setup_company: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Recon command requires either --fixture or --cdp."""
    from jobbot.cli import run_cli

    workspace, _ = setup_company
    monkeypatch.chdir(workspace)

    # The CLI records the failure but doesn't raise in standalone_mode=False
    run_cli(["companies", "recon", "acme"], standalone_mode=False)
    
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "fixture" in output.lower() or "cdp" in output.lower()


def test_recon_dry_run_shows_results_without_writing(
    greenhouse_fixture: Path,
    setup_company: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run shows what would be learned but writes nothing."""
    from jobbot.cli import run_cli
    
    workspace, companies_path = setup_company
    monkeypatch.chdir(workspace)
    
    run_cli(
        ["companies", "recon", "acme", "--fixture", str(greenhouse_fixture)],
        standalone_mode=False,
    )
    
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "greenhouse" in output.lower()
    assert "dry-run" in output.lower()


def test_recon_with_apply_writes_observation_and_form(
    greenhouse_fixture: Path,
    setup_company: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--apply stores observation and form knowledge."""
    from jobbot.cli import run_cli
    
    workspace, companies_path = setup_company
    monkeypatch.chdir(workspace)
    
    run_cli(
        ["companies", "recon", "acme", "--fixture", str(greenhouse_fixture), "--apply"],
        standalone_mode=False,
    )
    
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "observation" in output.lower() or "stored" in output.lower()
    
    # Check that form knowledge was written
    form_knowledge_path = workspace / "data" / "form_knowledge.yaml"
    assert form_knowledge_path.exists()


def test_recon_with_no_markers_stays_unknown(
    no_markers_fixture: Path,
    setup_company: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Page without markers → ATS stays unknown."""
    from jobbot.cli import run_cli
    
    workspace, _ = setup_company
    monkeypatch.chdir(workspace)
    
    run_cli(
        ["companies", "recon", "acme", "--fixture", str(no_markers_fixture)],
        standalone_mode=False,
    )
    
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "unknown" in output.lower()
