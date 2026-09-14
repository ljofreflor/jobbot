"""HTML fixture parsing for portal profiles."""

from pathlib import Path

from jobbot.adapters.html_parse import parse_indeed_profile_html, parse_linkedin_profile_html


def test_parse_indeed_fixture(project_root: Path) -> None:
    html = (project_root / "tests/fixtures/indeed_profile.html").read_text(encoding="utf-8")
    profile = parse_indeed_profile_html(html)
    assert profile.headline == "Data Scientist"
    assert profile.experience[0].company == "Mercado Libre"
    assert "Python" in profile.skills


def test_parse_linkedin_fixture(project_root: Path) -> None:
    html = (project_root / "tests/fixtures/linkedin_profile.html").read_text(encoding="utf-8")
    profile = parse_linkedin_profile_html(html)
    assert profile.source == "linkedin"
    assert profile.headline == "Data Scientist"
    assert profile.summary
