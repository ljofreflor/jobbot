<<<<<<< HEAD
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
=======
"""CLI `companies recon` dry-run vs --apply (issue #45)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.portals.detect import AtsKind
from jobbot.portals.form_learn import default_form_knowledge_path, load_form_knowledge

FIXTURE = Path("tests/fixtures/forms/career_inside_greenhouse.html")


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    payload = {
        "version": 1,
        "companies": [
            {
                "id": "acme",
                "name": "Acme",
                "career_sites": [
                    {
                        "url": "https://careers.acme.example/join",
                        "domain": "careers.acme.example",
                        "site_type": "company_career_portal",
                        "ats": "unknown",
                        "status": "active",
                    }
                ],
            }
        ],
    }
    (tmp_path / "data" / "companies.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_recon_dry_run_with_fixture_does_not_write(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli
    from jobbot.companies.registry import default_companies_path, load_companies

    before = load_companies(default_companies_path(tmp_path)).find_company("acme")
    assert before is not None and before.career_sites[0].ats == AtsKind.UNKNOWN

    assert (
        run_cli(
            ["companies", "recon", "Acme", "--fixture", str(project_root / FIXTURE)],
            standalone_mode=False,
        )
        == SUCCESS
    )
    out = capsys.readouterr().out
    assert "greenhouse" in out.casefold()
    assert "Dry-run" in out
    after = load_companies(default_companies_path(tmp_path)).find_company("acme")
    assert after is not None and after.career_sites[0].ats == AtsKind.UNKNOWN
    assert not default_form_knowledge_path(tmp_path).is_file()


def test_recon_apply_stores_ats_and_form(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli
    from jobbot.companies.registry import default_companies_path, load_companies

    assert (
        run_cli(
            [
                "companies",
                "recon",
                "Acme",
                "--fixture",
                str(project_root / FIXTURE),
                "--apply",
            ],
            standalone_mode=False,
        )
        == SUCCESS
    )
    site = load_companies(default_companies_path(tmp_path)).find_company("acme")
    assert site is not None
    assert site.career_sites[0].ats == AtsKind.GREENHOUSE
    forms = load_form_knowledge(default_form_knowledge_path(tmp_path))
    assert forms and "Resume/CV" in [f.label for f in forms[0].fields]


def test_recon_apply_without_html_fails(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli

    assert run_cli(["companies", "recon", "Acme", "--apply"], standalone_mode=False) == (
        VALIDATION_FAILURE
    )
>>>>>>> origin/develop
