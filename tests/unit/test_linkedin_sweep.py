"""LinkedIn post sweep parsing tests."""

from pathlib import Path

from jobbot.adapters.linkedin.posts_source import LinkedInPostJobSource
from jobbot.adapters.linkedin.sweep import is_data_relevant, parse_posts_fixture, post_to_job
from jobbot.portals.detect import AtsKind


def test_parse_posts_fixture_filters_and_detects_ats(project_root: Path) -> None:
    text = (project_root / "tests/fixtures/linkedin_posts.txt").read_text(encoding="utf-8")
    posts = parse_posts_fixture(text)
    assert len(posts) == 7
    relevant = [p for p in posts if is_data_relevant(p.text)]
    assert len(relevant) == 6  # hiking post excluded
    greenhouse = next(p for p in relevant if p.ats_kind == AtsKind.GREENHOUSE)
    assert greenhouse.ats_url and "greenhouse" in greenhouse.ats_url
    gob = next(p for p in relevant if p.ats_kind == AtsKind.GETONBOARD)
    assert gob.ats_url and "getonbrd.com" in gob.ats_url
    email = next(p for p in relevant if p.ats_kind == AtsKind.EMAIL)
    assert email.ats_url == "mailto:seleccion@empresa.cl"
    job = post_to_job(greenhouse, job_id="J0001")
    assert job.source == "linkedin_post"
    assert job.ats_kind == "greenhouse"
    assert "Data Scientist" in job.title or "data scientist" in job.title.casefold()


def test_parse_post_expands_short_links(monkeypatch: object) -> None:
    from jobbot.adapters.linkedin.sweep import parse_post_blob

    def fake_expand(urls: list[str]) -> list[str]:
        return urls + ["https://boards.greenhouse.io/acme/jobs/99"]

    import jobbot.adapters.linkedin.sweep as sweep_mod

    monkeypatch.setattr(sweep_mod, "expand_urls", fake_expand)
    post = parse_post_blob(
        "Hiring DS! Apply: https://lnkd.in/short\n",
    )
    assert post.ats_kind.value == "greenhouse"
    assert post.ats_url and "greenhouse" in post.ats_url


def test_source_from_fixture(project_root: Path, tmp_path: Path) -> None:
    from jobbot.config import JobbotConfig, PathsConfig

    config = JobbotConfig(paths=PathsConfig(output=tmp_path / "out"), root=project_root)
    source = LinkedInPostJobSource(config)
    jobs = source.search_from_fixture(
        project_root / "tests/fixtures/linkedin_posts.txt",
        query="data scientist",
    )
    assert len(jobs) >= 2
    kinds = {j.ats_kind for j in jobs}
    assert "greenhouse" in kinds
    assert "lever" in kinds
