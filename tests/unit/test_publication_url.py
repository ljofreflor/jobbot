"""Publication.url in CV render and LinkedIn package (#253)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.adapters.linkedin.package import build_linkedin_publication_items
from jobbot.cv.renderer import CvStyle, render_cv_ats, render_cv_tex
from jobbot.models.candidate import Candidate, PersonalInfo
from jobbot.models.skill import Publication
from jobbot.profile.loader import ProfileLoadError, load_profile


def _candidate_with_pubs(pubs: list[Publication]) -> Candidate:
    return Candidate(
        personal=PersonalInfo(name="Alex Rivera", headline="Analyst"),
        publications=pubs,
    )


def test_publication_url_without_doi_in_linkedin_items() -> None:
    cand = _candidate_with_pubs(
        [
            Publication(
                id="repo-note",
                title="Open repository note",
                journal="Institutional repository",
                year=2020,
                url="https://example.org/repos/open-note",
                authors=["Alex Rivera"],
            )
        ]
    )
    items = build_linkedin_publication_items(cand)
    assert items[0].url == "https://example.org/repos/open-note"


def test_doi_takes_priority_over_url_in_linkedin_items() -> None:
    cand = _candidate_with_pubs(
        [
            Publication(
                id="both",
                title="Dual link paper",
                doi="10.1000/xyz",
                url="https://example.org/other",
                authors=["Alex Rivera"],
            )
        ]
    )
    items = build_linkedin_publication_items(cand)
    assert items[0].url == "https://doi.org/10.1000/xyz"


def test_invalid_publication_url_fails_validation(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(
        """
name: Alex Rivera
email: alex@example.com
experience: []
publications:
  - id: bad
    title: Bad link
    url: not-a-url
"""
    )
    with pytest.raises(ProfileLoadError, match="url"):
        load_profile(path)


def test_cv_renders_publication_url(project_root: Path) -> None:
    repo_url = "https://example.org/repos/open-note"
    cand = _candidate_with_pubs(
        [
            Publication(
                id="repo-note",
                title="Open repository note",
                year=2020,
                url=repo_url,
                authors=["Alex Rivera"],
            )
        ]
    )
    templates = project_root / "templates"
    for style in (CvStyle.PLAIN, CvStyle.MODERNCV):
        tex = render_cv_tex(cand, templates, style=style)
        assert repo_url in tex
    ats = render_cv_ats(cand, templates)
    assert repo_url in ats
