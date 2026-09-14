"""Redirect resolution tests."""

from unittest.mock import MagicMock, patch

from jobbot.portals.redirect import expand_urls, follow_redirect_url


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
