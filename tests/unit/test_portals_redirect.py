"""Redirect resolution tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from jobbot.portals.redirect import (
    expand_urls,
    follow_redirect_url,
    read_interstitial_destination,
)


def test_follow_redirect_url_returns_original_on_failure() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError("network")):
        assert follow_redirect_url("https://lnkd.in/abc") == "https://lnkd.in/abc"


def test_follow_redirect_url_follows_location() -> None:
    resp = MagicMock()
    resp.geturl.return_value = "https://boards.greenhouse.io/acme/jobs/1"
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        assert (
            follow_redirect_url("https://lnkd.in/xyz")
            == "https://boards.greenhouse.io/acme/jobs/1"
        )


def test_read_interstitial_destination(project_root: Path) -> None:
    html = (project_root / "tests/fixtures/lnkd_in_interstitial.html").read_text(encoding="utf-8")
    assert read_interstitial_destination(html) == (
        "https://career.example.com/en-us/vacancies/lead-data-scientist-89203"
    )


def test_read_interstitial_destination_ignores_other_linkedin_links(project_root: Path) -> None:
    html = (project_root / "tests/fixtures/lnkd_in_interstitial.html").read_text(encoding="utf-8")
    assert "answer/a1341680" not in (read_interstitial_destination(html) or "")
    assert read_interstitial_destination("<html><a href='https://x.test'>x</a></html>") is None


def test_follow_redirect_url_reads_interstitial_when_lnkd_in_answers_200(
    project_root: Path,
) -> None:
    """A lnkd.in link to an external site answers 200, not 30x; the target is in the body."""
    html = (project_root / "tests/fixtures/lnkd_in_interstitial.html").read_text(encoding="utf-8")

    def urlopen(req: object, **_kw: object) -> MagicMock:
        resp = MagicMock()
        resp.__enter__ = MagicMock(return_value=resp)
        resp.__exit__ = MagicMock(return_value=False)
        resp.geturl.return_value = req.full_url  # type: ignore[attr-defined]
        resp.read.return_value = html.encode("utf-8")
        return resp

    with patch("urllib.request.urlopen", side_effect=urlopen):
        assert follow_redirect_url("https://lnkd.in/e3KmPHyp") == (
            "https://career.example.com/en-us/vacancies/lead-data-scientist-89203"
        )


def test_follow_redirect_url_does_not_fetch_bodies_off_lnkd_in() -> None:
    """Only LinkedIn serves that interstitial; other hosts must not be re-fetched."""
    resp = MagicMock()
    resp.geturl.return_value = "https://career.example.com/vacancies/1"
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp) as urlopen:
        assert follow_redirect_url("https://career.example.com/vacancies/1") == (
            "https://career.example.com/vacancies/1"
        )
    assert urlopen.call_count == 1
    resp.read.assert_not_called()


def test_expand_urls_keeps_order_and_dedupes() -> None:
    with patch(
        "jobbot.portals.redirect.follow_redirect_url",
        side_effect=lambda u: u.replace("lnkd.in/abc", "boards.greenhouse.io/acme/jobs/9"),
    ):
        out = expand_urls(
            [
                "https://lnkd.in/abc",
                "https://www.linkedin.com/feed/update/1",
            ]
        )
    assert "https://boards.greenhouse.io/acme/jobs/9" in out
    assert out[0] == "https://lnkd.in/abc"
